import frappe
import requests
import json
import openapi.api.aziende.search as search


def search_company(data):
    dataOk = json.loads(data)

    aziende = search.search_company(dataOk)

    return json.dumps(aziende, indent=4)


def get_advanced(data):
    dataOk = json.loads(data)

    azienda = search.get_advanced(dataOk)

    return json.dumps(azienda, indent=4)


def get_full(data):
    dataOk = json.loads(data)

    azienda = search.get_full(dataOk)

    return json.dumps(azienda, indent=4)


def get_code_meaning(data):
    dataOk = json.loads(data)

    azienda = search.get_code_meaning(dataOk)

    return json.dumps(azienda, indent=4)
