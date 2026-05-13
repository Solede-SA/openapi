"""Orchestratori firma OpenAPI eSignature.

Funzioni pubbliche pensate per essere richiamate dai consumer (garemed, daeok, ...).
La libreria non sa nulla di wallet/tenant: i consumer iniettano il comportamento via
callback opzionali:

  on_charge(amount_eur: float, note: str)        — addebito al wallet del consumer
  on_refund(amount_eur: float, note: str)        — refund (errore/scaduto)
  on_signed_file(reference_doctype, reference_name, original_filename,
                 signed_bytes, signer_cn, cert_expires_at, signature_id)
                                                  — invocata per ogni file firmato

Nessun fallback: se un parametro mancante o un endpoint OpenAPI fallisce, frappe.throw
con messaggio diagnostico.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Callable

import frappe
from frappe.utils import now_datetime, today, add_days, get_datetime, getdate, format_datetime

from openapi.api.esignature import client as esign_client


# --- Listino --------------------------------------------------------------

_COST_FIELDS = {
	"cert_namirial_otp_eur",
	"firma_per_doc_eur",
	"timestamp_eur",
	"verify_eur",
}


def get_costo(key: str) -> float:
	if key not in _COST_FIELDS:
		frappe.throw(f"Voce listino sconosciuta: {key}")
	value = frappe.db.get_single_value("OpenApi Signature Settings", key)
	if value is None:
		frappe.throw(
			f"OpenApi Signature Settings.{key} non configurato. "
			f"Eseguire 'bench migrate' (patch setup_signature_settings_defaults)."
		)
	return float(value)


# --- Helper anagrafica → payload Namirial --------------------------------

_REQUIRED_PAYLOAD_KEYS = (
	"nome", "cognome", "codice_fiscale", "data_nascita",
	"comune_nascita", "provincia_nascita", "email_otp", "telefono_otp",
)


def _validate_onboarding_payload(payload: dict) -> None:
	missing = [k for k in _REQUIRED_PAYLOAD_KEYS if not payload.get(k)]
	if missing:
		frappe.throw(f"Payload onboarding firma incompleto: campi mancanti {missing}")


def _build_namirial_request(payload: dict) -> dict:
	"""Costruisce il body POST /certificates/namirial-otp dalla forma normalizzata."""
	return {
		"firstName": payload["nome"],
		"lastName": payload["cognome"],
		"taxCode": payload["codice_fiscale"],
		"dateOfBirth": str(payload["data_nascita"]),
		"placeOfBirth": payload["comune_nascita"],
		"provinceOfBirth": payload["provincia_nascita"],
		"email": payload["email_otp"],
		"phoneNumber": payload["telefono_otp"],
	}


# --- Onboarding certificato ----------------------------------------------

def start_namirial_onboarding(*, payload: dict, customer: str | None = None,
                              on_charge: Callable[[float, str], None] | None = None,
                              consumer_app: str = "openapi") -> "frappe.Document":
	"""Avvia onboarding certificato Namirial OTP.

	Step:
	  1. valida payload anagrafico + contatti
	  2. POST /certificates/namirial-otp
	  3. crea OpenApi Signature Certificate (stato=in_attesa_identificazione)
	  4. addebita on_charge se fornito

	Ritorna il documento `OpenApi Signature Certificate` creato.
	"""
	_validate_onboarding_payload(payload)

	request_body = _build_namirial_request(payload)
	response = esign_client.create_namirial_otp_certificate(request_body)

	openapi_cert_id = response.get("id") or response.get("certificateId")
	if not openapi_cert_id:
		frappe.throw(
			f"OpenAPI eSignature non ha restituito un certificateId. Body: {response}"
		)
	identification_url = (
		response.get("identificationUrl")
		or response.get("identification_url")
		or response.get("verifyUrl")
	)

	cost = get_costo("cert_namirial_otp_eur")

	cert = frappe.get_doc({
		"doctype": "OpenApi Signature Certificate",
		"customer": customer,
		"provider": "namirial_otp",
		"openapi_certificate_id": openapi_cert_id,
		"stato": "in_attesa_identificazione",
		"nome": payload["nome"],
		"cognome": payload["cognome"],
		"codice_fiscale": payload["codice_fiscale"],
		"data_nascita": payload["data_nascita"],
		"comune_nascita": payload["comune_nascita"],
		"provincia_nascita": payload["provincia_nascita"],
		"email_otp": payload["email_otp"],
		"telefono_otp": payload["telefono_otp"],
		"identification_url": identification_url,
		"costo_eur": cost,
		"submitted_at": now_datetime(),
		"raw_response": json.dumps(response, default=str, ensure_ascii=False),
	})
	cert.flags.consumer_app = consumer_app
	cert.flags.ignore_permissions = True
	cert.insert()

	if on_charge is not None:
		on_charge(cost, f"Emissione certificato Namirial OTP {cert.name}")

	return cert


def refresh_certificate(certificate_name: str) -> dict:
	"""GET /certificates/{id} e aggiorna lo stato sul DocType.

	Ritorna lo stato normalizzato: {stato, data_emissione, data_scadenza, cn_certificato}.
	"""
	cert = frappe.get_doc("OpenApi Signature Certificate", certificate_name)
	if not cert.openapi_certificate_id:
		frappe.throw(f"Certificato {certificate_name} senza openapi_certificate_id")

	data = esign_client.get_certificate(cert.openapi_certificate_id)
	new_stato = _normalize_cert_state(data.get("status") or data.get("state"))
	issued_at = data.get("issuedAt") or data.get("issued_at") or data.get("createdAt")
	expires_at = data.get("expiresAt") or data.get("expires_at") or data.get("expiryDate")
	cn = data.get("commonName") or data.get("cn") or data.get("subjectCN")

	cert.stato = new_stato
	if issued_at and not cert.data_emissione:
		cert.data_emissione = getdate(issued_at)
	if expires_at:
		cert.data_scadenza = getdate(expires_at)
	if cn:
		cert.cn_certificato = cn
	cert.last_poll_at = now_datetime()
	if new_stato == "attivo" and not cert.completed_at:
		cert.completed_at = now_datetime()
	cert.raw_response = json.dumps(data, default=str, ensure_ascii=False)
	cert.flags.ignore_permissions = True
	cert.save()

	return {
		"stato": cert.stato,
		"data_emissione": str(cert.data_emissione) if cert.data_emissione else None,
		"data_scadenza": str(cert.data_scadenza) if cert.data_scadenza else None,
		"cn_certificato": cert.cn_certificato,
	}


def _normalize_cert_state(raw: str | None) -> str:
	if not raw:
		return "pending"
	s = raw.lower().strip()
	if s in esign_client.CERT_ACTIVE_STATES:
		return "attivo"
	if s in {"expired", "scaduto"}:
		return "scaduto"
	if s in {"revoked", "revocato"}:
		return "revocato"
	if s in {"rejected", "rifiutato"}:
		return "rifiutato"
	if s in esign_client.CERT_PENDING_STATES:
		return "in_attesa_identificazione"
	if s in {"error", "failed", "errore"}:
		return "errore"
	return "in_attesa_identificazione"


def poll_pending_certificates() -> dict:
	"""Cron: refresh stato per certificati in attesa o pending.

	Schedulato ogni 30 minuti (vedi hooks.py).
	"""
	pending_states = ("pending", "in_attesa_identificazione")
	candidates = frappe.get_all(
		"OpenApi Signature Certificate",
		filters={"stato": ["in", pending_states]},
		fields=["name"],
	)
	updated = 0
	for row in candidates:
		try:
			refresh_certificate(row["name"])
			updated += 1
		except Exception as exc:
			frappe.log_error(
				message=f"poll_pending_certificates: errore su {row['name']}: {exc}",
				title="OpenAPI Signature poll",
			)
	return {"checked": len(candidates), "updated": updated}


# --- Firma batch ----------------------------------------------------------

def _validate_certificate_active(cert: "frappe.Document") -> None:
	if cert.stato != "attivo":
		frappe.throw(
			f"Certificato {cert.name} non attivo (stato={cert.stato}). "
			f"Completa l'identificazione prima di firmare."
		)
	if cert.data_scadenza and getdate(cert.data_scadenza) < getdate(add_days(today(), 7)):
		frappe.throw(
			f"Certificato {cert.name} in scadenza il {cert.data_scadenza}. "
			f"Rinnova prima di firmare."
		)


def _md5_of(blob: bytes) -> str:
	return hashlib.md5(blob).hexdigest()


def _mask_destination(raw: str | None) -> str:
	if not raw:
		return ""
	if "@" in raw:
		left, _, domain = raw.partition("@")
		return f"{left[:2]}***@{domain}"
	if len(raw) >= 4:
		return f"{raw[:3]}***{raw[-2:]}"
	return "***"


def start_sign_batch(*, certificate_name: str, documents: list[dict],
                     signature_type: str = "pades",
                     with_timestamp: bool = False,
                     customer: str | None = None,
                     on_charge: Callable[[float, str], None] | None = None,
                     consumer_app: str = "openapi") -> "frappe.Document":
	"""Crea sessione di firma batch e invia OTP al firmatario.

	documents: lista di dict con chiavi
	  - reference_doctype (str, opzionale)
	  - reference_name (str, opzionale)
	  - filename (str)
	  - file_bytes (bytes)
	"""
	if not documents:
		frappe.throw("Nessun documento da firmare")
	if len(documents) > 50:
		frappe.throw("Massimo 50 documenti per batch")

	cert = frappe.get_doc("OpenApi Signature Certificate", certificate_name)
	_validate_certificate_active(cert)

	prepared_files = []
	for d in documents:
		blob = d["file_bytes"]
		if not isinstance(blob, (bytes, bytearray)):
			frappe.throw(f"file_bytes deve essere bytes per documento {d.get('filename')}")
		prepared_files.append({
			"fileName": d["filename"],
			"content": base64.b64encode(blob).decode("ascii"),
			"md5": _md5_of(blob),
			"reference_doctype": d.get("reference_doctype"),
			"reference_name": d.get("reference_name"),
		})

	costo_firma = get_costo("firma_per_doc_eur") * len(prepared_files)
	costo_timestamp = get_costo("timestamp_eur") * len(prepared_files) if with_timestamp else 0
	totale = costo_firma + costo_timestamp

	response = esign_client.submit_qes_otp_batch(
		certificate_id=cert.openapi_certificate_id,
		files=[{"fileName": f["fileName"], "content": f["content"]} for f in prepared_files],
		signature_type=signature_type,
		with_timestamp=with_timestamp,
	)

	signature_id = response.get("id") or response.get("signatureId")
	if not signature_id:
		frappe.throw(f"OpenAPI eSignature non ha restituito un signatureId. Body: {response}")
	otp_destination = response.get("otpDestination") or response.get("otp_destination")
	otp_expires_at = response.get("otpExpiresAt") or response.get("otp_expires_at")

	req = frappe.get_doc({
		"doctype": "OpenApi Signature Request",
		"certificate": cert.name,
		"customer": customer,
		"consumer_app": consumer_app,
		"signature_type": signature_type,
		"with_timestamp": 1 if with_timestamp else 0,
		"stato": "otp_inviato",
		"openapi_signature_id": signature_id,
		"otp_destination_masked": _mask_destination(otp_destination),
		"otp_expires_at": get_datetime(otp_expires_at) if otp_expires_at else None,
		"costo_eur": totale,
		"richiesta_at": now_datetime(),
		"documenti": [
			{
				"nome_file_originale": f["fileName"],
				"md5_originale": f["md5"],
				"reference_doctype": f["reference_doctype"],
				"reference_name": f["reference_name"],
			}
			for f in prepared_files
		],
	})
	req.flags.ignore_permissions = True
	req.insert()

	if on_charge is not None:
		on_charge(totale, f"Firma {len(prepared_files)} documenti — sessione {req.name}")

	return req


def confirm_otp_and_complete(*, request_name: str, otp: str,
                              on_signed_file: Callable | None = None,
                              on_refund: Callable[[float, str], None] | None = None) -> "frappe.Document":
	"""Conferma OTP, attende firma e invoca callback per ogni file firmato.

	on_signed_file(reference_doctype, reference_name, original_filename,
	               signed_bytes, signer_cn, cert_expires_at, signature_id)
	"""
	req = frappe.get_doc("OpenApi Signature Request", request_name)

	if req.stato != "otp_inviato":
		frappe.throw(
			f"Sessione {request_name} non in stato 'otp_inviato' (corrente: {req.stato})"
		)
	if req.otp_expires_at and get_datetime(req.otp_expires_at) < now_datetime():
		req.stato = "scaduta"
		req.error_message = "OTP scaduto"
		req.flags.ignore_permissions = True
		req.save()
		if on_refund is not None:
			on_refund(float(req.costo_eur or 0), f"Refund — OTP scaduto sessione {request_name}")
		frappe.throw("OTP scaduto. Avvia una nuova sessione di firma.")

	req.stato = "firma_in_corso"
	req.flags.ignore_permissions = True
	req.save()

	try:
		esign_client.confirm_otp(req.openapi_signature_id, otp)
		final_data = esign_client.poll_signature(req.openapi_signature_id)
		audit = esign_client.get_signature_audit(req.openapi_signature_id)

		cert = frappe.get_doc("OpenApi Signature Certificate", req.certificate)
		signer_cn = cert.cn_certificato or _extract_cn_from_audit(audit) or ""
		cert_expires_at = cert.data_scadenza

		signed_files = _extract_signed_files(req, final_data)

		for row, signed_bytes in signed_files:
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": f"signed_{row.nome_file_originale}",
				"content": signed_bytes,
				"is_private": 1,
				"attached_to_doctype": "OpenApi Signature Request",
				"attached_to_name": req.name,
			}).insert(ignore_permissions=True)
			row.file_firmato = file_doc.file_url
			row.firmato_at = now_datetime()

			if on_signed_file is not None and row.reference_doctype and row.reference_name:
				on_signed_file(
					row.reference_doctype, row.reference_name,
					row.nome_file_originale, signed_bytes,
					signer_cn, cert_expires_at, req.openapi_signature_id,
				)

		req.stato = "completata"
		req.completata_at = now_datetime()
		req.audit_trail = json.dumps({"final": final_data, "audit": audit}, default=str, ensure_ascii=False)
		req.save()
		return req
	except Exception as exc:
		req.reload()
		req.stato = "errore"
		req.error_message = str(exc)[:500]
		req.save()
		if on_refund is not None:
			on_refund(float(req.costo_eur or 0), f"Refund — errore sessione {request_name}: {exc}")
		raise


def _extract_signed_files(req, final_data: dict) -> list:
	"""Scarica i file firmati e li abbina alle child row per nome.

	OpenAPI ritorna un singolo file se N=1, uno zip se N>1.
	"""
	import io
	import zipfile

	blob = esign_client.download_signed_document(req.openapi_signature_id)
	rows_by_name = {row.nome_file_originale: row for row in req.documenti}

	pairs = []

	# Single-file case: una sola child row
	if len(req.documenti) == 1:
		row = req.documenti[0]
		pairs.append((row, blob))
		return pairs

	# Multi-file: tentativo zip
	try:
		with zipfile.ZipFile(io.BytesIO(blob)) as zf:
			for member in zf.namelist():
				row = _match_row(member, rows_by_name)
				if row is None:
					frappe.throw(f"File firmato '{member}' non riconducibile a nessun originale nella sessione {req.name}")
				pairs.append((row, zf.read(member)))
	except zipfile.BadZipFile:
		frappe.throw(f"Risposta /signedDocument non è uno zip valido (atteso per batch multi-file). Sessione {req.name}.")

	if len(pairs) != len(req.documenti):
		frappe.throw(
			f"Sessione {req.name}: file firmati {len(pairs)} ≠ documenti inviati {len(req.documenti)}"
		)
	return pairs


def _match_row(filename_in_zip: str, rows_by_name: dict):
	"""Match per nome file firmato all'originale: OpenAPI suffissa .p7m o aggiunge prefisso 'signed_'."""
	if filename_in_zip in rows_by_name:
		return rows_by_name[filename_in_zip]
	for name, row in rows_by_name.items():
		if name in filename_in_zip:
			return row
		# .p7m envelope
		if filename_in_zip.endswith(".p7m") and filename_in_zip[:-4] == name:
			return row
	return None


