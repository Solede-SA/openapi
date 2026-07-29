"""Base HTTP condivisa dei client openapi.com.

Perché esiste: `api/docuengine/client.py` e `api/esignature/client.py` avevano scritto due volte,
identiche, le stesse quattro funzioni di configurazione — base URL dal registro `OpenApi Services`,
token dalla Company, header con prefisso Bearer, errore fail-loud. L'SMS sarebbe stata la terza
copia. Qui quella logica vive una volta sola, parametrizzata sul nome del servizio.

Un servizio si dichiara una volta a livello di modulo:

    _api = OpenApiService("SMS", created_by="openapi.install.ensure_services",
                          sandbox_setting=("OpenApi SMS Settings", "sandbox_mode"),
                          sandbox_host_replace=("sms.openapi.com", "test.sms.openapi.com"))

Niente ripieghi: base URL mancante, token mancante o risposta di errore sono `frappe.throw`, mai un
`{"error": ...}` di ritorno che il chiamante può dimenticarsi di controllare (è il difetto della
prima generazione di client, `api/aziende/company_start.py`).
"""

import frappe
import requests

# Tutte le chiamate hanno un tempo massimo: senza, un blocco di openapi.com terrebbe fermo un worker.
DEFAULT_TIMEOUT_SEC = 30


class OpenApiService:
	"""Un servizio di openapi.com: dove sta, come ci si autentica, come si sbaglia.

	`sandbox_setting` è la coppia (DocType Single, fieldname) dell'interruttore sandbox,
	`sandbox_host_replace` la coppia (host di produzione, host di prova) da sostituire quando è
	acceso, e `sandbox_token_setting` la coppia (DocType Single, fieldname) della chiave d'accesso
	dell'ambiente di prova. Tutti opzionali: un servizio senza ambiente di prova non li dichiara.

	**La chiave di prova è un campo a parte, non un doppione.** Nella console di openapi.com Prod e
	Sandbox sono due API key distinte con due liste di token separate: la chiave di produzione
	nell'ambiente di prova viene rifiutata con «Wrong Token». Non è la stessa credenziale scritta due
	volte — è la credenziale di un altro ambiente, che non ha altro posto dove stare.
	"""

	def __init__(
		self, name, *, created_by, sandbox_setting=None, sandbox_host_replace=None, sandbox_token_setting=None
	):
		self.name = name
		self.created_by = created_by
		self.sandbox_setting = sandbox_setting
		self.sandbox_host_replace = sandbox_host_replace
		self.sandbox_token_setting = sandbox_token_setting

	# --- configurazione ------------------------------------------------------
	def is_sandbox(self) -> bool:
		"""Vero se il servizio è configurato per puntare all'ambiente di prova."""
		if not self.sandbox_setting:
			return False
		doctype, fieldname = self.sandbox_setting
		return bool(frappe.db.get_single_value(doctype, fieldname))

	def base_url(self) -> str:
		"""Indirizzo del servizio dal registro `OpenApi Services`.

		Il messaggio d'errore dice come rimediare: il record lo crea la migrazione, quindi il rimedio
		è `bench migrate`, non «configura qualcosa da qualche parte»."""
		url = frappe.db.get_value("OpenApi Services", self.name, "url")
		if not url:
			frappe.throw(
				f"OpenApi Services '{self.name}' non configurato. "
				f"Eseguire 'bench migrate' (il record lo crea {self.created_by})."
			)
		url = url.rstrip("/")
		if self.sandbox_host_replace and self.is_sandbox():
			url = url.replace(*self.sandbox_host_replace)
		return url

	def token(self, token=None) -> str:
		"""Chiave d'accesso per l'ambiente attivo: quella di prova se l'interruttore è acceso e il
		servizio ne dichiara una, altrimenti quella condivisa della Company.

		Fail-loud sulla chiave di prova mancante: senza, si ricadrebbe su quella di produzione e il
		servizio risponderebbe «Wrong Token» — un errore che parla di autenticazione e non dice
		affatto che si stava usando la chiave dell'ambiente sbagliato."""
		if token:
			return token
		if self.sandbox_token_setting and self.is_sandbox():
			doctype, fieldname = self.sandbox_token_setting
			configured = frappe.get_cached_doc(doctype).get_password(fieldname, raise_exception=False)
			if not configured:
				frappe.throw(
					f"Chiave d'accesso dell'ambiente di prova mancante in «{doctype}». "
					f"Su openapi.com Prod e Sandbox hanno chiavi distinte: quella di produzione qui non vale."
				)
			return configured
		return resolve_token()

	def headers(self, token=None, *, json_content=True, accept="application/json") -> dict:
		"""Intestazioni di autenticazione. Il prefisso `Bearer` si aggiunge se non c'è già: i token
		si incollano dalla console a volte con e a volte senza."""
		tok = self.token(token).strip()
		if not tok.lower().startswith("bearer "):
			tok = f"Bearer {tok}"
		built = {"Authorization": tok, "Accept": accept}
		if json_content:
			built["Content-Type"] = "application/json"
		return built

	# --- errori --------------------------------------------------------------
	def raise_error(self, method: str, path: str, response: requests.Response):
		"""Errore esplicito col corpo della risposta: senza, davanti a un 422 si resta a indovinare
		quale campo il servizio ha rifiutato."""
		try:
			body = response.json()
		except ValueError:
			body = response.text[:500]
		frappe.throw(f"OpenAPI {self.name} {method} {path} → {response.status_code}: {body}")

	# --- chiamata ------------------------------------------------------------
	def request(self, method: str, path: str, *, token=None, json=None, params=None, timeout=DEFAULT_TIMEOUT_SEC):
		"""Chiamata REST al servizio: risposta già scartata dell'involucro `data`, errore fail-loud.

		`path` è relativo alla base (es. `/messages/{id}`) e finisce nel messaggio d'errore così
		com'è, per rendere leggibile quale chiamata è fallita."""
		response = requests.request(
			method,
			f"{self.base_url()}{path}",
			headers=self.headers(token),
			json=json,
			params=params,
			timeout=timeout,
		)
		if response.status_code >= 400:
			self.raise_error(method, path, response)
		return unwrap(response.json())


def resolve_token(token=None) -> str:
	"""Token OpenAPI: quello passato, altrimenti quello della Company corrente.

	Una sola fonte, nessun ripiego: se non c'è, è un errore che dice dove metterlo."""
	if token:
		return token
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if company:
		configured = frappe.db.get_value("Company", company, "custom_open_api_token")
		if configured:
			return configured
	frappe.throw(
		f"Token OpenAPI non configurato su Company '{company}'. "
		f"Imposta Company.custom_open_api_token, oppure passa token esplicito."
	)
	return ""  # irraggiungibile: frappe.throw solleva


def unwrap(body):
	"""Contenuto della risposta senza l'involucro `data` standard di openapi.com."""
	if isinstance(body, dict) and "data" in body:
		return body["data"]
	return body


def as_list(body, *keys) -> list:
	"""Lista dentro una risposta che può essere la lista stessa o un oggetto che la contiene.

	I servizi di openapi.com non concordano sul nome della chiave (`data`, `documents`, `items`…):
	chi chiama dichiara quelle plausibili per il proprio endpoint."""
	if isinstance(body, list):
		return body
	if isinstance(body, dict):
		for key in keys:
			if isinstance(body.get(key), list):
				return body[key]
	return []
