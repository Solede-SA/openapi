# Contributing to OpenAPI

Grazie per il tuo interesse nel contribuire a OpenAPI! 🎉

## 📋 Indice

- [Codice di Condotta](#codice-di-condotta)
- [Come Contribuire](#come-contribuire)
- [Setup Ambiente di Sviluppo](#setup-ambiente-di-sviluppo)
- [Convenzioni di Codice](#convenzioni-di-codice)
- [Testing](#testing)
- [Commit Convention](#commit-convention)
- [Pull Request Process](#pull-request-process)

## Codice di Condotta

Questo progetto segue il [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/). Partecipando, ti aspettiamo che tu rispetti questo codice.

## Come Contribuire

Ci sono molti modi per contribuire:

- 🐛 Segnalare bug
- 💡 Proporre nuove funzionalità
- 📝 Migliorare la documentazione
- 🔧 Fixare bug
- ✨ Implementare nuove feature
- 🧪 Scrivere test
- 🌍 Tradurre in altre lingue

## Setup Ambiente di Sviluppo

### Prerequisiti

- Frappe Framework v15+
- ERPNext v15+
- Python 3.10+
- Node.js 18+
- Account OpenAPI.it (per testing con servizi reali)

### Installazione

1. **Fork del repository**
   ```bash
   cd frappe-bench/apps
   git clone https://github.com/TUO-USERNAME/openapi.git
   cd openapi
   ```

2. **Installa l'app**
   ```bash
   bench --site your-site.local install-app openapi
   ```

3. **Crea branch per la tua feature**
   ```bash
   git checkout -b feature/nome-feature
   ```

## Convenzioni di Codice

### Python

- Seguire **PEP 8**
- Usare **type hints** quando possibile
- Docstring in formato Google style
- Principio **DRY** (Don't Repeat Yourself)
- Principio **KISS** (Keep It Simple, Stupid)
- **NO fallback**: mostrare sempre errori all'utente

```python
def validate_partita_iva(partita_iva: str) -> bool:
    """Valida una Partita IVA italiana.

    Args:
        partita_iva: Partita IVA da validare (11 cifre)

    Returns:
        True se valida, False altrimenti

    Raises:
        frappe.ValidationError: Se formato non valido
    """
    if not partita_iva or len(partita_iva) != 11:
        frappe.throw("Partita IVA deve essere di 11 cifre")

    if not partita_iva.isdigit():
        frappe.throw("Partita IVA deve contenere solo numeri")

    return True
```

### JavaScript

- Usare ES6+ syntax
- Arrow functions quando possibile
- Nomi variabili descrittivi

```javascript
function sendInvoiceToSDI(frm) {
    frappe.call({
        method: "openapi.api.sdi.fatture.send_invoice",
        args: { invoice_name: frm.doc.name },
        callback: (r) => {
            if (r.message) {
                frm.set_value("custom_uuid", r.message.uuid);
                frm.refresh();
            }
        }
    });
}
```

## Testing

### Scrivere Test

Tutti i nuovi features devono includere test:

```python
# openapi/openapi/doctype/openapi_services/test_openapi_services.py
import frappe
from frappe.tests.utils import FrappeTestCase

class TestOpenApiServices(FrappeTestCase):
    def test_validate_api_token(self):
        """Test validazione token API"""
        service = frappe.get_doc({
            "doctype": "OpenAPI Services",
            "api_token": "test_token_123"
        })

        self.assertTrue(service.validate_token())
```

### Eseguire Test

```bash
# Tutti i test
bench --site your-site.local run-tests --app openapi

# Test specifico
bench --site your-site.local run-tests --app openapi --doctype "OpenAPI Services"
```

## Commit Convention

Usa [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: Nuova funzionalità
- `fix`: Bug fix
- `docs`: Modifiche documentazione
- `style`: Formattazione (no logic changes)
- `refactor`: Refactoring codice
- `test`: Aggiunta/modifica test
- `chore`: Maintenance tasks

### Scope Suggeriti

- `sdi`: Integrazione Sistema di Interscambio
- `api`: API OpenAPI.it
- `webhook`: Gestione webhook
- `aziende`: Ricerca e validazione aziende
- `invoice`: Gestione fatture
- `config`: Configurazione e settings

### Esempi

```bash
feat(sdi): add automatic retry for failed invoice submissions

- Implement exponential backoff strategy
- Add max retry configuration in OpenAPI Services
- Log all retry attempts for debugging

Closes #42

fix(webhook): resolve signature verification issue

The webhook signature validation was failing for
requests with special characters in the body.

Fixes #38

docs(readme): update installation instructions

- Add prerequisites section
- Include OpenAPI.it account setup
- Add troubleshooting for common errors
```

## Pull Request Process

1. **Update Documentation**
   - Aggiorna README.md se necessario
   - Aggiungi entry in CHANGELOG.md
   - Commenta il codice complesso

2. **Test Your Changes**
   ```bash
   bench --site your-site.local migrate
   bench restart
   ```

3. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

4. **Push to Fork**
   ```bash
   git push origin feature/nome-feature
   ```

5. **Create Pull Request**
   - Vai su GitHub
   - Clicca "New Pull Request"
   - Compila il template:
     - Descrizione chiara delle modifiche
     - Link alle issue correlate
     - Screenshots se UI changes
     - Checklist completata

6. **Code Review**
   - Rispondi ai commenti
   - Fai le modifiche richieste
   - Push aggiornamenti (stesso branch)

## Segnalazione Bug

### Template Bug Report

```markdown
**Descrizione Bug**
Descrizione chiara del problema.

**Come Riprodurre**
1. Vai a '...'
2. Clicca su '...'
3. Vedi errore

**Comportamento Atteso**
Cosa ti aspettavi che succedesse.

**Screenshots**
Se applicabile, aggiungi screenshots.

**Ambiente:**
- Frappe Version: [es. v15.10.0]
- ERPNext Version: [es. v15.8.0]
- App Version: [es. v1.0.0]
- Python: [es. 3.10.12]

**Log di Errore**
```
Paste error log here
```

**Configurazione OpenAPI.it**
- Ambiente: Produzione/Test
- Token configurato: Sì/No
```

## Richiesta Feature

### Template Feature Request

```markdown
**La tua feature risolve un problema?**
Descrizione chiara del problema.

**Descrivi la soluzione che vorresti**
Cosa vorresti che succedesse.

**Use Case**
Scenario d'uso concreto.

**Compatibilità API OpenAPI.it**
Se la feature richiede nuove API OpenAPI.it, fornisci:
- Documentazione API
- Endpoint richiesti
- Esempio request/response

**Contesto Aggiuntivo**
Screenshots, mockup, esempi.
```

## Licenza

Contribuendo a questo progetto, accetti che i tuoi contributi saranno rilasciati sotto la licenza **GNU Affero General Public License v3.0**.

Tutti i file devono includere l'header copyright:

```python
# Copyright (c) 2024-2025, Solede SA and contributors
# For license information, please see license.txt
# License: GNU Affero General Public License v3 or later (AGPLv3+)
# See https://www.gnu.org/licenses/agpl-3.0.html
```

## Domande?

- 💬 Apri una [Discussion su GitHub](https://github.com/Solede-SA/openapi/discussions)
- 📧 Email: info@solede.com
- 🐛 Segnala bug: [GitHub Issues](https://github.com/Solede-SA/openapi/issues)

## Grazie! 🙏

Ogni contributo, grande o piccolo, è apprezzato e aiuta a migliorare questo progetto per tutta la community italiana ERPNext!

---

Made with ❤️ by Solede SA and contributors
