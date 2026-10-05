"""
Test della verifica negatività: codice fiscale di persona o di azienda, conteggi dal dettaglio,
job programmato che raccoglie i risultati. Tutto mockato: nessuna chiamata di rete.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from openapi.api.aziende import negativita_persona

CUSTOMER_NAME = "_Test Negatività Azienda"


class TestNegativitaPersona(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for p in (
			patch.object(frappe.db, "commit"),
			patch.object(negativita_persona.common_data, "get_service", side_effect=lambda name, endpoint: f"https://risk.test/{endpoint}"),
			patch.object(negativita_persona, "get_company_doc", return_value=SimpleNamespace(custom_open_api_token="Bearer test")),
		):
			p.start()
			self.addCleanup(p.stop)
		if not frappe.db.exists("Customer", CUSTOMER_NAME):
			frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER_NAME, "customer_type": "Company", "tax_id": "00946130945"}).insert(ignore_permissions=True)

	def _post(self, fiscal_code):
		response = MagicMock(status_code=200)
		response.json.return_value = {"success": True, "data": {"id": "neg_test", "status": "PENDING"}}
		with patch.object(negativita_persona.requests, "post", return_value=response) as post:
			result = negativita_persona.request_negativita_check(fiscal_code, CUSTOMER_NAME)
		return result, post

	def test_partita_iva_azienda_senza_callback(self):
		result, post = self._post("00946130945")
		self.assertEqual(result["request_id"], "neg_test")
		self.assertEqual(post.call_args.kwargs["json"], {"cf_piva": "00946130945"})
		self.assertEqual(frappe.db.get_value("Customer", CUSTOMER_NAME, "custom_negativita_status"), "In Elaborazione")

	def test_codice_non_valido_si_ferma_prima_della_chiamata(self):
		result, post = self._post("1234")
		self.assertIn("error", result)
		post.assert_not_called()

	def test_azienda_dal_cliente_senza_prefisso_it(self):
		frappe.db.set_value("Customer", CUSTOMER_NAME, "tax_id", "IT00946130945")
		with patch.object(negativita_persona, "request_negativita_check") as request:
			negativita_persona.get_customer_negativita(CUSTOMER_NAME)
		request.assert_called_once_with("00946130945", CUSTOMER_NAME)

	def test_conta_le_procedure(self):
		negativita_persona.save_negativita_to_customer(
			CUSTOMER_NAME, {"protesti": [{"effetti": []}], "pregiudizievoli": [], "procedure": [{}, {}]}
		)
		customer = frappe.get_doc("Customer", CUSTOMER_NAME)
		self.assertEqual((customer.custom_negativita_protesti, customer.custom_negativita_procedure), (1, 2))
		self.assertEqual(customer.custom_negativita_status, "Completata")

	def test_job_registra_gli_errori(self):
		frappe.db.set_value("Customer", CUSTOMER_NAME, {"custom_negativita_status": "In Elaborazione", "custom_negativita_request_id": "neg_test"})
		logged = {"method": "OpenAPI verifica negatività", "error": ["like", f"%{CUSTOMER_NAME}%"]}
		before = frappe.db.count("Error Log", logged)
		with patch.object(negativita_persona, "check_request_status", return_value={"error": "Errore API: 500"}):
			negativita_persona.poll_pending_requests()
		self.assertEqual(frappe.db.count("Error Log", logged), before + 1)
