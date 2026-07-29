"""Client REST sms.openapi.com (Gateway SMS v2) — primitive di basso livello.

Schema di riferimento: https://console.openapi.com/oas/en/smsv2.openapi.json

Endpoint gestiti:
  POST /WW-messages      → invio messaggio (mondiale)
  GET  /messages/{id}    → stato di un messaggio
  GET  /senders          → mittenti registrati

**Un solo endpoint per Italia e Svizzera.** Esistono anche `/IT-messages` e `/ES-messages`
dedicati, ma con l'abbonamento SMS Italia attivo il traffico italiano inviato su `/WW-messages`
viene comunque scalato dal credito dell'abbonamento: due endpoint darebbero due percorsi da
mantenere per lo stesso risultato.

**Il richiamo di consegna si configura per messaggio**, dentro il corpo dell'invio (`callback`), non
con una registrazione globale: ogni invio dice a chi notificare e con quali intestazioni. Le
intestazioni sono il posto in cui passa il segreto condiviso che il nostro endpoint verifica —
è il meccanismo previsto dal servizio, e ci risparmia una firma HMAC da entrambi i lati.

**L'OTP non passa di qui.** Esiste un `POST /otp` che genera e spedisce il codice per conto nostro,
ma il nostro OTP vive in `solede_auth` ed è la sorgente unica per email e telefono: usarlo
significherebbe avere due generatori e due scadenze diverse per la stessa cosa.
"""

import frappe

from openapi.api._client import DEFAULT_TIMEOUT_SEC, OpenApiService, as_list

SERVICE_NAME = "SMS"
SANDBOX_HOST_REPLACE = ("sms.openapi.com", "test.sms.openapi.com")

_api = OpenApiService(
	SERVICE_NAME,
	created_by="openapi.install.ensure_services",
	sandbox_setting=("OpenApi SMS Settings", "sandbox_mode"),
	sandbox_host_replace=SANDBOX_HOST_REPLACE,
	sandbox_token_setting=("OpenApi SMS Settings", "sandbox_token"),
)

# Stati del messaggio (enum `state` dello schema). Il servizio prova a consegnare per 48 ore, poi
# passa a EXPIRED.
STATE_NEW = "NEW"
STATE_PENDING = "PENDING"
STATE_DELIVERED = "DELIVERED"
STATE_UNDELIVERABLE = "UNDELIVERABLE"
STATE_EXPIRED = "EXPIRED"
STATE_REJECTED = "REJECTED"

# Stati terminali: oltre questi il messaggio non cambia più, e il richiamo non tornerà.
FINAL_STATES = {STATE_DELIVERED, STATE_UNDELIVERABLE, STATE_EXPIRED, STATE_REJECTED}
FAILED_STATES = {STATE_UNDELIVERABLE, STATE_EXPIRED, STATE_REJECTED}

# Tentativi di riconsegna del richiamo se il nostro endpoint non risponde 200 (massimo ammesso: 5).
CALLBACK_RETRY = 3

# Stati della registrazione di un mittente. Solo APPROVED permette di spedire.
SENDER_APPROVED = "APPROVED"
# Limite del servizio sul campo che descrive il legame fra mittente e azienda.
ALIAS_RELATIONSHIP_MAX = 60


