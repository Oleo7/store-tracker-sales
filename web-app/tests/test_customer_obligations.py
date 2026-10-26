from datetime import timedelta
import copy
import json
from unittest.mock import patch

from test_planning import PlanningApiTestCase, NOW
import app as app_module
from customer_obligations import build_customer_state, attention_items

CID = "11111111-1111-4111-8111-111111111111"


class CustomerObligationApiTests(PlanningApiTestCase):
    def source(self, contact_id="promise", due="2026-07-25", **extra):
        return self.append_contact_row(contact_id=contact_id, customer_id=CID,
                                       date_time="2026-07-20 09:00",
                                       follow_up_purpose="customer_followup", follow_up_agreement_confirmed="Y", **extra)

    def state(self):
        return app_module.customer_state_snapshot(self.spreadsheet)

    def test_feature_disabled_returns_explicit_model_error(self):
        with patch.dict(app_module.app.config, {"VALUE_PRIORITY_ENABLED": False}):
            response = self.client.get("/customer-insights", headers={"X-PB-Value-Model": "v3.3"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["code"], "value_priority_disabled")

    def test_recorded_after_as_of_cannot_introduce_permission_or_obligation(self):
        customers = app_module.get_customer_rows(self.spreadsheet)
        contact = {"customer_id": CID, "date_time": "2026-07-20 09:00", "recorded_at": "2026-07-28T09:00+02:00",
                   "contact_id": "late-import", "result": "Återkom ej", "follow_up_date": "2026-07-24"}
        state = build_customer_state(customers, [contact], [], as_of=NOW)
        self.assertEqual(state["obligations"], {})
        self.assertEqual(state["contact_permissions"], {})

    def test_old_scheduled_event_does_not_reopen_later_explicit_completion(self):
        self.source()
        plan = self.append_planning_row(planned_activity_id="linked", source="follow_up", source_contact_id="promise",
                                       scheduled_at="2026-07-25T08:00:00+02:00", status="completed", completed_contact_id="resolution")
        self.append_contact_row(contact_id="resolution", customer_id=CID, date_time="2026-07-27 09:00", follow_up_date="",
                                planned_activity_id="linked", obligation_id="followup:promise", obligation_outcome="resolved")
        event = {"event_id": "old-event", "kind": "obligation", "entity_id": "followup:promise", "customer_id": CID,
                 "revision": 2, "occurred_at": "2026-07-23T10:00+02:00",
                 "payload_json": json.dumps({"status": "scheduled", "planned_activity_id": "linked"})}
        state = build_customer_state(app_module.get_customer_rows(self.spreadsheet), self.contact_rows(), [plan], [event], as_of=NOW)
        self.assertEqual(state["obligations"][CID][0]["status"], "resolved")
        self.assertEqual(attention_items(state, as_of=NOW), [])
