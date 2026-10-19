"""Native annexure dispatch and saved-data regression tests; no site required."""
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jinja2 import Environment
import frappe

from wahni_kseb.annexure import printing


class Grid(frappe._dict):
    def check_permission(self, permission):
        pass

    def as_dict(self):
        return dict(self)


class TestNativeAnnexures(unittest.TestCase):
    def test_dates_and_choices_come_from_saved_grid_fields(self):
        grid = Grid(consumer_name="അനിൽ കുമാർ", consumer_no="123", proposed_solar_capacity=5.5,
                    date_anx1="2026-09-01", completion_date_anx2="2027-02-03", is_rooftop="Ground mounted")
        values = printing.print_context(grid)
        self.assertEqual(values["date_anx1"], "01/09/2026")
        self.assertEqual(values["date_anx2"], "")
        self.assertEqual(values["completion_date_anx2"], "February 2027")
        self.assertEqual(values["completion_date"], printing.month_year())
        self.assertEqual(printing.month_year("October 2026"), "October 2026")
        self.assertEqual(values["capacity"], "5.5 kW")
        self.assertIn("അനിൽ കുമാർ", values["name_address"])
        self.assertIn("data:font/ttf;base64", values["font_css"])
        root = Path(__file__).resolve().parents[1]
        for path in (root / "kseb_grid_data/print_format").glob("*/*.json"):
            fmt = json.loads(path.read_text())
            grid.annexure_context = values
            rendered = Environment().from_string(fmt["html"]).render(doc=grid)
            if fmt["name"] == "KSEB Annexure I":
                self.assertIn("Ground mounted", rendered)
            self.assertNotIn("None", rendered)

    def test_generate_selects_format_and_private_attachment_for_each_number(self):
        for number, print_format in printing.PRINT_FORMATS.items():
            grid = Grid(doctype="KSEB Grid Check", name="G", consumer_name="Name", consumer_no="123",
                        proposed_solar_capacity=5, annexure_context={"font_css": "font", "capacity": "5 kW"})
            with patch.object(printing, "frappe") as fake, \
                    patch.object(printing, "save_file", return_value=Grid(file_url="/private/files/new.pdf", file_name="new.pdf")) as save:
                fake.get_doc.return_value = grid
                fake.get_print.return_value = b"native-pdf"
                result = printing.generate_annexure("G", number)
                self.assertEqual(fake.get_print.call_args.kwargs["print_format"], print_format)
                self.assertTrue(fake.get_print.call_args.kwargs["as_pdf"])
                self.assertEqual(save.call_args.args[1:], (b"native-pdf", "KSEB Grid Check", "G"))
                self.assertTrue(save.call_args.kwargs["is_private"])
                self.assertEqual(result["file_url"], "/private/files/new.pdf")
                self.assertNotIn("font_css", result["resolved_inputs"]["values"])

    def test_missing_capacity_does_not_render(self):
        with patch.object(printing, "frappe") as fake:
            fake.get_doc.return_value = Grid(consumer_name="Name", consumer_no="123")
            fake.throw.side_effect = ValueError
            with self.assertRaises(ValueError):
                printing.generate_annexure("G", 3)
            fake.get_print.assert_not_called()
