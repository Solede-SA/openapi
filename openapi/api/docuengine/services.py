"""Orchestratore Docuengine: dato un nome documento + payload search,
fa submit + polling + download. Ritorna i bytes dei file scaricati.

API generica (vedi client.py per le primitive REST).

Note sul `search` payload:
docuengine accetta i campi via chiavi posizionali `field0`, `field1`, ... — il
`requestStructure` di ogni documento mappa ogni `fieldN` a un nome logico
(`taxCode`, `year`, `actGroupCode`, ...). Questo modulo accetta dal chiamante
chiavi logiche (es. `{"taxCode": "..."}`) e le traduce internamente in
`fieldN` leggendo il `request_structure_json` salvato in
`Docuengine Document Price`.
"""

import json

import frappe

from openapi.api.docuengine import client, pricing


def _resolve_document(name_query: str) -> tuple[str, str]:
	"""Ritorna (document_id, matched_document_name). Solleva se nessun match."""
	doc_id = pricing.find_document_id_by_name(name_query)
	if not doc_id:
		frappe.throw(
			f"Nessun documento Docuengine attivo per query '{name_query}'. "
			"Sincronizzare il listino da Docuengine Settings."
		)
	matched_name = frappe.db.get_value("Docuengine Document Price", doc_id, "document_name") or doc_id
	return doc_id, matched_name


def _normalize_search_payload(document_id: str, payload: dict) -> dict:
	"""Traduce le chiavi logiche del payload in `fieldN` posizionali.

	Esempio: `{"taxCode": "1234", "year": 2024}` con request_structure che mappa
	field0→taxCode, field1→year diventa `{"field0": "1234", "field1": 2024}`.

	Se il chiamante passa già `field0`/`field1` letterali, vengono lasciati invariati.
	"""
	rs_raw = frappe.db.get_value("Docuengine Document Price", document_id, "request_structure_json")
	if not rs_raw:
		return payload
	try:
		rs = json.loads(rs_raw)
	except (json.JSONDecodeError, TypeError):
		return payload

	fields = rs.get("fields") or {}
	# Mappa nome_logico → field_key
	name_to_field: dict[str, str] = {}
	for field_key, meta in fields.items():
		if not isinstance(meta, dict):
			continue
		logical_name = meta.get("name")
		if logical_name and field_key.startswith("field"):
			name_to_field[logical_name] = field_key

	out: dict = {}
	for k, v in payload.items():
		if k.startswith("field") and k[5:].isdigit():
			out[k] = v  # già posizionale
		elif k in name_to_field:
			out[name_to_field[k]] = v
		else:
			# Chiave non riconosciuta — la lascio passare (l'API rifiuterà se invalida)
			out[k] = v
	return out


def _download_files(request_id: str, token: str | None = None) -> list[dict]:
	"""Scarica tutti i file della request. Ritorna lista normalizzata."""
	files_meta = client.list_request_files(request_id, token=token)
	out = []
	for f in files_meta:
		url = f.get("downloadUrl") or f.get("download_url") or f.get("url")
		if not url:
			continue
		content = client.download_signed(url)
		filename = f.get("fileName") or f.get("filename") or "openapi_doc.pdf"
		out.append({
			"bytes": content,
			"filename": filename,
			"mimeType": f.get("mimeType") or f.get("mime_type") or "application/pdf",
			"fileSize": f.get("fileSize") or len(content),
			"meta": {k: v for k, v in f.items() if k not in ("downloadUrl", "download_url", "url")},
		})
	return out


def request_document(name_query: str, search_payload: dict, token: str | None = None) -> dict:
	"""Orchestratore end-to-end per servizi single-result.

	Step: risolvi documentId → submit_request → poll → download files.
	Ritorna {document_id, document_name, request_id, raw, files: [{bytes, filename, ...}]}.
	"""
	doc_id, matched_name = _resolve_document(name_query)
	search_normalized = _normalize_search_payload(doc_id, search_payload)
	submit = client.submit_request(doc_id, search_normalized, token=token)
	request_id = submit.get("id")
	if not request_id:
		frappe.throw(f"Docuengine: submit non ha ritornato request_id. Body: {submit}")
	final = client.poll_request(request_id, token=token)
	files = _download_files(request_id, token=token)
	return {
		"document_id": doc_id,
		"document_name": matched_name,
		"request_id": request_id,
		"raw": final,
		"files": files,
	}


def request_document_with_result_choice(
	name_query: str,
	search_payload: dict,
	picker_fn,
	token: str | None = None,
) -> dict:
	"""Variante per servizi multi-result (es. bilanci con scelta anno, catastali multi-immobile).

	`picker_fn(results: list[dict]) -> str` deve ritornare il `resultId` scelto.
	"""
	doc_id, matched_name = _resolve_document(name_query)
	search_normalized = _normalize_search_payload(doc_id, search_payload)
	submit = client.submit_request(doc_id, search_normalized, token=token)
	request_id = submit.get("id")
	if not request_id:
		frappe.throw(f"Docuengine: submit non ha ritornato request_id. Body: {submit}")

	# Primo poll: aspetta che la richiesta abbia generato la lista results
	first = client.poll_request(request_id, token=token)
	results = first.get("results") or []
	if not results:
		# Forse è single-result, scarica direttamente
		files = _download_files(request_id, token=token)
		return {
			"document_id": doc_id,
			"document_name": matched_name,
			"request_id": request_id,
			"raw": first,
			"files": files,
		}

	chosen_result_id = picker_fn(results)
	if not chosen_result_id:
		frappe.throw("Docuengine: picker_fn non ha scelto alcun resultId")
	client.patch_request(request_id, chosen_result_id, token=token)
	final = client.poll_request(request_id, token=token)
	files = _download_files(request_id, token=token)
	return {
		"document_id": doc_id,
		"document_name": matched_name,
		"request_id": request_id,
		"raw": final,
		"files": files,
	}
