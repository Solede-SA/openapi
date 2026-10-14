"""Marca temporale generica (openapi.tools.marca_temporale) col servizio simulato: il servizio scarica una copia
pubblica temporanea con un nome sicuro, il .m7m diventa un File privato allegato, il lotto esaurito si ricompra e si
riprova."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from openapi.tools import marca_temporale

MARKED = {"timestamp_body": "https://test.invalid/_test.m7m", "transaction": "_test", "available": 97, "used": 3}


def response(status_code, payload=None, content=b""):
	return MagicMock(status_code=status_code, json=MagicMock(return_value=payload), text=str(payload), content=content)


class TestTimestampFile(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(patch.stopall)
		self.addCleanup(frappe.db.rollback)
		self.file = frappe.get_doc(
			{"doctype": "File", "file_name": "_test marca è.txt", "content": b"_test", "is_private": 1,
			 "attached_to_doctype": "Company", "attached_to_name": frappe.get_all("Company", pluck="name")[0]}
		).insert(ignore_permissions=True)
		self.get = patch("openapi.tools.marca_temporale.requests.get", return_value=response(200, content=b"_m7m")).start()
		self.counters = patch("openapi.tools.marca_temporale.aggiorna_contatori").start()

	def test_marks_a_public_copy_with_a_safe_name(self):
		post = patch("openapi.tools.marca_temporale.requests.post", return_value=response(200, {"success": True, "data": MARKED})).start()
		mark = marca_temporale.timestamp_file(self.file, "_test_marca.m7m", ("Company", self.file.attached_to_name))
		self.assertTrue(post.call_args.kwargs["json"]["file"].endswith("/files/_test_marca_.txt"))  # niente spazi né accenti
		self.assertFalse(frappe.db.exists("File", {"file_name": "_test_marca_.txt"}))  # la copia sparisce
		self.assertEqual(frappe.db.get_value("File", self.file.name, "is_private"), 1)  # l'originale non cambia
		marked = frappe.get_doc("File", {"file_url": mark["file_url"]})
		self.assertEqual((marked.is_private, marked.attached_to_doctype, marked.get_content()), (1, "Company", "_m7m"))  # get_content decodifica il testo
		self.assertEqual((mark["transaction"], mark["remote_url"]), ("_test", MARKED["timestamp_body"]))
		self.counters.assert_called_once_with(97, 3)

	def test_failure_removes_the_copy_and_raises(self):
		patch("openapi.tools.marca_temporale.requests.post", return_value=response(500, {"message": "errore"})).start()
		self.assertRaisesRegex(frappe.ValidationError, "500", marca_temporale.timestamp_file, self.file, "_x.m7m", ("Company", "x"))
		self.assertFalse(frappe.db.exists("File", {"file_name": "_test_marca_.txt"}))

	def test_exhausted_lot_is_bought_and_retried(self):
		frappe.db.set_single_value(marca_temporale.SETTINGS, "auto_acquisto", 1)
		post = patch(
			"openapi.tools.marca_temporale.requests.post",
			side_effect=[response(422, {"error": marca_temporale.LOT_EXHAUSTED}), response(200, {"success": True, "data": MARKED})],
		).start()
		with patch("openapi.openapi.doctype.openapi_marca_temporale_settings.openapi_marca_temporale_settings.OpenApiMarcaTemporaleSettings.acquista_lotto") as buy:
			marca_temporale.timestamp_file(self.file, "_test_marca.m7m", ("Company", self.file.attached_to_name))
		buy.assert_called_once()
		self.assertEqual(post.call_count, 2)
