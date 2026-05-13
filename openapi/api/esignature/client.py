"""Client REST esignature.openapi.com — primitive di basso livello.

API gestite:
  POST  /certificates/namirial-otp        → richiesta certificato Namirial OTP
  GET   /certificates/{id}                → dettaglio certificato (stato, scadenza, CN)
  GET   /certificates                     → lista certificati (filtri opzionali)
  POST  /EU-QES_otp                       → submit firma QES batch con OTP
  POST  /signatures/{id}/confirm          → conferma OTP
  GET   /signatures/{id}                  → stato sessione di firma
  GET   /signatures/{id}/audit            → audit trail completo
  GET   /signatures/{id}/signedDocument   → download file firmato (binary o zip)
  POST  /verify                           → validazione firma su file esterni

Auth:
  Header `Authorization` con Bearer token. Token risolto da Company.custom_open_api_token
  (riusa la stessa convenzione di docuengine/client.py — un'unica fonte, nessun fallback).

Base URL:
  Lookup record `OpenApi Services` "eSignature". Se `OpenApi Signature Settings.sandbox_mode = 1`
  il client riscrive l'host verso `test.esignature.openapi.com` automaticamente.
"""

import time

import frappe
import requests

POLL_INTERVAL_SEC = 4
SIGN_POLL_MAX_SEC = 90
DOWNLOAD_TIMEOUT_SEC = 60

SIGN_DONE_STATES = {"completed", "signed", "done", "success", "ok"}
SIGN_ERROR_STATES = {"failed", "rejected", "expired", "error", "ko"}

CERT_ACTIVE_STATES = {"active", "attivo", "valid", "issued"}
CERT_PENDING_STATES = {"pending", "in_progress", "waiting", "waiting_identification", "waiting_video"}
CERT_TERMINAL_BAD_STATES = {"rejected", "revoked", "expired", "failed", "error"}

SERVICE_NAME = "eSignature"
SANDBOX_HOST_REPLACE = ("esignature.openapi.com", "test.esignature.openapi.com")


# --- Configurazione --------------------------------------------------------

def _is_sandbox() -> bool:
	value = frappe.db.get_single_value("OpenApi Signature Settings", "sandbox_mode")
	return bool(value)


def _base_url() -> str:
	url = frappe.db.get_value("OpenApi Services", SERVICE_NAME, "url")
	if not url:
		frappe.throw(
			f"OpenApi Services '{SERVICE_NAME}' non configurato. "
			f"Eseguire 'bench migrate' (la patch setup_esignature_service crea il record)."
		)
	url = url.rstrip("/")
	if _is_sandbox():
		url = url.replace(SANDBOX_HOST_REPLACE[0], SANDBOX_HOST_REPLACE[1])
	return url


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


def _headers(token: str | None = None, json_content: bool = True) -> dict:
	tok = _resolve_token(token).strip()
	if not tok.lower().startswith("bearer "):
		tok = f"Bearer {tok}"
	h = {
		"Authorization": tok,
		"Accept": "application/json",
	}
	if json_content:
		h["Content-Type"] = "application/json"
	return h


def _raise_error(method: str, path: str, response: requests.Response):
	try:
		body = response.json()
	except Exception:
		body = response.text[:500]
	frappe.throw(f"OpenAPI eSignature {method} {path} → {response.status_code}: {body}")


def _unwrap(body):
	"""Le response OpenAPI a volte sono dict puri, a volte {data: ...}. Normalizza."""
	if isinstance(body, dict) and "data" in body and len(body) <= 3:
		return body["data"]
	return body


# --- Certificati -----------------------------------------------------------

def create_namirial_otp_certificate(payload: dict, token: str | None = None) -> dict:
	"""POST /certificates/namirial-otp.

	payload: anagrafica firmatario + contatti OTP (nome, cognome, codice_fiscale,
	         data_nascita ISO, comune_nascita, provincia_nascita, email, telefono).
	Ritorna: {id, status, identificationUrl, ...} (chiavi camelCase da OpenAPI).
	"""
	path = "/certificates/namirial-otp"
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=30)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())


