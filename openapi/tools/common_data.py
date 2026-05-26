import frappe


def get_service(name, endpoint="business_registry_configurations"):
    url = frappe.get_value("OpenApi Services", name, "url")
    if not url:
        frappe.throw(
            f"OpenApi Services '{name}' non configurato (record mancante o campo url vuoto). "
            f"Crea il record in Desk → OpenApi Services."
        )
    return f"{url}/{endpoint}"
