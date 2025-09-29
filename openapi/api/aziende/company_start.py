import frappe
import json
import openapi.tools.common_data as common_data
import requests
from frappe import _


def get_company_doc():
    return frappe.get_doc("Company", frappe.defaults.get_global_default("company"))


@frappe.whitelist()
def search_companies(filters):
    """
    Ricerca avanzata aziende con IT-search

    Parametri disponibili:
    - companyName: nome azienda (supporta wildcard *)
    - autocomplete: per autocompletamento
    - province: codice provincia
    - townCode: codice catastale/Belfiore
    - atecoCode: codice ATECO
    - cciaa: Camera di Commercio
    - reaCode: codice REA
    - minTurnover/maxTurnover: fatturato min/max
    - minEmployees/maxEmployees: dipendenti min/max
    - sdiCode: codice SDI
    - legalFormCode: forma giuridica
    - shareHolderTaxCode: CF socio
    - activityStatus: ATTIVA, CESSATA, REGISTRATA, INATTIVA, SOSPESA, IN_ISCRIZIONE
    - pec: indirizzo PEC
    - lat/long/radius: ricerca geografica
    - dataEnrichment: start, advanced, pec, address, shareholders, name
    - dryRun: 1 per simulazione (ritorna solo conteggio)
    - skip/limit: paginazione
    """
    if isinstance(filters, str):
        filters = json.loads(filters)

    url = common_data.get_service("Company Start", "IT-search")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    # Parametri predefiniti
    params = {
        "limit": filters.get("limit", 10),
        "dataEnrichment": filters.get("dataEnrichment", "advanced")
    }

    # Aggiungi solo i parametri forniti
    optional_params = [
        "companyName", "autocomplete", "vatCode", "taxCode", "province", "townCode", "atecoCode",
        "cciaa", "reaCode", "minTurnover", "maxTurnover", "minEmployees",
        "maxEmployees", "sdiCode", "legalFormCode", "shareHolderTaxCode",
        "activityStatus", "pec", "lat", "long", "radius", "dryRun", "skip",
        "creationTimestamp", "lastUpdateTimestamp"
    ]

    for param in optional_params:
        if param in filters and filters[param]:
            params[param] = filters[param]

    print(f"\n=== CHIAMATA API SEARCH ===")
    print(f"URL: {url}")
    print(f"PARAMS: {params}")
    print(f"HEADERS: {headers}")

    try:
        response = requests.get(url, headers=headers, params=params)
        print(f"STATUS CODE: {response.status_code}")
        print(f"RESPONSE HEADERS: {response.headers}")

        if response.status_code == 200:
            result = response.json()
            print(f"RESPONSE BODY: {json.dumps(result, indent=2)}")
            return result
        else:
            error_result = {"error": f"Errore API: {response.status_code}", "details": response.json()}
            print(f"ERROR RESPONSE: {json.dumps(error_result, indent=2)}")
            return error_result
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"error": str(e)}


@frappe.whitelist()
def quick_search(search_text, search_type="companyName"):
    """Ricerca rapida per nome o autocompletamento"""
    filters = {
        search_type: search_text,
        "limit": 10,
        "dataEnrichment": "advanced"
    }
    return search_companies(filters)


