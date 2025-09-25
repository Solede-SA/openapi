frappe.listview_settings['Customer'] = frappe.listview_settings['Customer'] || {};

// Funzione per sostituire il comportamento del bottone
function replace_add_button(listview) {
    // Trova e sostituisci il bottone Add Customer
    let add_button = listview.page.btn_primary;
    if (add_button && add_button.length > 0) {
        // Rimuovi tutti gli event handler esistenti
        add_button.off('click');

        // Aggiungi il nuovo comportamento - vai direttamente al form completo
        add_button.on('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            // Vai direttamente al form usando set_route
            frappe.set_route('Form', 'Customer', 'new-customer-' + frappe.utils.get_random(5));
        });
    }
}

// Sovrascrivi il comportamento del bottone "Add Customer" standard
frappe.listview_settings['Customer'].onload = function(listview) {
    // Sostituisci subito
    replace_add_button(listview);

    // E anche dopo un breve delay per sicurezza
    setTimeout(function() {
        replace_add_button(listview);
    }, 500);
};

// Gestisci anche il refresh della lista
frappe.listview_settings['Customer'].refresh = function(listview) {
    setTimeout(function() {
        replace_add_button(listview);
    }, 100);
};