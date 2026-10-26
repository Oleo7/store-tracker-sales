from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch


WEB_APP_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_APP_DIR))
sys.path.insert(0, str(TESTS_DIR))

import app as app_module  # noqa: E402
from contact_channel import recommend_contact_channel  # noqa: E402
from planning_suggestions import SCORE_EVENTS_SHEET, SUGGESTIONS_SHEET  # noqa: E402
from v3_fixtures import current_rank

from route_proposal import (  # noqa: E402
    Coordinate,
    RouteCandidate,
    TravelTimeResult,
    anchor_aware_preselect_candidates,
)
from test_planning import ConstantRoadProvider, PlanningApiTestCase  # noqa: E402
from test_priority_v4 import contact, customer, order, scored


class ProgressiveQueueTests(PlanningApiTestCase):
    def setUp(self):
        super().setUp()
        app_module.app.config["PLANNING_SUGGESTIONS_STUB"] = True
        sheet = self.spreadsheet.worksheet("customers_enriched")
        headers = sheet.row_values(1)
        for index in range(71):
            row = {
                "customer": f"Previewkund {index:02d}",
                "customer_id": f"preview-{index:02d}",
                "customer_number": f"P-{index:02d}",
                "sales_person": "Olle",
                "customer_segment": "C",
            }
            sheet.append_row([row.get(column, "") for column in headers])

    def tearDown(self):
        app_module.app.config.pop("PLANNING_SUGGESTIONS_STUB", None)
        super().tearDown()

    def queue(self, limit=None):
        suffix = "" if limit is None else f"?preview_limit={limit}"
        response = self.client.get(f"/planning/suggestions{suffix}")
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_progressive_preview_uses_one_sparse_materialized_top(self):
        responses = [self.queue()]
        responses.extend(self.queue(limit) for limit in range(15, 76, 5))

        self.assertEqual(responses[0]["pending_count"], 73)
        self.assertEqual(
            [len(response["queue_preview"]) for response in responses],
            [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 72],
        )
        complete = responses[-1]
        self.assertEqual(
            len(complete["queue_preview"]), complete["pending_count"] - 1
        )
        self.assertTrue(all(
            item["revision"] == 0 and not item["materialized"]
            for item in complete["queue_preview"]
        ))
        self.assertEqual(
            len(self.spreadsheet.worksheet(SUGGESTIONS_SHEET).dict_rows()), 1
        )
        created = [
            row for row in self.spreadsheet.worksheet(SCORE_EVENTS_SHEET).dict_rows()
            if row["event_type"] == "suggestion_created"
        ]
        self.assertEqual(len(created), 1)

    def test_preview_limit_is_validated_without_product_hard_cap(self):
        self.assertEqual(self.queue("inte-ett-tal")["preview_limit"], 10)
        negative = self.queue(-5)
        self.assertEqual(negative["preview_limit"], 0)
        self.assertEqual(negative["queue_preview"], [])
        complete = self.queue(999)
        self.assertEqual(complete["preview_limit"], 999)
        self.assertEqual(len(complete["queue_preview"]), 72)


class ChannelRecommendationTests(TestCase):

    def test_segment_a_positive_dialogue_is_visit_without_score_change(self):
        item = scored(
            today=date(2026, 8, 12),
            contacts=[contact("2026-08-01 10:00:00", result="Positiv")],
            customers=[customer(segment="A")],
        )[0]
        score_before = item["priority_score"]
        channel = recommend_contact_channel(
            lifecycle=item["lifecycle"],
            trigger_key="positive_dialogue_followup",
            segment="A",
            has_human_contact=True,
            phone="0701234567",
            email_available=True,
        )
        self.assertEqual(channel["base_contact_type"], "visit")
        self.assertEqual(channel["recommended_contact_type"], "visit")
        self.assertEqual(item["priority_score"], score_before)


class MatrixProvider:
    def __init__(self, seconds):
        self.seconds = tuple(tuple(row) for row in seconds)
        self.call_shapes = []

    def get_matrix_seconds(
        self, origins, destinations, *, ephemeral_origin_indexes=frozenset()
    ):
        self.call_shapes.append((len(origins), len(destinations)))
        return TravelTimeResult(
            seconds=self.seconds,
            pair_count=len(origins) * len(destinations),
            request_count=1,
            routing_preference="TRAFFIC_UNAWARE",
        )


