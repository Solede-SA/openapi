import frappe
import json
import openapi.tools.common_data as common_data
import requests


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
        "dataEnrichment": filters.get("dataEnrichment", "advanced"),
    }

    # Aggiungi solo i parametri forniti
    optional_params = [
        "companyName",
        "autocomplete",
        "vatCode",
        "taxCode",
        "province",
        "townCode",
        "atecoCode",
        "cciaa",
        "reaCode",
        "minTurnover",
        "maxTurnover",
        "minEmployees",
        "maxEmployees",
        "sdiCode",
        "legalFormCode",
        "shareHolderTaxCode",
        "activityStatus",
        "pec",
        "lat",
        "long",
        "radius",
        "dryRun",
        "skip",
        "creationTimestamp",
        "lastUpdateTimestamp",
    ]

    for param in optional_params:
        if param in filters and filters[param]:
            params[param] = filters[param]

    print("\n=== CHIAMATA API SEARCH ===")
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
            error_result = {
                "error": f"Errore API: {response.status_code}",
                "details": response.json(),
            }
            print(f"ERROR RESPONSE: {json.dumps(error_result, indent=2)}")
            return error_result
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"error": str(e)}


@frappe.whitelist()
def quick_search(search_text, search_type="companyName"):
    """Ricerca rapida per nome o autocompletamento"""
    filters = {search_type: search_text, "limit": 10, "dataEnrichment": "advanced"}
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

    print("\n=== CHIAMATA API IT-ADVANCED ===")
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
                if (
                    isinstance(response_data["data"], list)
                    and len(response_data["data"]) > 0
                ):
                    data = response_data["data"][0]
                    print("IT-ADVANCED: Array trovato in 'data', uso il primo elemento")
                    print(f"DATA ESTRATTI DA IT-ADVANCED: {json.dumps(data, indent=2)}")

                    # Verifica presenza sdiCode
                    if data.get("sdiCode"):
                        print(f"IT-ADVANCED: sdiCode trovato: {data['sdiCode']}")
                    else:
                        print("IT-ADVANCED: sdiCode NON trovato nei dati")

                    # Verifica presenza PEC
                    if data.get("pec"):
                        print(f"IT-ADVANCED: PEC trovata: {data['pec']}")
                    else:
                        print("IT-ADVANCED: PEC NON trovata nei dati")

                    frappe.cache.set_value(chiave_cache, data, expires_in_sec=3600)
                    return data
                else:
                    print("IT-ADVANCED: Nessun dato nell'array")
                    return {"error": "Nessun dato trovato per questa P.IVA/CF"}
            else:
                # Se success=false, restituisci l'errore
                return {
                    "error": response_data.get("message", "Errore sconosciuto"),
                    "details": response_data,
                }
        else:
            response_json = response.json()

            # Gestione specifica per errore 406 (P.IVA non valida)
            if response.status_code == 406:
                error_message = response_json.get("message", "P.IVA/CF non valido")
                error_data = {
                    "error": f"Partita IVA non valida: {error_message}",
                    "details": response_json,
                }
            else:
                error_message = response_json.get(
                    "message", f"Errore API: {response.status_code}"
                )
                error_data = {"error": error_message, "details": response_json}

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

    print("\n=== CHIAMATA API COMPANY FULL ===")
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
            if (
                isinstance(response_data, dict)
                and "data" in response_data
                and response_data.get("success")
            ):
                data = response_data["data"]
                # Normalizza i campi per compatibilità con IT-search/start
                if "companyDetails" in data:
                    data["companyName"] = data["companyDetails"].get("companyName", "")
                    data["vatCode"] = data["companyDetails"].get("vatCode", "")
                    data["taxCode"] = data["companyDetails"].get("taxCode", "")
                if "companyStatus" in data and data["companyStatus"].get(
                    "activityStatus"
                ):
                    data["activityStatus"] = data["companyStatus"][
                        "activityStatus"
                    ].get("code", "")
            else:
                data = response_data

            frappe.cache.set_value(chiave_cache, data, expires_in_sec=3600)
            return data
        else:
            error_data = {
                "error": f"Errore API: {response.status_code}",
                "details": response.json(),
            }
            print(f"ERROR RESPONSE: {json.dumps(error_data, indent=2)}")
            return error_data
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")
        return {"error": str(e)}


