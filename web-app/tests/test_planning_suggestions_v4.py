from datetime import date, datetime, time
from pathlib import Path
import sys
from unittest.mock import patch


WEB_APP_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_APP_DIR))
sys.path.insert(0, str(TESTS_DIR))

import app as app_module  # noqa: E402
from planning_suggestions import SUGGESTIONS_SHEET  # noqa: E402
from test_planning import PlanningApiTestCase  # noqa: E402


class PlanningSuggestionV4IntegrationTests(PlanningApiTestCase):
    def setUp(self):
        super().setUp()
        app_module.app.config.pop("PLANNING_SUGGESTIONS_STUB", None)
        customer_sheet = self.spreadsheet.worksheet("customers_enriched")
        headers = customer_sheet.row_values(1)
        customer_col = headers.index("customer")
        cancelled_col = headers.index("cancelled_flag") + 1
        segment_col = headers.index("customer_segment") + 1
        for row_index, row in enumerate(customer_sheet.get_all_values()[1:], start=2):
            if row[customer_col] == "Butik A":
                customer_sheet.update_cell(row_index, segment_col, "C")
            else:
                customer_sheet.update_cell(row_index, cancelled_col, "Y")

    @staticmethod
    def clock(day):
        instant = datetime.combine(day, time(9, 0), tzinfo=app_module.STOCKHOLM_ZONE)
        return (
            patch.object(app_module, "stockholm_today", return_value=day),
            patch.object(app_module, "stockholm_now", return_value=instant),
        )


    def append_order(self, reference, delivered):
        row = {
            "Reference": reference, "Order date": delivered, "Delivery date": delivered,
            "Customer": "Butik A", "Customer number": "C-1",
            "customer_id": "11111111-1111-4111-8111-111111111111",
            "Quantity": "20", "Total weight": "20", "Total": "400",
        }
        self.spreadsheet.worksheet("order_rows").append_row(
            [row.get(column, "") for column in app_module.ORDER_COLUMNS]
        )

    def append_legacy_followup(self):
        row = {
            "contact_id": "legacy-source", "date_time": "2026-07-01 10:00:00",
            "sales_person": "Olle", "customer": "Butik A",
            "customer_id": "11111111-1111-4111-8111-111111111111",
            "contact_channel": "Telefon", "result": "Neutral",
            "follow_up_date": "2026-07-10",
            "follow_up_purpose": "customer_followup", "follow_up_agreement_confirmed": "Y",
        }
        self.spreadsheet.worksheet("sales_activities").append_row(
            [row.get(column, "") for column in app_module.CONTACT_COLUMNS]
        )


    def test_legacy_followup_is_suggestion_not_planned_activity(self):
        self.append_legacy_followup()
        today_patch, now_patch = self.clock(date(2026, 8, 2))
        with today_patch, now_patch:
            payload = self.client.get("/planning/suggestions").get_json()
        self.assertEqual(payload["suggestion"]["trigger_key"], "overdue_planned_activity")
        self.assertEqual(self.planning_rows(), [])


    def test_empty_calibration_export_is_read_only(self):
        before = set(self.spreadsheet.sheets)
        response = self.client.get("/planning/calibration-export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["rows"], [])
        self.assertEqual(set(self.spreadsheet.sheets), before)
