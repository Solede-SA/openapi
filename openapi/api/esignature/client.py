"""Client REST esignature.openapi.com — primitive di basso livello.

Schema riferimento: https://console.openapi.com/oas/en/esignature.openapi.json

Endpoint gestiti:
  POST  /certificates/namirial-otp        → richiesta certificato Namirial OTP
  GET   /certificates/{id}                → dettaglio certificato (state, cn, expireAt)
  GET   /certificates                     → lista certificati (filtri state, certificateType)
  POST  /EU-QES_otp                       → firma QES sincrona con OTP nel body
  GET   /signatures/{id}/detail           → dettaglio sessione di firma
  GET   /signatures/{id}/audit            → audit trail completo (JSON)
  GET   /signatures/{id}/signedDocument   → download file firmato (binary o zip)
  POST  /verify                           → validazione firma su file esterni

Auth:
  Header `Authorization` con Bearer token. Token risolto da Company.custom_open_api_token
  (riusa la stessa convenzione di docuengine/client.py — un'unica fonte, nessun fallback).

Base URL:
  Lookup record `OpenApi Services` "eSignature". Se `OpenApi Signature Settings.sandbox_mode = 1`
  il client riscrive l'host verso `test.esignature.openapi.com` automaticamente.

Note critiche sul flow OTP:
  L'OTP è generato dall'app Namirial Sign mobile del firmatario (TOTP, valido 30s).
  Va passato direttamente nel body di POST /EU-QES_otp come `certificateOtp`.
  Non esiste un endpoint server-side per "inviare l'OTP".
"""

import time

import frappe
import requests

POLL_INTERVAL_SEC = 4
SIGN_POLL_MAX_SEC = 90
DOWNLOAD_TIMEOUT_SEC = 60

# Enum reali da OAS schema --------------------------------------------------

# certificate.state
CERT_STATE_ACTIVE = {"DONE"}
CERT_STATE_PENDING = {"NEW", "REGISTERING", "WORKING"}
CERT_STATE_EXPIRED = {"EXPIRED"}
CERT_STATE_SUSPENDED = {"SUSPENDED"}
CERT_STATE_CANCELLED = {"CANCELLED"}

# signature.state
SIGN_STATE_DONE = {"DONE"}
SIGN_STATE_ERROR = {"ERROR"}
SIGN_STATE_PENDING = {"WAIT_VALIDATION", "WAIT_SIGN", "WAIT_SIGNER"}

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


def _headers(token: str | None = None, json_content: bool = True, accept: str = "application/json") -> dict:
	tok = _resolve_token(token).strip()
	if not tok.lower().startswith("bearer "):
		tok = f"Bearer {tok}"
	h = {
		"Authorization": tok,
		"Accept": accept,
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
	"""Estrae il campo `data` dalla response (OpenAPI wrapper standard)."""
	if isinstance(body, dict) and "data" in body:
		return body["data"]
	return body


# --- Certificati -----------------------------------------------------------

def create_namirial_otp_certificate(
	certificate_owner: str,
	custom_reference: str | None = None,
	callback_url: str | None = None,
	token: str | None = None,
) -> dict:
	"""POST /certificates/namirial-otp.

	Body minimal secondo schema OAS:
	  - certificateOwner (string, obbligatorio) — display name "Nome Cognome"
	  - customReference (string, opzionale) — nostro identificativo interno
	  - callback (object, opzionale) — URL webhook per notifiche async

	Anagrafica firmatario (CF, data/luogo nascita, ecc.) NON va qui:
	la raccoglie Namirial direttamente nel video-riconoscimento.

	Ritorna `data` del response: {id, certificateType, state, certificateLink,
	certificateOwner: {owner, customReference}, createdAt, expireAt, ...}.
	"""
	if not certificate_owner:
		frappe.throw("certificate_owner obbligatorio")
	path = "/certificates/namirial-otp"
	payload: dict = {"certificateOwner": certificate_owner}
	if custom_reference:
		payload["customReference"] = custom_reference
	if callback_url:
		payload["callback"] = {"method": "POST", "url": callback_url}
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=30)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())


def get_certificate(certificate_id: str, token: str | None = None) -> dict:
	"""GET /certificates/{id}.

	Ritorna: {id, certificateType, state, certificateLink, createdAt, expireAt,
	certificateOwner: {owner, customReference}}.
	"""
	path = f"/certificates/{certificate_id}"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def list_certificates(filters: dict | None = None, token: str | None = None) -> list[dict]:
	"""GET /certificates con filtri opzionali (state, certificateType, skip, limit)."""
	path = "/certificates"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), params=filters or {}, timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	body = r.json()
	if isinstance(body, list):
		return body
	data = body.get("data") if isinstance(body, dict) else None
	if isinstance(data, list):
		return data
	return []


# --- Firma sincrona QES-OTP -----------------------------------------------

