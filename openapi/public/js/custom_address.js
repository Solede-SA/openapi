// Estensione del form Address per il geocoding via OpenAPI.
// Helpers in window.openapiGeocode (geocode_suggestions.js, app_include_js).

frappe.ui.form.on("Address", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(
            __("Aggiorna geocoding"),
            () => window.openapiGeocode.refresh(frm.doc.name, () => frm.reload_doc()),
            __("Geocoding")
        );

        if (frm.doc.geocode_status === "Warning" || frm.doc.geocode_status === "OK") {
            frm.add_custom_button(
                __("Applica correzioni geocoder"),
                () => window.openapiGeocode.showSuggestions(frm.doc.name, () => frm.reload_doc()),
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
