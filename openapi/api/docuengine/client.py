"""Client REST docuengine.openapi.com — primitive di basso livello.

API generica:
  GET   /documents                → lista tipi documento con prezzo
  POST  /requests                 → submit con {documentId, search}
  GET   /requests/{id}            → polling stato (DONE/FAILED/ERROR)
  PATCH /requests/{id}            → multi-results: scegli {resultId}
  GET   /requests/{id}/files      → lista file con downloadUrl signed GCS

Auth:
  Header `Authorization` con valore letterale dal token configurato.
  Se manca il prefisso "Bearer ", lo aggiungo (cURL ufficiale richiede Bearer).

Configurazione:
  Base URL → DocType `OpenApi Services` record "Docuengine".
  Token   → param esplicito o Company.custom_open_api_token (un'unica fonte, no fallback).
"""

import time

import frappe
import requests

POLL_INTERVAL_SEC = 4
POLL_MAX_SEC = 120
DOWNLOAD_TIMEOUT_SEC = 60

DONE_STATES = {"done", "finished", "completed", "ok", "success"}
ERROR_STATES = {"error", "failed", "ko", "rejected"}

SERVICE_NAME = "Docuengine"


# --- Configurazione --------------------------------------------------------

def _base_url() -> str:
	url = frappe.db.get_value("OpenApi Services", SERVICE_NAME, "url")
	if not url:
		frappe.throw(
			f"OpenApi Services '{SERVICE_NAME}' non configurato. "
			f"Eseguire 'bench migrate' (la patch setup_docuengine_service crea il record)."
		)
	return url.rstrip("/")


def _resolve_token(token: str | None = None) -> str:
	if token:
		return token
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if company:
		tok = frappe.db.get_value("Company", company, "custom_open_api_token")
		if tok:
			return tok
	frappe.throw(
		f"Token OpenAPI non configurato su Company '{company}'. "
		f"Imposta Company.custom_open_api_token, oppure passa token esplicito."
	)
	return ""  # unreachable


def _headers(token: str | None = None) -> dict:
	tok = _resolve_token(token).strip()
	if not tok.lower().startswith("bearer "):
		tok = f"Bearer {tok}"
	return {
		"Authorization": tok,
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _raise_error(method: str, path: str, response: requests.Response):
	try:
		body = response.json()
	except Exception:
		body = response.text[:500]
	frappe.throw(f"OpenAPI Docuengine {method} {path} → {response.status_code}: {body}")


# --- Primitive REST --------------------------------------------------------

def list_documents(token: str | None = None) -> list[dict]:
	"""GET /documents — lista tipi documento con prezzi e requestStructure."""
	url = f"{_base_url()}/documents"
	r = requests.get(url, headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", "/documents", r)
	body = r.json()
	# La forma può essere lista diretta o {data: [...]} o {documents: [...]}
	if isinstance(body, list):
		return body
	if isinstance(body, dict):
		for key in ("data", "documents", "items"):
			if isinstance(body.get(key), list):
				return body[key]
	return []


def submit_request(document_id: str, search: dict, token: str | None = None) -> dict:
	"""POST /requests con body {documentId, search}. Ritorna il dict `data` (con id, state)."""
	url = f"{_base_url()}/requests"
	payload = {"documentId": document_id, "search": search}
	r = requests.post(url, headers=_headers(token), json=payload, timeout=30)
	if r.status_code >= 400:
		_raise_error("POST", "/requests", r)
	body = r.json()
	return body.get("data") or body


def get_request(request_id: str, token: str | None = None) -> dict:
	"""GET /requests/{id} — stato singolo."""
	path = f"/requests/{request_id}"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	body = r.json()
	return body.get("data") or body


def poll_request(request_id: str, token: str | None = None, max_sec: int = POLL_MAX_SEC) -> dict:
	"""Polling /requests/{id} fino a state terminale o timeout."""
	deadline = time.time() + max_sec
	last_state = None
	while time.time() < deadline:
		data = get_request(request_id, token=token)
		state = (data.get("state") or "").lower()
		last_state = state
		if state in DONE_STATES:
			return data
		if state in ERROR_STATES:
			frappe.throw(f"Docuengine request {request_id} fallito: state={state}, body={data}")
		time.sleep(POLL_INTERVAL_SEC)
	frappe.throw(f"Docuengine request {request_id} timeout dopo {max_sec}s (state={last_state})")
	return {}  # unreachable


def patch_request(request_id: str, result_id: str, token: str | None = None) -> dict:
	"""PATCH /requests/{id} body {resultId} per scegliere uno tra multi-results."""
	path = f"/requests/{request_id}"
	r = requests.patch(
		f"{_base_url()}{path}",
		headers=_headers(token),
		json={"resultId": result_id},
		timeout=30,
	)
	if r.status_code >= 400:
		_raise_error("PATCH", path, r)
	body = r.json()
	return body.get("data") or body


def list_request_files(request_id: str, token: str | None = None) -> list[dict]:
	"""GET /requests/{id}/documents — lista file scaricabili con downloadUrl GCS signed.

	Schema response: `{data: [{fileName, mimeType, fileSize, downloadUrl, urlExpire, md5}]}`.
	"""
	path = f"/requests/{request_id}/documents"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	body = r.json()
	if isinstance(body, list):
		return body
	if isinstance(body, dict):
		for key in ("data", "files", "documents"):
			if isinstance(body.get(key), list):
				return body[key]
	return []


def download_signed(url: str) -> bytes:
	"""Scarica binary da signed URL Google Cloud Storage. Niente Authorization header."""
	r = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SEC)
	if r.status_code >= 400:
		_raise_error("GET (download)", url, r)
	return r.content
