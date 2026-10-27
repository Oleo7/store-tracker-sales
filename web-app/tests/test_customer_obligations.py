"""Calendar-only follow-up contracts for the separate Store Tracker Sales."""
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from test_planning import PlanningApiTestCase, NOW
import app as app_module
from customer_obligations import build_customer_state, attention_items

CID = "11111111-1111-4111-8111-111111111111"


class CustomerObligationApiTests(PlanningApiTestCase):
    def test_retired_date_only_mutation_has_no_side_effects(self):
        before_plans = list(self.planning_rows())
        before_sheets = set(self.spreadsheet.sheets)
        response = self.client.post("/customer-obligations/action", json={
            "customer_id": CID, "obligation_id": "followup:old",
            "action": "reschedule", "client_request_id": "legacy-no-op",
            "scheduled_at": "2026-08-01T10:00:00+02:00",
        })
        self.assertEqual(response.status_code, 410, response.get_json())
        self.assertEqual(self.planning_rows(), before_plans)
        self.assertEqual(set(self.spreadsheet.sheets), before_sheets)

    def test_real_calendar_followup_is_single_obligation(self):
        self.append_contact_row(contact_id="source", customer_id=CID,
            date_time="2026-07-20 09:00", follow_up_date="2026-07-25")
        self.append_planning_row(planned_activity_id="real-calendar",
            source="follow_up", source_contact_id="source",
            scheduled_at="2026-07-25T09:00:00+02:00",
            created_at="2026-07-20T09:00:00+02:00")
        model = app_module.customer_state_snapshot(self.spreadsheet)
        items = model["obligations"].get(CID, [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["planned_activity_id"], "real-calendar")
        self.assertEqual(items[0]["source_contact_id"], "source")
        self.assertEqual(len(attention_items(model, as_of=NOW)), 1)

    def test_legacy_contact_date_alone_does_not_create_obligation(self):
        self.append_contact_row(contact_id="legacy", customer_id=CID,
            date_time="2026-07-20 09:00", follow_up_date="2026-07-25")
        model = app_module.customer_state_snapshot(self.spreadsheet)
        self.assertFalse(model["obligations"].get(CID))
        self.assertEqual(attention_items(model, as_of=NOW), [])

    def test_skipping_calendar_followup_does_not_rewrite_contact(self):
        self.append_contact_row(contact_id="source", customer_id=CID,
            date_time="2026-07-20 09:00")
        plan = self.append_planning_row(planned_activity_id="real-skip",
            source="follow_up", source_contact_id="source",
            scheduled_at="2026-07-25T09:00:00+02:00",
            created_at="2026-07-20T09:00:00+02:00")
        before_contacts = list(self.contact_rows())
        response = self.client.patch("/planning/activities/real-skip", json={
            "client_request_id": "skip-real-calendar",
            "expected_revision": plan["revision"], "status": "skipped",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.contact_rows(), before_contacts)
        self.assertEqual(self.planning_rows()[0]["status"], "skipped")

    def test_disabled_priority_returns_explicit_error(self):
        with patch.dict(app_module.app.config, {"VALUE_PRIORITY_ENABLED": False}):
            response = self.client.get("/customer-insights", headers={"X-PB-Value-Model": "v3.3"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["code"], "value_priority_disabled")

    def test_late_import_cannot_create_retroactive_followup(self):
        customers = app_module.get_customer_rows(self.spreadsheet)
        contact = {
            "customer_id": CID, "date_time": "2026-07-20 09:00",
            "recorded_at": "2026-07-28T09:00+02:00",
            "contact_id": "late-import", "result": "Återkom ej",
            "follow_up_date": "2026-07-24",
        }
        as_of = datetime(2026, 7, 27, 12, tzinfo=ZoneInfo("Europe/Stockholm"))
        model = build_customer_state(customers, [contact], [], as_of=as_of)
        self.assertEqual(model["obligations"], {})
        self.assertEqual(model["contact_permissions"], {})
