# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-27

### Added

#### Integrazione OpenAPI.it
- Integrazione completa con servizi OpenAPI.it per fatturazione elettronica
- Provider SDI per invio automatico fatture al Sistema di Interscambio
- Gestione webhook per ricezione notifiche SDI in tempo reale
- Configurazione multi-company con token API separati

#### Gestione Aziende
- Ricerca e validazione aziende tramite P.IVA e Codice Fiscale
- Auto-popolamento dati anagrafici (denominazione, sede legale, PEC)
- Sincronizzazione automatica con ERPNext Company/Customer/Supplier
- API company_start per inizializzazione rapida configurazione

#### Fatturazione Elettronica SDI
- Invio automatico fatture attive al SDI tramite OpenAPI.it
- Download XML fatture ricevute e inviate
- Tracking stato transazioni SDI con timeline completa
- Gestione notifiche: RC, NS, MC, EC con parsing automatico
- Callback handler per aggiornamenti stato fattura in tempo reale

#### Import Fatture Passive
- Ricezione automatica XML fatture fornitori via webhook
- Parsing e creazione automatica Purchase Invoice
- Matching fornitore intelligente basato su P.IVA
- Auto-link con Purchase Orders aperti

#### Custom DocTypes
- **OpenAPI Services**: Configurazione servizi e credenziali API
- **OpenAPI Webhook**: Log e gestione webhook ricevuti
- **Configurazione Fattura SDI**: Settings fatturazione elettronica per company

#### Custom Fields
- Company: `custom_open_api_token`, `custom_openapi_webhook_url`
- Customer/Supplier: Campi fiscali italiani (P.IVA, CF, PEC, SDI)
- Sales/Purchase Invoice: UUID, tipo documento, riferimenti SDI

#### UI Enhancements
- Custom scripts per Company, Customer, Sales/Purchase Invoice
- Pulsanti azione rapida per invio fatture e download XML
- List view personalizzate con stato SDI visibile
- Form validazioni automatiche dati fiscali

### Security
- Token API configurabili per company (no hardcoded credentials)
- Validazione webhook con signature verification
- HTTPS obbligatorio per endpoint webhook
- Gestione sicura file XML in private/files

### Developer Experience
- ~1,600 linee di codice Python production-ready
- Architettura modulare: api/sdi, api/aziende, api/eInvoice
- Type hints e docstrings per tutte le funzioni pubbliche
- Error handling completo con messaggi user-friendly
- Compatibilità con italian_invoice app (provider pluggabile)

### Compliance
- Conforme API OpenAPI.it v2
- Standard FatturaPA v1.2.1
- Gestione completa flusso SDI italiano
- Supporto notifiche Agenzia delle Entrate

[1.0.0]: https://github.com/Solede-SA/openapi/releases/tag/v1.0.0
