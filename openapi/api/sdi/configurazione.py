import frappe
import requests


def get_service(name, endpoint="business_registry_configurations"):
    url = frappe.get_value("OpenApi Services", name, "url")
    urlOk = url + "/" + endpoint

    return urlOk


def prepare_data(data):
    data = frappe.parse_json(data)
    data["apply_legal_storage"] = bool(data.get("apply_legal_storage", False))
    data["apply_signature"] = bool(data.get("apply_signature", False))

    return data


@frappe.whitelist()
def create_business_register(data):
    """
    Wrapper per retrocompatibilità - usa il provider SDI configurato
    Configura il business register per il provider
    """
    try:
        import italian_invoice.utilities.fatture as fatture

        data = prepare_data(data)
        company = frappe.get_doc("Company", data["name"])

        # Ottieni provider e configura business register
        provider = fatture.get_sdi_provider(company.name)
        return provider.setup_business_register(company, data)

    except Exception as e:
        frappe.log_error(str(e), "SDI Business Register Error")
        frappe.throw(f"Errore business register: {str(e)}")


@frappe.whitelist()
def update_business_register(data):
    """
    Aggiorna configurazione business register esistente (PATCH)
    """
    import italian_invoice.utilities.fatture as fatture

    data = prepare_data(data)
    company = frappe.get_doc("Company", data["name"])

    provider = fatture.get_sdi_provider(company.name)
    result = provider.update_business_register(company, data)

    return result


def prepare_configuration(company):
    fiscal_id = company.tax_id
    callbacks = []

    for webhook in company.custom_elenco_webhook:
        callback = {
            "event": webhook.event,
            "url": company.custom_webhook_url + webhook.url,
            "auth_header": company.custom_auth_header,
        }
        callbacks.append(callback)

    configuration = {"fiscal_id": fiscal_id, "callbacks": callbacks}

    return frappe.parse_json(configuration)


@frappe.whitelist()
def send_configuration(data):
    """
    Wrapper per retrocompatibilità - usa il provider SDI configurato
    Configura i webhook per il provider
    """
    try:
        import italian_invoice.utilities.fatture as fatture

        data = prepare_data(data)
        company = frappe.get_doc("Company", data["name"])

        # Ottieni provider e configura webhook
        provider = fatture.get_sdi_provider(company.name)
        return provider.configure_webhooks(company)

    except Exception as e:
        frappe.log_error(str(e), "SDI Configuration Error")
        frappe.throw(f"Errore configurazione: {str(e)}")


@frappe.whitelist()
def check_business_register(data):
    try:
        frappe.log_error(
            f"Inizializzazione check_business_register con dati: {data}",
            "SDI Check Business Log",
        )

        data = prepare_data(data)
        frappe.log_error(f"Dati preparati: {data}", "SDI Check Business Log")

        company = frappe.get_doc("Company", data["name"])
        frappe.log_error(
            f"Company recuperata: {company.name}", "SDI Check Business Log"
        )

        url = get_service("SDI")
        frappe.log_error(f"URL servizio: {url}", "SDI Check Business Log")

        headers = {
            "Authorization": company.custom_open_api_token,
            "Content-Type": "application/json",
        }

        frappe.log_error(f"Headers impostati: {headers}", "SDI Check Business Log")
        frappe.log_error(f"Invio richiesta GET a {url}", "SDI Check Business Log")

        response = requests.get(url, headers=headers, params=data)

        frappe.log_error(
            f"Risposta ricevuta con status code: {response.status_code}",
            "SDI Check Business Log",
        )
        frappe.log_error(
            f"Contenuto risposta: {response.content}", "SDI Check Business Log"
        )

        print(response.content)

        # Verifica se la richiesta è andata a buon fine
        if response.status_code == 200:
            try:
                json_response = response.json()
                frappe.log_error(
                    f"Risposta JSON: {json_response}", "SDI Check Business Log"
                )
                return f"Prova: {json_response['data']}"
            except ValueError as e:
                error_msg = f"Errore nel parsing JSON della risposta: {str(e)}"
                frappe.log_error(
                    f"{error_msg}\nContenuto risposta: {response.content}",
                    "SDI Check Business Error",
                )
                return f"Errore: {error_msg}"
            except KeyError as e:
                error_msg = f"Chiave 'data' non trovata nella risposta JSON: {str(e)}"
                frappe.log_error(
                    f"{error_msg}\nContenuto risposta JSON: {response.json()}",
                    "SDI Check Business Error",
                )
                return f"Errore: {error_msg}"
        else:
            try:
                if response.content:
                    json_response = response.json()
                    message = json_response.get(
                        "message", f"Status code: {response.status_code}"
                    )
                else:
                    message = f"Status code: {response.status_code}"
            except ValueError:  # JSONDecodeError è una sottoclasse di ValueError
                message = f"Risposta non in formato JSON: {response.content}"

            error_msg = f"Errore nella richiesta: {message}"
            print(response.content)
            frappe.log_error(
                f"{error_msg}\nStatus Code: {response.status_code}\nContenuto risposta: {response.content}",
                "SDI Check Business Error",
            )
            return error_msg
    except Exception as e:
        error_details = f"Errore imprevisto in check_business_register: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_details, "SDI Check Business Critical Error")
        return f"Errore durante la verifica del business register: {str(e)}"
