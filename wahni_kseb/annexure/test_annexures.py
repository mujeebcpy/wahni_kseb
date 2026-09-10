import datetime
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfReader

from wahni_kseb.annexure.annexure1 import build_annexure1_data, fill_annexure1
from wahni_kseb.annexure.annexure2 import build_annexure2_data, fill_annexure2
from wahni_kseb.annexure.annexure3 import build_annexure3_data, fill_annexure3


class TestAnnexurePDFs(unittest.TestCase):
    def setUp(self):
        self.doc = SimpleNamespace(
            consumer_name="Test Consumer",
            consumer_no="1234567890123",
            phase="Single",
            registered_mobile="9876543210",
            customer_address="Test House\nThrissur",
            connected_load="4500",
            proposed_solar_capacity=5.5,
        )
        self.name_address = (
            "Test Consumer,1234567890123,Single\n9876543210\nTest House\nThrissur"
        )

    def read_generated_fields(self, number, data, fill_pdf):
        template = Path(__file__).parents[1] / "templates" / f"kseb-Annexure-{number}.pdf"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "annexure.pdf"
            fill_pdf(data, template, output)
            reader = PdfReader(output)
            self.assertEqual(len(reader.pages), len(PdfReader(template).pages))
            return {name: field.get("/V", "") for name, field in reader.get_fields().items()}

    def test_annexure1_consumer_details_are_preserved(self):
        fields = self.read_generated_fields(1, build_annexure1_data(self.doc), fill_annexure1)
        self.assertEqual(fields["name_address"], self.name_address)
        self.assertEqual(fields["connected_load"], "4500")
        self.assertEqual(fields["solar_capacity"], "5.5")

    def test_annexure2_fills_requested_fields_and_leaves_others_blank(self):
        with patch("wahni_kseb.annexure.annexure2.datetime.date") as date:
            date.today.return_value = datetime.datetime(2026, 9, 10).date()
            data = build_annexure2_data(self.doc)
        fields = self.read_generated_fields(2, data, fill_annexure2)
        self.assertEqual(fields, {
            "name_address_anx2": self.name_address,
            "connected_load_anx2": "",
            "solar_capacity_anx2": "5.5 kW",
            "component_details": "yes",
            "component_specification": "Production Meter: yes\nNet Meter : NO",
            "images_included": "Yes",
            "completion_date_anx2": "September 2026",
            "place_anx2": "",
            "date_anx2": "",
        })

    def test_annexure2_completion_month_changes_with_current_date(self):
        with patch("wahni_kseb.annexure.annexure2.datetime.date") as date:
            date.today.return_value = datetime.datetime(2027, 1, 1).date()
            self.assertEqual(build_annexure2_data(self.doc).completion_date_anx2, "January 2027")

    def test_annexure3_fills_requested_fields_and_leaves_others_blank(self):
        fields = self.read_generated_fields(3, build_annexure3_data(self.doc), fill_annexure3)
        self.assertEqual(fields, {
            "name_address_anx3": self.name_address,
            "solar_regno": "",
            "solar_capacity_anx3": "5.5 kW",
            "specification_anx3": "yes",
            "inspection_certificate": "",
            "place_anx3": "",
            "date_anx3": "",
        })
