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


if __name__ == "__main__":
    unittest.main()
