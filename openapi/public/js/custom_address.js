// Estensione del form Address per il geocoding via OpenAPI.
// - bottone "Aggiorna geocoding" (gruppo "Geocoding")
// - indicator nello header con stato corrente

frappe.ui.form.on("Address", {
    refresh(frm) {
        if (!frm.is_new()) {
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

            const status = frm.doc.geocode_status;
            if (status) {
                const color = status === "OK" ? "green" : status === "Warning" ? "orange" : status === "Error" ? "red" : "gray";
                const warnings = (frm.doc.geocode_warnings || "").split("\n").filter(Boolean);
                const label = warnings.length
                    ? `${status}: ${warnings.length} anomalie`
                    : status;
                frm.dashboard.add_indicator(label, color);
            }
        }
    },
});