@frappe.whitelist()
def get_company_start_data(vat_or_tax_code):
    """Recupera dati base azienda con Company Start"""
    if not vat_or_tax_code:
        return {"error": "Inserire partita IVA o codice fiscale"}

    # Pulisci l'input rimuovendo spazi e caratteri speciali
    vat_or_tax_code = vat_or_tax_code.strip().replace(" ", "").replace("-", "")

    chiave_cache = f"openapi|company_start|{vat_or_tax_code}"
    risultato_cache = frappe.cache.get_value(chiave_cache)
    if risultato_cache is not None:
        return risultato_cache

    url = common_data.get_service("Company Start", f"IT-advanced/{vat_or_tax_code}")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    print(f"\n=== CHIAMATA API IT-ADVANCED ===")
    print(f"URL: {url}")
    print(f"VAT/TAX CODE: {vat_or_tax_code}")
    print(f"HEADERS: {headers}")

    try:
        response = requests.get(url, headers=headers)
        print(f"STATUS CODE: {response.status_code}")
        print(f"RESPONSE HEADERS: {response.headers}")

        if response.status_code == 200:
            response_data = response.json()
            print(f"IT-ADVANCED RESPONSE BODY: {json.dumps(response_data, indent=2)}")

            # IT-start restituisce SEMPRE un array in "data" quando success=true
            if response_data.get("success") and response_data.get("data"):
                if isinstance(response_data["data"], list) and len(response_data["data"]) > 0:
                    data = response_data["data"][0]
                    print(f"IT-ADVANCED: Array trovato in 'data', uso il primo elemento")
                    print(f"DATA ESTRATTI DA IT-ADVANCED: {json.dumps(data, indent=2)}")

                    # Verifica presenza sdiCode
                    if data.get("sdiCode"):
                        print(f"IT-ADVANCED: sdiCode trovato: {data['sdiCode']}")
                    else:
                        print(f"IT-ADVANCED: sdiCode NON trovato nei dati")

                    # Verifica presenza PEC
                    if data.get("pec"):
                        print(f"IT-ADVANCED: PEC trovata: {data['pec']}")
                    else:
                        print(f"IT-ADVANCED: PEC NON trovata nei dati")

                    frappe.cache.set_value(chiave_cache, data, expires_in_sec=3600)
                    return data
                else:
                    print(f"IT-ADVANCED: Nessun dato nell'array")
                    return {"error": "Nessun dato trovato per questa P.IVA/CF"}
            else:
                # Se success=false, restituisci l'errore
                return {"error": response_data.get("message", "Errore sconosciuto"), "details": response_data}
        else:
            response_json = response.json()

            # Gestione specifica per errore 406 (P.IVA non valida)
            if response.status_code == 406:
                error_message = response_json.get("message", "P.IVA/CF non valido")
                error_data = {
                    "error": f"Partita IVA non valida: {error_message}",
                    "details": response_json
                }
            else:
                error_message = response_json.get("message", f"Errore API: {response.status_code}")
                error_data = {
                    "error": error_message,
                    "details": response_json
                }

            print(f"ERROR RESPONSE: {json.dumps(error_data, indent=2)}")
            return error_data
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"error": str(e)}


@frappe.whitelist()
def get_company_full_data(vat_or_tax_code):
    """Recupera dati completi azienda"""
    if not vat_or_tax_code:
        return {"error": "Inserire partita IVA o codice fiscale"}

    # Pulisci l'input
    vat_or_tax_code = vat_or_tax_code.strip().replace(" ", "").replace("-", "")

    chiave_cache = f"openapi|company_full|{vat_or_tax_code}"
    risultato_cache = frappe.cache.get_value(chiave_cache)
    if risultato_cache is not None:
        return risultato_cache

    url = common_data.get_service("Company Start", f"IT-full/{vat_or_tax_code}")
    company = get_company_doc()

    if not company.custom_open_api_token:
        return {"error": "Token OpenAPI non configurato"}

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    print(f"\n=== CHIAMATA API COMPANY FULL ===")
    print(f"URL: {url}")
    print(f"HEADERS: {headers}")

    try:
        response = requests.get(url, headers=headers)
        print(f"STATUS CODE: {response.status_code}")
        print(f"RESPONSE HEADERS: {response.headers}")

        if response.status_code == 200:
            response_data = response.json()
            print(f"RESPONSE BODY: {json.dumps(response_data, indent=2)}")

            # IT-full restituisce i dati dentro un oggetto "data"
            if isinstance(response_data, dict) and "data" in response_data and response_data.get("success"):
                data = response_data["data"]
                # Normalizza i campi per compatibilità con IT-search/start
                if "companyDetails" in data:
                    data["companyName"] = data["companyDetails"].get("companyName", "")
                    data["vatCode"] = data["companyDetails"].get("vatCode", "")
                    data["taxCode"] = data["companyDetails"].get("taxCode", "")
                if "companyStatus" in data and data["companyStatus"].get("activityStatus"):
                    data["activityStatus"] = data["companyStatus"]["activityStatus"].get("code", "")
            else:
                data = response_data

            frappe.cache.set_value(chiave_cache, data, expires_in_sec=3600)
            return data
        else:
            error_data = {"error": f"Errore API: {response.status_code}", "details": response.json()}
            print(f"ERROR RESPONSE: {json.dumps(error_data, indent=2)}")
            return error_data
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"error": str(e)}