def get_certificate(certificate_id: str, token: str | None = None) -> dict:
	"""GET /certificates/{id} — stato, scadenza, CN."""
	path = f"/certificates/{certificate_id}"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def list_certificates(filters: dict | None = None, token: str | None = None) -> list[dict]:
	path = "/certificates"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), params=filters or {}, timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	body = r.json()
	if isinstance(body, list):
		return body
	for key in ("data", "items", "certificates"):
		if isinstance(body.get(key), list):
			return body[key]
	return []


# --- Firma batch -----------------------------------------------------------

def submit_qes_otp_batch(certificate_id: str, files: list[dict],
                          signature_type: str = "pades",
                          with_timestamp: bool = False,
                          token: str | None = None) -> dict:
	"""POST /EU-QES_otp.

	files: [{"fileName": "doc.pdf", "content": "<base64>"}].
	Ritorna {id, status, otpDestination, otpExpiresAt} (camelCase OpenAPI).
	"""
	path = "/EU-QES_otp"
	input_documents = [
		{"sourceType": "base64", "content": f["content"], "fileName": f["fileName"]}
		for f in files
	]
	payload = {
		"certificateId": certificate_id,
		"inputDocument": input_documents,
		"signatureType": signature_type,
		"withTimestamp": bool(with_timestamp),
	}
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=60)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())


def confirm_otp(signature_id: str, otp: str, token: str | None = None) -> dict:
	"""POST /signatures/{id}/confirm con body {otp}."""
	path = f"/signatures/{signature_id}/confirm"
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json={"otp": otp}, timeout=60)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())


def get_signature(signature_id: str, token: str | None = None) -> dict:
	path = f"/signatures/{signature_id}"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def get_signature_audit(signature_id: str, token: str | None = None) -> dict:
	path = f"/signatures/{signature_id}/audit"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def download_signed_document(signature_id: str, token: str | None = None) -> bytes:
	"""GET /signatures/{id}/signedDocument.

	Ritorna il binary direttamente. Per N>1 file, OpenAPI ritorna uno zip.
	"""
	path = f"/signatures/{signature_id}/signedDocument"
	r = requests.get(
		f"{_base_url()}{path}",
		headers=_headers(token, json_content=False),
		timeout=DOWNLOAD_TIMEOUT_SEC,
	)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return r.content


def poll_signature(signature_id: str, token: str | None = None,
                    max_sec: int = SIGN_POLL_MAX_SEC) -> dict:
	"""Polling /signatures/{id} fino a stato terminale o timeout."""
	deadline = time.time() + max_sec
	last_state = None
	while time.time() < deadline:
		data = get_signature(signature_id, token=token)
		state = (data.get("status") or data.get("state") or "").lower()
		last_state = state
		if state in SIGN_DONE_STATES:
			return data
		if state in SIGN_ERROR_STATES:
			frappe.throw(f"OpenAPI signature {signature_id} fallita: stato={state}, body={data}")
		time.sleep(POLL_INTERVAL_SEC)
	frappe.throw(f"OpenAPI signature {signature_id} timeout dopo {max_sec}s (stato={last_state})")
	return {}  # unreachable


# --- Validazione firma esterna --------------------------------------------

def verify_signed_file(file_b64: str, filename: str | None = None,
                       verify_on_date: str | None = None,
                       token: str | None = None) -> dict:
	"""POST /verify con body {inputDocument: <b64>, verifyOnDate?: 'YYYY-MM-DD'}."""
	path = "/verify"
	payload: dict = {"inputDocument": file_b64}
	if filename:
		payload["fileName"] = filename
	if verify_on_date:
		payload["verifyOnDate"] = verify_on_date
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=60)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())
