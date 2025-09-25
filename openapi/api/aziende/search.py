import frappe
import json
import openapi.tools.common_data as common_data
import requests
from frappe.utils.caching import redis_cache


def get_company_doc():
    # recupero la company dell'utente che chiama la funzione
    return frappe.get_doc("Company", frappe.defaults.get_global_default("company"))


@frappe.whitelist()
def search_company(data):
    companyName = data.get("companyName")
    limit = data.get("limit", 10)
    url = common_data.get_service("Company", "IT-search")
    company = get_company_doc()

    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    queryFilter = "?dataEnrichment=name,pec"

    if companyName:
        queryFilter += f"&companyName={companyName}"

    if limit:
        queryFilter += f"&limit={limit}"

    url += queryFilter

    print(url)

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            return response.json()
    except Exception as e:
        print(e)
        return e


@frappe.whitelist()
def get_advanced(data):
    vatCode_taxCode_or_id = data.get("vatCode_taxCode_or_id")
    company = get_company_doc()

    if not vatCode_taxCode_or_id:
        return "Inserire un codice fiscale, partita iva o id"

    queryFilter = f"/{vatCode_taxCode_or_id}"

    url = common_data.get_service("Company", "IT-advanced")
    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    url += queryFilter

    print(url)

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            return response.json()
    except Exception as e:
        print(e)
        return e


@frappe.whitelist()
def get_full(data):
    vatCode_or_taxCode = data.get("vatCode_or_taxCode")
    company = get_company_doc()

    if not vatCode_or_taxCode:
        return "Inserire un codice fiscale, partita iva"

    chiave_cache = f"openapi|get_full|{vatCode_or_taxCode}"
    risultato_cache = frappe.cache.get_value(chiave_cache)
    if risultato_cache is not None:
        print("Risultato preso dalla cache")
        return risultato_cache

    queryFilter = f"/{vatCode_or_taxCode}"

    url = common_data.get_service("Company", "IT-full")
    headers = {
        "Authorization": company.custom_open_api_token,
        "Content-Type": "application/json",
    }

    url += queryFilter

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            frappe.cache.set_value(chiave_cache, response.json(), expires_in_sec=3600)
            return response.json()
        else:
            return response.json()
    except Exception as e:
        print(e)
        return e


import requests
from bs4 import BeautifulSoup


@frappe.whitelist()
def get_code_meaning(data):
    code = data.get("code")
    url = "https://docs.openapi.it/company-legend.html"

    # Effettua la richiesta alla pagina
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(
            f"Impossibile accedere alla pagina. Status code: {response.status_code}"
        )

    # Parsing dell'HTML con BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")

    # Cerchiamo tutte le tabelle della pagina
    tables = soup.find_all("table")

    # Iteriamo su tutte le tabelle
    for table in tables:
        rows = table.find_all("tr")
        # Iteriamo su tutte le righe
        for row in rows:
            # Cerchiamo l'elemento <th> con attributo id (che dovrebbe contenere il codice)
            th = row.find("th", id=True)
            if th is not None:
                th_text = th.get_text(strip=True)
                if th_text == code:
                    # Abbiamo trovato la riga giusta, ora cerchiamo i td
                    cells = row.find_all("td")
                    # Dato che la struttura è <th>, <td>, <td>, <td>
                    # Il significato è nella seconda <td>, quindi cells[1]
                    if len(cells) >= 2:
                        meaning = cells[1].get_text(strip=True)
                        return meaning

    # Se non troviamo il codice
    return f"Significato non trovato per il codice {code}"
