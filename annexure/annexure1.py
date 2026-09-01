from dataclasses import dataclass
from pathlib import Path
import datetime

from pypdf import PdfReader, PdfWriter


@dataclass
class Annexure1Data:
    """Data required to fill KSEB Annexure-1."""

    name_address: str
    connected_load: str
    solar_capacity: str
    usein_otherplaces: str = "No"
    tod_bill: str = "No"
    is_rooftop: str = "Rooftop"
    completion_date: str = ""
    place_anx1: str = ""
    date_anx1: str = ""


def fill_annexure1(
    data: Annexure1Data,
    template: str | Path,
    output: str | Path,
) -> None:
    """Fill the KSEB Annexure-1 PDF."""

    reader = PdfReader(template)
    writer = PdfWriter()

    writer.append(reader)

    writer.update_page_form_field_values(
        writer.pages[0],
        {
            "name_address": data.name_address,
            "connected_load": data.connected_load,
            "solar_capacity": data.solar_capacity,
            "usein_otherplaces": data.usein_otherplaces,
            "tod_bill": data.tod_bill,
            "is_rooftop": data.is_rooftop,
            "completion_date": data.completion_date,
            "place_anx1": data.place_anx1,
            "date_anx1": data.date_anx1,
        },
    )

    with open(output, "wb") as fp:
        writer.write(fp)


def build_annexure1_data(doc) -> Annexure1Data:
    """Build Annexure-1 data from a KSEB Grid Check document."""

    name_address = (
        f"{doc.consumer_name},{doc.consumer_no},{doc.phase}\n"
        f"{doc.registered_mobile}\n"
        f"{doc.customer_address}"
    )

    return Annexure1Data(
        name_address=name_address,
        connected_load=str(doc.connected_load or ""),
        solar_capacity=str(doc.proposed_solar_capacity or ""),
        usein_otherplaces="No",
        tod_bill="No",
        is_rooftop="Rooftop",
        completion_date="",
        place_anx1="Thalikulam",
        date_anx1=datetime.date.today().strftime("%d/%m/%Y"),
    )