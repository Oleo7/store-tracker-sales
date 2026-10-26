"""PR5 calendar-only contracts for Store Tracker Sales.

These tests deliberately emulate a legacy column still present in the separate
test Sheet, then prove it is never a scheduling source or write target.
All data, API calls and users are synthetic; no live Sheet or Render service.
"""
from copy import deepcopy

import app as app_module
from test_planning import PlanningApiTestCase

CID = "11111111-1111-4111-8111-111111111111"


class CalendarOnlyFollowupTests(PlanningApiTestCase):
    def legacy_date(self, value="2026-07-25"):
        """Model a physically present old column without adding it to the contract."""
        sheet = self.spreadsheet.worksheet("sales_activities")
        self.append_contact_row(
            customer_id=CID, contact_id="historic-contact",
            date_time="2026-07-20 09:00", follow_up_date=value,
        )
        sheet.values[0].append("follow_up_date")
        for row in sheet.values[1:]:
            row.append(value)
        return sheet

    def test_old_contact_date_is_inert_in_attention_insights_and_calendar(self):
        sheet = self.legacy_date()
        before = deepcopy(sheet.get_all_values())
        state = app_module.customer_state_snapshot(self.spreadsheet)
        self.assertEqual(state["obligations"], {})
        attention = self.client.get("/planning/attention?user_name=olle")
        self.assertEqual(attention.status_code, 200, attention.get_json())
        self.assertEqual(attention.get_json()["total"], 0)
        planning = self.client.get("/planning/activities?start=2026-07-24&end=2026-08-02")
        self.assertEqual(planning.status_code, 200, planning.get_json())
        self.assertEqual(planning.get_json()["activities"], [])
        self.assertNotIn("unscheduled_followups", planning.get_json())
        stats = self.client.get("/customers/Butik%20A/stats")
        self.assertEqual(stats.status_code, 200, stats.get_json())
        self.assertIsNone(stats.get_json()["next_follow_up"])
        self.assertEqual(sheet.get_all_values(), before)

    def test_contact_creates_one_real_calendar_followup_and_no_date_column(self):
        payload = {
            "customer_id": CID, "date_time": "2026-07-27 09:00",
            "contact_channel": "Telefon", "result": "Positiv",
            "comment": "Bokade nästa samtal", "client_request_id": "pr5-contact-calendar-1",
            "follow_up": {
                "enabled": True, "contact_type": "phone",
                "scheduled_at": "2026-08-01T10:30:00+02:00",
                "note": "Följ upp", "appointment_confirmed": False,
            },
        }
        first = self.client.post("/customers/Butik%20A/contacts", json=payload)
        self.assertIn(first.status_code, (200, 201), first.get_json())
        second = self.client.post("/customers/Butik%20A/contacts", json=payload)
        self.assertEqual(second.status_code, 200, second.get_json())
        self.assertEqual(len(self.contact_rows()), 1)
        self.assertEqual(len(self.planning_rows()), 1)
        contact = self.contact_rows()[0]
        plan = self.planning_rows()[0]
        self.assertNotIn("follow_up_date", app_module.CONTACT_COLUMNS)
        self.assertNotIn("follow_up_date", contact)
        self.assertEqual(plan["source"], "follow_up")
        self.assertEqual(plan["source_contact_id"], contact["contact_id"])
        self.assertEqual(plan["scheduled_at"], "2026-08-01T10:30+02:00")
        self.assertEqual(plan["status"], "planned")
        stats = self.client.get("/customers/Butik%20A/stats")
        self.assertEqual(stats.status_code, 200, stats.get_json())
        self.assertEqual(stats.get_json()["next_follow_up"]["source"], "planned_activity")

    def test_calendar_reschedule_does_not_modify_old_contact_date(self):
        sheet = self.legacy_date("2026-07-24")
        plan = self.append_planning_row(
            planned_activity_id="pr5-move-1",
            source="follow_up", source_contact_id="historic-contact",
            scheduled_at="2026-08-01T10:00:00+02:00",
        )
        before = deepcopy(sheet.get_all_values())
        response = self.client.patch("/planning/activities/pr5-move-1", json={
            "client_request_id": "pr5-patch-1",
            "expected_revision": 1,
            "scheduled_at": "2026-08-02T11:00:00+02:00",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.planning_rows()[0]["scheduled_at"], "2026-08-02T11:00+02:00")
        self.assertEqual(sheet.get_all_values(), before)
        self.assertEqual(sheet.batch_update_count, 0)
        self.assertEqual(sheet.update_cell_count, 0)

    def test_raw_follow_up_date_input_cannot_create_a_calendar_promise(self):
        payload = {
            "customer_id": CID, "date_time": "2026-07-27 09:00",
            "contact_channel": "Telefon", "result": "Neutral",
            "comment": "Legacy payload should be ignored",
            "client_request_id": "pr5-old-field-only",
            "follow_up_date": "2026-07-28",
            "follow_up": {"enabled": False},
        }
        response = self.client.post("/customers/Butik%20A/contacts", json=payload)
        self.assertIn(response.status_code, (200, 201), response.get_json())
        self.assertEqual(len(self.planning_rows()), 0)
        self.assertEqual(len(self.contact_rows()), 1)
        self.assertNotIn("follow_up_date", self.contact_rows()[0])

    def test_only_real_missed_calendar_activity_reaches_attention_and_skip(self):
        self.legacy_date("2026-07-25")
        first = self.client.get("/planning/attention?user_name=olle")
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertEqual(first.get_json()["total"], 0)
        self.append_planning_row(
            planned_activity_id="pr5-missed-calendar",
            scheduled_at="2026-07-25T09:00:00+02:00",
            created_at="2026-07-20T09:00:00+02:00",
        )
        second = self.client.get("/planning/attention?user_name=olle")
        self.assertEqual(second.status_code, 200, second.get_json())
        self.assertEqual(second.get_json()["total"], 1)
        self.assertEqual(second.get_json()["items"][0]["item_type"], "missed_calendar_activity")
        response = self.client.patch("/planning/activities/pr5-missed-calendar", json={
            "client_request_id": "pr5-skip-1", "expected_revision": 1, "status": "skipped",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        final = self.client.get("/planning/attention?user_name=olle")
        self.assertEqual(final.status_code, 200, final.get_json())
        self.assertEqual(final.get_json()["total"], 0)

    def test_retired_virtual_obligation_endpoint_cannot_write(self):
        before = deepcopy({key: sheet.get_all_values() for key, sheet in self.spreadsheet.sheets.items()})
        response = self.client.post("/customer-obligations/action", json={
            "customer_id": CID, "action": "reschedule",
            "obligation_id": "followup:historic-contact",
            "client_request_id": "pr5-retired-endpoint",
        })
        self.assertEqual(response.status_code, 404, response.get_json())
        self.assertEqual(
            {key: sheet.get_all_values() for key, sheet in self.spreadsheet.sheets.items()},
            before,
        )
