import frappe
from frappe.model.document import Document


class DocuengineDocumentPrice(Document):
	def validate(self):
		self._compute_final_price()

	def _compute_final_price(self):
		cost = float(self.cost_eur or 0)
		# 0 trattato come "non impostato" → usa default globale.
		# Per disattivare manualmente un documento, usa il flag `enabled`.
		mult = float(self.multiplier_override or 0)
		if mult <= 0:
			settings = frappe.get_single("Docuengine Settings")
			mult = float(settings.default_multiplier or 1)
		self.final_price_eur = round(cost * mult, 2)
