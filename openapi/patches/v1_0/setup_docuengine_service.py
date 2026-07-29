"""Crea il record del servizio se manca.

Il registro degli indirizzi vive in `openapi.install.SERVICES`, ed è agganciato anche a
`after_install`/`after_migrate`: questa patch resta per non spezzare il registro delle patch dei
siti che l'hanno già eseguita, e delega, invece di ripetere qui l'indirizzo del servizio.
"""

from openapi.install import ensure_services


def execute():
	ensure_services()
