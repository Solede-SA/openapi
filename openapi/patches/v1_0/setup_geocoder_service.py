"""
Crea il record OpenApi Services "Geocoder" se non esiste.

URL di default: https://geocoding.openapi.it
L'utente puo' modificarlo dal desk se l'endpoint differisce.
"""

import frappe


SERVICE_NAME = "Geocoder"
DEFAULT_URL = "https://geocoding.openapi.it"


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