@frappe.whitelist()
def verify_existing_customer(customer_name):
    """Verifica e confronta dati di un cliente esistente con OpenAPI"""
    customer = frappe.get_doc("Customer", customer_name)

    if not customer.tax_id:
        return {"error": "Il cliente non ha partita IVA/codice fiscale"}

    openapi_data = get_company_start_data(customer.tax_id)

    if "error" in openapi_data:
        return openapi_data

    differences = []

    # Confronta ragione sociale - IT-start usa "companyName"
    openapi_name = openapi_data.get("companyName") or ""
    customer_name = customer.customer_name or ""
    if openapi_name != customer_name and openapi_name:
        differences.append({
            "field": "customer_name",
            "current": customer_name,
            "openapi": openapi_name,
            "label": "Ragione Sociale"
        })

    # Confronta partita IVA - IT-start usa "vatCode"
    openapi_vat = openapi_data.get("vatCode") or ""
    customer_vat = customer.tax_id or ""
    if openapi_vat != customer_vat and openapi_vat:
        differences.append({
            "field": "tax_id",
            "current": customer_vat,
            "openapi": openapi_vat,
            "label": "Partita IVA"
        })

    # Confronta codice fiscale - per le aziende è uguale alla partita IVA
    customer_fiscal = customer.fiscal_code or ""
    if openapi_vat != customer_fiscal and openapi_vat:
        differences.append({
            "field": "fiscal_code",
            "current": customer_fiscal,
            "openapi": openapi_vat,
            "label": "Codice Fiscale"
        })

    # Verifica stato azienda - IT-start usa "activityStatus"
    if openapi_data.get("activityStatus") == "CESSATA" and not customer.disabled:
        differences.append({
            "field": "disabled",
            "current": "Attivo",
            "openapi": "Cessata",
            "label": "Stato Azienda"
        })

    # Verifica codice SDI
    if hasattr(customer, 'custom_codice_univoco'):
        openapi_sdi = openapi_data.get("sdiCode") or ""
        customer_sdi = customer.custom_codice_univoco or ""
        if openapi_sdi != customer_sdi and openapi_sdi:
            differences.append({
                "field": "custom_codice_univoco",
                "current": customer_sdi,
                "openapi": openapi_sdi,
                "label": "Codice Univoco SDI"
            })

    # Verifica PEC
    if hasattr(customer, 'pec'):
        openapi_pec = openapi_data.get("pec") or ""
        customer_pec = customer.pec or ""
        if openapi_pec != customer_pec and openapi_pec:  # Solo se OpenAPI ha una PEC diversa
            differences.append({
                "field": "pec",
                "current": customer_pec,
                "openapi": openapi_pec,
                "label": "PEC"
            })

    # Verifica indirizzo e provincia
    if openapi_data.get("address"):
        # Recupera l'indirizzo principale del cliente
        primary_address = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": "Customer",
                "link_name": customer_name,
                "parenttype": "Address"
            },
            "parent"
        )

        if primary_address:
            address_doc = frappe.get_doc("Address", primary_address)

            # Estrai la provincia da OpenAPI
            openapi_province = ""
            if isinstance(openapi_data["address"], dict) and openapi_data["address"].get("registeredOffice"):
                openapi_province = openapi_data["address"]["registeredOffice"].get("province", "")
            else:
                openapi_province = openapi_data["address"].get("province", "")

            # Confronta provincia
            current_province = address_doc.state or ""
            if openapi_province and openapi_province != current_province:
                # Aggiungi nota speciale se la provincia non è 2 lettere
                note = ""
                if len(openapi_province) != 2:
                    note = " ⚠️ (Formato non standard - dovrebbe essere 2 lettere)"

                differences.append({
                    "field": "address_province",
                    "current": current_province,
                    "openapi": openapi_province + note,
                    "label": "Provincia (Indirizzo)",
                    "is_address_field": True
                })

    return {
        "openapi_data": openapi_data,
        "differences": differences,
        "has_differences": len(differences) > 0
    }


