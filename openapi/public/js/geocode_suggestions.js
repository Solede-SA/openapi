// Helper globale per la dialog "Applica correzioni geocoder".
// Riusato da custom_address.js (form Address) e da dae_order.js (form DAE Order)
// per lavorare sul shipping_address_name.

(function () {
    if (window.openapiGeocode) return;
    window.openapiGeocode = {
        /**
         * Apre la dialog dei suggerimenti geocoder per un Address.
         * @param {string} addressName  Nome del documento Address.
         * @param {function} onApplied  Callback (opzionale) eseguita dopo apply_geocode_suggestions.
         */
        showSuggestions(addressName, onApplied) {
            if (!addressName) {
                frappe.msgprint(__("Nessun indirizzo selezionato"));
                return;
            }
            frappe.call({
                method: "openapi.api.geocoding.validator.get_geocode_suggestions",
                args: { address_name: addressName },
                callback: (r) => {
                    const data = r.message || {};
                    if (!data.available) {
                        frappe.msgprint(__("Nessun suggerimento disponibile (esegui prima 'Aggiorna geocoding' sull'Address)."));
                        return;
                    }
                    if (!data.differences || data.differences.length === 0) {
                        frappe.msgprint(__("L'indirizzo coincide gia' con la versione riconosciuta dal geocoder."));
                        return;
                    }

                    const fields = [
                        {
                            fieldtype: "HTML",
                            fieldname: "intro",
                            options:
                                `<p class="text-muted">Confronto fra l'indirizzo inserito (<a href="/app/address/${encodeURIComponent(addressName)}" target="_blank">${frappe.utils.escape_html(addressName)}</a>) e quello riconosciuto dal geocoder OpenAPI. Seleziona i campi da aggiornare.</p>`,
                        },
                    ];
                    data.differences.forEach((d) => {
                        fields.push({
                            fieldtype: "Check",
                            fieldname: `apply_${d.field}`,
                            label: d.label,
                            default: 1,
                            description: `<span class="text-danger">${frappe.utils.escape_html(d.current || "(vuoto)")}</span> &rarr; <span class="text-success">${frappe.utils.escape_html(d.suggested)}</span>`,
                        });
                    });

                    const dialog = new frappe.ui.Dialog({
                        title: __("Applica correzioni geocoder"),
                        fields,
                        primary_action_label: __("Applica selezionati"),
                        primary_action: (values) => {
                            const selected = data.differences
                                .filter((d) => values[`apply_${d.field}`])
                                .map((d) => d.field);
                            if (selected.length === 0) {
                                frappe.show_alert({ message: __("Nessun campo selezionato"), indicator: "orange" });
                                return;
                            }
                            frappe.call({
                                method: "openapi.api.geocoding.validator.apply_geocode_suggestions",
                                args: { address_name: addressName, fields: selected },
                                freeze: true,
                                callback: (rr) => {
                                    const m = rr.message || {};
                                    frappe.show_alert({
                                        message: __("Aggiornati: {0}", [(m.applied || []).join(", ")]),
                                        indicator: "green",
                                    });
                                    dialog.hide();
                                    if (typeof onApplied === "function") onApplied(m);
                                },
                            });
                        },
                    });
                    dialog.show();
                },
            });
        },

        /**
         * Forza il re-geocoding di un Address e ricarica via callback.
         */
        refresh(addressName, onDone) {
            if (!addressName) return;
            frappe.call({
                method: "openapi.api.geocoding.validator.refresh_address_geocode",
                args: { address_name: addressName },
                freeze: true,
                freeze_message: __("Geocoding in corso..."),
                callback: (r) => {
                    const msg = r.message || {};
                    if (msg.warnings) {
                        frappe.show_alert({ message: __("Geocoding completato con anomalie"), indicator: "orange" });
                    } else if (msg.status === "OK") {
                        frappe.show_alert({ message: __("Geocoding OK"), indicator: "green" });
                    } else {
                        frappe.show_alert({ message: __("Geocoding fallito"), indicator: "red" });
                    }
                    if (typeof onDone === "function") onDone(msg);
                },
            });
        },
    };
})();
