"""Gestione delle Docuengine Pending Request: pattern fire-and-forget.

Workflow:
  1. `submit_async(...)` → POST /requests + crea Pending Request (state=pending)
  2. Cron `process_pending_requests()` ogni 5 min → poll, se DONE scarica e chiama
     il callback registrato per quel sync_type, marca state=done.
     Se ERROR/expired → state=error/expired e refund (callback dedicato).

Il `callback_on_done(pending_doc, files)` e `callback_on_error(pending_doc, error)`
sono iniettati dal consumer (es. garemed) via registry, per disaccoppiare
docuengine dalla logica di salvataggio specifica del consumer.
"""

import json

import frappe
from frappe.utils import getdate, now, time_diff_in_hours

from openapi.api.docuengine import client


# Registry callback: sync_type → {on_done(pending_doc, files), on_error(pending_doc, error)}
_CALLBACKS: dict = {}

EXPIRY_HOURS = 24


def register_callbacks(sync_type: str, on_done, on_error):
	"""Registra le callback per un sync_type. Chiamato all'init dei consumer (hooks)."""
	_CALLBACKS[sync_type] = {"on_done": on_done, "on_error": on_error}


def submit_async(customer: str, sync_type: str, document_id: str,
                  document_name: str, search_payload: dict,
                  cost_eur: float, token: str | None = None) -> str:
	"""Submit fire-and-forget: chiama POST /requests, salva Pending Request, ritorna request_id.
	Il chiamante deve aver già fatto _normalize_search_payload e charge wallet.
	"""
	submit = client.submit_request(document_id, search_payload, token=token)
	request_id = submit.get("id")
	if not request_id:
		frappe.throw(f"Docuengine: submit non ha ritornato request_id. Body: {submit}")

	pending = frappe.get_doc({
		"doctype": "Docuengine Pending Request",
		"customer": customer,
		"sync_type": sync_type,
		"state": "pending",
		"submitted_at": now(),
		"request_id": request_id,
		"document_id": document_id,
		"document_name": document_name,
		"cost_eur": cost_eur,
		"search_payload": json.dumps(search_payload, indent=2, ensure_ascii=False),
	})
	pending.flags.ignore_permissions = True
	pending.insert()
	return request_id


def process_pending_requests() -> dict:
	"""Cron: poll tutte le Docuengine Pending Request in `pending` o `processing`.

	- DONE: scarica file, chiama callback on_done, state=done.
	- ERROR/FAILED: state=error, chiama callback on_error.
	- ancora pending dopo EXPIRY_HOURS: state=expired, callback on_error per refund.
	"""
	rows = frappe.get_all(
		"Docuengine Pending Request",
		filters={"state": ["in", ["pending", "processing"]]},
		fields=["name", "submitted_at"],
		limit_page_length=100,
	)
	stats = {"done": 0, "error": 0, "expired": 0, "still_pending": 0}
	for r in rows:
		try:
			result = _process_one(r["name"])
			stats[result] = stats.get(result, 0) + 1
		except Exception as e:
			frappe.log_error(f"process_pending {r['name']}: {e}", "docuengine_pending")
	frappe.db.commit()
	return stats


def _process_one(pending_name: str) -> str:
	pending = frappe.get_doc("Docuengine Pending Request", pending_name)

	# Expired check
	if time_diff_in_hours(now(), pending.submitted_at) > EXPIRY_HOURS:
		pending.state = "expired"
		pending.error_message = f"Timeout dopo {EXPIRY_HOURS}h senza completion."
		pending.completed_at = now()
		pending.flags.ignore_permissions = True
		pending.save()
		_invoke_callback(pending, "on_error", error=pending.error_message)
		return "expired"

	# Poll Docuengine
	try:
		data = client.get_request(pending.request_id)
	except Exception as e:
		# Errore di network: non cambio state, ritento al prossimo cron
		pending.last_poll_at = now()
		pending.flags.ignore_permissions = True
		pending.save()
		raise

	state = (data.get("state") or "").lower()
	pending.last_poll_at = now()

	if state in client.DONE_STATES:
		# Scarica file
		try:
			files_meta = client.list_request_files(pending.request_id)
			files = []
			for fm in files_meta:
				url = fm.get("downloadUrl") or fm.get("url")
				if not url:
					continue
				content = client.download_signed(url)
				files.append({
					"bytes": content,
					"filename": fm.get("fileName") or "openapi_doc.pdf",
					"mimeType": fm.get("mimeType") or "application/pdf",
					"fileSize": fm.get("fileSize") or len(content),
				})
		except Exception as e:
			pending.error_message = f"Download fallito: {e}"
			pending.flags.ignore_permissions = True
			pending.save()
			raise

		pending.state = "done"
		pending.completed_at = now()
		pending.flags.ignore_permissions = True
		pending.save()
		_invoke_callback(pending, "on_done", files=files, raw=data)
		return "done"

	if state in client.ERROR_STATES:
		pending.state = "error"
		pending.error_message = f"Docuengine state={state}: {data}"[:500]
		pending.completed_at = now()
		pending.flags.ignore_permissions = True
		pending.save()
		_invoke_callback(pending, "on_error", error=pending.error_message)
		return "error"

	# Ancora processing
	if state and pending.state != "processing":
		pending.state = "processing"
	pending.flags.ignore_permissions = True
	pending.save()
	return "still_pending"


def _invoke_callback(pending, kind: str, **kwargs):
	cb_set = _CALLBACKS.get(pending.sync_type)
	if not cb_set:
		return
	fn = cb_set.get(kind)
	if not fn:
		return
	try:
		fn(pending, **kwargs)
	except Exception as e:
		frappe.log_error(
			f"Callback {kind} per {pending.sync_type} request_id={pending.request_id}: {e}",
			"docuengine_pending",
		)
