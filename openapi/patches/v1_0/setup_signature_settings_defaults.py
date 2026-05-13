"""Seed listino default in OpenApi Signature Settings (Single).

Scrive direttamente in tabSingles (frappe.db.set_single_value), perché il default JSON
del DocType non viene persistito automaticamente al primo migrate.

Idempotente: scrive solo i field con valore corrente vuoto/zero.
"""

import frappe


DEFAULTS = {
	# Listino top-up consultabile su https://console.openapi.com/it/apis/esignature/pricing
	"cert_namirial_otp_eur": 29,       # Cert Namirial OTP 3 anni (non confondere con Automatic = 137€)
	"firma_per_doc_eur": 0.025,        # POST /EU-QES_otp top-up (abbonamento 0,0065€)
	"timestamp_eur": 0.15,             # marca temporale
	"verify_eur": 0.001,               # POST /verify oltre i 10/giorno gratuiti
}


def execute():
	doctype = "OpenApi Signature Settings"
	for key, default_value in DEFAULTS.items():
		existing = frappe.db.get_single_value(doctype, key)
		if not existing:
			frappe.db.set_single_value(doctype, key, default_value)
	frappe.db.commit()
