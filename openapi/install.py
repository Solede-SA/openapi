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

import json
import os

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


def sync_workspace_from_json(app, workspace, module=None):
	"""Riallinea il layout di un Workspace pubblico al JSON dell'app.

	Serve perché **Frappe v16 non riallinea un Workspace già esistente**: al primo `bench migrate` lo
	crea dal JSON e poi non lo guarda più. Una voce aggiunta al JSON dopo il debutto dell'app non
	comparirebbe mai — è così che la sezione dei messaggi non si vedeva pur essendo nel file.

	Sovrascrive `content`, `links` e `shortcuts`: il JSON dell'app è l'unica fonte del layout, quindi
	le modifiche fatte a mano dall'interfaccia vengono sostituite. Idempotente.

	La barra laterale NON si tocca qui: ogni app la costruisce a modo suo — bookfit la deriva dalle
	scorciatoie, openapi la tiene in una fixture — e generalizzare anche quella vorrebbe dire
	scegliere per entrambe.
	"""
	module = module or app
	path = os.path.join(
		frappe.get_app_path(app), frappe.scrub(module), "workspace",
		frappe.scrub(workspace), f"{frappe.scrub(workspace)}.json",
	)
	with open(path) as handle:
		data = json.load(handle)

	if not frappe.db.exists("Workspace", workspace):
		frappe.get_doc(data).insert(ignore_permissions=True)
		return

	doc = frappe.get_doc("Workspace", workspace)
	doc.content = data["content"]
	doc.set("links", data["links"])
	doc.set("shortcuts", data["shortcuts"])
	# `type` è diventato obbligatorio dopo che alcuni workspace erano già stati creati: un record
	# nato prima ce l'ha vuoto e il primo salvataggio fallirebbe su un campo che non stiamo nemmeno
	# toccando. Si completa col valore predefinito del DocType.
	doc.type = doc.type or data.get("type") or "Workspace"
	doc.save(ignore_permissions=True)


def sync_openapi_workspace():
	"""Riallinea il Workspace «Openapi» al JSON dell'app, a ogni migrazione."""
	sync_workspace_from_json("openapi", "Openapi")
	frappe.db.commit()


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
