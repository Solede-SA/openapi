"""
Test del wrapper Geocoder e della gestione del protocollo asincrono ("sourcing")
del provider OpenAPI/HERE. Tutto mockato: nessuna chiamata di rete ne' accesso al DB.
"""

import unittest
from unittest.mock import MagicMock, patch

from openapi.api.geocoding import forward
from openapi.api.geocoding.forward import _is_sourcing_pending, geocode_address


def _resp(status, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.text = text
    return r


# Risposta "sourcing avviato ma non pronto": success/sourced True, element lista vuota.
SOURCED_EMPTY = {"element": [], "sourced": True, "success": True, "message": "", "error": None}
# Vuoto definitivo (senza 'sourced'): indirizzo/civico non mappato -> nessun risultato.
DEFINITIVE_EMPTY = {"element": [], "success": True, "message": "", "error": None}
# Risposta reale popolata.
REAL = {
    "element": {
        "latitude": 45.46795, "longitude": 9.19566,
        "streetNumber": "8", "streetName": "Via Montenapoleone",
        "postalCode": "20121", "locality": "Milano",
        "adminLevels": {"2": {"code": "MI", "name": "Milano"}},
        "country": "Italia", "countryCode": "IT",
    },
    "success": True, "message": "", "error": None,
}


class TestGeocodeSourcingRetry(unittest.TestCase):
    def setUp(self):
        self._patchers = [
            patch.object(forward, "_get_company_token", return_value="Bearer test-token"),
            patch.object(forward.common_data, "get_service", return_value="https://geo.example/geocode"),
            patch.object(forward.frappe, "cache", MagicMock()),
            patch.object(forward.time, "sleep"),
            patch.object(forward.requests, "post"),
        ]
        (self.mock_token, self.mock_service, self.mock_cache,
         self.mock_sleep, self.mock_post) = [p.start() for p in self._patchers]
        self.mock_cache.get_value.return_value = None  # mai in cache

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()

    def test_sourced_then_real(self):
        """1a risposta in sourcing, 2a popolata -> il retry risolve, success=True."""
        self.mock_post.side_effect = [_resp(200, SOURCED_EMPTY), _resp(200, REAL)]
        res = geocode_address("Via Montenapoleone 8, Milano")
        self.assertTrue(res["success"])
        self.assertFalse(res["pending"])
        self.assertAlmostEqual(res["lat"], 45.46795)
        self.assertEqual(res["state"], "MI")
        self.assertEqual(self.mock_post.call_count, 2)
        self.mock_sleep.assert_called_once()

    def test_sourced_persistent_returns_pending(self):
        """Sempre in sourcing -> dopo i retry ritorna pending=True (non un errore)."""
        self.mock_post.side_effect = [_resp(200, SOURCED_EMPTY)] * (forward.SOURCING_RETRY_MAX + 1)
        res = geocode_address("Via Ignota 999, Nowhere")
        self.assertFalse(res["success"])
        self.assertTrue(res["pending"])
        self.assertEqual(self.mock_post.call_count, forward.SOURCING_RETRY_MAX + 1)
        self.assertEqual(self.mock_sleep.call_count, forward.SOURCING_RETRY_MAX)

    def test_definitive_empty_no_retry(self):
        """Vuoto senza 'sourced' -> nessun risultato, nessun retry (non e' pending)."""
        self.mock_post.side_effect = [_resp(200, DEFINITIVE_EMPTY)]
        res = geocode_address("Via Boh, Boh")
        self.assertFalse(res["success"])
        self.assertFalse(res.get("pending"))
        self.assertIn("nessun risultato", res["error"])
        self.assertEqual(self.mock_post.call_count, 1)
        self.mock_sleep.assert_not_called()

    def test_http_error_no_retry(self):
        """HTTP != 200 -> errore immediato, nessun retry (fail-loud)."""
        self.mock_post.side_effect = [_resp(500, text="boom")]
        with patch.object(forward.frappe, "log_error"):
            res = geocode_address("Via X, Y")
        self.assertFalse(res["success"])
        self.assertIn("HTTP 500", res["error"])
        self.assertEqual(self.mock_post.call_count, 1)
        self.mock_sleep.assert_not_called()

    def test_direct_success_no_sleep(self):
        """Risposta popolata al primo colpo -> nessuna attesa, normalizzazione corretta."""
        self.mock_post.side_effect = [_resp(200, REAL)]
        res = geocode_address("Via Montenapoleone 8, Milano 20121")
        self.assertTrue(res["success"])
        self.assertEqual(res["pincode"], "20121")
        self.assertEqual(self.mock_post.call_count, 1)
        self.mock_sleep.assert_not_called()

    def test_is_sourcing_pending_predicate(self):
        self.assertTrue(_is_sourcing_pending(SOURCED_EMPTY))
        self.assertFalse(_is_sourcing_pending(REAL))
        self.assertFalse(_is_sourcing_pending(DEFINITIVE_EMPTY))
        # success False + sourced True: e' un errore, non un pending.
        self.assertFalse(_is_sourcing_pending({"success": False, "sourced": True, "element": []}))
        self.assertFalse(_is_sourcing_pending([]))
