# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class SDIWebhookLog(Document):
	@frappe.whitelist()
	def retry(self):
		"""Riesegue il webhook usando il payload salvato"""
		import italian_invoice.utilities.fatture as fatture

		data = json.loads(self.payload)
		endpoint = self.event_type.replace("-", "_")

		result = fatture.handle_sdi_webhook(endpoint, data)

		if result.get("success"):
			self.response_status = "Success"
			self.processing_result = str(result)
			self.error_message = ""
		else:
			error_msg = result.get("message", "Errore elaborazione")
			frappe.throw(error_msg)

		self.save()
