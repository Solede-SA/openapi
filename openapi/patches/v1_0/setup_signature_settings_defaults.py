"""Seed listino default in OpenApi Signature Settings (Single).

Scrive direttamente in tabSingles (frappe.db.set_single_value), perché il default JSON
del DocType non viene persistito automaticamente al primo migrate.

Idempotente: scrive solo i field con valore corrente vuoto/zero.
"""

import frappe


DEFAULTS = {
	"cert_namirial_otp_eur": 137,
	"firma_per_doc_eur": 0.05,
	"timestamp_eur": 0.15,
	"verify_eur": 0.10,
}


def execute():
	doctype = "OpenApi Signature Settings"
	for key, default_value in DEFAULTS.items():
		existing = frappe.db.get_single_value(doctype, key)
		if not existing:
			frappe.db.set_single_value(doctype, key, default_value)
	frappe.db.commit()
