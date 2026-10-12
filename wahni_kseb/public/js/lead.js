frappe.ui.form.on("Lead", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(
            __("Check KSEB Grid Capacity"),
            () => open_kseb_lookup_dialog(frm),
            __("Action")
        );
    }
});

function open_kseb_lookup_dialog(frm, preferred_method = "bill") {
    const dialog = new frappe.ui.Dialog({
        title: __("Check KSEB Grid Capacity"),
        fields: [
            {
                fieldname: "method",
                fieldtype: "Select",
                label: __("Lookup Method"),
                options: [
                    { label: __("Bill lookup"), value: "bill" },
                    { label: __("Select transformer (without bill details)"), value: "options" }
                ],
                default: preferred_method,
                reqd: 1,
                onchange() {
                    update_lookup_dialog(dialog);
                }
            },
            {
                fieldname: "method_note",
                fieldtype: "HTML",
                options: `<p class="text-muted kseb-method-note"></p>`
            },
            {
                fieldname: "consumer_no",
                fieldtype: "Data",
                label: __("KSEB Consumer Number"),
                default: frm.doc.custom_kseb_consumer_no,
                reqd: 1
            },
            {
                fieldname: "registered_mobile",
                fieldtype: "Data",
                label: __("Registered Mobile Number (Bill lookup only)"),
                default: frm.doc.custom_kseb_connected_mobile_no
            },
            {
                fieldname: "captcha_image",
                fieldtype: "HTML",
                label: __("CAPTCHA")
            },
            {
                fieldname: "captcha_code",
                fieldtype: "Data",
                label: __("Enter CAPTCHA"),
                reqd: 1
            }
        ],
        primary_action_label: __("Continue"),
        primary_action(values) {
            if (values.method === "options") {
                fetch_transformer_options(frm, dialog, values);
                return;
            }
            run_bill_lookup(frm, dialog, values);
        }
    });
    dialog.__kseb = { uniqueId: null, options: null };
    dialog.show();
    update_lookup_dialog(dialog);
}

function update_lookup_dialog(dialog) {
    const method = dialog.get_value("method");
    dialog.set_df_property("registered_mobile", "reqd", method === "bill");
    dialog.set_df_property("registered_mobile", "hidden", method !== "bill");
    dialog.get_field("method_note").$wrapper.html(
        method === "bill"
            ? `<p class="text-muted">${__("Bill lookup retrieves bill details and matches its transformer using the same CAPTCHA-protected transformer service.")}</p>`
            : `<p class="text-muted">${__("Select transformer retrieves section and grid capacity details only. It does not retrieve bill details.")}</p>`
    );
    dialog.set_df_property("captcha_image", "hidden", Boolean(dialog.__kseb.options));
    dialog.set_df_property("captcha_code", "hidden", Boolean(dialog.__kseb.options));
    if (!dialog.__kseb.options && !dialog.__kseb.uniqueId) {
        load_kseb_captcha(dialog);
    }
}

function run_bill_lookup(frm, dialog, values) {
    frappe.call({
        method: "wahni_kseb.api.check_grid_capacity",
        args: {
            lead: frm.doc.name,
            consumer_no: values.consumer_no,
            registered_mobile: values.registered_mobile,
            captcha_code: values.captcha_code,
            unique_id: dialog.__kseb.uniqueId
        },
        freeze: true,
        freeze_message: __("Checking KSEB grid availability..."),
        callback(r) {
            if (!r.message) return;
            dialog.hide();
            show_grid_check_result(r.message);
        },
        error(xhr) {
            const message = get_frappe_error_message(xhr);
            if (is_kseb_validation_error(message)) return;

            frappe.confirm(
                __("Bill lookup failed. Would you like to try transformer options? This method requires a CAPTCHA and does not retrieve bill details."),
                () => {
                    dialog.set_value("method", "options");
                    dialog.__kseb.uniqueId = null;
                    dialog.__kseb.options = null;
                    update_lookup_dialog(dialog);
                }
            );
        }
    });
}

