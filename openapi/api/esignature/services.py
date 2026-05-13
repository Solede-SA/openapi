"""Orchestratori firma OpenAPI eSignature.

Funzioni pubbliche pensate per essere richiamate dai consumer (garemed, daeok, ...).
La libreria non sa nulla di wallet/tenant: i consumer iniettano il comportamento via
callback opzionali:

  on_charge(amount_eur: float, note: str)        — addebito al wallet del consumer
  on_refund(amount_eur: float, note: str)        — refund (errore/scaduto)
  on_signed_file(reference_doctype, reference_name, original_filename,
                 signed_bytes, signer_cn, cert_expires_at, signature_id)
                                                  — invocata per ogni file firmato

Flow OTP reale (schema OAS):
  1. start_namirial_onboarding → POST /certificates/namirial-otp con solo
     certificateOwner + customReference. Risposta: id + certificateLink + state=NEW.
  2. Cliente apre certificateLink, completa video-ID Namirial, riceve via PDF + SMS:
     certificateUsername (RHI...) + certificatePassword.
  3. save_certificate_credentials → cliente inserisce username + password nel
     wizard onboarding step 4. Salvati in Password fieldtype (cifrato).
  4. poll_pending_certificates (cron) → quando state passa a DONE → "attivo".
  5. sign_batch_sincrono → chiama POST /EU-QES_otp con OTP (da app mobile) +
     username/password salvate + documenti base64. Risposta sincrona, scarica file
     firmati, invoca on_signed_file per ogni doc.

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


# --- State mapping (OAS → interno) ----------------------------------------

def _map_cert_state(raw: str | None, has_credentials: bool = False) -> str:
	"""Mappa state OAS Namirial sul nostro enum interno.

	OAS: NEW | REGISTERING | WORKING | DONE | SUSPENDED | EXPIRED | CANCELLED
	Interno: pending | in_attesa_identificazione | in_attesa_credenziali | attivo |
	         scaduto | revocato | rifiutato | errore

	Logica:
	- DONE: il certificato è emesso → 'in_attesa_credenziali' finché il cliente non
	  ha inserito certificate_username/password, poi 'attivo'.
	- NEW/REGISTERING/WORKING: in attesa video-ID Namirial.
	- EXPIRED: scaduto. SUSPENDED: revocato. CANCELLED: rifiutato.
	"""
	if not raw:
		return "pending"
	s = raw.upper().strip()
	if s in esign_client.CERT_STATE_ACTIVE:
		return "attivo" if has_credentials else "in_attesa_credenziali"
	if s in esign_client.CERT_STATE_EXPIRED:
		return "scaduto"
	if s in esign_client.CERT_STATE_SUSPENDED:
		return "revocato"
	if s in esign_client.CERT_STATE_CANCELLED:
		return "rifiutato"
	if s in esign_client.CERT_STATE_PENDING:
		return "in_attesa_identificazione"
	return "pending"


def _map_sign_state(raw: str | None) -> str:
	"""Mappa state firma OAS sul nostro enum interno.

	OAS: WAIT_VALIDATION | WAIT_SIGN | WAIT_SIGNER | DONE | ERROR
	Interno: bozza | in_corso | completata | errore | annullata
	"""
	if not raw:
		return "bozza"
	s = raw.upper().strip()
	if s in esign_client.SIGN_STATE_DONE:
		return "completata"
	if s in esign_client.SIGN_STATE_ERROR:
		return "errore"
	if s in esign_client.SIGN_STATE_PENDING:
		return "in_corso"
	return "bozza"


# --- Onboarding certificato ----------------------------------------------

def start_namirial_onboarding(*, payload: dict, customer: str | None = None,
                              on_charge: Callable[[float, str], None] | None = None,
                              consumer_app: str = "openapi") -> "frappe.Document":
	"""Avvia onboarding certificato Namirial OTP.

	payload (dict) deve contenere:
	  - certificate_owner (str, obbligatorio): "Nome Cognome" display
	  - custom_reference (str, opzionale): nostro identificativo interno
	  - email_otp (str, opzionale): per nostre notifiche, non inviato a Namirial
	  - telefono_otp (str, opzionale): idem

	Step:
	  1. POST /certificates/namirial-otp con solo certificateOwner + customReference
	  2. Crea OpenApi Signature Certificate (stato='in_attesa_identificazione')
	  3. Addebita on_charge se fornito

	Ritorna il documento `OpenApi Signature Certificate` creato.
	"""
	certificate_owner = (payload.get("certificate_owner") or "").strip()
	if not certificate_owner:
		frappe.throw("payload.certificate_owner obbligatorio")
	custom_reference = (payload.get("custom_reference") or "").strip() or None

	response = esign_client.create_namirial_otp_certificate(
		certificate_owner=certificate_owner,
		custom_reference=custom_reference,
	)

	openapi_cert_id = response.get("id") or response.get("certificateId")
	if not openapi_cert_id:
		frappe.throw(f"OpenAPI eSignature non ha restituito un certificateId. Body: {response}")
	certificate_link = response.get("certificateLink") or response.get("certificate_link")
	api_state = response.get("state") or "NEW"

	cost = get_costo("cert_namirial_otp_eur")

	cert = frappe.get_doc({
		"doctype": "OpenApi Signature Certificate",
		"customer": customer,
		"provider": "namirial_otp",
		"openapi_certificate_id": openapi_cert_id,
		"stato": _map_cert_state(api_state, has_credentials=False),
		"certificate_owner_display": certificate_owner,
		"custom_reference": custom_reference,
		"email_otp": payload.get("email_otp"),
		"telefono_otp": payload.get("telefono_otp"),
		"certificate_link": certificate_link,
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
	api_state = data.get("state") or "NEW"
	created_at = data.get("createdAt") or data.get("created_at")
	expire_at = data.get("expireAt") or data.get("expire_at")
	# Il CN non è sempre presente in /certificates/{id} — lo riprendiamo dall'audit
	# di una signature quando disponibile. Lo lasciamo opzionale qui.

	has_credentials = bool(cert.certificate_username and cert.get_password("certificate_password", raise_exception=False))
	cert.stato = _map_cert_state(api_state, has_credentials=has_credentials)
	if created_at and not cert.data_emissione:
		try:
			cert.data_emissione = getdate(created_at)
		except Exception:
			pass
	if expire_at:
		try:
			cert.data_scadenza = getdate(expire_at)
		except Exception:
			pass
	cert.last_poll_at = now_datetime()
	if cert.stato == "attivo" and not cert.completed_at:
		cert.completed_at = now_datetime()
	cert.raw_response = json.dumps(data, default=str, ensure_ascii=False)
	cert.flags.ignore_permissions = True
	cert.save()

	return {
		"stato": cert.stato,
		"data_emissione": str(cert.data_emissione) if cert.data_emissione else None,
		"data_scadenza": str(cert.data_scadenza) if cert.data_scadenza else None,
		"cn_certificato": cert.cn_certificato,
		"api_state": api_state,
	}


def save_certificate_credentials(certificate_name: str, username: str, password: str) -> dict:
	"""Salva username (RHI...) + password ricevuti dal firmatario post-KYC.

	Le credenziali vanno cifrate via Frappe Password fieldtype (auto-encrypt).
	Aggiorna anche stato a 'attivo' se il certificato è DONE su OpenAPI.
	"""
	if not username or not password:
		frappe.throw("certificate_username e certificate_password obbligatori")
	cert = frappe.get_doc("OpenApi Signature Certificate", certificate_name)
	cert.certificate_username = username.strip()
	cert.certificate_password = password  # Password fieldtype → cifrato automaticamente
	cert.certificate_credentials_received_at = now_datetime()
	# Se il cert è già DONE su OpenAPI, ora che abbiamo le credenziali può passare ad attivo
	if cert.stato == "in_attesa_credenziali":
		cert.stato = "attivo"
		if not cert.completed_at:
			cert.completed_at = now_datetime()
	cert.flags.ignore_permissions = True
	cert.save()
	return {
		"certificate": cert.name,
		"stato": cert.stato,
		"certificate_username": cert.certificate_username,
	}


def poll_pending_certificates() -> dict:
	"""Cron: refresh stato per certificati in attesa.

	Schedulato ogni 30 minuti (vedi hooks.py).
	"""
	pending_states = ("pending", "in_attesa_identificazione", "in_attesa_credenziali")
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


# --- Firma batch sincrona -------------------------------------------------

def _validate_certificate_ready_to_sign(cert: "frappe.Document") -> None:
	if cert.stato != "attivo":
		frappe.throw(
			f"Certificato {cert.name} non attivo (stato={cert.stato}). "
			f"Completa l'identificazione video Namirial e l'inserimento delle credenziali."
		)
	if not cert.certificate_username:
		frappe.throw(
			f"Certificato {cert.name} senza certificate_username. "
			f"Inserisci le credenziali ricevute via PDF Namirial."
		)
	password = cert.get_password("certificate_password", raise_exception=False)
	if not password:
		frappe.throw(
			f"Certificato {cert.name} senza certificate_password. "
			f"Inserisci la password ricevuta via SMS Namirial."
		)
	if cert.data_scadenza and getdate(cert.data_scadenza) < getdate(add_days(today(), 7)):
		frappe.throw(
			f"Certificato {cert.name} in scadenza il {cert.data_scadenza}. "
			f"Rinnova prima di firmare."
		)


def _md5_of(blob: bytes) -> str:
	return hashlib.md5(blob).hexdigest()


def sign_batch_sincrono(*, certificate_name: str, certificate_otp: str,
                        documents: list[dict],
                        signature_type: str = "pades",
                        with_timestamp: bool = False,
                        certificate_id_otp: int = -1,
                        customer: str | None = None,
                        on_charge: Callable[[float, str], None] | None = None,
                        on_refund: Callable[[float, str], None] | None = None,
                        on_signed_file: Callable | None = None,
                        consumer_app: str = "openapi") -> "frappe.Document":
	"""Firma N documenti in batch sincrono.

	documents: lista di dict con chiavi {reference_doctype, reference_name, filename, file_bytes}.
	certificate_otp: codice TOTP a 6 cifre dall'app Namirial Sign mobile del firmatario.

	Flow:
	  1. Valida certificato (stato attivo, credenziali salvate, non scaduto)
	  2. Carica certificate_password (decifrata) dal DocType
	  3. POST /EU-QES_otp sincrono con base64 dei file
	  4. Se DONE: download signed document, abbina alle child row, chiama on_signed_file
	  5. Se ERROR: stato='errore', on_refund

	Ritorna OpenApi Signature Request completata (o errore).
	"""
	if not documents:
		frappe.throw("Nessun documento da firmare")
	if len(documents) > 50:
		frappe.throw("Massimo 50 documenti per batch")
	if not certificate_otp or len(certificate_otp.strip()) < 4:
		frappe.throw("OTP non valido. Apri l'app Namirial Sign sul telefono e inserisci il codice corrente.")

	cert = frappe.get_doc("OpenApi Signature Certificate", certificate_name)
	_validate_certificate_ready_to_sign(cert)
	cert_password = cert.get_password("certificate_password")

	prepared_files = []
	for d in documents:
		blob = d["file_bytes"]
		if not isinstance(blob, (bytes, bytearray)):
			frappe.throw(f"file_bytes deve essere bytes per documento {d.get('filename')}")
		prepared_files.append({
			"filename": d["filename"],
			"payload_b64": base64.b64encode(blob).decode("ascii"),
			"md5": _md5_of(blob),
			"reference_doctype": d.get("reference_doctype"),
			"reference_name": d.get("reference_name"),
		})

	costo_firma = get_costo("firma_per_doc_eur") * len(prepared_files)
	costo_timestamp = get_costo("timestamp_eur") * len(prepared_files) if with_timestamp else 0
	totale = costo_firma + costo_timestamp

	# Crea la Request PRIMA della call API per tracciare anche errori
	req = frappe.get_doc({
		"doctype": "OpenApi Signature Request",
		"certificate": cert.name,
		"customer": customer,
		"consumer_app": consumer_app,
		"signature_type": signature_type,
		"with_timestamp": 1 if with_timestamp else 0,
		"stato": "in_corso",
		"costo_eur": totale,
		"richiesta_at": now_datetime(),
		"documenti": [
			{
				"nome_file_originale": f["filename"],
				"md5_originale": f["md5"],
				"reference_doctype": f["reference_doctype"],
				"reference_name": f["reference_name"],
			}
			for f in prepared_files
		],
	})
	req.flags.ignore_permissions = True
	req.insert()
	# Commit early in modo che la richiesta esista anche se la POST OpenAPI fallisce con timeout
	frappe.db.commit()

	# Charge wallet prima della chiamata API (refund su errore)
	if on_charge is not None:
		on_charge(totale, f"Firma {len(prepared_files)} documenti — sessione {req.name}")

	# Costruisci payload e chiama OpenAPI eSignature
	input_documents = [
		{"sourceType": "base64", "payload": f["payload_b64"]}
		for f in prepared_files
	]

	try:
		response = esign_client.submit_qes_otp(
			certificate_username=cert.certificate_username,
			certificate_password=cert_password,
			certificate_otp=certificate_otp.strip(),
			input_documents=input_documents,
			signature_type=signature_type,
			certificate_id_otp=certificate_id_otp,
			with_timestamp=with_timestamp,
			title=f"Firma {len(prepared_files)} documenti — {consumer_app}",
		)
	except Exception as exc:
		req.reload()
		req.stato = "errore"
		req.error_message = str(exc)[:500]
		req.save()
		if on_refund is not None:
			on_refund(totale, f"Refund — errore firma {req.name}: {exc}")
		# IMPORTANTE: commit DOPO on_refund, prima del raise.
		# Il raise propaga l'eccezione fuori dall'@whitelist Frappe → auto-rollback;
		# senza questo commit le transazioni di refund e di stato='errore' verrebbero perse.
		frappe.db.commit()
		raise

	# Aggiorna Request con dati API
	signature_id = response.get("id") or response.get("signatureId")
	api_state = response.get("state") or ""

	req.reload()
	req.openapi_signature_id = signature_id

	if api_state.upper() in esign_client.SIGN_STATE_PENDING:
		# async — lasciamo in_corso, cron polling separato (raro nel MVP)
		req.audit_trail = json.dumps(response, default=str, ensure_ascii=False)
		req.save()
		frappe.db.commit()
		return req

	if api_state.upper() in esign_client.SIGN_STATE_ERROR:
		err_msg = response.get("errorMessage") or response.get("errorNumber") or "errore non specificato"
		req.stato = "errore"
		req.error_message = f"OpenAPI ERROR: {err_msg}"
		req.audit_trail = json.dumps(response, default=str, ensure_ascii=False)
		req.save()
		if on_refund is not None:
			on_refund(totale, f"Refund — firma fallita {req.name}: {err_msg}")
		# Commit DOPO refund (vedi nota sopra sull'auto-rollback Frappe @whitelist).
		frappe.db.commit()
		frappe.throw(f"Firma rifiutata da OpenAPI: {err_msg}")

	# SUCCESS sincrono (state == DONE)
	# Download signed document(s) + audit
	try:
		audit = esign_client.get_signature_audit(signature_id)
	except Exception:
		audit = {}

	signer_cn = _extract_cn(audit) or cert.cn_certificato or cert.certificate_owner_display

	signed_files = _split_signed_documents(req, signature_id, signature_type)

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
				signer_cn, cert.data_scadenza, signature_id,
			)

	# Aggiorna CN se ricevuto dall'audit
	if signer_cn and not cert.cn_certificato:
		cert.cn_certificato = signer_cn
		cert.flags.ignore_permissions = True
		cert.save()

	req.stato = "completata"
	req.completata_at = now_datetime()
	req.audit_trail = json.dumps({"response": response, "audit": audit}, default=str, ensure_ascii=False)
	req.save()
	frappe.db.commit()
	return req


def _split_signed_documents(req, signature_id: str, signature_type: str) -> list:
	"""Scarica il signed document e abbina ai child row.

	OpenAPI può ritornare un singolo file (N=1) o uno zip (N>1).
	Per PAdES singolo: PDF firmato (estensione invariata).
	Per CAdES: .p7m envelope.
	"""
	import io
	import zipfile

	blob = esign_client.download_signed_document(signature_id)

	if len(req.documenti) == 1:
		return [(req.documenti[0], blob)]

	rows_by_name = {row.nome_file_originale: row for row in req.documenti}
	pairs = []

	try:
		with zipfile.ZipFile(io.BytesIO(blob)) as zf:
			for member in zf.namelist():
				row = _match_row_to_original(member, rows_by_name)
				if row is None:
					frappe.throw(
						f"File firmato '{member}' non riconducibile ad alcun originale "
						f"nella sessione {req.name}"
					)
				pairs.append((row, zf.read(member)))
	except zipfile.BadZipFile:
		frappe.throw(
			f"Risposta /signedDocument non è uno zip valido (atteso per batch multi-file). "
			f"Sessione {req.name}."
		)

	if len(pairs) != len(req.documenti):
		frappe.throw(
			f"Sessione {req.name}: file firmati {len(pairs)} ≠ documenti inviati {len(req.documenti)}"
		)
	return pairs


def _match_row_to_original(filename_in_zip: str, rows_by_name: dict):
	"""Match per nome file firmato all'originale. OpenAPI può suffissare .p7m o aggiungere
	prefisso 'signed_'."""
	if filename_in_zip in rows_by_name:
		return rows_by_name[filename_in_zip]
	for name, row in rows_by_name.items():
		if name in filename_in_zip:
			return row
		if filename_in_zip.endswith(".p7m") and filename_in_zip[:-4] == name:
			return row
	return None


def _extract_cn(audit: dict) -> str | None:
	"""Estrae il CN del firmatario dall'audit trail OpenAPI."""
	if not isinstance(audit, dict):
		return None
	for key in ("subjectCN", "commonName", "signerCN", "cn"):
		if audit.get(key):
			return audit[key]
	signers = audit.get("signers") or audit.get("signatures") or audit.get("signatureReportList")
	if isinstance(signers, list) and signers:
		first = signers[0]
		if isinstance(first, dict):
			for key in ("subjectCN", "commonName", "cn", "signerCN"):
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
	"""Annulla richiesta in stato 'in_corso' (caso raro async).

	Per sincrono questo non serve: la chiamata API è già terminata al ritorno.
	"""
	req = frappe.get_doc("OpenApi Signature Request", request_name)
	if req.stato not in ("in_corso", "bozza"):
		frappe.throw(f"Sessione {request_name} non annullabile (stato={req.stato})")
	req.stato = "annullata"
	req.flags.ignore_permissions = True
	req.save()
	if on_refund is not None:
		on_refund(float(req.costo_eur or 0), f"Refund — sessione {request_name} annullata")


