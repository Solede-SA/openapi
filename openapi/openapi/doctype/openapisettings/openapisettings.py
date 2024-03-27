# Copyright (c) 2024, Solede SA and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class OpenApiSettings(Document):

    def before_save(self):
        print(self.configurazione_fattura_sdi)
        for item in self.configurazione_fattura_sdi:
            item.before_save(item)
