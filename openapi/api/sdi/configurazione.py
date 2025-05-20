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
    try:
        frappe.log_error(f"Inizializzazione create_business_register con dati: {data}", "SDI Business Register Log")
        
        data = prepare_data(data)
        frappe.log_error(f"Dati preparati: {data}", "SDI Business Register Log")
        
        company = frappe.get_doc("Company", data["name"])
        frappe.log_error(f"Company recuperata: {company.name}", "SDI Business Register Log")
        
        url = get_service("SDI")
        frappe.log_error(f"URL servizio: {url}", "SDI Business Register Log")
        
        headers = {
            "Authorization": company.custom_open_api_token,
            "Content-Type": "application/json",
        }
        
        frappe.log_error(f"Headers impostati: {headers}", "SDI Business Register Log")
        frappe.log_error(f"Invio richiesta POST a {url}", "SDI Business Register Log")
        
        response = requests.post(url, headers=headers, json=data)
        
        frappe.log_error(f"Risposta ricevuta con status code: {response.status_code}", "SDI Business Register Log")
        frappe.log_error(f"Contenuto risposta: {response.content}", "SDI Business Register Log")

        # Verifica se la richiesta è andata a buon fine
        if response.status_code == 200:
            try:
                json_response = response.json()
                frappe.log_error(f"Risposta JSON: {json_response}", "SDI Business Register Log")
                return json_response["data"]
            except ValueError as e:
                error_msg = f"Errore nel parsing JSON della risposta: {str(e)}"
                frappe.log_error(f"{error_msg}\nContenuto risposta: {response.content}", "SDI Business Register Error")
                frappe.throw(error_msg)
            except KeyError as e:
                error_msg = f"Chiave 'data' non trovata nella risposta JSON: {str(e)}"
                frappe.log_error(f"{error_msg}\nContenuto risposta JSON: {response.json()}", "SDI Business Register Error")
                frappe.throw(error_msg)
        else:
            try:
                if response.content:
                    json_response = response.json()
                    message = json_response.get("message", f"Status code: {response.status_code}")
                else:
                    message = f"Status code: {response.status_code}"
            except ValueError:  # JSONDecodeError è una sottoclasse di ValueError
                message = f"Risposta non in formato JSON: {response.content}"
            
            error_msg = f"Errore nella richiesta: {message}"
            frappe.log_error(f"{error_msg}\nStatus Code: {response.status_code}\nContenuto risposta: {response.content}", "SDI Business Register Error")
            frappe.throw(error_msg)
    except Exception as e:
        error_details = f"Errore imprevisto in create_business_register: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_details, "SDI Business Register Critical Error")
        frappe.throw(f"Errore durante la creazione del business register: {str(e)}")


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
    try:
        frappe.log_error(f"Inizializzazione invio configurazione con dati: {data}", "SDI Configuration Log")
        
        data = prepare_data(data)
        frappe.log_error(f"Dati preparati: {data}", "SDI Configuration Log")
        
        company = frappe.get_doc("Company", data["name"])
        frappe.log_error(f"Company recuperata: {company.name}", "SDI Configuration Log")
        
        configuration = prepare_configuration(company)
        frappe.log_error("Configurazione preparata", "SDI Configuration Log")
        frappe.log_error(f"Fiscal ID: {configuration.get('fiscal_id')}", "SDI Configuration Log")
        frappe.log_error(f"Numero di callbacks configurati: {len(configuration.get('callbacks', []))}", "SDI Configuration Log")
        
        url = get_service("SDI", "api_configurations")
        frappe.log_error(f"URL servizio: {url}", "SDI Configuration Log")

        headers = {
            "Authorization": company.custom_open_api_token,
            "Content-Type": "application/json",
        }
        
        # Non loggiamo gli headers completi per evitare di esporre token nei log
        frappe.log_error("Headers impostati correttamente", "SDI Configuration Log")
        frappe.log_error(f"Invio richiesta POST a {url}", "SDI Configuration Log")
        
        response = requests.post(url, headers=headers, json=configuration)
        
        frappe.log_error(f"Risposta ricevuta con status code: {response.status_code}", "SDI Configuration Log")
        # Limita il log del contenuto della risposta
        content_preview = str(response.content)[:100] + "..." if len(str(response.content)) > 100 else str(response.content)
        frappe.log_error(f"Preview risposta: {content_preview}", "SDI Configuration Log")

        # Verifica se la richiesta è andata a buon fine
        if response.status_code == 200:
            try:
                json_response = response.json()
                # Log limitato della risposta JSON
                frappe.log_error("Risposta JSON ricevuta correttamente", "SDI Configuration Log")
                return json_response["data"]
            except ValueError as e:
                error_msg = f"Errore nel parsing JSON della risposta: {str(e)}"
                frappe.log_error(f"{error_msg}\nContenuto risposta: {response.content}", "SDI Configuration Error")
                frappe.throw(error_msg)
            except KeyError as e:
                error_msg = f"Chiave 'data' non trovata nella risposta JSON: {str(e)}"
                # Limitiamo il log della risposta JSON per evitare troncamenti
                json_preview = str(response.json())[:100] + "..." if len(str(response.json())) > 100 else str(response.json())
                frappe.log_error(f"{error_msg}\nPreview risposta JSON: {json_preview}", "SDI Configuration Error")
                frappe.throw(error_msg)
        else:
            try:
                if response.content:
                    json_response = response.json()
                    message = json_response.get("message", f"Status code: {response.status_code}")
                else:
                    message = f"Status code: {response.status_code}"
            except ValueError:  # JSONDecodeError è una sottoclasse di ValueError
                message = f"Risposta non in formato JSON: {response.content}"
            
            error_msg = f"Errore nella richiesta: {message}"
            content_preview = str(response.content)[:100] + "..." if len(str(response.content)) > 100 else str(response.content)
            frappe.log_error(f"{error_msg}\nStatus Code: {response.status_code}\nPreview risposta: {content_preview}", "SDI Configuration Error")
            frappe.throw(error_msg)
    except Exception as e:
        error_details = f"Errore imprevisto in send_configuration: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_details, "SDI Configuration Critical Error")
        frappe.throw(f"Errore durante l'invio della configurazione: {str(e)}")


