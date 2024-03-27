# Copyright (c) 2024, Solede SA and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ConfigurazioneFatturaSDI(Document):

    def before_save(self, parent):
        print(parent)