@frappe.whitelist()
def create_customer_from_openapi(vat_or_tax_code, use_full_data=False):
    """Prepara i dati per creare un nuovo cliente da OpenAPI"""
    if use_full_data:
        data = get_company_full_data(vat_or_tax_code)
    else:
        data = get_company_start_data(vat_or_tax_code)

    if "error" in data:
        return data

    # Gestisci i diversi formati di risposta (IT-search vs IT-start/full)
    vat_code = data.get("vatCode", data.get("vatNumber", data.get("taxCode", "")))
    customer_data = {
        "doctype": "Customer",
        "customer_name": data.get("companyName", data.get("name", "")),
        "tax_id": vat_code,
        "fiscal_code": vat_code,  # Per le aziende, fiscal_code è uguale a tax_id
        "customer_type": "Company",
        "disabled": 1 if data.get("activityStatus") == "CESSATA" or data.get("status") == "CESSATA" else 0
    }

    # Aggiungi codice SDI se presente
    if data.get("sdiCode"):
        customer_data["custom_codice_univoco"] = data["sdiCode"]
        print(f"SDI Code trovato: {data['sdiCode']}")
    else:
        print(f"SDI Code NON trovato nei dati")

    # Aggiungi PEC se presente
    if data.get("pec"):
        customer_data["pec"] = data["pec"]
        print(f"PEC trovata: {data['pec']}")
    else:
        print(f"PEC NON trovata nei dati")

    # Prepara dati indirizzo se disponibili
    address_data = None
    if data.get("address"):
        # Verifica se è formato IT-search (con registeredOffice) o IT-start/full
        if isinstance(data["address"], dict) and data["address"].get("registeredOffice"):
            addr = data["address"]["registeredOffice"]
            address_data = {
                "address_line1": addr.get("streetName", addr.get("street", "")),
                "city": addr.get("town", ""),
                "state": addr.get("province", ""),
                "pincode": addr.get("zipCode", ""),
                "country": "Italy",
                "address_type": "Billing",
                "is_primary_address": 1,
                "is_shipping_address": 0
            }
        else:
            # Formato IT-start/full
            address_data = {
                "address_line1": data["address"].get("street", ""),
                "city": data["address"].get("town", ""),
                "state": data["address"].get("province", ""),
                "pincode": data["address"].get("zip", ""),
                "country": "Italy",
                "address_type": "Billing",
                "is_primary_address": 1,
                "is_shipping_address": 0
            }

    print(f"CUSTOMER_DATA FINALE: {json.dumps(customer_data, indent=2)}")

    return {
        "customer_data": customer_data,
        "address_data": address_data,
        "source_data": data
    }


@frappe.whitelist()
def update_customer_from_openapi(customer_name, fields_to_update):
    """Aggiorna campi selezionati di un cliente esistente"""
    if isinstance(fields_to_update, str):
        fields_to_update = json.loads(fields_to_update)

    customer = frappe.get_doc("Customer", customer_name)
    address_updated = False

    for field in fields_to_update:
        # Gestisci campi speciali dell'indirizzo
        if field["field"] == "address_province":
            # Recupera l'indirizzo principale del cliente
            primary_address = frappe.db.get_value(
                "Dynamic Link",
                {
                    "link_doctype": "Customer",
                    "link_name": customer_name,
                    "parenttype": "Address"
                },
                "parent"
            )

            if primary_address:
                address_doc = frappe.get_doc("Address", primary_address)
                # Rimuovi eventuali note di warning dalla provincia
                new_province = field["openapi"].replace(" ⚠️ (Formato non standard - dovrebbe essere 2 lettere)", "")
                address_doc.state = new_province
                address_doc.save()
                address_updated = True

                # Log warning se provincia non è 2 lettere
                if len(new_province) != 2:
                    frappe.log_error(
                        f"Provincia aggiornata con formato non standard: '{new_province}' per cliente {customer_name}",
                        "OpenAPI Province Update Warning"
                    )

        # Gestisci campi standard del cliente
        elif hasattr(customer, field["field"]):
            if field["field"] == "disabled":
                customer.disabled = 1 if field["openapi"] == "Cessata" else 0
            else:
                setattr(customer, field["field"], field["openapi"])

    customer.save()

    message = f"Cliente {customer_name} aggiornato con successo"
    if address_updated:
        message += " (incluso indirizzo)"

    return {"success": True, "message": message}