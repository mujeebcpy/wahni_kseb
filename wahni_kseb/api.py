import frappe
from frappe.utils import now_datetime
from kseb_client import KSEBClient, KSEBValidationError, KSEBClientError
from wahni_kseb.annexure.printing import generate_annexure

@frappe.whitelist()
def check_grid_capacity(lead, consumer_no, registered_mobile):
    if not lead:
        frappe.throw("Lead is required")

    if not consumer_no:
        frappe.throw("Consumer Number is required")

    if not registered_mobile:
        frappe.throw("Registered Mobile is required")

    try:
        client = KSEBClient()

        result = client.get_grid_capacity(
            consumer_no=consumer_no,
            mobile=registered_mobile,
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
    last_checked = now_datetime()
    existing_name = frappe.db.get_value(
    "KSEB Grid Check",
    {"lead": lead},
    "name",
)

    if existing_name:
        doc = frappe.get_doc("KSEB Grid Check", existing_name)
    else:
        doc = frappe.new_doc("KSEB Grid Check")
        doc.lead = lead

    if result.transformer.balance_available > 0:
        grid_availability = "Available"
    else:
        grid_availability = "Not Available"

    # KSEB input
    doc.consumer_no = consumer_no
    doc.registered_mobile = registered_mobile
    if not doc.customer_email:
        doc.customer_email = frappe.db.get_value("Lead", lead, "email_id")

    # KSEB Consumer
    doc.consumer_name = result.bill.consumer_name
    doc.customer_address = result.bill.customer_address
    doc.tariff = result.bill.tariff
    doc.phase = result.bill.phase.split(" ")[0]
    doc.connected_load = result.bill.connected_load

    # KSEB Section
    doc.section = result.section.section
    doc.section_code = result.section.office_code
    doc.section_phone = result.section.phone
    doc.section_email = result.section.email
    doc.subdivision = result.section.subdivision
    doc.subdivision_email = result.section.subdivision_email
    doc.division = result.section.division
    doc.division_phone = result.section.division_phone
    doc.division_email = result.section.division_email

    # Transformer / Grid
    doc.transformer_name = result.transformer.transformer_name
    doc.allowed_cap = result.transformer.allowed_cap
    doc.regi = result.transformer.regi
    doc.comp_cap = result.transformer.comp_cap
    doc.balance_available = result.transformer.balance_available

    # Result
    doc.grid_availability = grid_availability
    doc.last_checked = last_checked

    # Save
    if doc.is_new():
        doc.insert()
    else:
        doc.save()

    return {
        "name": doc.name,
        "data": doc.as_dict(),
    }


@frappe.whitelist()
def generate_annexure1(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 1)


@frappe.whitelist()
def generate_annexure2(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 2)


@frappe.whitelist()
def generate_annexure3(kseb_grid_check):
    return generate_annexure(kseb_grid_check, 3)
