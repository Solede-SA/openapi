"""Registro dei servizi openapi.com: un record `OpenApi Services` per servizio, creato se manca.

Perché non è (solo) una patch: su un sito appena creato Frappe **marca** le patch come eseguite
senza eseguirle, dando per scontato che lo schema nuovo le contenga già. Un seed affidato alla sola
patch quindi non arriva mai su un'installazione fresca, e il servizio risulta «non configurato» in
produzione il giorno del debutto. Agganciato a `after_install` e `after_migrate` invece arriva su
entrambi: sito nuovo e sito esistente.

**Crea se manca, non sovrascrive mai.** Gli indirizzi si personalizzano per sito (sull'installazione
di sviluppo il servizio SDI punta a un host locale): riscriverli a ogni migrazione cancellerebbe
quella configurazione senza dirlo a nessuno.
"""

import frappe

# Nome del servizio → indirizzo di produzione. Gli ambienti di prova NON sono record separati: il
# client riscrive l'host quando l'interruttore «Ambiente di prova» delle rispettive Impostazioni è
# acceso, così l'indirizzo resta uno solo da tenere aggiornato.
SERVICES = {
	"Geocoder": "https://geocoding.openapi.it",
	"Docuengine": "https://docuengine.openapi.com",
	"eSignature": "https://esignature.openapi.com",
	"SMS": "https://sms.openapi.com",
}


def ensure_services():
	"""Crea i record dei servizi mancanti. Idempotente: eseguibile a ogni migrazione."""
	created = []
	for name, url in SERVICES.items():
		if frappe.db.exists("OpenApi Services", name):
			continue
		service = frappe.get_doc(
			{"doctype": "OpenApi Services", "name": name, "titolo_servizio": name, "url": url}
		)
		service.flags.ignore_permissions = True
		service.insert(ignore_if_duplicate=True)
		created.append(name)

	linked = _link_sms_settings()
	if created or linked:
		frappe.db.commit()
	return created


def _link_sms_settings() -> bool:
	"""Aggancia il servizio alle Impostazioni SMS. Il campo è di sola lettura sul modulo: è qui che
	viene valorizzato, e senza il client non saprebbe quale record del registro leggere.

	Fuori dal ramo «creato»: il record del servizio e il collegamento sono due cose distinte, e se
	il primo esiste già (creato a mano, o da una vecchia patch) il secondo resterebbe vuoto per
	sempre."""
	if frappe.db.get_single_value("OpenApi SMS Settings", "service"):
		return False
	frappe.db.set_single_value("OpenApi SMS Settings", "service", "SMS")
	return True
