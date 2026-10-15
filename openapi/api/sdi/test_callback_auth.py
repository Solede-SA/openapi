"""Il callback SDI delle fatture fornitori (allow_guest) accetta solo richieste col segreto della Company."""
import frappe
from frappe.tests import IntegrationTestCase

from openapi.api.sdi.callback import authorize_guest_callback

SECRET = "segreto-di-prova-" + "x" * 16


def _payload(vat_id):
	return {"cessionario_committente": {"dati_anagrafici": {"id_fiscale_iva": {"id_codice": vat_id}}}}


class TestCallbackAuth(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.company = frappe.get_all("Company", fields=["name", "tax_id"], limit=1)[0]
		self.tax_id = self.company.tax_id or "01234567890"
		frappe.db.set_value("Company", self.company.name, {"tax_id": self.tax_id, "custom_auth_header": SECRET})
		self.payload = _payload(self.tax_id)
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(setattr, frappe.local, "request", None)
		frappe.set_user("Guest")

	def _request(self, authorization=None):
		headers = {"Authorization": authorization} if authorization is not None else {}
		frappe.utils.set_request(path="/api/method/openapi.api.sdi.callback.supplier_invoice", headers=headers)

	def _assert_refused(self, authorization, payload=None):
		self._request(authorization)
		with self.assertRaises(frappe.AuthenticationError):
			authorize_guest_callback(payload or self.payload)

	def test_secret_required_for_guest(self):
		for wrong in (None, "", "altro-segreto"):
			self._assert_refused(wrong)

	def test_right_secret_passes(self):
		self._request(SECRET)
		authorize_guest_callback(self.payload)

	def test_unknown_company_is_refused_even_with_a_secret(self):
		self._assert_refused(SECRET, _payload("99999999999"))

	def test_company_without_secret_refuses_everyone(self):
		frappe.db.set_value("Company", self.company.name, "custom_auth_header", "")
		self._assert_refused("")

	def test_authenticated_caller_passes(self):
		frappe.set_user("Administrator")
		self._request(None)
		authorize_guest_callback(self.payload)