@frappe.whitelist()
def verify_existing_party(party_type, party_name):
    """Verifica e confronta dati di un cliente/fornitore esistente con OpenAPI

    Args:
        party_type: 'Customer' o 'Supplier'
        party_name: Nome del documento
    """
    party = frappe.get_doc(party_type, party_name)

    if not party.tax_id:
        return {"error": f"Il {party_type.lower()} non ha partita IVA/codice fiscale"}

    openapi_data = get_company_start_data(party.tax_id)

    if "error" in openapi_data:
        return openapi_data

    differences = []

    # Campo nome dipende dal party_type
    name_field = "customer_name" if party_type == "Customer" else "supplier_name"
    party_name_value = getattr(party, name_field, "") or ""

    # Confronta ragione sociale - IT-start usa "companyName"
    openapi_name = openapi_data.get("companyName") or ""
    if openapi_name != party_name_value and openapi_name:
        differences.append(
            {
                "field": name_field,
                "current": party_name_value,
                "openapi": openapi_name,
                "label": "Ragione Sociale",
            }
        )

    # Confronta partita IVA - IT-start usa "vatCode"
    openapi_vat = openapi_data.get("vatCode") or ""
    party_vat = party.tax_id or ""
    if openapi_vat != party_vat and openapi_vat:
        differences.append(
            {
                "field": "tax_id",
                "current": party_vat,
                "openapi": openapi_vat,
                "label": "Partita IVA",
            }
        )

    # Confronta codice fiscale - per le aziende è uguale alla partita IVA
    party_fiscal = getattr(party, "fiscal_code", "") or ""
    if openapi_vat != party_fiscal and openapi_vat:
        differences.append(
            {
                "field": "fiscal_code",
                "current": party_fiscal,
                "openapi": openapi_vat,
                "label": "Codice Fiscale",
            }
        )

    # Verifica stato azienda - IT-start usa "activityStatus"
    if openapi_data.get("activityStatus") == "CESSATA" and not party.disabled:
        differences.append(
            {
                "field": "disabled",
                "current": "Attivo",
                "openapi": "Cessata",
                "label": "Stato Azienda",
            }
        )

    # Verifica codice SDI
    if hasattr(party, "custom_codice_univoco"):
        openapi_sdi = openapi_data.get("sdiCode") or ""
        party_sdi = party.custom_codice_univoco or ""
        if openapi_sdi != party_sdi and openapi_sdi:
            differences.append(
                {
                    "field": "custom_codice_univoco",
                    "current": party_sdi,
                    "openapi": openapi_sdi,
                    "label": "Codice Univoco SDI",
                }
            )

    # Verifica PEC
    if hasattr(party, "pec"):
        openapi_pec = openapi_data.get("pec") or ""
        party_pec = party.pec or ""
        if (
            openapi_pec != party_pec and openapi_pec
        ):  # Solo se OpenAPI ha una PEC diversa
            differences.append(
                {
                    "field": "pec",
                    "current": party_pec,
                    "openapi": openapi_pec,
                    "label": "PEC",
                }
            )

    # Verifica indirizzo e provincia
    if openapi_data.get("address"):
        # Troviamo l'indirizzo principale tramite Dynamic Link
        primary_address = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": party_type,
                "link_name": party.name,
                "parenttype": "Address",
            },
            "parent",
        )

        print(f"DEBUG: Looking for address linked to {party_type} ID: {party.name}")
        print(f"DEBUG: Primary address found: {primary_address}")

        if primary_address:
            address_doc = frappe.get_doc("Address", primary_address)
            print(f"DEBUG: Current province in address: '{address_doc.state}'")

            # Estrai la provincia da OpenAPI
            openapi_province = ""
            if isinstance(openapi_data["address"], dict) and openapi_data[
                "address"
            ].get("registeredOffice"):
                openapi_province = openapi_data["address"]["registeredOffice"].get(
                    "province", ""
                )
            else:
                openapi_province = openapi_data["address"].get("province", "")

            print(f"DEBUG: OpenAPI province: '{openapi_province}'")

            # Confronta provincia
            current_province = address_doc.state or ""

            # Verifica se c'è una differenza O se il formato corrente non è standard
            if openapi_province:
                should_update = False
                current_note = ""
                openapi_note = ""

                # Check se provincia corrente non è 2 lettere
                if current_province and len(current_province) != 2:
                    current_note = " ⚠️ (Formato non standard)"
                    should_update = (
                        True  # Sempre suggerire aggiornamento se formato non standard
                    )
                    print(
                        f"DEBUG: Current province is not 2 letters: '{current_province}'"
                    )

                # Check se provincia OpenAPI non è 2 lettere
                if len(openapi_province) != 2:
                    openapi_note = (
                        " ⚠️ (Formato non standard - dovrebbe essere 2 lettere)"
                    )
                    print(
                        f"DEBUG: OpenAPI province is not 2 letters: '{openapi_province}'"
                    )

                # Check se sono diversi
                if openapi_province != current_province:
                    should_update = True
                    print(
                        f"DEBUG: Provinces are different: '{current_province}' != '{openapi_province}'"
                    )

                if should_update:
                    print("DEBUG: Adding province difference to list")
                    differences.append(
                        {
                            "field": "address_province",
                            "current": current_province + current_note,
                            "openapi": openapi_province + openapi_note,
                            "label": "Provincia (Indirizzo)",
                            "is_address_field": True,
                        }
                    )

    return {
        "openapi_data": openapi_data,
        "differences": differences,
        "has_differences": len(differences) > 0,
    }


