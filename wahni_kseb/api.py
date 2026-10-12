import base64

import frappe
from frappe.utils import now_datetime
from kseb_client import KSEBClient, KSEBValidationError, KSEBClientError
from wahni_kseb.annexure.printing import generate_annexure

@frappe.whitelist()
def check_grid_capacity(lead, consumer_no, registered_mobile, captcha_code, unique_id):
    if not lead:
        frappe.throw("Lead is required")

    if not consumer_no:
        frappe.throw("Consumer Number is required")

    if not registered_mobile:
        frappe.throw("Registered Mobile is required")
    if not captcha_code or not unique_id:
        frappe.throw("CAPTCHA session is required. Please load a new CAPTCHA.")

    try:
        client = KSEBClient()

        result = client.get_grid_capacity(
            consumer_no=consumer_no,
            mobile=registered_mobile,
            captcha_code=captcha_code,
            unique_id=unique_id,
        )

    except KSEBValidationError as e:
        frappe.throw(str(e))

    except KSEBClientError as e:
        frappe.throw(
            f"Unable to retrieve KSEB information: {e}"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "KSEB Grid Check Error",
        )

        frappe.throw(
            "An unexpected error occurred while checking KSEB data. "
            "Please try again later."
        )
    saved = _save_grid_capacity_result(lead, consumer_no, result, result.transformer)
    doc = frappe.get_doc("KSEB Grid Check", saved["name"])
    doc.registered_mobile = registered_mobile
    doc.consumer_name = result.bill.consumer_name
    doc.customer_address = result.bill.customer_address
    doc.tariff = result.bill.tariff
    doc.phase = (result.bill.phase or "").split(" ")[0]
    doc.connected_load = result.bill.connected_load
    doc.save()
    return {"name": doc.name, "data": doc.as_dict()}


@frappe.whitelist()
def get_grid_capacity_captcha():
    """Return a transformer lookup CAPTCHA for the interactive fallback flow."""
    try:
        captcha = KSEBClient().get_transformer_captcha()
        content_type = captcha.content_type or "image/png"
        return {
            "unique_id": captcha.unique_id,
            "image": f"data:{content_type};base64,{base64.b64encode(captcha.image).decode('ascii')}",
        }
    except KSEBClientError as e:
        frappe.throw(f"Unable to retrieve KSEB CAPTCHA: {e}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "KSEB CAPTCHA Error")
        frappe.throw("Unable to retrieve the KSEB CAPTCHA. Please try again later.")


@frappe.whitelist()
def get_grid_capacity_options(lead, consumer_no, captcha_code, unique_id):
    """Fetch section and transformer choices without downloading a bill."""
    if not lead:
        frappe.throw("Lead is required")
    if not consumer_no:
        frappe.throw("Consumer Number is required")
    if not captcha_code:
        frappe.throw("CAPTCHA answer is required")
    if not unique_id:
        frappe.throw("CAPTCHA session has expired. Please load a new CAPTCHA.")

    try:
        result = KSEBClient().get_grid_capacity_options(
            consumer_no=consumer_no,
            captcha_code=captcha_code,
            unique_id=unique_id,
        )
    except KSEBValidationError as e:
        frappe.throw(str(e))
    except KSEBClientError as e:
        frappe.throw(f"Unable to retrieve KSEB transformer options: {e}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "KSEB Grid Options Error")
        frappe.throw("An unexpected error occurred while retrieving KSEB transformer options.")

    return {
        "section": result.section.__dict__,
        "transformers": [transformer.__dict__ for transformer in result.transformers],
    }


def _save_grid_capacity_result(lead, consumer_no, result, transformer):
    """Persist a verified bill or transformer-options result."""
    section_data = result.section.__dict__
    transformer_data = transformer.__dict__
    existing_name = frappe.db.get_value("KSEB Grid Check", {"lead": lead}, "name")
    doc = frappe.get_doc("KSEB Grid Check", existing_name) if existing_name else frappe.new_doc("KSEB Grid Check")
    doc.lead = lead
    doc.consumer_no = consumer_no
    doc.transformer_name = transformer_data.get("transformer_name")
    doc.allowed_cap = transformer_data.get("allowed_cap")
    doc.regi = transformer_data.get("regi")
    doc.comp_cap = transformer_data.get("comp_cap")
    doc.balance_available = transformer_data.get("balance_available")
    doc.grid_availability = "Available" if (doc.balance_available or 0) > 0 else "Not Available"

    doc.section = section_data.get("section")
    doc.section_code = section_data.get("office_code")
    doc.section_phone = section_data.get("phone")
    doc.section_email = section_data.get("email")
    doc.subdivision = section_data.get("subdivision")
    doc.subdivision_email = section_data.get("subdivision_email")
    doc.division = section_data.get("division")
    doc.division_phone = section_data.get("division_phone")
    doc.division_email = section_data.get("division_email")
    if not doc.customer_email:
        doc.customer_email = frappe.db.get_value("Lead", lead, "email_id")
    doc.last_checked = now_datetime()

    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return {"name": doc.name, "data": doc.as_dict()}


@frappe.whitelist()
def save_grid_capacity_option(lead, consumer_no, transformer_data, section_data):
    """Save the transformer and section selected from a fetched options list."""
    if not lead:
        frappe.throw("Lead is required")
    if not consumer_no:
        frappe.throw("Consumer Number and Transformer are required")

    transformer_data = frappe.parse_json(transformer_data)
    section_data = frappe.parse_json(section_data)
    if not isinstance(transformer_data, dict) or not isinstance(section_data, dict):
        frappe.throw("Invalid KSEB transformer selection")
    if not transformer_data.get("transformer_name"):
        frappe.throw("Select a transformer from the returned options")

    existing_name = frappe.db.get_value("KSEB Grid Check", {"lead": lead}, "name")
    doc = frappe.get_doc("KSEB Grid Check", existing_name) if existing_name else frappe.new_doc("KSEB Grid Check")
    doc.lead = lead
    doc.consumer_no = consumer_no
    doc.registered_mobile = ""
    doc.transformer_name = transformer_data.get("transformer_name")
    doc.allowed_cap = transformer_data.get("allowed_cap")
    doc.regi = transformer_data.get("regi")
    doc.comp_cap = transformer_data.get("comp_cap")
    doc.balance_available = transformer_data.get("balance_available")
    doc.grid_availability = "Available" if (doc.balance_available or 0) > 0 else "Not Available"

    doc.section = section_data.get("section")
    doc.section_code = section_data.get("office_code")
    doc.section_phone = section_data.get("phone")
    doc.section_email = section_data.get("email")
    doc.subdivision = section_data.get("subdivision")
    doc.subdivision_email = section_data.get("subdivision_email")
    doc.division = section_data.get("division")
    doc.division_phone = section_data.get("division_phone")
    doc.division_email = section_data.get("division_email")
    if not doc.customer_email:
        doc.customer_email = frappe.db.get_value("Lead", lead, "email_id")
    doc.last_checked = now_datetime()

    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return {"name": doc.name, "data": doc.as_dict()}


@frappe.whitelist()
def generate_annexure1(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 1)


@frappe.whitelist()
def generate_annexure2(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 2)


@frappe.whitelist()
def generate_annexure3(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 3)