def _extract_cn_from_audit(audit: dict) -> str | None:
	"""Estrae il CN del firmatario dall'audit trail OpenAPI."""
	if not isinstance(audit, dict):
		return None
	for key in ("commonName", "signerCN", "subjectCN", "cn"):
		if audit.get(key):
			return audit[key]
	signers = audit.get("signers") or audit.get("signatures")
	if isinstance(signers, list) and signers:
		first = signers[0]
		if isinstance(first, dict):
			for key in ("commonName", "cn", "subjectCN", "signerCN"):
				if first.get(key):
					return first[key]
	return None


def get_request_status(request_name: str) -> dict:
	req = frappe.get_doc("OpenApi Signature Request", request_name)
	return {
		"name": req.name,
		"stato": req.stato,
		"signature_type": req.signature_type,
		"openapi_signature_id": req.openapi_signature_id,
		"otp_destination_masked": req.otp_destination_masked,
		"otp_expires_at": format_datetime(req.otp_expires_at) if req.otp_expires_at else None,
		"costo_eur": float(req.costo_eur or 0),
		"richiesta_at": format_datetime(req.richiesta_at) if req.richiesta_at else None,
		"completata_at": format_datetime(req.completata_at) if req.completata_at else None,
		"error_message": req.error_message,
		"documenti": [
			{
				"nome_file_originale": r.nome_file_originale,
				"reference_doctype": r.reference_doctype,
				"reference_name": r.reference_name,
				"file_firmato": r.file_firmato,
				"firmato_at": format_datetime(r.firmato_at) if r.firmato_at else None,
			}
			for r in req.documenti
		],
	}


