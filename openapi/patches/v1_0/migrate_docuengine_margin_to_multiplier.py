"""Migra Docuengine: campo `default_margin_pct` (Percent) → `default_multiplier` (Float).
Conversione: multiplier = 1 + margin/100. Es. margin=50 → mult=1.5; margin=100 → mult=2.

Idempotente: skip se default_multiplier è già valorizzato.
"""

import frappe


def execute():
	# Single Docuengine Settings
	if frappe.db.exists("DocType", "Docuengine Settings"):
		# Provo a leggere il vecchio campo in modo difensivo
		row = frappe.db.sql(
			"""SELECT field, value FROM `tabSingles`
			   WHERE doctype = 'Docuengine Settings'
			     AND field IN ('default_margin_pct', 'default_multiplier')""",
			as_dict=True,
		)
		old_margin = next((r.value for r in row if r.field == "default_margin_pct"), None)
		new_mult = next((r.value for r in row if r.field == "default_multiplier"), None)
		if old_margin is not None and (new_mult is None or float(new_mult or 0) == 0):
			try:
				margin = float(old_margin)
				mult = round(1 + margin / 100.0, 3)
				settings = frappe.get_single("Docuengine Settings")
				settings.default_multiplier = mult
				settings.flags.ignore_permissions = True
				settings.save()
			except (TypeError, ValueError):
				pass

	# Documenti con override
	if frappe.db.exists("DocType", "Docuengine Document Price"):
		# Leggo eventuali colonne legacy
		columns = frappe.db.sql(
			"""SELECT COLUMN_NAME FROM information_schema.COLUMNS
			   WHERE TABLE_SCHEMA = DATABASE()
			     AND TABLE_NAME = 'tabDocuengine Document Price'""",
			as_dict=True,
		)
		col_names = {c["COLUMN_NAME"] for c in columns}
		if "margin_override_pct" in col_names:
			rows = frappe.db.sql(
				"""SELECT name, margin_override_pct FROM `tabDocuengine Document Price`
				   WHERE margin_override_pct IS NOT NULL AND margin_override_pct != 0""",
				as_dict=True,
			)
			for r in rows:
				try:
					mult = round(1 + float(r["margin_override_pct"]) / 100.0, 3)
					frappe.db.set_value(
						"Docuengine Document Price", r["name"],
						"multiplier_override", mult,
					)
				except (TypeError, ValueError):
					continue

	# Ricalcolo final_price su tutti i record
	if frappe.db.exists("DocType", "Docuengine Document Price"):
		all_names = frappe.get_all("Docuengine Document Price", pluck="name")
		for n in all_names:
			doc = frappe.get_doc("Docuengine Document Price", n)
			doc.flags.ignore_permissions = True
			doc.save()

	frappe.db.commit()
