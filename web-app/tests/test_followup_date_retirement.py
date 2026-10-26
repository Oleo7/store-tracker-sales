"""PR5: no operational follow-ups may originate from sales_activities.follow_up_date.

These negative contracts deliberately test the shipped code, independent of
whether historical rows remain in the copied Google Sheet.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CalendarOnlyFollowupContractTests(unittest.TestCase):
    def test_contact_schema_does_not_require_or_write_legacy_date(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('"follow_up_date"', source)
        self.assertNotIn("sync_planned_followup_mirror", source)
        self.assertNotIn("sync_followup_date_to_source_contact", source)
        self.assertIn('PLANNED_ACTIVITIES_SHEET = "planned_activities"', source)
        self.assertIn('"source_contact_id":', source)

    def test_no_virtual_followups_from_sales_history(self):
        source = (ROOT / "customer_obligations.py").read_text(encoding="utf-8")
        self.assertNotIn('row.get("follow_up_date")', source)
        self.assertNotIn("classify_legacy_completed_followups", source)
        self.assertIn('for row in plans:', source)

    def test_priority_and_coaching_never_read_contact_date(self):
        for file in ("priority.py", "sales_coaching.py"):
            source = (ROOT / file).read_text(encoding="utf-8")
            self.assertNotIn('row.get("follow_up_date")', source, file)
            self.assertNotIn('contact.get("follow_up_date")', source, file)

    def test_frontend_creates_real_calendar_activity_not_mirrored_date(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('follow_up_date:', html)
        self.assertIn('follow_up: followupEnabled ? {', html)
        self.assertIn('scheduled_at: followupScheduledAt', html)


from datetime import datetime
from zoneinfo import ZoneInfo

from test_planning import PlanningApiTestCase, NOW
import app as application
from customer_obligations import build_customer_state
from priority import build_priority_customers, build_order_features, build_contact_features


class CalendarOnlyModelTests(unittest.TestCase):
    def test_historical_contact_date_never_becomes_a_promise(self):
        cid = "11111111-1111-4111-8111-111111111111"
        customers = [{"customer_id": cid, "customer": "Butik A",
                      "sales_person": "Olle", "customer_segment": "A", "row": 2}]
        contact = {
            "customer_id": cid, "customer": "Butik A", "contact_id": "source",
            "date_time": "2026-07-20T09:00:00+02:00",
            "recorded_at": "2026-07-20T09:00:00+02:00",
            "result": "Positiv", "contact_channel": "Telefon",
            "follow_up_date": "2026-07-25",
        }
        now = datetime(2026, 7, 28, 12, tzinfo=ZoneInfo("Europe/Stockholm"))
        without = build_customer_state(customers, [contact], [], as_of=now)
        self.assertFalse(without["obligations"].get(cid))
        plan = {
            "planned_activity_id": "calendar-one", "customer_id": cid,
            "customer": "Butik A", "user_name": "olle",
            "scheduled_at": "2026-07-29T10:00:00+02:00",
            "created_at": "2026-07-20T09:01:00+02:00",
            "source": "follow_up", "source_contact_id": "source",
            "contact_type": "phone", "status": "planned",
        }
        with_plan = build_customer_state(customers, [contact], [plan], as_of=now)
        self.assertEqual(len(with_plan["obligations"].get(cid, [])), 1)
        item = with_plan["obligations"][cid][0]
        self.assertEqual(item["planned_activity_id"], "calendar-one")
        self.assertEqual(item["due_date"], "2026-07-29")

    def test_old_date_does_not_change_commercial_priority(self):
        cid = "11111111-1111-4111-8111-111111111111"
        customer = {"customer_id": cid, "customer": "Butik A",
                    "sales_person": "Olle", "customer_segment": "A",
                    "phone": "0701234567", "row": 2}
        now = datetime(2026, 7, 28, 12, tzinfo=ZoneInfo("Europe/Stockholm"))
        base = {"customer_id": cid, "customer": "Butik A", "contact_id": "source",
                "date_time": "2026-07-20T09:00:00+02:00",
                "recorded_at": "2026-07-20T09:00:00+02:00",
                "result": "Positiv", "contact_channel": "Telefon"}
        orders = build_order_features([], customers=[customer], as_of=now)
        def priority(row):
            features = build_contact_features([row], orders, customers=[customer], as_of=now)
            return build_priority_customers([customer], orders, features, None,
                now.date(), now=now, planned_activities=[])[0]
        with_date = priority({**base, "follow_up_date": "2026-07-25"})
        clean = priority(base)
        for field in ("priority_score", "work_priority_raw", "recommendation_eligible"):
            self.assertEqual(with_date[field], clean[field], field)
        self.assertEqual(with_date["customer_guidance"], clean["customer_guidance"])


class CalendarOnlyFollowupApiTests(PlanningApiTestCase):
    def setUp(self):
        super().setUp()
        application.stockholm_now.return_value = NOW.replace(day=28)
        application.stockholm_today.return_value = NOW.replace(day=28).date()

    def test_contact_and_followup_have_one_calendar_link_on_retry(self):
        original = self.append_planning_row(planned_activity_id="pr5-source", contact_type="phone",
            scheduled_at="2026-07-28T09:00:00+02:00")
        payload = {
            "client_request_id": "pr5-calendar-only",
            "planned_activity_id": original["planned_activity_id"],
            "date_time": "2026-07-28 09:10",
            "contact_channel": "Telefon", "result": "Positiv",
            "comment": "Kalenderbokad uppföljning",
            "follow_up": {"enabled": True, "contact_type": "phone",
                          "scheduled_at": "2026-08-01T11:00:00+02:00",
                          "note": "Ring igen"},
        }
        first = self.client.post("/customers/Butik%20A/contacts", json=payload)
        second = self.client.post("/customers/Butik%20A/contacts", json=payload)
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertEqual(second.status_code, 200, second.get_json())
        self.assertTrue(second.get_json()["duplicate"])
        contacts = self.contact_rows()
        self.assertEqual(len(contacts), 1)
        self.assertNotIn("follow_up_date", contacts[0])
        calendar = [a for a in self.planning_rows() if a.get("source") == "follow_up"]
        self.assertEqual(len(calendar), 1)
        self.assertEqual(calendar[0]["source_contact_id"], contacts[0]["contact_id"])
        self.assertEqual(calendar[0]["scheduled_at"], "2026-08-01T11:00+02:00")

    def test_duplicate_source_id_across_customers_cannot_create_followup(self):
        cid = "11111111-1111-4111-8111-111111111111"
        foreign = "22222222-2222-4222-8222-222222222222"
        self.append_contact_row(contact_id="shared-source", customer_id=cid,
                                customer="Butik A")
        self.append_contact_row(contact_id="shared-source", customer_id=foreign,
                                customer="Butik B", sales_person="Sofia")
        before_contacts = [dict(row) for row in self.contact_rows()]
        response = self.client.post("/planning/activities", json={
            "client_request_id": "pr5-cross-customer-source",
            "customer_id": cid,
            "source": "follow_up",
            "source_contact_id": "shared-source",
            "scheduled_at": "2026-08-01T10:00:00+02:00",
            "contact_type": "phone",
        })
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(response.get_json()["code"], "follow_up_source_not_found")
        self.assertEqual(self.planning_rows(), [])
        self.assertEqual(self.contact_rows(), before_contacts)

    def test_foreign_source_id_cannot_be_attached_to_customer(self):
        self.append_contact_row(
            contact_id="foreign-only",
            customer_id="22222222-2222-4222-8222-222222222222",
            customer="Butik B", sales_person="Sofia",
        )
        response = self.client.post("/planning/activities", json={
            "client_request_id": "pr5-foreign-source",
            "customer_id": "11111111-1111-4111-8111-111111111111",
            "source": "follow_up",
            "source_contact_id": "foreign-only",
            "scheduled_at": "2026-08-01T10:00:00+02:00",
            "contact_type": "phone",
        })
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertEqual(self.planning_rows(), [])

    def test_reschedule_never_modifies_retained_legacy_sheet_date(self):
        cid = "11111111-1111-4111-8111-111111111111"
        self.append_contact_row(contact_id="source-calendar", customer_id=cid)
        sheet = self.spreadsheet.worksheet("sales_activities")
        self.assertNotIn("follow_up_date", sheet.values[0])
        sheet.values[0].append("follow_up_date")
        for row in sheet.values[1:]:
            row.append("2026-07-25")
        before = [dict(row) for row in self.contact_rows()]
        activity = self.append_planning_row(
            planned_activity_id="pr5-calendar-reschedule",
            source="follow_up", source_contact_id="source-calendar",
            scheduled_at="2026-08-01T09:00:00+02:00",
        )
        response = self.client.patch("/planning/activities/pr5-calendar-reschedule", json={
            "client_request_id": "pr5-calendar-move",
            "expected_revision": activity["revision"],
            "scheduled_at": "2026-08-03T11:00:00+02:00",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.planning_rows()[0]["scheduled_at"], "2026-08-03T11:00+02:00")
        self.assertEqual(self.contact_rows(), before)

    def test_legacy_date_input_without_calendar_request_is_inert(self):
        payload = {"client_request_id": "pr5-ignored-date",
                   "date_time": "2026-07-28 09:10",
                   "contact_channel": "Telefon", "result": "Positiv",
                   "comment": "Inget nytt uppföljningsärende",
                   "follow_up_date": "2026-08-02"}
        response = self.client.post("/customers/Butik%20A/contacts", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.planning_rows(), [])
        self.assertNotIn("follow_up_date", self.contact_rows()[0])


if __name__ == "__main__":
    unittest.main()