class AnchorAwareRouteTests(TestCase):
    def candidate(self, row, score, lat, lon, required=False):
        return RouteCandidate(
            row=row, customer=f"Kund {row}",
            coordinate=Coordinate(lat, lon), priority_score=score,
            required=required,
         commercial_value=score)

    def test_preselection_round_robin_keeps_anchor_and_geographic_rankings(self):
        start = Coordinate(0, 0)
        anchor = self.candidate(2, 0, 0, 10, required=True)
        high = self.candidate(3, 100, 40, 40)
        near = self.candidate(4, 30, 0, 10.1)
        corridor = self.candidate(5, 40, 0, 5)
        efficient = self.candidate(6, 80, 0, 1)
        selected = anchor_aware_preselect_candidates(
            start=start,
            candidates=[anchor, high, near, corridor, efficient],
            anchor_rows=[2],
            limit=5,
        )
        self.assertEqual(selected[0].row, 2)
        self.assertEqual({item.row for item in selected}, {2, 3, 4, 5, 6})

    def test_anchor_candidate_pool_is_at_most_35_and_unanchored_uses_old_solver(self):
        customers = []
        priorities = []
        for index in range(40):
            row = index + 2
            customers.append({
                "row": row, "customer_id": f"cid-{row}",
                "customer": f"Kund {row}", "sales_person": "Olle",
                "latitude_google": 57.0 + index / 100, "longitude_google": 12.0 + index / 100,
            })
            priorities.append(current_rank({"row": row, "priority_score": 100 - index}))
        snapshot = {"customers": customers, "priorities": priorities}
        owner = {"user_name": "olle", "name": "Olle"}
        with patch.object(
            app_module, "get_authoritative_priority_snapshot", return_value=snapshot
        ):
            anchored, error = app_module.calculate_route_proposal_for_user(
                spreadsheet=object(), start=Coordinate(57, 12),
                client_requested_rows=tuple(range(2, 42)), user=owner, owner=owner,
                route_date=date(2026, 8, 10), required_rows=(2,),
                anchor_rows=(2,), respect_requested_rows=True,
            )
        self.assertIsNone(error)
        self.assertEqual(len(anchored["stops"]), 35)
        self.assertTrue(any(stop["row"] == 2 and stop["required"] for stop in anchored["stops"]))
        self.assertTrue(anchored["meta"]["anchor_aware"])

        one_snapshot = {"customers": customers[:1], "priorities": priorities[:1]}
        with patch.object(
            app_module, "get_authoritative_priority_snapshot", return_value=one_snapshot
        ), patch.object(
            app_module, "anchor_aware_preselect_candidates",
            side_effect=AssertionError("unanchored path must not preselect anchors"),
        ), patch.object(
            app_module, "get_route_travel_time_provider",
            return_value=ConstantRoadProvider(seconds=60),
        ):
            unanchored, error = app_module.calculate_route_proposal_for_user(
                spreadsheet=object(), start=Coordinate(57, 12),
                client_requested_rows=(2,), user=owner, owner=owner,
                route_date=date(2026, 8, 10), respect_requested_rows=True,
            )
        self.assertIsNone(error)
        self.assertFalse(unanchored["meta"]["anchor_aware"])

    def test_anchor_scheduler_avoids_large_backtrack_and_keeps_hard_limits(self):
        start_at = datetime(2026, 8, 10, 9, 0, tzinfo=app_module.STOCKHOLM_ZONE)
        stops = [current_rank({
            "row": 2, "customer_row": 2, "customer_id": "anchor",
            "customer": "Fast besök", "latitude": 57.7, "longitude": 12.8,
            "priority_score": 0, "required": True,
            "scheduled_at": "2026-08-10T13:00:00+02:00",
            "duration_minutes": 20, "planned_activity_id": "anchor-1",
        }), current_rank({
            "row": 3, "customer_row": 3, "customer_id": "backtrack",
            "customer": "Stor omväg", "latitude": 57.9, "longitude": 11.7,
            "priority_score": 90, "required": False,
            "duration_minutes": 20,
        })]
        for index in range(14):
            row = index + 4
            stops.append(current_rank({
                "row": row, "customer_row": row, "customer_id": f"rational-{row}",
                "customer": f"Rationellt stopp {row}",
                "latitude": 57.7, "longitude": 12.2 + index / 100,
                "priority_score": 84 - index, "required": False,
                "duration_minutes": 20,
            }))

        point_count = len(stops) + 1
        matrix = [[300 for _ in range(point_count)] for _ in range(point_count)]
        for index in range(point_count):
            matrix[index][index] = 0
        anchor_index = 1
        backtrack_index = 2
        matrix[0][anchor_index] = matrix[anchor_index][0] = 3600
        for index in range(3, point_count):
            matrix[0][index] = matrix[index][0] = 900
            matrix[index][anchor_index] = matrix[anchor_index][index] = 600
        for index in range(point_count):
            if index != backtrack_index:
                matrix[index][backtrack_index] = 10800
                matrix[backtrack_index][index] = 10800
        matrix[0][backtrack_index] = 1200

        provider = MatrixProvider(matrix)
        with patch.object(
            app_module, "get_route_travel_time_provider", return_value=provider
        ):
            scheduled, timeline, error = app_module.schedule_planning_route_with_anchors(
                stops=stops, fixed_non_route=[], route_start_at=start_at,
                start=Coordinate(57.7, 11.9),
            )
        self.assertIsNone(error)
        self.assertNotIn("backtrack", {stop["customer_id"] for stop in scheduled})
        anchor_stop = next(stop for stop in scheduled if stop["required"])
        self.assertEqual(anchor_stop["scheduled_at"], "2026-08-10T13:00+02:00")
        self.assertEqual(anchor_stop["estimated_at"], anchor_stop["scheduled_at"])
        self.assertLessEqual(len(scheduled), 15)
        self.assertLessEqual(
            app_module.parse_planning_datetime(timeline["route_end_at"]),
            app_module.route_workday_end(start_at),
        )
        self.assertEqual(provider.call_shapes, [(17, 17)])

    def test_optional_stop_is_scheduled_between_two_immutable_anchors(self):
        start_at = datetime(2026, 8, 10, 9, 0, tzinfo=app_module.STOCKHOLM_ZONE)
        stops = [current_rank({
            "row": 2, "customer_row": 2, "customer_id": "anchor-one",
            "customer": "Fast besök 1", "latitude": 57.7, "longitude": 12.2,
            "priority_score": 0, "required": True,
            "scheduled_at": "2026-08-10T10:00:00+02:00",
            "duration_minutes": 20, "planned_activity_id": "anchor-1",
        }), current_rank({
            "row": 3, "customer_row": 3, "customer_id": "anchor-two",
            "customer": "Fast besök 2", "latitude": 57.7, "longitude": 13.0,
            "priority_score": 0, "required": True,
            "scheduled_at": "2026-08-10T14:00:00+02:00",
            "duration_minutes": 20, "planned_activity_id": "anchor-2",
        }), current_rank({
            "row": 4, "customer_row": 4, "customer_id": "between",
            "customer": "Mellanstopp", "latitude": 57.7, "longitude": 12.6,
            "priority_score": 80, "required": False, "duration_minutes": 20,
        })]
        minutes = (
            (0, 30, 120, 60),
            (30, 0, 180, 15),
            (30, 180, 0, 15),
            (60, 60, 15, 0),
        )
        provider = MatrixProvider([
            [value * 60 for value in row] for row in minutes
        ])
        with patch.object(
            app_module, "get_route_travel_time_provider", return_value=provider
        ):
            scheduled, timeline, error = app_module.schedule_planning_route_with_anchors(
                stops=stops, fixed_non_route=[], route_start_at=start_at,
                start=Coordinate(57.7, 11.9),
            )
        self.assertIsNone(error)
        self.assertEqual(
            [stop["customer_id"] for stop in scheduled],
            ["anchor-one", "between", "anchor-two"],
        )
        self.assertEqual(scheduled[0]["scheduled_at"], "2026-08-10T10:00+02:00")
        self.assertEqual(scheduled[2]["scheduled_at"], "2026-08-10T14:00+02:00")
        self.assertLess(
            app_module.parse_planning_datetime(timeline["route_end_at"]),
            app_module.route_workday_end(start_at),
        )
