import frappe


def get_service(name, endpoint="business_registry_configurations"):
    url = frappe.get_value("OpenApi Services", name, "url")
    urlOk = url + "/" + endpoint

    return urlOk