@frappe.whitelist()
def create_party_from_openapi(party_type, vat_or_tax_code, use_full_data=False):
    """Prepara i dati per creare un nuovo cliente/fornitore da OpenAPI

    Args:
        party_type: 'Customer' o 'Supplier'
        vat_or_tax_code: P.IVA o Codice Fiscale
        use_full_data: Se True usa IT-full invece di IT-start
    """
    if use_full_data:
        data = get_company_full_data(vat_or_tax_code)
    else:
        data = get_company_start_data(vat_or_tax_code)

    if "error" in data:
        return data

    # Gestisci i diversi formati di risposta (IT-search vs IT-start/full)
    vat_code = data.get("vatCode", data.get("vatNumber", data.get("taxCode", "")))

    # Costruisci dati base in base al party_type
    if party_type == "Customer":
        party_data = {
            "doctype": "Customer",
            "customer_name": data.get("companyName", data.get("name", "")),
            "tax_id": vat_code,
            "fiscal_code": vat_code,
            "customer_type": "Company",
            "disabled": 1
            if data.get("activityStatus") == "CESSATA" or data.get("status") == "CESSATA"
            else 0,
        }
    else:  # Supplier
        party_data = {
            "doctype": "Supplier",
            "supplier_name": data.get("companyName", data.get("name", "")),
            "tax_id": vat_code,
            "fiscal_code": vat_code,
            "supplier_type": "Company",
            "disabled": 1
            if data.get("activityStatus") == "CESSATA" or data.get("status") == "CESSATA"
            else 0,
        }

    # Aggiungi codice SDI se presente
    if data.get("sdiCode"):
        party_data["custom_codice_univoco"] = data["sdiCode"]
        print(f"SDI Code trovato: {data['sdiCode']}")
    else:
        print("SDI Code NON trovato nei dati")

    # Aggiungi PEC se presente
    if data.get("pec"):
        party_data["pec"] = data["pec"]
        print(f"PEC trovata: {data['pec']}")
    else:
        print("PEC NON trovata nei dati")

    # Prepara dati indirizzo se disponibili
    address_data = None
    if data.get("address"):
        # Verifica se è formato IT-search (con registeredOffice) o IT-start/full
        if isinstance(data["address"], dict) and data["address"].get(
            "registeredOffice"
        ):
            addr = data["address"]["registeredOffice"]
            address_data = {
                "address_line1": addr.get("streetName", addr.get("street", "")),
                "city": addr.get("town", ""),
                "state": addr.get("province", ""),
                "pincode": addr.get("zipCode", ""),
                "country": "Italy",
                "address_type": "Billing",
                "is_primary_address": 1,
                "is_shipping_address": 0,
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
                "is_shipping_address": 0,
            }

    print(f"PARTY_DATA FINALE: {json.dumps(party_data, indent=2)}")

    return {
        "party_data": party_data,
        "address_data": address_data,
        "source_data": data,
    }