@frappe.whitelist()
def check_business_register(data):
    try:
        frappe.log_error(f"Inizializzazione check_business_register con dati: {data}", "SDI Check Business Log")
        
        data = prepare_data(data)
        frappe.log_error(f"Dati preparati: {data}", "SDI Check Business Log")
        
        company = frappe.get_doc("Company", data["name"])
        frappe.log_error(f"Company recuperata: {company.name}", "SDI Check Business Log")
        
        url = get_service("SDI")
        frappe.log_error(f"URL servizio: {url}", "SDI Check Business Log")
        
        headers = {
            "Authorization": company.custom_open_api_token,
            "Content-Type": "application/json",
        }
        
        frappe.log_error(f"Headers impostati: {headers}", "SDI Check Business Log")
        frappe.log_error(f"Invio richiesta GET a {url}", "SDI Check Business Log")
        
        response = requests.get(url, headers=headers, params=data)
        
        frappe.log_error(f"Risposta ricevuta con status code: {response.status_code}", "SDI Check Business Log")
        frappe.log_error(f"Contenuto risposta: {response.content}", "SDI Check Business Log")

        print(response.content)

        # Verifica se la richiesta è andata a buon fine
        if response.status_code == 200:
            try:
                json_response = response.json()
                frappe.log_error(f"Risposta JSON: {json_response}", "SDI Check Business Log")
                return f"Prova: {json_response['data']}"
            except ValueError as e:
                error_msg = f"Errore nel parsing JSON della risposta: {str(e)}"
                frappe.log_error(f"{error_msg}\nContenuto risposta: {response.content}", "SDI Check Business Error")
                return f"Errore: {error_msg}"
            except KeyError as e:
                error_msg = f"Chiave 'data' non trovata nella risposta JSON: {str(e)}"
                frappe.log_error(f"{error_msg}\nContenuto risposta JSON: {response.json()}", "SDI Check Business Error")
                return f"Errore: {error_msg}"
        else:
            try:
                if response.content:
                    json_response = response.json()
                    message = json_response.get("message", f"Status code: {response.status_code}")
                else:
                    message = f"Status code: {response.status_code}"
            except ValueError:  # JSONDecodeError è una sottoclasse di ValueError
                message = f"Risposta non in formato JSON: {response.content}"
            
            error_msg = f"Errore nella richiesta: {message}"
            print(response.content)
            frappe.log_error(f"{error_msg}\nStatus Code: {response.status_code}\nContenuto risposta: {response.content}", "SDI Check Business Error")
            return error_msg
    except Exception as e:
        error_details = f"Errore imprevisto in check_business_register: {str(e)}\n{frappe.get_traceback()}"
        frappe.log_error(error_details, "SDI Check Business Critical Error")
        return f"Errore durante la verifica del business register: {str(e)}"
