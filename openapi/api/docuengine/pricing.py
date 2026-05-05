"""Sync e gestione listino Docuengine.

- `sync_documents`: scarica `GET /documents` e fa upsert su `Docuengine Document Price`.
- `get_final_price`: prezzo finale (cost × markup) per un document_id.
- `list_active_for_client`: catalogo da esporre al cliente nel dialog "Importa dai registri pubblici".
- `find_document_id_by_name`: lookup case-insensitive per consumer (es. garemed).
"""

import json

import frappe
from frappe.utils import now

from openapi.api.docuengine import client


def _coerce_float(value, default=0.0) -> float:
	if value is None or value == "":
		return float(default)
	try:
		return float(value)
	except (TypeError, ValueError):
		return float(default)


def _extract_price(doc: dict) -> tuple[float, float, bool]:
	"""Estrae (cost, search_cost, has_search) da un record `/documents`.

	Schema osservato openapi.com (2026-05): `documentPrice`, `searchPrice`, `totalPrice`,
	`hasSearch` (bool). `cost_eur` salvato è `totalPrice` (cost + search) per coerenza
	con l'addebito wallet finale (che è l'importo totale che l'API fattura).
	"""
	doc_price = _coerce_float(doc.get("documentPrice") or 0)
	search_price = _coerce_float(doc.get("searchPrice") or 0)
	total_price = _coerce_float(doc.get("totalPrice") or (doc_price + search_price))
	has_search = bool(doc.get("hasSearch"))
	return total_price, search_price, has_search


@frappe.whitelist()
def sync_documents(token: str | None = None) -> dict:
	"""Scarica /documents e fa upsert su Docuengine Document Price.

	Documenti non più ritornati dall'API → enabled=0 (soft delete).
	"""
	docs = client.list_documents(token=token)
	now_str = now()
	seen_ids = set()
	added = 0
	updated = 0

	for d in docs:
		doc_id = d.get("id") or d.get("_id")
		if not doc_id:
			continue
		seen_ids.add(doc_id)
		name = d.get("name") or d.get("title") or doc_id
		category = d.get("category") or ""
		cost, search_cost, has_search = _extract_price(d)
		is_sync = bool(d.get("isSync"))
		req_structure = d.get("requestStructure") or d.get("request_structure") or {}
		try:
			req_structure_json = json.dumps(req_structure, indent=2, ensure_ascii=False)
		except Exception:
			req_structure_json = json.dumps({"raw": str(req_structure)}, indent=2)

		if frappe.db.exists("Docuengine Document Price", doc_id):
			row = frappe.get_doc("Docuengine Document Price", doc_id)
			row.document_name = name
			row.category = category
			row.cost_eur = cost
			row.search_cost_eur = search_cost
			row.has_search_cost = 1 if has_search else 0
			row.is_sync_service = 1 if is_sync else 0
			row.request_structure_json = req_structure_json
			row.last_seen_at = now_str
			# Se era stato disabilitato perchè non più visto, riabilita
			if not row.enabled:
				row.enabled = 1
			row.flags.ignore_permissions = True
			row.save()
			updated += 1
		else:
			row = frappe.get_doc({
				"doctype": "Docuengine Document Price",
				"document_id": doc_id,
				"document_name": name,
				"category": category,
				"cost_eur": cost,
				"search_cost_eur": search_cost,
				"has_search_cost": 1 if has_search else 0,
				"is_sync_service": 1 if is_sync else 0,
				"request_structure_json": req_structure_json,
				"last_seen_at": now_str,
				"enabled": 1,
			})
			row.flags.ignore_permissions = True
			row.insert()
			added += 1

	# Soft-delete: documenti nel DB non più visti → enabled=0
	all_db_ids = frappe.get_all("Docuengine Document Price", pluck="name")
	hidden = 0
	for did in all_db_ids:
		if did not in seen_ids:
			cur = frappe.db.get_value("Docuengine Document Price", did, "enabled")
			if cur:
				frappe.db.set_value("Docuengine Document Price", did, "enabled", 0)
				hidden += 1

	# Aggiorna Settings
	settings = frappe.get_single("Docuengine Settings")
	settings.last_sync_at = now_str
	settings.last_sync_count = len(seen_ids)
	settings.flags.ignore_permissions = True
	settings.save()

	frappe.db.commit()
	return {"added": added, "updated": updated, "hidden": hidden, "total": len(seen_ids)}


def get_final_price(document_id: str) -> float:
	"""Ritorna il prezzo finale (cost × markup) per un document_id."""
	row = frappe.db.get_value(
		"Docuengine Document Price",
		document_id,
		["final_price_eur", "enabled"],
		as_dict=True,
	)
	if not row:
		frappe.throw(f"Docuengine Document Price '{document_id}' non trovato. Eseguire la sincronizzazione listino.")
	if not row.enabled:
		frappe.throw(f"Documento '{document_id}' disabilitato.")
	return float(row.final_price_eur or 0)


@frappe.whitelist()
def list_active_for_client() -> list[dict]:
	"""Catalogo per il dialog cliente: solo documenti enabled, prezzo finale (con margine)."""
	rows = frappe.get_all(
		"Docuengine Document Price",
		filters={"enabled": 1},
		fields=[
			"name as document_id",
			"document_name",
			"category",
			"final_price_eur",
			"is_sync_service",
		],
		order_by="category asc, document_name asc",
	)
	return rows


def find_document_id_by_name(name_query: str) -> str | None:
	"""Match case-insensitive su document_name o category. Esatto preferito, fallback contains."""
	if not name_query:
		return None
	q = name_query.strip().lower()

	# match esatto su document_name
	exact = frappe.db.sql(
		"""SELECT name FROM `tabDocuengine Document Price`
		   WHERE LOWER(document_name) = %s AND enabled = 1
		   LIMIT 1""",
		(q,),
	)
	if exact:
		return exact[0][0]

	# match starts-with
	starts = frappe.db.sql(
		"""SELECT name FROM `tabDocuengine Document Price`
		   WHERE LOWER(document_name) LIKE %s AND enabled = 1
		   ORDER BY LENGTH(document_name) ASC
		   LIMIT 1""",
		(q + "%",),
	)
	if starts:
		return starts[0][0]

	# fallback contains
	contains = frappe.db.sql(
		"""SELECT name FROM `tabDocuengine Document Price`
		   WHERE LOWER(document_name) LIKE %s AND enabled = 1
		   ORDER BY LENGTH(document_name) ASC
		   LIMIT 1""",
		("%" + q + "%",),
	)
	if contains:
		return contains[0][0]
	return None