def delete_signature_session(*, request_name: str,
                              on_unsign_document: Callable | None = None) -> dict:
	"""Cancella completamente una sessione di firma.

	Use-case: richiesta GDPR del cliente, cleanup test, errore post-firma.
	Operazione **irreversibile**:
	  1. DELETE /signatures/{id} su OpenAPI (cancella signed document + audit trail server-side)
	  2. Elimina i File Frappe del documento firmato attaccati alla Request
	  3. Chiama on_unsign_document(reference_doctype, reference_name) per il consumer
	     (es. garemed reset Gara Documento: firma_metodo=nessuno, firmato=0, ecc.)
	  4. Mantiene il record OpenApi Signature Request con stato='annullata' per audit
	     nostro (nessun refund — la firma era valida e completata)

	Niente refund wallet: la firma era valida; il delete è azione successiva (GDPR).
	"""
	req = frappe.get_doc("OpenApi Signature Request", request_name)
	if not req.openapi_signature_id:
		frappe.throw(f"Sessione {request_name} senza openapi_signature_id — niente da cancellare su OpenAPI")
	if req.stato == "annullata":
		frappe.throw(f"Sessione {request_name} già annullata")

	# 1. DELETE su OpenAPI (irreversibile server-side)
	esign_client.delete_signature(req.openapi_signature_id)

	# 2. Elimina File Frappe attached alla Request + reset child rows
	for row in req.documenti:
		if row.file_firmato:
			file_doc_name = frappe.db.get_value("File", {"file_url": row.file_firmato}, "name")
			if file_doc_name:
				frappe.delete_doc("File", file_doc_name, ignore_permissions=True, delete_permanently=True)
		# 3. Callback consumer per cleanup reference_doctype/reference_name
		if on_unsign_document is not None and row.reference_doctype and row.reference_name:
			try:
				on_unsign_document(row.reference_doctype, row.reference_name)
			except Exception as exc:
				frappe.log_error(
					message=f"on_unsign_document error per {row.reference_doctype}/{row.reference_name}: {exc}",
					title=f"delete_signature_session {request_name}",
				)
		row.file_firmato = None
		row.firmato_at = None

	# 4. Aggiorna Request
	req.stato = "annullata"
	req.error_message = f"Sessione cancellata via DELETE /signatures/{req.openapi_signature_id}"
	req.flags.ignore_permissions = True
	req.save()
	frappe.db.commit()

	return {
		"name": req.name,
		"stato": req.stato,
		"openapi_signature_id": req.openapi_signature_id,
		"deleted_at": str(now_datetime()),
	}


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
	data = esign_client.verify_signed_file(b64)

	# Schema OAS: data.overallVerified (bool) + data.signatureReportList[]
	overall_verified = bool(data.get("overallVerified"))
	reports = data.get("signatureReportList") or []

	signers = []
	for r in reports:
		if not isinstance(r, dict):
			continue
		signers.append({
			"cn": r.get("subjectCN") or r.get("signerCN"),
			"issuer": r.get("issuerCN") or r.get("issuerDN"),
			"expires_at": r.get("signerCertificateNotAfter"),
			"valid_chain": r.get("integrity"),
			"cert_status": r.get("signerCertificateStatus"),
			"qc_compliance": r.get("qcComplianceStatus"),
			"signature_date": r.get("signatureDate") or r.get("trustedSignatureDate"),
		})

	result = {
		"valid": overall_verified,
		"signers": signers,
		"signature_format": data.get("signatureFormat"),
		"nr_of_signatures": data.get("nrOfSignatures"),
		"check_date": data.get("checkDate") or data.get("verificationDate"),
		"raw": data,
	}

	if not overall_verified:
		frappe.throw(
			"Firma non valida secondo OpenAPI eSignature. Dettagli: "
			+ json.dumps({k: result[k] for k in ("signers", "signature_format")},
			              default=str, ensure_ascii=False)
		)
	if not signers:
		frappe.throw(
			f"Validazione completata ma OpenAPI non ha restituito firmatari. Body: {data}"
		)
	return result
