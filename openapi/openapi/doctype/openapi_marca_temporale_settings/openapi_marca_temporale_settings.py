# Copyright (c) 2026, Solede SA and contributors
# For license information, please see license.txt

import requests

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


BASE_URL = "https://ws.marchetemporali.com"


def _get_auth_headers():
    """Restituisce gli headers di autenticazione OpenAPI.it dalla Company."""
    company = frappe.get_doc(
        "Company",
        frappe.defaults.get_global_default("company"),
    )
    return {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }


class OpenApiMarcaTemporaleSettings(Document):

    @frappe.whitelist()
    def check_lotto(self):
        """Controlla le marche disponibili/usate nel lotto attivo."""
        if not self.lotto_username:
            frappe.throw("Credenziali lotto non configurate. Acquista un lotto prima.")

        headers = _get_auth_headers()
        password = self.get_password("lotto_password")

        response = requests.post(
            f"{BASE_URL}/check_lotto",
            headers=headers,
            json={
                "username": self.lotto_username,
                "password": password,
                "type": self.provider or "infocert",
            },
        )

        if response.status_code != 200:
            frappe.throw(f"Errore check lotto: {response.status_code} - {response.text}")

        data = response.json()
        if not data.get("success"):
            frappe.throw(f"Check lotto fallito: {data.get('message', 'errore sconosciuto')}")

        available = int(data["data"].get("available", 0))
        used = int(data["data"].get("used", 0))

        self.db_set("marche_disponibili", available, update_modified=False)
        self.db_set("marche_usate", used, update_modified=False)
        self.db_set("ultimo_controllo", now_datetime(), update_modified=False)
        self.reload()

        return {"available": available, "used": used}

    @frappe.whitelist()
    def acquista_lotto(self):
        """Acquista un nuovo lotto di marche temporali."""
        headers = _get_auth_headers()
        provider = self.provider or "infocert"
        qty = self.qty_acquisto or "100"

        response = requests.get(
            f"{BASE_URL}/marche/{provider}/{qty}",
            headers=headers,
        )

        if response.status_code == 402:
            frappe.throw("Credito insufficiente nel portafoglio OpenAPI.it")

        if response.status_code != 200:
            frappe.throw(f"Errore acquisto lotto: {response.status_code} - {response.text}")

        data = response.json()
        if not data.get("success"):
            frappe.throw(f"Acquisto fallito: {data.get('message', 'errore sconosciuto')}")

        lotto = data["data"]
        self.db_set("lotto_username", lotto["username"], update_modified=False)
        frappe.utils.password.set_encrypted_password(
            self.doctype, self.name, lotto["password"], "lotto_password"
        )
        self.db_set("marche_disponibili", int(qty), update_modified=False)
        self.db_set("marche_usate", 0, update_modified=False)
        self.db_set("ultimo_acquisto", now_datetime(), update_modified=False)
        self.db_set("ultimo_controllo", now_datetime(), update_modified=False)
        self.reload()

        return {"username": lotto["username"], "qty": qty}

    @frappe.whitelist()
    def get_lotti(self):
        """Restituisce la lista di tutti i lotti acquistati."""
        headers = _get_auth_headers()

        response = requests.get(f"{BASE_URL}/marche", headers=headers)

        if response.status_code != 200:
            frappe.throw(f"Errore recupero lotti: {response.status_code} - {response.text}")

        data = response.json()
        if not data.get("success"):
            frappe.throw(f"Recupero lotti fallito: {data.get('message', 'errore sconosciuto')}")

        return data["data"]


def aggiorna_contatori(available, used):
    """Aggiorna i contatori marche dalla response di /marca."""
    settings = frappe.get_doc("OpenApi Marca Temporale Settings")
    settings.db_set("marche_disponibili", int(available), update_modified=False)
    settings.db_set("marche_usate", int(used), update_modified=False)
    settings.db_set("ultimo_controllo", now_datetime(), update_modified=False)

    # Alert se sotto soglia
    soglia = settings.soglia_alert or 10
    if int(available) <= soglia:
        _invia_alert(int(available), soglia)


def check_lotto_e_alert():
    """Scheduled task giornaliero: controlla saldo lotto e invia alert se sotto soglia."""
    settings = frappe.get_doc("OpenApi Marca Temporale Settings")

    if not settings.lotto_username:
        return

    result = settings.check_lotto()
    available = result["available"]

    if available <= (settings.soglia_alert or 10):
        # Auto-acquisto se abilitato e lotto esaurito
        if settings.auto_acquisto and available == 0:
            try:
                settings.acquista_lotto()
                frappe.logger().info(
                    f"Lotto marche temporali acquistato automaticamente: {settings.qty_acquisto} marche"
                )
                return
            except Exception as e:
                frappe.log_error(
                    f"Auto-acquisto lotto fallito: {e}",
                    "Marca Temporale Alert",
                )

        _invia_alert(available, settings.soglia_alert or 10)


def _invia_alert(available, soglia):
    """Invia alert ai System Manager."""
    recipients = _get_alert_recipients()
    if not recipients:
        return

    frappe.sendmail(
        recipients=recipients,
        subject=f"[Alert] Marche temporali in esaurimento: {available} disponibili",
        message=(
            f"<p>Il lotto di marche temporali ha solo <strong>{available}</strong> "
            f"marche disponibili (soglia: {soglia}).</p>"
            f"<p>Accedi a OpenApi Marca Temporale Settings per acquistare un nuovo lotto.</p>"
        ),
        now=True,
    )


def _get_alert_recipients():
    """Restituisce le email dei System Manager."""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "System Manager", "parenttype": "User"},
        fields=["parent"],
    )
    emails = []
    for u in users:
        user = frappe.get_doc("User", u.parent)
        if user.enabled and user.email and user.email != "Administrator":
            emails.append(user.email)
    return emails
