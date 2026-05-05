"""Crea il record OpenApi Services "Docuengine" se non esiste.

URL di default: https://docuengine.openapi.com
"""

import frappe


SERVICE_NAME = "Docuengine"
DEFAULT_URL = "https://docuengine.openapi.com"


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
