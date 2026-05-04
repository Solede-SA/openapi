"""Wrapper alto livello docuengine.openapi.com — un'API per servizio.

Ogni funzione ritorna un dict normalizzato:
{
  "request_id": str,
  "raw": dict (response data finale),
  "attachments": [{"bytes": b"…", "filename": str, "meta": {...}}],
  "people": [...] | None,        # solo per esponenti/soci
}

Il consumer (es. garemed) gestisce billing, save su DocType, idempotenza.
"""

from openapi.api.docuengine import client


def _attach_all(data: dict, token: str | None) -> list[dict]:
	out = []
	for att in client.extract_attachments(data):
		content, filename = client.download_attachment(att, token=token)
		out.append({
			"bytes": content,
			"filename": filename,
			"meta": {k: v for k, v in att.items() if k not in ("data", "content")},
		})
	return out


def visura_camerale_ordinaria(tax_code: str, token: str | None = None) -> dict:
	"""Visura camerale ordinaria per società di capitale."""
	data = client.run_service(
		"visura-camerale-ordinaria-societa-di-capitale",
		{"taxCode": tax_code},
		token=token,
	)
	return {
		"request_id": data.get("id"),
		"raw": data,
		"attachments": _attach_all(data, token),
	}


def durc_online(tax_code: str, token: str | None = None) -> dict:
	data = client.run_service("durc-online", {"taxCode": tax_code}, token=token)
	return {
		"request_id": data.get("id"),
		"raw": data,
		"attachments": _attach_all(data, token),
	}


def fascicolo_societa_di_capitali(tax_code: str, token: str | None = None) -> dict:
	data = client.run_service(
		"fascicolo-societa-di-capitali",
		{"taxCode": tax_code},
		token=token,
	)
	return {
		"request_id": data.get("id"),
		"raw": data,
		"attachments": _attach_all(data, token),
	}


def bilancio_xbrl(tax_code: str, year: int, token: str | None = None) -> dict:
	data = client.run_service(
		"bilancio-xbrl",
		{"taxCode": tax_code, "year": year},
		token=token,
	)
	return {
		"request_id": data.get("id"),
		"raw": data,
		"attachments": _attach_all(data, token),
		"year": year,
	}


def esponenti_attivi_azienda(tax_code: str, token: str | None = None) -> dict:
	data = client.run_service(
		"esponenti-attivi-azienda",
		{"taxCode": tax_code},
		token=token,
	)
	people = data.get("people") or data.get("data") or []
	if isinstance(people, dict):
		people = people.get("items") or people.get("list") or []
	return {
		"request_id": data.get("id"),
		"raw": data,
		"people": people,
	}


def soci_attivi_azienda(tax_code: str, token: str | None = None) -> dict:
	data = client.run_service(
		"soci-attivi-azienda",
		{"taxCode": tax_code},
		token=token,
	)
	people = data.get("people") or data.get("shareholders") or data.get("data") or []
	if isinstance(people, dict):
		people = people.get("items") or people.get("list") or []
	return {
		"request_id": data.get("id"),
		"raw": data,
		"people": people,
	}


def eventi_negativi_azienda(tax_code: str, token: str | None = None) -> dict:
	data = client.run_service(
		"eventi-negativi-azienda",
		{"taxCode": tax_code},
		token=token,
	)
	return {
		"request_id": data.get("id"),
		"raw": data,
		"attachments": _attach_all(data, token),
	}
