import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web-app"))
import app as app_module
from crm_utils import USER_COLUMNS, split_email_values

class FakeWorksheet:
    def __init__(self, title, headers, rows=None):
        self.title = title
        self.values = [list(headers)] + [
            [row.get(header, "") for header in headers] if isinstance(row, dict) else list(row)
            for row in (rows or [])
        ]

    def get_all_values(self):
        return [list(row) for row in self.values]

    def row_values(self, row):
        return list(self.values[row - 1]) if 0 < row <= len(self.values) else []

    def append_row(self, values, value_input_option=None):
        self.values.append(list(values))

    def append_rows(self, values, value_input_option=None):
        self.values.extend([list(row) for row in values])

    def update_cell(self, row, column, value):
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < column:
            self.values[row - 1].append("")
        self.values[row - 1][column - 1] = value

    def update(self, range_name, values):
        # Only header expansion is needed by the application helpers.
        if range_name.startswith("A1:"):
            self.values[0] = list(values[0])

    def batch_update(self, data, value_input_option=None):
        for item in data:
            match = __import__("re").match(
                r"([A-Z]+)(\d+):([A-Z]+)(\d+)", item["range"]
            )
            if not match:
                continue
            first_column, first_row, _last_column, _last_row = match.groups()
            column_number = 0
            for character in first_column:
                column_number = column_number * 26 + ord(character) - ord("A") + 1
            for row_offset, values in enumerate(item["values"]):
                for column_offset, value in enumerate(values):
                    self.update_cell(
                        int(first_row) + row_offset,
                        column_number + column_offset,
                        value,
                    )

class FakeSpreadsheet:
    def __init__(self, sheets):
        self.sheets = {sheet.title: sheet for sheet in sheets}

    def worksheet(self, title):
        try:
            return self.sheets[title]
        except KeyError as error:
            raise app_module.WorksheetNotFound(title) from error

RECORD_COLUMNS = ["record_id", "customer", "status", "kind"]
EVENT_COLUMNS = ["event_key", "event_type"]

class CrmUtilityTests(unittest.TestCase):
    def test_append_dict_row_starts_in_column_a_despite_blank_and_orphan_rows(self):
        sheet = FakeWorksheet("records", RECORD_COLUMNS)
        sheet.values.append([])
        sheet.values.append(
            [""] * (len(RECORD_COLUMNS) - 1) + ["orphaned-kind"]
        )

        row_index = app_module.append_dict_row(sheet, RECORD_COLUMNS, {
            "record_id": "mail-live-1",
            "customer": "Coop Test",
            "status": "pending",
            "kind": "reactivation",
        })

        self.assertEqual(row_index, 4)
        self.assertEqual(sheet.values[3][0], "mail-live-1")
        self.assertEqual(sheet.values[3][1], "Coop Test")
        self.assertEqual(
            sheet.values[3][RECORD_COLUMNS.index("kind")],
            "reactivation",
        )
        self.assertEqual(len(sheet.values[3]), len(RECORD_COLUMNS))

    def test_append_dict_rows_writes_a_contiguous_explicit_range(self):
        sheet = FakeWorksheet("events", EVENT_COLUMNS)
        row_indexes = app_module.append_dict_rows(
            sheet,
            EVENT_COLUMNS,
            [
                {"event_key": "event-1", "event_type": "sent"},
                {"event_key": "event-2", "event_type": "delivered"},
            ],
        )

        self.assertEqual(row_indexes, [2, 3])
        self.assertEqual(sheet.values[1][0], "event-1")
        self.assertEqual(sheet.values[2][0], "event-2")
        self.assertEqual(
            sheet.values[2][EVENT_COLUMNS.index("event_type")],
            "delivered",
        )

    def test_recipient_values_are_split_validated_and_deduplicated(self):
        result = split_email_values(
            "Buyer@Example.com; info@example.com\ninvalid",
            "buyer@example.com, second@example.se",
        )
        self.assertEqual(
            [item["email"] for item in result],
            ["Buyer@Example.com", "info@example.com", "invalid", "second@example.se"],
        )
        self.assertEqual([item["valid"] for item in result], [True, True, False, True])

class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        users = FakeWorksheet("users", USER_COLUMNS, [
            {"user_name": "olle", "name": "Olle", "role": "Account Manager", "email": "olle@eatpolarbar.com", "phone": "070", "password": "ExactPass", "active": "Y"},
            {"user_name": "inactive", "name": "Inaktiv", "role": "Säljare", "email": "inactive@polarbar.se", "phone": "", "password": "pass", "active": "N"},
        ])
        self.spreadsheet = FakeSpreadsheet([users])
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.patcher = patch.object(app_module, "get_spreadsheet_with_retry", return_value=self.spreadsheet)
        self.patcher.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.patcher.stop()

    def test_login_is_case_insensitive_for_username_and_exact_for_password(self):
        response = self.client.post("/login", json={"user_name": "OLLE", "password": "ExactPass"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["name"], "Olle")
        self.assertIn("HttpOnly", response.headers.get("Set-Cookie", ""))
        session_response = self.client.get("/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertTrue(session_response.get_json()["authenticated"])

        self.client.post("/logout")
        self.assertEqual(self.client.get("/session").status_code, 401)

    def test_wrong_password_and_inactive_user_are_rejected(self):
        wrong = self.client.post("/login", json={"user_name": "olle", "password": "exactpass"})
        inactive = self.client.post("/login", json={"user_name": "inactive", "password": "pass"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(inactive.status_code, 401)