function load_kseb_captcha(dialog) {
    dialog.__kseb.uniqueId = null;
    dialog.set_value("captcha_code", "");
    dialog.get_field("captcha_image").$wrapper.html(`<p class="text-muted">${__("Loading CAPTCHA...")}</p>`);
    frappe.call({
        method: "wahni_kseb.api.get_grid_capacity_captcha",
        freeze: true,
        freeze_message: __("Loading KSEB CAPTCHA..."),
        callback(r) {
            if (!r.message || !r.message.image || !r.message.unique_id) return;
            dialog.__kseb.uniqueId = r.message.unique_id;
            dialog.get_field("captcha_image").$wrapper.html(
                `<img src="${frappe.utils.escape_html(r.message.image)}" alt="${__("KSEB CAPTCHA")}" style="width: 360px; max-width: 100%; height: auto; image-rendering: auto;"> ` +
                `<button type="button" class="btn btn-default btn-xs kseb-refresh-captcha">${__("Refresh")}</button>`
            );
            dialog.get_field("captcha_image").$wrapper.find(".kseb-refresh-captcha").on("click", () => load_kseb_captcha(dialog));
        }
    });
}

function fetch_transformer_options(frm, dialog, values) {
    if (!dialog.__kseb.uniqueId) {
        frappe.msgprint(__("Please wait for the CAPTCHA to load or refresh it."));
        return;
    }
    frappe.call({
        method: "wahni_kseb.api.get_grid_capacity_options",
        args: {
            lead: frm.doc.name,
            consumer_no: values.consumer_no,
            captcha_code: values.captcha_code,
            unique_id: dialog.__kseb.uniqueId
        },
        freeze: true,
        freeze_message: __("Retrieving KSEB transformer options..."),
        callback(r) {
            if (!r.message) return;
            if (!r.message.transformers.length) {
                frappe.msgprint(__("No transformer options were returned for this consumer."));
                load_kseb_captcha(dialog);
                return;
            }
            dialog.__kseb.options = {
                consumerNo: values.consumer_no,
                section: r.message.section,
                transformers: r.message.transformers
            };
            dialog.hide();
            show_transformer_choices(frm, dialog.__kseb.options);
        }
    });
}

function show_transformer_choices(frm, optionData) {
    const { consumerNo, section, transformers } = optionData;
    const options = transformers.map((item) => ({
        label: item.transformer_name,
        value: item.transformer_name,
        description: `${item.balance_available} kW ${__("available")}`
    }));
    const selection = new frappe.ui.Dialog({
        title: __("Select Transformer"),
        fields: [
            {
                fieldname: "note",
                fieldtype: "HTML",
                options: `<p class="text-muted">${__("Bill information is not included. Select the transformer serving this consumer.")}</p>`
            },
            {
                fieldname: "transformer_name",
                fieldtype: "Autocomplete",
                label: __("Transformer / DTR"),
                options,
                reqd: 1
            }
        ],
        primary_action_label: __("Save Selection"),
        primary_action(values) {
            const transformer = transformers.find((item) => item.transformer_name === values.transformer_name);
            if (!transformer) {
                frappe.msgprint(__("Select a transformer from the suggestions."));
                return;
            }
            frappe.call({
                method: "wahni_kseb.api.save_grid_capacity_option",
                args: {
                    lead: frm.doc.name,
                    consumer_no: consumerNo,
                    transformer_data: JSON.stringify(transformer),
                    section_data: JSON.stringify(section)
                },
                freeze: true,
                freeze_message: __("Saving KSEB grid details..."),
                callback(r) {
                    if (!r.message) return;
                    selection.hide();
                    show_grid_check_result(r.message);
                }
            });
        }
    });
    selection.show();
}

function show_grid_check_result(result) {
    frappe.msgprint({
        title: __("KSEB Grid Check Complete"),
        message: __("Available Capacity: {0} kW", [result.data.balance_available]),
        indicator: "green"
    });
    frappe.set_route("Form", "KSEB Grid Check", result.name);
}

function get_frappe_error_message(xhr) {
    try {
        const response = JSON.parse(xhr.responseText || "{}");
        return response._server_messages ? JSON.parse(response._server_messages).join(" ") : (response.exception || "");
    } catch (e) {
        return xhr.responseText || "";
    }
}

function is_kseb_validation_error(message) {
    return /validation error|consumer number is required|registered mobile is required|invalid consumer number|invalid mobile number/i.test(message);
}
