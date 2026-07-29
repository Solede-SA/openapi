import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from openapi.api.sms import client as sms_client

# Vincoli dell'alias imposti dal servizio: da 3 a 11 caratteri e mai tutto cifre (un mittente
# numerico verrebbe scambiato per un numero di telefono e rifiutato).
ALIAS_MIN_LENGTH = 3
ALIAS_MAX_LENGTH = 11

# Paesi in cui BookFit spedisce: il mittente va approvato per ciascuno, separatamente.
ALIAS_COUNTRIES = ("IT", "CH")


class OpenApiSMSSettings(Document):
	def validate(self):
		"""L'alias si valida qui, non al primo invio: un mittente sbagliato si scopre altrimenti
		dentro un lavoro in coda, quando l'SMS e' gia' stato tentato e il messaggio d'errore non
		arriva a nessuno."""
		alias = (self.sender_alias or "").strip()
		self.sender_alias = alias
		if not alias:
			return
		if not (ALIAS_MIN_LENGTH <= len(alias) <= ALIAS_MAX_LENGTH):
			frappe.throw(
				_("Il mittente deve avere da {0} a {1} caratteri.").format(ALIAS_MIN_LENGTH, ALIAS_MAX_LENGTH)
			)
		if alias.isdigit():
			frappe.throw(_("Il mittente non puo' essere composto solo da cifre."))

	@frappe.whitelist()
	def register_sender(self):
		"""Registra il mittente presso il fornitore, per ogni paese in cui BookFit spedisce.

		Una registrazione per paese: l'approvazione vale per quello, e un mittente approvato per
		l'Italia non spedisce in Svizzera. In produzione la richiesta entra in `PENDING` e passa da
		una revisione manuale; nell'ambiente di prova viene approvata subito. Il pulsante e' rilanciabile:
		un paese gia' approvato viene semplicemente saltato, cosi' non si accodano richieste inutili."""
		frappe.only_for("System Manager")
		mancanti = _missing_countries(sms_client.list_senders(), self.sender_alias)
		if not mancanti:
			return self.refresh_senders()

		for campo in ("sender_alias", "sender_company_website", "sender_industry", "sender_relationship"):
			if not self.get(campo):
				frappe.throw(
					_("Compila «{0}» prima di registrare il mittente.").format(self.meta.get_label(campo))
				)

		for paese in mancanti:
			sms_client.register_alias(
				paese,
				self.sender_alias,
				company_website=self.sender_company_website,
				industry=self.sender_industry,
				company_relationship=self.sender_relationship,
			)
		return self.refresh_senders()

	@frappe.whitelist()
	def refresh_senders(self):
		"""Rilegge dal fornitore lo stato dei mittenti e lo scrive nel campo di riepilogo.

		Perche' esiste: finche' un mittente non e' APPROVED ogni invio viene rifiutato, e senza
		guardare qui lo si scopre dal primo messaggio che non parte. Lo stato resta scritto sul
		documento cosi' si legge riaprendo il modulo, senza dover ripremere il pulsante.

		L'ambiente e' quello dell'interruttore: produzione e prova hanno liste di mittenti separate."""
		frappe.only_for("System Manager")
		ambiente = _("ambiente di prova") if self.sandbox_mode else _("produzione")
		senders = sms_client.list_senders()

		if not senders:
			righe = [_("Nessun mittente registrato.")]
		else:
			righe = [
				"{0} · {1} · {2}".format(s.get("countryCode"), s.get("sender"), s.get("state"))
				for s in sorted(senders, key=lambda s: (s.get("countryCode") or "", s.get("sender") or ""))
			]

		mancanti = _missing_countries(senders, self.sender_alias)
		if mancanti:
			righe.append(
				_("Non ancora utilizzabile in: {0}.").format(", ".join(mancanti))
			)

		self.db_set(
			"senders_state",
			"{0} — {1}\n{2}".format(
				frappe.utils.format_datetime(now_datetime(), "dd/MM/yyyy HH:mm"), ambiente, "\n".join(righe)
			),
		)
		return self.senders_state


def _missing_countries(senders, alias):
	"""Paesi in cui l'alias non e' (ancora) approvato. E' l'informazione che conta davvero: sapere
	che una registrazione esiste non basta, perche' PENDING non spedisce."""
	approvati = {
		s.get("countryCode")
		for s in senders
		if s.get("sender") == alias and s.get("state") == sms_client.SENDER_APPROVED
	}
	return [paese for paese in ALIAS_COUNTRIES if paese not in approvati]
