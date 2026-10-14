"""Marca temporale qualificata di un file (OpenAPI.it): il servizio scarica il file dall'indirizzo pubblico del sito
(frappe.utils.get_url, cioè host_name) e restituisce il file .m7m autocontenuto (file + marca), con valore probatorio.
Usata dai contratti dei clienti (daeok) e dagli accordi dei segnalatori (solede_agents)."""

import re

import requests

import frappe
from frappe import _

from openapi.openapi.doctype.openapi_marca_temporale_settings.openapi_marca_temporale_settings import (
	_get_auth_headers,
	aggiorna_contatori,
)
from openapi.tools.common_data import get_service

SETTINGS = "OpenApi Marca Temporale Settings"
LOT_EXHAUSTED = 215  # codice d'errore del servizio: lotto di marche terminato
# Il servizio pubblica il .m7m col nome del file marcato e rifiuta (403) i nomi con spazi o accenti
UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def timestamp_file(file_doc, file_name, attached_to):
	"""Marca il contenuto di `file_doc`: il servizio scarica una copia pubblica temporanea con un nome sicuro, poi la
	copia sparisce e l'originale resta com'è. Il .m7m diventa il File privato `file_name` allegato a
	`attached_to` = (doctype, name). Ritorna {file_url, transaction, remote_url}."""
	settings = frappe.get_single(SETTINGS)
	copy = frappe.get_doc(
		{"doctype": "File", "file_name": UNSAFE_NAME_CHARS.sub("_", file_doc.file_name), "content": file_doc.get_content(), "is_private": 0}
	).insert(ignore_permissions=True)
	try:
		data = _mark(settings, frappe.utils.get_url(copy.file_url))
	finally:
		copy.delete(ignore_permissions=True)

	remote_url = data["timestamp_body"]
	download = requests.get(remote_url, timeout=60)
	if download.status_code != 200:
		frappe.throw(_("Download del file marcato non riuscito: {0}").format(download.status_code))
	marked = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": download.content,
			"attached_to_doctype": attached_to[0],
			"attached_to_name": attached_to[1],
			"is_private": 1,
		}
	).insert(ignore_permissions=True)
	aggiorna_contatori(data["available"], data["used"])
	return {"file_url": marked.file_url, "transaction": data["transaction"], "remote_url": remote_url}


def _mark(settings, file_url):
	"""Chiamata /marca con le credenziali del lotto; lotto terminato e acquisto automatico = compra e riprova."""
	response = _post_mark(settings, file_url)
	if response.status_code == 422 and settings.auto_acquisto and response.json().get("error") == LOT_EXHAUSTED:
		settings.acquista_lotto()
		settings.reload()
		response = _post_mark(settings, file_url)
	if response.status_code != 200:
		frappe.throw(_("Marca temporale non riuscita ({0}): {1}").format(response.status_code, response.text[:500]))
	data = response.json()
	if not data.get("success"):
		frappe.throw(_("Marca temporale non riuscita: {0}").format(data.get("message")))
	return data["data"]


def _post_mark(settings, file_url):
	payload = {"file": file_url, "mime": True}  # mime: .m7m autocontenuto
	if settings.lotto_username:
		payload.update(username=settings.lotto_username, password=settings.get_password("lotto_password"), type=settings.provider)
	return requests.post(get_service("Marca Temporale", "marca"), headers=_get_auth_headers(), json=payload, timeout=60)

