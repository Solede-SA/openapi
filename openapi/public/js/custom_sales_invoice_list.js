frappe.listview_settings['Sales Invoice'] = {
        formatters: {
        custom_stato_invio: function (value, doc, row) {
                console.log(row);
                if (value == '') {
                    return '';
                }
                
                if (value == 'NS') {
                    let color = 'red';
                    return `<span style="color:${color}; font-weight: bold;">${row.custom_stato_invio_descrizione}</span>`;
                } else if (value == 'RC') {
                    let color = 'green';
                    return `<span style="color:${color}; font-weight: bold;">${row.custom_stato_invio_descrizione}</span>`;
                } else if (value == 'MC') {
                    let color = 'red';
                    return `<span style="color:${color}; font-weight: bold;">${row.custom_stato_invio_descrizione}</span>`;
                } else {
                    return row.custom_stato_invio_descrizione
                }
            }
        },
        
};