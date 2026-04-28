// Estensione del form Address per il geocoding via OpenAPI.
// - bottone "Aggiorna geocoding" (forza re-geocode)
// - bottone "Applica correzioni" (mostra diff vs payload geocoder e applica)
// - indicator nello header con stato corrente

frappe.ui.form.on("Address", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(
            __("Aggiorna geocoding"),
            () => {
                frappe.call({
                    method: "openapi.api.geocoding.validator.refresh_address_geocode",
                    args: { address_name: frm.doc.name },
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
                        frm.reload_doc();
                    },
                });
            },
            __("Geocoding")
        );

        if (frm.doc.geocode_status === "Warning" || frm.doc.geocode_status === "OK") {
            frm.add_custom_button(
                __("Applica correzioni geocoder"),
                () => show_suggestions_dialog(frm),
                __("Geocoding")
            );
        }

        const status = frm.doc.geocode_status;
        if (status) {
            const color = status === "OK" ? "green" : status === "Warning" ? "orange" : status === "Error" ? "red" : "gray";
            const warnings = (frm.doc.geocode_warnings || "").split("\n").filter(Boolean);
            const label = warnings.length ? `${status}: ${warnings.length} anomalie` : status;
            frm.dashboard.add_indicator(label, color);
        }
    },
});

function show_suggestions_dialog(frm) {
    frappe.call({
        method: "openapi.api.geocoding.validator.get_geocode_suggestions",
        args: { address_name: frm.doc.name },
        callback: (r) => {
            const data = r.message || {};
            if (!data.available) {
                frappe.msgprint(__("Nessun suggerimento disponibile (esegui prima 'Aggiorna geocoding')."));
                return;
            }
            if (!data.differences || data.differences.length === 0) {
                frappe.msgprint(__("L'indirizzo coincide gia' con la versione riconosciuta dal geocoder."));
                return;
            }

            const fields = [
                { fieldtype: "HTML", fieldname: "intro", options:
                    `<p class="text-muted">Confronto fra l'indirizzo inserito e quello riconosciuto dal geocoder OpenAPI. Seleziona i campi da aggiornare.</p>` },
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
                        args: { address_name: frm.doc.name, fields: selected },
                        freeze: true,
                        callback: (rr) => {
                            const m = rr.message || {};
                            frappe.show_alert({
                                message: __("Aggiornati: {0}", [(m.applied || []).join(", ")]),
                                indicator: "green",
                            });
                            dialog.hide();
                            frm.reload_doc();
                        },
                    });
                },
            });
            dialog.show();
        },
    });
}
