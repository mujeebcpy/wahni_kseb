"""KSEB lookup endpoint tests with the KSEB client and database mocked; no site required."""
import unittest
from unittest.mock import MagicMock, patch

import frappe
from kseb_client import BillInfo, KSEBTurnstileError, SectionInfo, Transformer

from wahni_kseb import api


class Thrown(Exception):
    pass


def throw(message, *args, **kwargs):
    raise Thrown(message)


class Doc(frappe._dict):
    def __init__(self, *args, new=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._new = new
        self.saved = False

    def is_new(self):
        return self._new

    def set(self, key, value):
        self[key] = value

    def check_permission(self, permission):
        pass

    def insert(self):
        self.name = "KGC-0001"
        self.saved = True

    def save(self):
        self.saved = True

    def as_dict(self):
        return dict(self)


SECTION = SectionInfo(
    office_code="5668", section="Valappad", subdivision="Nattika", subdivision_email="sd@kseb.in",
    division="Irinjalakuda", division_phone="1", division_email="d@kseb.in", phone="0480-2837123",
    email="s@kseb.in",
)
BILL = BillInfo(
    consumer_no="1156680000000", consumer_name="Anil", section="Valappad", dtr="KUNJIPALLI",
    connected_load="5 kW", tariff="LT-1A", phase="Single Phase", customer_address="Valappad",
)
TRANSFORMER = Transformer(
    transformer_name="KUNJIPALLI", division="", sub_division="", allowed_cap=81.0, comp_cap=29.025,
    regi=0.0, balance_available=51.975, capacity_kva=100.0, as_on="28-10-2026 02:04 pm",
)


class TestKSEBLookup(unittest.TestCase):
    def setUp(self):
        self.lead = Doc(custom_kseb_consumer_no="1156680000000", custom_kseb_connected_mobile_no="9895672251")
        self.check = Doc(new=True)
        self.client = MagicMock()
        self.client.get_section.return_value = SECTION
        self.client.download_bill.return_value = b"%PDF"
        self.client.parse_bill.return_value = BILL
        self.client.get_transformer.return_value = TRANSFORMER

        def get_doc(doctype, name=None):
            return self.lead if doctype == "Lead" else self.check

        def get_value(doctype, filters, field):
            if doctype == "KSEB Grid Check":
                return None if self.check.is_new() else "KGC-0001"
            return "lead@example.com"

        db = MagicMock()
        db.get_value.side_effect = get_value
        patches = [
            patch.object(api.frappe, "get_doc", side_effect=get_doc),
            patch.object(api.frappe, "new_doc", side_effect=lambda doctype: self.check),
            patch.object(api.frappe, "db", db),
            patch.object(api.frappe, "throw", side_effect=throw),
            patch.object(api.frappe, "log_error"),
            patch.object(api, "KSEBClient", return_value=self.client),
            patch.object(api, "now_datetime", return_value="2026-10-28 15:00:00"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_bill_step_saves_section_and_bill_from_lead_details(self):
        result = api.fetch_bill_details("LEAD-1", "abcd", "session")

        self.client.download_bill.assert_called_once_with(
            "1156680000000", "9895672251", captcha_code="abcd", session_id="session"
        )
        self.assertTrue(self.check.saved)
        self.assertEqual(result["data"]["lookup_method"], "Bill")
        self.assertEqual(self.check.consumer_name, "Anil")
        self.assertEqual(self.check.phase, "Single")
        self.assertEqual(self.check.section_code, "5668")
        self.assertIsNone(self.check.transformer_name)

    def test_transformer_step_after_bill_reuses_saved_section(self):
        self.check = Doc(new=False, consumer_no="1156680000000", section_code="5668", lookup_method="Bill")

        api.fetch_transformer_capacity("LEAD-1", "token")

        self.client.get_section.assert_not_called()
        self.client.get_transformer.assert_called_once_with("1156680000000", turnstile_token="token")
        self.assertEqual(self.check.lookup_method, "Bill")
        self.assertEqual(self.check.balance_available, 51.975)
        self.assertEqual(self.check.transformer_capacity_kva, 100.0)
        self.assertEqual(self.check.kseb_as_on, "28-10-2026 02:04 pm")
        self.assertEqual(self.check.grid_availability, "Available")

    def test_without_bill_fetches_section_and_does_not_need_mobile(self):
        self.lead.custom_kseb_connected_mobile_no = ""

        api.fetch_transformer_capacity("LEAD-1", "token", without_bill=1)

        self.client.get_section.assert_called_once_with("1156680000000")
        self.assertEqual(self.check.lookup_method, "Without Bill")
        self.assertEqual(self.check.section, "Valappad")
        self.assertTrue(self.check.saved)

    def test_rejected_turnstile_token_shows_kseb_message_and_saves_nothing(self):
        self.client.get_transformer.side_effect = KSEBTurnstileError(
            "Turnstile verification failed: Verification failed. Complete the Cloudflare check again."
        )

        with self.assertRaises(Thrown) as ctx:
            api.fetch_transformer_capacity("LEAD-1", "used-token", without_bill=1)

        self.assertIn("Turnstile verification failed", str(ctx.exception))
        self.assertFalse(self.check.saved)

    def test_lead_without_consumer_number_is_rejected(self):
        self.lead.custom_kseb_consumer_no = ""

        with self.assertRaises(Thrown) as ctx:
            api.fetch_transformer_capacity("LEAD-1", "token", without_bill=1)

        self.assertIn("Consumer Number on the Lead", str(ctx.exception))
        self.client.get_transformer.assert_not_called()

    def test_bill_details_of_a_previous_consumer_are_cleared(self):
        self.check = Doc(new=False, consumer_no="1156689999999", consumer_name="Old", registered_mobile="9000000000")

        api.fetch_transformer_capacity("LEAD-1", "token", without_bill=1)

        self.assertEqual(self.check.consumer_no, "1156680000000")
        self.assertIsNone(self.check.consumer_name)
        self.assertIsNone(self.check.registered_mobile)


if __name__ == "__main__":
    unittest.main()
