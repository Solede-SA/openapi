import frappe
import json
import openapi.tools.common_data as common_data
import requests


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

    queryFilter = "?dataEnrichment=name"

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


@frappe.whitelist(allow_guest=False)
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


@frappe.whitelist(allow_guest=True)
def get_full(data):
    print(data)
    vatCode_or_taxCode = data.get("vatCode_or_taxCode")
    company = get_company_doc()

    if not vatCode_or_taxCode:
        return "Inserire un codice fiscale, partita iva"

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
            return response.json()
        else:
            return response.json()
    except Exception as e:
        print(e)
        return e
