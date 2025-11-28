# OpenAPI

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Frappe](https://img.shields.io/badge/Frappe-v15+-blue.svg)](https://frappeframework.com)
[![ERPNext](https://img.shields.io/badge/ERPNext-v15+-green.svg)](https://erpnext.com)

App Frappe/ERPNext per integrazione con servizi **OpenAPI.it** per fatturazione elettronica italiana e Sistema di Interscambio (SDI).

## 💡 Caratteristiche

- ✅ Integrazione completa con API OpenAPI.it
- ✅ Provider SDI per invio automatico fatture al Sistema di Interscambio
- ✅ Webhook per ricezione notifiche SDI in tempo reale
- ✅ Ricerca e validazione aziende tramite P.IVA/Codice Fiscale
- ✅ Auto-popolamento dati anagrafici (denominazione, PEC, sede legale)
- ✅ **Credit Scoring Advanced** - Verifica creditizia clienti azienda con rating e limite credito
- ✅ **Negatività Persona** - Verifica protesti, pregiudizievoli e procedure per persone fisiche
- ✅ Integrazione OpenAPI per **Customer e Supplier** con funzioni DRY
- ✅ Import automatico fatture fornitori via webhook
- ✅ Tracking completo stato transazioni SDI
- ✅ Configurazione multi-company con token separati

## 📦 Installazione

```bash
# Ottieni l'app da GitHub
bench get-app https://github.com/Solede-SA/openapi.git

# Installa nel sito
bench --site [nome-sito] install-app openapi

# Applica modifiche
bench --site [nome-sito] migrate
```

**Requisiti**: Frappe v15+, ERPNext v15+, Python 3.10+, Account OpenAPI.it

## 🔧 Configurazione

### 1. Account OpenAPI.it

Registrati su [OpenAPI.it](https://www.openapi.it) e ottieni:
- **API Token**: Token autenticazione per chiamate API
- **Webhook URL**: URL per ricezione notifiche (configurato automaticamente)

### 2. Setup Company

Vai in **Company** → Seleziona la tua azienda e compila:

- **OpenAPI Token**: Incolla il token API di OpenAPI.it
- **OpenAPI Webhook URL**: Auto-generato (es. `https://tuosito.com/api/method/openapi.api.sdi.callback.handle_webhook`)

### 3. Configurazione OpenAPI Services

Vai in **OpenAPI Services** e crea i seguenti record:

| Nome | URL |
|------|-----|
| `Company Start` | `https://business.openapi.com` |
| `Company` | `https://business.openapi.com` |
| `Credit Scoring Advanced` | `https://risk.openapi.com` |
| `Negativita Persona` | `https://risk.openapi.com` |

Questi servizi sono necessari per le diverse funzionalità:
- **Company Start / Company**: Ricerca aziende per P.IVA/CF e ragione sociale
- **Credit Scoring Advanced**: Verifica creditizia clienti azienda (richiede abbonamento specifico)
- **Negativita Persona**: Verifica protesti, pregiudizievoli e procedure concorsuali per persone fisiche

## 🚀 Utilizzo

### Integrazione con Italian Invoice

Questa app funziona come **Provider SDI** per l'app [italian_invoice](https://github.com/Solede-SA/italian_invoice):

1. Installa sia `openapi` che `italian_invoice`
2. In Company, imposta **Provider SDI** = "OpenAPI"
3. Le fatture vengono inviate automaticamente al SDI tramite OpenAPI.it

### Credit Scoring (Verifica Creditizia)

Per clienti di tipo **Company** con P.IVA, è disponibile la verifica creditizia:

1. Apri il form Customer
2. Clicca **OpenAPI > Verifica Creditizia**
3. Visualizza: Rating (A1-C3), Risk Score, Limite Credito Operativo
4. Clicca "Salva nel Cliente" per memorizzare i dati

```python
# Via API
result = frappe.call("openapi.api.aziende.credit_scoring.get_credit_score",
                     vat_or_tax_code="12345678901")

# Ritorna:
{
    "rating": "A2",
    "risk_score": "Verde",
    "risk_score_description": "Rischio basso",
    "operational_credit_limit": 50000.00,
    "risk_severity": 150
}
```

**Nota**: Richiede abbonamento Credit Scoring Advanced su OpenAPI.it

### Verifica Negatività (Persone Fisiche)

Per clienti di tipo **Individual** con codice fiscale, è disponibile la verifica negatività:

1. Apri il form Customer (di tipo Individual)
2. Clicca **OpenAPI > Verifica Negatività**
3. La richiesta viene inviata (API asincrona)
4. Usa **Controlla Stato Negatività** per verificare il completamento
5. Visualizza: Protesti, Pregiudizievoli, Procedure Concorsuali

```python
# Via API
result = frappe.call("openapi.api.aziende.negativita_persona.request_negativita_check",
                     fiscal_code="RSSMRA80A01H501U",
                     customer_name="Mario Rossi")

# Ritorna:
{
    "success": True,
    "request_id": "abc123",
    "status": "PENDING",
    "message": "Richiesta inviata..."
}

# Controlla stato
result = frappe.call("openapi.api.aziende.negativita_persona.check_request_status",
                     request_id="abc123",
                     customer_name="Mario Rossi")
```

**Nota**: Richiede abbonamento Negatività Persona su OpenAPI.it. L'API è asincrona e supporta callback webhook.

### Ricerca Aziende

```python
# Via API
import frappe

# Cerca per P.IVA
result = frappe.call("openapi.api.aziende.search.search_by_vat",
                     vat_number="12345678901")

# Cerca per Codice Fiscale
result = frappe.call("openapi.api.aziende.search.search_by_fiscal_code",
                     fiscal_code="RSSMRA80A01H501U")
```

Ritorna dati completi:
```python
{
    "denominazione": "ACME SRL",
    "partita_iva": "12345678901",
    "codice_fiscale": "12345678901",
    "pec": "acme@pec.it",
    "codice_sdi": "ABCDEFG",
    "indirizzo": {
        "via": "Via Roma 1",
        "cap": "20100",
        "citta": "Milano",
        "provincia": "MI"
    }
}
```

### Invio Fatture al SDI

Le fatture create in ERPNext vengono automaticamente inviate al SDI quando:

1. Hai configurato Provider SDI = "OpenAPI" in Company
2. Fai submit della Sales Invoice
3. Clicchi "Genera e-Invoice"

Il sistema:
- Genera XML FatturaPA
- Invia tramite OpenAPI.it al SDI
- Crea Transazione SDI per tracking
- Riceve notifiche via webhook (RC, NS, MC, EC)

### Webhook Notifiche SDI

Le notifiche SDI vengono ricevute automaticamente:

- **RC** (Ricevuta Consegna): Fattura consegnata al destinatario
- **NS** (Notifica Scarto): Fattura scartata dal SDI
- **MC** (Mancata Consegna): Destinatario non raggiungibile
- **EC** (Esito Committente): Accettazione/Rifiuto da destinatario

Ogni notifica aggiorna automaticamente lo stato in Transazione SDI.

### Import Fatture Passive

Quando ricevi una fattura fornitore:

1. OpenAPI.it invia notifica via webhook
2. Sistema scarica automaticamente XML fattura
3. Crea documento "Fattura Fornitori SDI"
4. Parsing automatico dati (fornitore, importi, righe)
5. Matching con Purchase Orders aperti
6. Creazione Purchase Invoice con un click

## 📊 DocTypes

### OpenAPI Services

Configurazione servizi OpenAPI.it:
- **API Token**: Token autenticazione
- **Environment**: Produzione/Test
- **Company**: Company associata
- **Webhook Secret**: Per validazione webhook

### OpenAPI Webhook

Log webhook ricevuti:
- **Webhook Type**: Tipo notifica (RC, NS, MC, EC)
- **Payload**: JSON completo ricevuto
- **Status**: Processed/Failed
- **Error Message**: Se processing fallito
- **Transaction ID**: Link a Transazione SDI

### Configurazione Fattura SDI

Settings fatturazione elettronica per company:
- **Default Tipo Documento**: TD01, TD04, etc.
- **Regime Fiscale**: RF01, RF02, etc.
- **Auto-send**: Invio automatico dopo submit

## 🔌 API Reference

### Ricerca Aziende

#### `openapi.api.aziende.search.search_by_vat`

```python
frappe.call("openapi.api.aziende.search.search_by_vat",
           vat_number="12345678901")
```

#### `openapi.api.aziende.search.search_by_fiscal_code`

```python
frappe.call("openapi.api.aziende.search.search_by_fiscal_code",
           fiscal_code="RSSMRA80A01H501U")
```

### Fatturazione SDI

#### `openapi.api.sdi.fatture.send_invoice`

```python
frappe.call("openapi.api.sdi.fatture.send_invoice",
           invoice_name="SINV-00001",
           xml_content=xml_string)
```

#### `openapi.api.sdi.fatture.get_invoice_status`

```python
frappe.call("openapi.api.sdi.fatture.get_invoice_status",
           uuid="uuid-fattura")
```

### Webhook Handler

#### `openapi.api.sdi.callback.handle_webhook`

Endpoint automatico per ricezione notifiche SDI:
```
POST /api/method/openapi.api.sdi.callback.handle_webhook
Headers:
  X-Webhook-Signature: <signature>
Body: JSON notifica SDI
```

## 🛠️ Architettura

```
openapi/
├── openapi/
│   ├── api/
│   │   ├── sdi/              # Integrazione SDI
│   │   │   ├── fatture.py    # Invio/download fatture
│   │   │   ├── callback.py   # Webhook handler
│   │   │   └── configurazione.py
│   │   ├── aziende/          # Ricerca aziende
│   │   │   ├── search.py     # P.IVA/CF lookup
│   │   │   ├── company_start.py  # Dati anagrafici azienda
│   │   │   ├── credit_scoring.py # Credit Scoring Advanced
│   │   │   └── negativita_persona.py # Negatività persone fisiche
│   │   └── eInvoice/         # Import fatture passive
│   │       └── purchase_invoice.py
│   │
│   ├── doctype/              # Custom DocTypes
│   │   ├── openapi_services/
│   │   ├── openapi_webhook/
│   │   └── configurazione_fattura_sdi/
│   │
│   ├── tools/                # Utilities
│   │   ├── openapi/          # Client OpenAPI.it
│   │   └── common_data.py
│   │
│   └── public/js/            # Client-side scripts
│       ├── openapi_party_utils.js  # Funzioni comuni Customer/Supplier
│       ├── custom_company.js
│       ├── custom_customer.js      # Ricerca azienda + Credit Scoring
│       ├── custom_supplier.js      # Ricerca azienda per Supplier
│       ├── custom_sales_invoice.js
│       └── custom_purchase_invoice.js
│
└── README.md
```

## 🐛 Troubleshooting

### Errori Comuni

**"API Token non configurato"**
- Verifica che hai creato OpenAPI Services
- Controlla che API Token sia compilato
- Verifica che Company abbia `custom_open_api_token`

**"Webhook non ricevuti"**
- Verifica URL webhook pubblicamente accessibile
- Controlla firewall/SSL certificate
- Test con `curl -X POST [webhook-url]`

**"Fattura non inviata al SDI"**
- Controlla Provider SDI = "OpenAPI" in Company
- Verifica API Token valido
- Controlla log: `logs/[sito]/error.log`

### Debug Mode

```bash
# Abilita developer mode
bench --site [sito] set-config developer_mode 1
bench --site [sito] clear-cache
bench restart

# Test manuale API
bench --site [sito] console
>>> import openapi.api.aziende.search as search
>>> search.search_by_vat("12345678901")
```

## 🤝 Contribuire

Contribuzioni benvenute! Leggi [CONTRIBUTING.md](CONTRIBUTING.md) per:

- Setup ambiente di sviluppo
- Convenzioni di codice
- Testing e commit conventions
- Come proporre nuove integrazioni API

### Quick Start

```bash
# Fork e clone
git clone https://github.com/[your-username]/openapi.git
cd openapi

# Crea branch
git checkout -b feature/AmazingFeature

# Sviluppa e testa
bench --site [test-site] run-tests --app openapi

# Commit e PR
git commit -m "feat(sdi): description"
git push origin feature/AmazingFeature
```

## 📚 Risorse

- [Documentazione OpenAPI.it](https://www.openapi.it/documentazione/)
- [Specifiche SDI](https://www.fatturapa.gov.it/it/norme-e-regole/documentazione-fattura-elettronica/)
- [ERPNext Documentation](https://docs.erpnext.com)
- [Frappe Framework](https://frappeframework.com)
- [Italian Invoice App](https://github.com/Solede-SA/italian_invoice)

## 📄 License

GNU Affero General Public License v3.0 - vedi [LICENSE](LICENSE)

Copyright (C) 2024-2025 Solede SA and contributors

Puoi usare, modificare e distribuire liberamente. Se offri come servizio web/SaaS, DEVI condividere il codice sorgente modificato.

---

**Sviluppato da Solede SA** | [GitHub Issues](https://github.com/Solede-SA/openapi/issues) | info@solede.com
