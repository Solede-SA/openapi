"""Crea il record OpenApi Services "eSignature" se non esiste.

URL di default: https://esignature.openapi.com (produzione).
La modalità sandbox è gestita da OpenApi Signature Settings.sandbox_mode che fa
puntare il client a https://test.esignature.openapi.com.
"""

import frappe


SERVICE_NAME = "eSignature"
DEFAULT_URL = "https://esignature.openapi.com"


def execute():
	if frappe.db.exists("OpenApi Services", SERVICE_NAME):
		return
	doc = frappe.get_doc({
		"doctype": "OpenApi Services",
		"name": SERVICE_NAME,
		"titolo_servizio": SERVICE_NAME,
		"url": DEFAULT_URL,
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_if_duplicate=True)
	frappe.db.commit()
