# Copyright (c) 2026, Wahni and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from wahni_kseb.annexure.printing import print_context, set_completion_month


class KSEBGridCheck(Document):
    def validate(self):
        set_completion_month(self)

    def before_print(self, print_settings=None):
        self.annexure_context = print_context(self)