def cancel_request(*, request_name: str,
                    on_refund: Callable[[float, str], None] | None = None) -> None:
	req = frappe.get_doc("OpenApi Signature Request", request_name)
	if req.stato not in ("otp_inviato", "firma_in_corso"):
		frappe.throw(f"Sessione {request_name} non annullabile (stato={req.stato})")
	req.stato = "annullata"
	req.flags.ignore_permissions = True
	req.save()
	if on_refund is not None:
		on_refund(float(req.costo_eur or 0), f"Refund — sessione {request_name} annullata")


# --- Validazione firma esterna -------------------------------------------

def verify_external(*, file_bytes: bytes, filename: str | None = None,
                     customer: str | None = None,
                     on_charge: Callable[[float, str], None] | None = None) -> dict:
	"""Valida una firma esterna via POST /verify.

	Throw se la firma non è valida (con dettaglio dalla response OpenAPI).
	"""
	if not isinstance(file_bytes, (bytes, bytearray)):
		frappe.throw("file_bytes deve essere bytes")
	cost = get_costo("verify_eur")
	if on_charge is not None:
		on_charge(cost, f"Validazione firma {filename or ''}".strip())

	b64 = base64.b64encode(file_bytes).decode("ascii")
	data = esign_client.verify_signed_file(b64, filename=filename)

	valid = bool(
		data.get("valid")
		or data.get("isValid")
		or (data.get("overallStatus") or "").lower() in ("valid", "passed", "ok")
		or (data.get("status") or "").lower() in ("valid", "passed", "ok")
	)
	signers_raw = data.get("signers") or data.get("signatures") or []
	signers = []
	for s in signers_raw:
		if not isinstance(s, dict):
			continue
		signers.append({
			"cn": s.get("commonName") or s.get("cn") or s.get("subjectCN") or s.get("signerCN"),
			"issuer": s.get("issuer"),
			"expires_at": s.get("certificateExpiry") or s.get("expiresAt") or s.get("expiryDate"),
			"valid_chain": s.get("validChain", s.get("isChainValid")),
		})

	result = {
		"valid": valid,
		"signers": signers,
		"eidas_compliant": data.get("eidasCompliant") or data.get("eIDASCompliant"),
		"details": data.get("details") or data.get("validationDetails"),
		"raw": data,
	}

	if not valid:
		frappe.throw(
			"Firma non valida: " + json.dumps(
				{k: result[k] for k in ("signers", "details") if result[k]},
				default=str, ensure_ascii=False,
			)
		)
	if not signers:
		frappe.throw(
			f"Validazione completata ma OpenAPI non ha restituito firmatari. Body: {data}"
		)
	return result
