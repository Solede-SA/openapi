"""
Test della registrazione dell'alias: i campi richiesti cambiano col paese (la PEC solo per l'Italia).
Tutto mockato: nessuna chiamata di rete.
"""

import unittest
from unittest.mock import patch

import frappe

from openapi.api.sms import client

COMMON = {
	"company_website": "https://www.example.ch",
	"industry": "Software",
	"company_relationship": "Marchio della piattaforma",
}


class TestRegisterAlias(unittest.TestCase):
	def _payload(self, country_code, **kwargs):
		with patch.object(client._api, "request", return_value={}) as request:
			client.register_alias(country_code, "Mittente", **COMMON, **kwargs)
		return request.call_args.kwargs["json"]

	def test_italia_manda_la_pec(self):
		self.assertEqual(self._payload("IT", pec="azienda@pec.it")["pec"], "azienda@pec.it")

	def test_italia_senza_pec_si_ferma_prima_della_chiamata(self):
		with patch.object(client._api, "request") as request:
			with self.assertRaises(frappe.ValidationError):
				client.register_alias("IT", "Mittente", **COMMON)
		request.assert_not_called()

	def test_svizzera_non_manda_la_pec(self):
		self.assertNotIn("pec", self._payload("CH", pec="azienda@pec.it"))
