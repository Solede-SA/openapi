import italian_invoice.utilities.fatture as fatture
import frappe


@frappe.whitelist()
def invia_fattura(docname, doctype):
    xml = fatture.get_xml(docname, doctype)
    return xml
