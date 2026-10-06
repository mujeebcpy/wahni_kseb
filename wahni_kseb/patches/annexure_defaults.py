import frappe


def execute():
    defaults = {'is_rooftop': 'Rooftop', 'usein_otherplaces': 'No', 'tod_bill': 'No', 'place_anx1': 'Thalikulam', 'component_details': 'Yes', 'component_specification': 'Production Meter: yes\nNet Meter: NO', 'images_included': 'Yes', 'specification_anx3': 'Yes'}
    for name in frappe.get_all("KSEB Grid Check", pluck="name"):
        doc = frappe.get_doc("KSEB Grid Check", name)
        values = {key: value for key, value in defaults.items() if not doc.get(key)}
        if values:
            frappe.db.set_value(doc.doctype, name, values, update_modified=False)