@frappe.whitelist()
def create_customer_from_openapi(vat_or_tax_code, use_full_data=False):
    """Wrapper per retrocompatibilità - usa create_party_from_openapi"""
    result = create_party_from_openapi("Customer", vat_or_tax_code, use_full_data)
    # Rinomina party_data in customer_data per retrocompatibilità
    if "party_data" in result:
        result["customer_data"] = result.pop("party_data")
    return result


@frappe.whitelist()
def update_party_from_openapi(party_type, party_name, fields_to_update):
    """Aggiorna campi selezionati di un cliente/fornitore esistente

    Args:
        party_type: 'Customer' o 'Supplier'
        party_name: Nome del documento
        fields_to_update: Lista di campi da aggiornare
    """
    if isinstance(fields_to_update, str):
        fields_to_update = json.loads(fields_to_update)

    party = frappe.get_doc(party_type, party_name)
    address_updated = False

    for field in fields_to_update:
        # Gestisci campi speciali dell'indirizzo
        if field["field"] == "address_province":
            # Recupera l'indirizzo principale
            primary_address = frappe.db.get_value(
                "Dynamic Link",
                {
                    "link_doctype": party_type,
                    "link_name": party_name,
                    "parenttype": "Address",
                },
                "parent",
            )

            if primary_address:
                address_doc = frappe.get_doc("Address", primary_address)
                # Rimuovi eventuali note di warning dalla provincia
                new_province = field["openapi"]
                new_province = new_province.replace(
                    " ⚠️ (Formato non standard - dovrebbe essere 2 lettere)", ""
                )
                new_province = new_province.replace(" ⚠️ (Formato non standard)", "")

                address_doc.state = new_province
                address_doc.save()
                address_updated = True

                if len(new_province) != 2:
                    frappe.log_error(
                        f"Provincia aggiornata con formato non standard: '{new_province}' per {party_type.lower()} {party_name}",
                        "OpenAPI Province Update Warning",
                    )

        # Gestisci campi standard
        elif hasattr(party, field["field"]):
            if field["field"] == "disabled":
                party.disabled = 1 if field["openapi"] == "Cessata" else 0
            else:
                setattr(party, field["field"], field["openapi"])

    party.save()

    party_label = "Cliente" if party_type == "Customer" else "Fornitore"
    message = f"{party_label} {party_name} aggiornato con successo"
    if address_updated:
        message += " (incluso indirizzo)"

    return {"success": True, "message": message}


@frappe.whitelist()
def verify_existing_customer(customer_name):
    """Wrapper per retrocompatibilità - usa verify_existing_party"""
    return verify_existing_party("Customer", customer_name)


@frappe.whitelist()
def update_customer_from_openapi(customer_name, fields_to_update):
    """Wrapper per retrocompatibilità - usa update_party_from_openapi"""
    return update_party_from_openapi("Customer", customer_name, fields_to_update)
