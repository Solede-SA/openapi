import json
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
CUSTOM_DIR = APP_DIR / "openapi" / "custom"
FIXTURES_CUSTOM_FIELD = APP_DIR / "fixtures" / "custom_field.json"
ALLOWED_MODULES = {None, "Openapi"}

# I campi del flusso SDI appartengono a italian_invoice (DocType Transazione SDI /
# Stato Fattura Elettronica, provider, fixture degli stati vivono lì): openapi non
# deve MAI rispedirli. Denylist esplicita perché un export-fixtures lanciato da un
# sito non ancora migrato (dove in DB hanno ancora module "Openapi") li
# reintrodurrebbe passando il filtro per modulo. La lista vive nell'app
# proprietaria (openapi dichiara già required_apps = ["italian_invoice"]).
from italian_invoice.tests.test_custom_export_hygiene import SDI_FIELDS as SDI_FIELDS_DENYLIST


class TestCustomExportHygiene(unittest.TestCase):
	"""Export Customizations su un sito multi-app ingloba anche campi e property
	setter di ALTRE app; con sync_on_migrate ogni migrate riscrive quelle copie
	sopra le definizioni canoniche delle app proprietarie (bug TD24). In
	custom/*.json possono vivere solo pezzi di modulo Openapi o senza modulo.
	Limite noto: entry senza chiave "module" e links non sono coperti —
	all'export usare "Apply Module Export Filter" e fare l'audit a mano.
	"""

	def test_no_foreign_module_entries(self):
		for path in sorted(CUSTOM_DIR.glob("*.json")):
			data = json.loads(path.read_text())
			for section in ("custom_fields", "property_setters"):
				for entry in data.get(section) or []:
					self.assertIn(
						entry.get("module"),
						ALLOWED_MODULES,
						f"{path.name}: '{entry.get('fieldname') or entry.get('name')}' "
						f"({section}) appartiene al modulo {entry.get('module')!r} di "
						"un'altra app: va rimosso, la proprietaria lo risincronizza al migrate",
					)

	def test_sdi_fields_never_shipped(self):
		sources = [(path, json.loads(path.read_text()).get("custom_fields") or [])
			for path in sorted(CUSTOM_DIR.glob("*.json"))]
		sources.append((FIXTURES_CUSTOM_FIELD, json.loads(FIXTURES_CUSTOM_FIELD.read_text())))
		for path, entries in sources:
			for entry in entries:
				self.assertNotIn(
					(entry["dt"], entry["fieldname"]),
					SDI_FIELDS_DENYLIST,
					f"{path.name}: '{entry['fieldname']}' ({entry['dt']}) è un campo "
					"SDI di italian_invoice: openapi non deve spedirlo (rimpatrio 2026-07)",
				)
