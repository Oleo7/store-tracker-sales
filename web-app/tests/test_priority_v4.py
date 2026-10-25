from datetime import date
from pathlib import Path
import sys
from unittest import TestCase


WEB_APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_APP_DIR))

import app as app_module  # noqa: E402
from planning_suggestions import decision_context_hash, deterministic_suggestion_id  # noqa: E402
from priority import build_contact_features, build_order_features, build_priority_customers  # noqa: E402


def customer(customer_id="cid-1", number="100", name="Butik", segment="C", row=2):
    return {
        "row": row, "customer_id": customer_id, "customer_number": number,
        "customer": name, "sales_person": "Olle", "customer_segment": segment,
    }


def order(reference, delivered, customer_id="cid-1", number="100", name="Butik"):
    return {
        "Reference": reference, "Order date": delivered, "Delivery date": delivered,
        "customer_id": customer_id, "Customer number": number, "Customer": name,
        "Quantity": "20", "Total weight": "20", "Total": "400",
    }


def contact(when, result="Neutral", contact_id="contact-1", follow_up=""):
    return {
        "contact_id": contact_id, "customer_id": "cid-1", "customer": "Butik",
        "date_time": when, "sales_person": "Olle", "contact_channel": "Telefon",
        "result": result, "follow_up_date": follow_up,
        "follow_up_purpose": "customer_followup" if follow_up else "",
        "follow_up_agreement_confirmed": "Y" if follow_up else "N",
    }


def scored(*, today, orders=(), contacts=(), customers=None, planned=()):
    customers = customers or [customer()]
    order_features = build_order_features(list(orders))
    return build_priority_customers(
        customers, order_features, build_contact_features(list(contacts), order_features),
        "Olle", today, limit=len(customers), planned_activities=list(planned),
    )


def suggestion_identity(item):
    context = decision_context_hash(
        owner="olle", customer_id=item["customer_id"],
        lifecycle=item["decision_context_lifecycle"], order_count=item["order_count"],
        latest_order_reference=item["latest_order_reference"],
        latest_order_date=item["latest_delivery_date"],
        latest_contact_id=item["latest_human_contact_id"],
        latest_contact_result=item["latest_contact_result"],
        latest_contact_date=item["latest_human_contact_date"],

    )
    return context, deterministic_suggestion_id("olle", item["customer_id"], context)


class Phase4PriorityContinuityTests(TestCase):
    def test_superseded_plan_does_not_change_priority_or_scoring(self):
        baseline = scored(today=date(2026, 8, 2))[0]
        with_history = scored(today=date(2026, 8, 2), planned=[{
            "planned_activity_id": "historic-plan",
            "customer_id": "cid-1",
            "user_name": "olle",
            "scheduled_at": "2026-08-04T09:00:00",
            "status": "superseded",
        }])[0]
        self.assertEqual(with_history, baseline)


class Phase4LegacyFollowupTests(TestCase):


    def test_future_explicit_followup_still_blocks_positive_dialogue(self):
        future_positive = contact(
            "2026-07-16 10:00:00", result="Positiv",
            contact_id="future-positive", follow_up="2026-08-10",
        )
        baseline = scored(
            today=date(2026, 8, 5),
            contacts=[contact(
                "2026-07-16 10:00:00", result="Neutral",
                contact_id="future-neutral", follow_up="2026-08-10",
            )],
        )[0]
        item = scored(
            today=date(2026, 8, 5), contacts=[future_positive],

        )[0]
        self.assertEqual(item["recommendation_suppression_reason"], "future_follow_up_date")
        self.assertNotIn("stockfiller_click_followup", item["covered_trigger_keys"])
        self.assertNotIn("positive_dialogue_followup", item["covered_trigger_keys"])
        self.assertEqual(item["intent_timing"], round(100 * (item)["work_contact_factor"]))


class Phase4CalibrationTests(TestCase):
    def test_score_band_boundaries(self):
        values = {
            0: "0-49", 49: "0-49", 50: "50-69", 69: "50-69",
            70: "70-79", 79: "70-79", 80: "80-89", 89: "80-89",
            90: "90-100", 100: "90-100",
        }
        for score_value, expected in values.items():
            with self.subTest(score=score_value):
                self.assertEqual(app_module.calibration_score_band(score_value), expected)

    def test_export_is_deterministic_and_uses_persisted_score(self):
        events = [{
            "event_id": "e-1", "event_type": "suggestion_planned",
            "occurred_at": "2026-08-01 09:00:00", "customer_id": "cid-1",
            "suggestion_id": "s-1", "decision_context_hash": "ctx",
            "primary_trigger_key": "stockfiller_click_followup",
            "score_version": "v2", "lifecycle": "prospect",
            "recommendation_eligible": "Y", "priority_score": "71",
            "intent_timing": "68", "value_index": "70", "strategic_index": "25",
            "actual_planned_contact_type": "phone", "status_after": "planned",
        }]
        orders = [order("ORDER-AFTER", "2026-08-03")]
        first = app_module.build_calibration_rows(events, orders, [customer()])
        second = app_module.build_calibration_rows(events, orders, [customer()])
        self.assertEqual(first, second)
        self.assertEqual(first[0]["priority_score"], "71")
        self.assertEqual(first[0]["priority_score_band"], "70-79")
        self.assertEqual(first[0]["order_outcome"], "order_after_event")
        self.assertEqual(first[0]["first_order_reference_after_event"], "ORDER-AFTER")
