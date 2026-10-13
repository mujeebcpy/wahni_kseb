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
                fieldname: "bill_captcha_image",
                fieldtype: "HTML"
            },
            {
                fieldname: "bill_captcha_code",
                fieldtype: "Data",
                label: __("Enter Bill CAPTCHA")
            },
            {
                fieldname: "captcha_image",
                fieldtype: "HTML"
            },
            {
                fieldname: "captcha_code",
                fieldtype: "Data",
                label: __("Enter Transformer CAPTCHA"),
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
    dialog.__kseb = { uniqueId: null, billSessionId: null, options: null };
    dialog.show();
    update_lookup_dialog(dialog);
}

// Bill lookup needs a bill CAPTCHA (kseb.in) and a transformer CAPTCHA (wss.kseb.in).
// Each CAPTCHA can be submitted only once, so both are reloaded after every failed attempt.
const KSEB_CAPTCHAS = {
    bill: {
        method: "wahni_kseb.api.get_bill_captcha",
        idKey: "session_id",
        stateKey: "billSessionId",
        imageField: "bill_captcha_image",
        codeField: "bill_captcha_code",
        label: __("Bill CAPTCHA")
    },
    transformer: {
        method: "wahni_kseb.api.get_grid_capacity_captcha",
        idKey: "unique_id",
        stateKey: "uniqueId",
        imageField: "captcha_image",
        codeField: "captcha_code",
        label: __("Transformer CAPTCHA")
    }
};

function update_lookup_dialog(dialog) {
    const method = dialog.get_value("method");
    const is_bill = method === "bill";
    const hide_captchas = Boolean(dialog.__kseb.options);
    dialog.set_df_property("registered_mobile", "reqd", is_bill);
    dialog.set_df_property("registered_mobile", "hidden", !is_bill);
    dialog.get_field("method_note").$wrapper.html(
        is_bill
            ? `<p class="text-muted">${__("Bill lookup retrieves bill details and matches its transformer. It needs two CAPTCHAs: one for the bill and one for the transformer service.")}</p>`
            : `<p class="text-muted">${__("Select transformer retrieves section and grid capacity details only. It does not retrieve bill details.")}</p>`
    );
    dialog.set_df_property("bill_captcha_image", "hidden", !is_bill || hide_captchas);
    dialog.set_df_property("bill_captcha_code", "hidden", !is_bill || hide_captchas);
    dialog.set_df_property("bill_captcha_code", "reqd", is_bill && !hide_captchas);
    dialog.set_df_property("captcha_image", "hidden", hide_captchas);
    dialog.set_df_property("captcha_code", "hidden", hide_captchas);
    if (hide_captchas) return;
    if (!dialog.__kseb.uniqueId) {
        load_kseb_captcha(dialog, "transformer");
    }
    if (is_bill && !dialog.__kseb.billSessionId) {
        load_kseb_captcha(dialog, "bill");
    }
}

function reload_kseb_captchas(dialog) {
    load_kseb_captcha(dialog, "transformer");
    if (dialog.get_value("method") === "bill") {
        load_kseb_captcha(dialog, "bill");
    } else {
        dialog.__kseb.billSessionId = null;
    }
}

function run_bill_lookup(frm, dialog, values) {
    if (!dialog.__kseb.uniqueId || !dialog.__kseb.billSessionId) {
        frappe.msgprint(__("Please wait for the CAPTCHAs to load or refresh them."));
        return;
    }
    frappe.call({
        method: "wahni_kseb.api.check_grid_capacity",
        args: {
            lead: frm.doc.name,
            consumer_no: values.consumer_no,
            registered_mobile: values.registered_mobile,
            bill_captcha_code: values.bill_captcha_code,
            bill_session_id: dialog.__kseb.billSessionId,
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
            reload_kseb_captchas(dialog);
            if (is_kseb_validation_error(message) || is_kseb_captcha_error(message)) return;

            frappe.confirm(
                __("Bill lookup failed. Would you like to try transformer options? This method requires a CAPTCHA and does not retrieve bill details."),
                () => {
                    dialog.set_value("method", "options");
                    dialog.__kseb.options = null;
                    update_lookup_dialog(dialog);
                }
            );
        }
    });
}

function load_kseb_captcha(dialog, kind) {
    const config = KSEB_CAPTCHAS[kind];
    const $wrapper = dialog.get_field(config.imageField).$wrapper;
    dialog.__kseb[config.stateKey] = null;
    dialog.set_value(config.codeField, "");
    $wrapper.html(
        `<label class="control-label">${config.label}</label>` +
        `<p class="text-muted">${__("Loading CAPTCHA...")}</p>`
    );
    frappe.call({
        method: config.method,
        freeze: true,
        freeze_message: __("Loading KSEB CAPTCHA..."),
        callback(r) {
            if (!r.message || !r.message.image || !r.message[config.idKey]) return;
            dialog.__kseb[config.stateKey] = r.message[config.idKey];
            $wrapper.html(
                `<label class="control-label">${config.label}</label><div>` +
                `<img src="${frappe.utils.escape_html(r.message.image)}" alt="${config.label}" style="width: 360px; max-width: 100%; height: auto; image-rendering: auto;"> ` +
                `<button type="button" class="btn btn-default btn-xs kseb-refresh-captcha">${__("Refresh")}</button></div>`
            );
            $wrapper.find(".kseb-refresh-captcha").on("click", () => load_kseb_captcha(dialog, kind));
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
                load_kseb_captcha(dialog, "transformer");
                return;
            }
            dialog.__kseb.options = {
                consumerNo: values.consumer_no,
                section: r.message.section,
                transformers: r.message.transformers
            };
            dialog.hide();
            show_transformer_choices(frm, dialog.__kseb.options);
        },
        error() {
            load_kseb_captcha(dialog, "transformer");
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

function is_kseb_captcha_error(message) {
    return /captcha rejected by kseb|captcha is required/i.test(message);
}

function is_kseb_validation_error(message) {
    return /validation error|consumer number is required|registered mobile is required|invalid consumer number|invalid mobile number/i.test(message);
}
