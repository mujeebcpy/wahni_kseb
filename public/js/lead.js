frappe.ui.form.on("Lead", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        frm.add_custom_button(
            __("Check KSEB Grid Capacity"),
            () => {
                check_kseb_grid(frm);
            },
            __("Action")
        );
    }
});


function check_kseb_grid(frm) {
    const consumer_no = frm.doc.custom_kseb_consumer_no;
    const registered_mobile = frm.doc.custom_kseb_connected_mobile_no;
    
    if (!consumer_no) {
        frappe.msgprint({
            title: __("Missing Consumer Number"),
            message: __("Please enter the KSEB Consumer Number."),
            indicator: "orange"
        });
        return;
    }

    if (!registered_mobile) {
        frappe.msgprint({
            title: __("Missing Registered Mobile"),
            message: __("Please enter the KSEB registered mobile number."),
            indicator: "orange"
        });
        return;
    }

    frappe.call({
        method: "wahni_kseb.api.check_grid_capacity",
        args: {
            lead: frm.doc.name,
            consumer_no: consumer_no,
            registered_mobile: registered_mobile
        },
        freeze: true,
        freeze_message: __("Checking KSEB grid availability..."),

        callback(r) {
            if (!r.message) {
                return;
            }

            const result = r.message;

            frappe.msgprint({
                title: __("KSEB Grid Check Complete"),
                message: __(
                    "Available Capacity: {0} kW",
                    [result.data.balance_available]
                ),
                indicator: "green"
            });

            frappe.set_route(
                "Form",
                "KSEB Grid Check",
                result.name
            );
            setTimeout(() => {
            cur_frm.reload_doc();
            }, 500);
        }
    });
}