def send_message(
	sender: str,
	recipient: str,
	message: str,
	*,
	callback_url: str | None = None,
	callback_headers: dict | None = None,
	dry_run: bool = False,
	fail_on_multiple: bool = False,
	token: str | None = None,
) -> dict:
	"""POST /WW-messages — accoda un messaggio e ritorna il documento del messaggio.

	Args:
		sender: alias alfanumerico già registrato e approvato (3-11 caratteri, mai solo cifre).
		recipient: numero in formato E.164 (`+41791234567`).
		message: testo. La segmentazione la calcola il servizio: 160 caratteri per segmento in
			GSM-7, 70 in UCS-2 (basta un'emoji o una virgoletta tipografica per passare a UCS-2 e
			dimezzare lo spazio).
		callback_url: indirizzo a cui notificare i cambi di stato. Senza, lo stato si può solo
			interrogare con `get_message`.
		callback_headers: intestazioni del richiamo — è qui che passa il segreto condiviso.
		dry_run: valida e calcola costo e segmenti **senza inviare**. Usato dai test.
		fail_on_multiple: rifiuta l'invio se il testo eccede un singolo segmento.

	Returns:
		Il documento del messaggio: `id`, `state`, `messageCount` (segmenti, cioè quanti SMS si
		pagano), `charactersCount`, `encoding`, `price`, `totalPrice`, marche temporali.
		Attenzione: sui messaggi mondiali `price` e `totalPrice` arrivano a 0 e vengono valorizzati
		dal servizio più tardi — il costo si legge dal richiamo, non dalla risposta all'invio.
	"""
	if not sender:
		frappe.throw("Mittente SMS mancante: serve un alias registrato e approvato.")
	if not recipient:
		frappe.throw("Destinatario SMS mancante.")
	if not message:
		frappe.throw("Testo del messaggio mancante.")

	payload = {
		"sender": sender,
		"recipient": recipient,
		"message": message,
		"options": {"dryRun": bool(dry_run), "failOnMultipleMessages": bool(fail_on_multiple)},
	}
	if callback_url:
		callback = {"method": "JSON", "url": callback_url, "retry": CALLBACK_RETRY}
		if callback_headers:
			callback["headers"] = callback_headers
		payload["callback"] = callback

	return _api.request("POST", "/WW-messages", token=token, json=payload)


def get_message(message_id: str, token: str | None = None) -> dict:
	"""GET /messages/{id} — stato autorevole di un messaggio.

	È la fonte di verità sullo stato: il richiamo dice *che* qualcosa è cambiato, questo dice *cosa*.
	"""
	if not message_id:
		frappe.throw("Identificativo del messaggio mancante.")
	return _api.request("GET", f"/messages/{message_id}", token=token)


def list_senders(token: str | None = None) -> list[dict]:
	"""GET /senders — mittenti registrati, con il loro stato di approvazione.

	Serve a sapere se si può spedire: un mittente non ancora approvato fa rifiutare ogni invio con
	«not approved for country», e senza guardare qui lo si scopre al primo messaggio che non parte.

	L'elenco vuoto arriva come 404 «No senders found»: è la convenzione del servizio per una
	collezione vuota, non un errore, e qui diventa una lista vuota. Ogni altro 404 resta un errore."""
	try:
		body = _api.request("GET", "/senders", token=token, timeout=DEFAULT_TIMEOUT_SEC)
	except Exception as err:
		if "No senders found" in str(err):
			return []
		raise
	return as_list(body, "data", "senders", "items")


def register_alias(
	country_code: str,
	sender: str,
	*,
	company_website: str,
	industry: str,
	company_relationship: str,
	traffic_type: str = "transactional",
	token: str | None = None,
) -> dict:
	"""POST /senders/alias — registra un mittente alfanumerico per un paese di destinazione.

	Una registrazione per paese: l'approvazione vale per quello, e un mittente approvato per l'Italia
	non spedisce in Svizzera. In produzione la richiesta entra in `PENDING` e passa da una revisione
	manuale; nell'ambiente di prova viene approvata subito.

	Partita IVA e PEC non si mandano qui: la conformità al registro degli alias la cura il fornitore
	durante la revisione."""
	if len(company_relationship) > ALIAS_RELATIONSHIP_MAX:
		frappe.throw(
			f"Il legame fra mittente e azienda non può superare {ALIAS_RELATIONSHIP_MAX} caratteri."
		)
	payload = {
		"countryCode": country_code,
		"sender": sender,
		"trafficType": traffic_type,
		"companyWebsite": company_website,
		"industry": industry,
		"senderCompanyRelationship": company_relationship,
	}
	return _api.request("POST", "/senders/alias", token=token, json=payload)