def submit_qes_otp(
	certificate_username: str,
	certificate_password: str,
	certificate_otp: str,
	input_documents: list[dict],
	signature_type: str = "pades",
	certificate_id_otp: int = -1,
	with_timestamp: bool = False,
	title: str | None = None,
	description: str | None = None,
	async_signature: bool = False,
	token: str | None = None,
) -> dict:
	"""POST /EU-QES_otp — firma QES con OTP, chiamata sincrona.

	input_documents: list di dict con chiavi {sourceType: 'base64'|'remote', payload?: '<b64>', url?: '<uri>'}.

	`certificate_otp` è generato dall'app Namirial Sign mobile del firmatario.
	`certificate_username` (RHI...) + `certificate_password` provengono dal PDF/SMS post-KYC.
	`certificate_id_otp` = -1 se il firmatario ha un solo dispositivo OTP abbinato.

	with_timestamp = True → options.level='T', altrimenti 'B'.

	Ritorna `data` con SignatureObject completo: {id, state, signatureType, document,
	options, certificateType, createdAt, errorNumber?, errorMessage?}.
	"""
	if not certificate_username or not certificate_password:
		frappe.throw("certificate_username e certificate_password obbligatori")
	if not certificate_otp:
		frappe.throw("certificate_otp obbligatorio (generato dall'app Namirial Sign)")
	if not input_documents:
		frappe.throw("input_documents non può essere vuoto")
	if signature_type not in ("cades", "pades", "xades", "pkcs1"):
		frappe.throw(f"signature_type non valido: {signature_type!r}")

	payload: dict = {
		"inputDocuments": input_documents,
		"certificateUsername": certificate_username,
		"certificatePassword": certificate_password,
		"certificateOtp": certificate_otp,
		"certificateIdOtp": certificate_id_otp,
		"signatureType": signature_type,
		"options": {
			"asyncSignature": async_signature,
			"asyncDocumentsValidation": False,
			"level": "T" if with_timestamp else "B",
		},
	}
	if title:
		payload["title"] = title
	if description:
		payload["description"] = description

	path = "/EU-QES_otp"
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=120)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())


def get_signature(signature_id: str, token: str | None = None) -> dict:
	"""GET /signatures/{id}/detail."""
	path = f"/signatures/{signature_id}/detail"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def get_signature_audit(signature_id: str, token: str | None = None) -> dict:
	"""GET /signatures/{id}/audit (richiede Accept: application/json)."""
	path = f"/signatures/{signature_id}/audit"
	r = requests.get(f"{_base_url()}{path}", headers=_headers(token), timeout=30)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return _unwrap(r.json())


def download_signed_document(signature_id: str, token: str | None = None) -> bytes:
	"""GET /signatures/{id}/signedDocument.

	Ritorna il binary direttamente. Per N>1 file, OpenAPI può ritornare uno zip.
	"""
	path = f"/signatures/{signature_id}/signedDocument"
	r = requests.get(
		f"{_base_url()}{path}",
		headers=_headers(token, json_content=False, accept="*/*"),
		timeout=DOWNLOAD_TIMEOUT_SEC,
	)
	if r.status_code >= 400:
		_raise_error("GET", path, r)
	return r.content


def poll_signature(signature_id: str, token: str | None = None,
                    max_sec: int = SIGN_POLL_MAX_SEC) -> dict:
	"""Polling /signatures/{id}/detail fino a stato terminale o timeout.

	Usato solo se options.asyncSignature=True (caso raro nel MVP, default sincrono).
	"""
	deadline = time.time() + max_sec
	last_state = None
	while time.time() < deadline:
		data = get_signature(signature_id, token=token)
		state = (data.get("state") or "").upper()
		last_state = state
		if state in SIGN_STATE_DONE:
			return data
		if state in SIGN_STATE_ERROR:
			err_msg = data.get("errorMessage") or data.get("errorNumber") or "errore non specificato"
			frappe.throw(f"OpenAPI signature {signature_id} fallita: {err_msg}")
		time.sleep(POLL_INTERVAL_SEC)
	frappe.throw(f"OpenAPI signature {signature_id} timeout dopo {max_sec}s (state={last_state})")
	return {}  # unreachable


# --- Validazione firma esterna --------------------------------------------

def verify_signed_file(
	file_b64: str,
	verify_on_date: str | None = None,
	pdf_encryption_password: str | None = None,
	recursive: bool = False,
	detached_content_b64: str | None = None,
	token: str | None = None,
) -> dict:
	"""POST /verify.

	Body: {inputDocument: <b64>, detachedContent?: <b64>, pdfEncryptionPassword?: str,
	       recursive?: bool, verifyOnDate?: 'YYYY-MM-DD'}.

	Ritorna `data` con {checkDate, verificationDate, signatureFormat, nrOfSignatures,
	overallVerified (bool), signatureReportList: [{integrity, subjectCN, issuerCN,
	signerCertificateNotBefore, signerCertificateNotAfter, signerCertificateStatus,
	signatureDate, qcComplianceStatus, ...}]}.
	"""
	if not file_b64:
		frappe.throw("file_b64 obbligatorio")
	path = "/verify"
	payload: dict = {"inputDocument": file_b64}
	if detached_content_b64:
		payload["detachedContent"] = detached_content_b64
	if pdf_encryption_password:
		payload["pdfEncryptionPassword"] = pdf_encryption_password
	if recursive:
		payload["recursive"] = True
	if verify_on_date:
		payload["verifyOnDate"] = verify_on_date
	r = requests.post(f"{_base_url()}{path}", headers=_headers(token), json=payload, timeout=60)
	if r.status_code >= 400:
		_raise_error("POST", path, r)
	return _unwrap(r.json())
