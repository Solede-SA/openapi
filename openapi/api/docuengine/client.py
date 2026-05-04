"""Client REST per docuengine.openapi.com — basso livello, riusabile da app diverse.

Pattern docuengine (async multi-step):
  1. POST  /{service}  payload  → {data:{id, state:'pending', ...}}
  2. GET   /requests/{id}        → polling fino a state in DONE_STATES
  3. GET   /attachments/{id}/file (o url diretto) → binary del documento

Token: parametro esplicito o, se omesso, letto da Company.custom_open_api_token.
URL base: hardcoded (https://docuengine.openapi.com) o override via param.
"""

import time

import frappe
import requests

DEFAULT_BASE_URL = "https://docuengine.openapi.com"
POLL_INTERVAL_SEC = 4
POLL_MAX_SEC = 90
DOWNLOAD_TIMEOUT_SEC = 60

DONE_STATES = {"done", "finished", "completed", "ok", "success"}
ERROR_STATES = {"error", "failed", "ko", "rejected"}


def _company_token():
	company_name = (frappe.defaults.get_user_default("Company") or
	                frappe.defaults.get_global_default("company"))
	if not company_name:
		return None
	return frappe.db.get_value("Company", company_name, "custom_open_api_token")


def _resolve_token(token: str | None) -> str:
	tok = token or _company_token()
	if not tok:
		frappe.throw(
			"Token OpenAPI non disponibile. Passa `token` esplicito o configura "
			"Company.custom_open_api_token."
		)
	return tok


def _headers(token: str) -> dict:
	return {
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _raise_api_error(method: str, path: str, response: requests.Response):
	try:
		body = response.json()
	except Exception:
		body = response.text[:500]
	frappe.throw(f"OpenAPI {method} {path} → {response.status_code}: {body}")


def post(service: str, payload: dict, token: str | None = None,
         base_url: str | None = None) -> dict:
	"""POST iniziale al servizio docuengine. Ritorna il body JSON parsato."""
	tok = _resolve_token(token)
	url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/{service.lstrip('/')}"
	r = requests.post(url, headers=_headers(tok), json=payload, timeout=30)
	if r.status_code >= 400:
		_raise_api_error("POST", service, r)
	return r.json()


def get(path: str, token: str | None = None, base_url: str | None = None) -> dict:
	tok = _resolve_token(token)
	url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/{path.lstrip('/')}"
	r = requests.get(url, headers=_headers(tok), timeout=30)
	if r.status_code >= 400:
		_raise_api_error("GET", path, r)
	return r.json()


def poll_until_done(request_id: str, token: str | None = None,
                    base_url: str | None = None) -> dict:
	"""Polling su /requests/{id} fino a stato terminale o timeout."""
	deadline = time.time() + POLL_MAX_SEC
	last_state = None
	while time.time() < deadline:
		resp = get(f"requests/{request_id}", token=token, base_url=base_url)
		data = resp.get("data") or resp
		state = (data.get("state") or "").lower()
		last_state = state
		if state in DONE_STATES:
			return data
		if state in ERROR_STATES:
			frappe.throw(f"OpenAPI request {request_id} fallito: state={state}, body={data}")
		time.sleep(POLL_INTERVAL_SEC)
	frappe.throw(f"OpenAPI request {request_id} timeout dopo {POLL_MAX_SEC}s (state={last_state})")


def download_attachment(att: dict, token: str | None = None,
                        base_url: str | None = None) -> tuple[bytes, str]:
	"""Scarica un attachment dato il dict {id|url, filename}. Ritorna (bytes, filename)."""
	tok = _resolve_token(token)
	att_id = att.get("id") or att.get("attachmentId")
	url = att.get("url") or att.get("file_url")
	filename = att.get("filename") or att.get("name") or "openapi_doc.pdf"
	if att_id:
		full = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/attachments/{att_id}/file"
	elif url:
		full = url
	else:
		frappe.throw(f"Attachment senza id né url: {att}")
		return b"", ""  # unreachable

	r = requests.get(full, headers={"Authorization": f"Bearer {tok}"}, timeout=DOWNLOAD_TIMEOUT_SEC)
	if r.status_code >= 400:
		_raise_api_error("GET (download)", full, r)
	cd = r.headers.get("Content-Disposition", "")
	if "filename=" in cd and not filename:
		filename = cd.split("filename=", 1)[1].strip().strip('"')
	return r.content, filename


def extract_attachments(data: dict) -> list[dict]:
	"""Trova la lista attachment nel response (chiave varia: attachments|documents|files)."""
	for key in ("attachments", "documents", "files"):
		if isinstance(data.get(key), list):
			return data[key]
	return []


def run_service(service: str, payload: dict, token: str | None = None,
                base_url: str | None = None) -> dict:
	"""Wrapper end-to-end: POST + polling se necessario. Ritorna dict `data` finale.

	Le chiamate sync (state già DONE alla POST) skippano il polling.
	"""
	resp = post(service, payload, token=token, base_url=base_url)
	data = resp.get("data") or resp
	state = (data.get("state") or "").lower()
	if state in DONE_STATES:
		return data
	request_id = data.get("id")
	if not request_id:
		frappe.throw(f"OpenAPI {service}: risposta priva di state e id: {resp}")
	return poll_until_done(request_id, token=token, base_url=base_url)
