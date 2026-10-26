"""V3.4 history semantics and raw route-ranking contracts.

Synthetic data only. Actual reducer, feature/model pipeline and Flask write
endpoints are used. No production credentials or reconstructed score formula.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from customer_obligations import build_customer_state, attention_items, stable_contact_source_id, source_fingerprint
from priority import build_order_features, build_contact_features, build_priority_customers
from route_proposal import Coordinate, RouteCandidate
from route_optimization import shipment_commercial_value, shipment_penalty
import app as application
from test_planning import PlanningApiTestCase

NOW = datetime(2026, 10, 19, 9, tzinfo=ZoneInfo('Europe/Stockholm'))
C = {'customer_id':'c1', 'customer':'Testbutik', 'customer_number':'100',
     'sales_person':'olle', 'customer_segment':'A', 'phone':'0701234567', 'row':2}


def contact(days=30, result='Neutral', **fields):
    return {'customer_id':'c1', 'customer':'Testbutik', 'customer_number':'100',
            'date_time':(NOW-timedelta(days=days)).isoformat(), 'sales_person':'olle',
            'contact_channel':'Telefon', 'result':result, **fields}


def order(days=1, **fields):
    day=(NOW-timedelta(days=days)).date().isoformat()
    return {'customer_id':'c1', 'Customer':'Testbutik', 'Customer number':'100',
            'Reference':'o'+str(days), 'Order date':day, 'Delivery date':day,
            'Total weight':'20', 'Total':'1000', 'SKU':'raspberry', **fields}


def plan(days=1, **fields):
    return {'customer_id':'c1', 'customer':'Testbutik', 'user_name':'olle',
            'planned_activity_id':'p1', 'status':'planned', 'source':'manual',
            'created_at':(NOW-timedelta(days=20)).isoformat(),
            'scheduled_at':(NOW+timedelta(days=days)).isoformat(), 'contact_type':'phone', **fields}


def state(contacts=(), plans=(), orders=(), events=(), now=NOW):
    return build_customer_state([C], list(contacts), list(plans), events, as_of=now,
                                owner_user_names={'c1':'olle'}, order_rows=list(orders))


def model(contacts=(), plans=(), orders=(), events=(), now=NOW):
    st=state(contacts, plans, orders, events, now)
    of=build_order_features(list(orders), customers=[C], as_of=now)
    cf=build_contact_features(list(contacts), of, customers=[C], as_of=now)
    row=build_priority_customers([C],of,cf,None,now.date(),now=now,
         planned_activities=list(plans), obligation_states=st['obligations'],
         contact_permissions=st['contact_permissions'], planning_owner_user_names={'c1':'olle'})[0]
    return row, st


class ContactAndRankingTests(TestCase):
    def test_date_alone_never_lifts_negative_contact_pause(self):
        for proof in (False,True):
            cs=[contact(5,'Negativ',follow_up_date='2026-10-18',contact_id='n',follow_up_agreement_confirmed=proof)]
            row,_=model(cs)
            self.assertFalse(row['can_start_unscheduled_contact'])
            self.assertFalse(row['list_guidance']['explicit_agreement_overrides_negative'])

    def test_safety_gate_remains_when_old_history_no_longer_blocks(self):
        for result in ['Negativ','Ej anträffbar']:
            row,_=model([contact(100,contact_id='old',follow_up_date='2026-08-01'),contact(0,result)])
            self.assertFalse(row['can_start_unscheduled_contact'])
            self.assertEqual(row['work_priority_raw'],0)
            self.assertIn(row['action_type'],{'negative_contact_cooldown','unanswered_retry_wait'})

    def test_direct_feature_call_uses_same_reconciled_history(self):
        cs=[contact(100,follow_up_date='2026-07-20'),contact(30)]
        row,_=model(cs)
        of=build_order_features([],customers=[C],as_of=NOW)
        cf=build_contact_features(cs,of,customers=[C],as_of=NOW)
        direct=build_priority_customers([C],of,cf,None,NOW.date(),now=NOW)[0]
        self.assertEqual(row['list_guidance']['reason_code'],direct['list_guidance']['reason_code'])
        self.assertEqual(row['work_priority_raw'],direct['work_priority_raw'])

    def test_first_order_phase_preserved_and_does_not_replace_real_booking(self):
        for age in (6,7,10,11,23,24,30,31,45,60,90,91):
            with self.subTest(age=age):
                row,_=model(orders=[order(age)],contacts=[contact(age+1,'Positiv')])
                self.assertNotIn('stale_follow_up_review',row['list_guidance']['reason_code'])
                if age==6:self.assertEqual(row['work_priority_raw'],0)
                if 7<=age<=10:self.assertEqual(row['list_guidance']['reason_code'],'first_order_onboarding')
                if 11<=age<=90:self.assertEqual(row['list_guidance']['reason_code'],'second_purchase_due')
        planned,_=model(orders=[order(24)],plans=[plan(2)])
        self.assertTrue(planned['has_planned_contact']);self.assertEqual(planned['contact_priority_raw'],0)
        self.assertGreater(planned['work_priority_raw'],0)

    def test_ranking_rollback_preserves_safety_and_obligations(self):
        c=contact(100,contact_id='old',follow_up_date='2026-08-01')
        base,_=model([c]);history,_=model([c,contact(1,'Återkom ej')])
        self.assertEqual(history['work_priority_raw'],base['work_priority_raw'])
        self.assertEqual(history['business_value_raw'],base['business_value_raw'])
        negative,_=model([c,contact(1,'Negativ')]);self.assertEqual(negative['work_priority_raw'],0)

    def test_normalized_route_index_is_not_raw_dfp_or_old_score(self):
        a={'value_model_version':'v3.5','score_version':'v3.5','priority_score':99,
           'contact_priority_score':95,'contact_priority_precise':95.1,'contact_priority_raw':50.,
           'work_priority_raw':60.,'work_priority_precise':96.2,'work_priority_score':96}
        b={**a,'priority_score':5,'contact_priority_precise':95.2,'contact_priority_raw':9999.}
        va=application.route_priority_values(a);vb=application.route_priority_values(b)
        self.assertEqual(va['priority_score'],vb['priority_score'])
        self.assertEqual(va['commercial_value'],95.1)
        self.assertEqual(vb['commercial_value'],95.2)
        self.assertGreater(shipment_penalty(vb),shipment_penalty(va))
        self.assertEqual(application.route_priority_values(a,required=True)['commercial_value'],96.2)

    def test_route_corrupt_value_fails_closed(self):
        for bad in (None,True,float('nan'),float('inf'),-1):
            p={'value_model_version':'v3.5','priority_score':99,
               'contact_priority_raw':bad,'contact_priority_score':90}
            self.assertIsNone(application.route_priority_values(p))


class AdditionalCommercialRegressionTests(TestCase):
    def test_old_report_is_annotation_not_confirmed_purchase_or_permanent_pause(self):
        row,_=model([contact(100,'Order lagd!')])
        self.assertGreater(row['work_priority_raw'],0)
        self.assertEqual(row['business_verified_delivery_count'],0)
        self.assertIn('historical_order_report',{w['code'] for w in row['data_warnings']})
        fresh,_=model([contact(10,'Order lagd!')])
        self.assertEqual(fresh['action_type'],'reported_order_sync_review')
        self.assertEqual(fresh['work_priority_raw'],0)
        rejected,_=model([contact(100,'Order lagd!'),contact(1,'Negativ')])
        self.assertEqual(rejected['action_type'],'negative_contact_cooldown')
        self.assertEqual(rejected['work_priority_raw'],0)

    def test_later_real_delivery_supersedes_acquisition_not_reference_match(self):
        row,_=model([contact(20,'Order lagd!')],orders=[order(15,**{'Order date':'2026-09-20'})])
        self.assertNotEqual(row['action_type'],'reported_order_sync_review')
        self.assertEqual(row['business_verified_delivery_count'],1)
        self.assertIn('delivery_after_report',{w['code'] for w in row['data_warnings']})

    def test_new_order_does_not_remove_retry_pause_for_separate_promise(self):
        cs=[contact(20,contact_id='service',follow_up_date='2026-10-17',follow_up_agreement_confirmed=True),
            contact(0,'Ej anträffbar',contact_id='attempt',obligation_id='followup:service',obligation_outcome='open')]
        row,_=model(cs,orders=[order(0)])
        self.assertEqual(row['action_type'],'first_order_new')
        self.assertFalse(row['can_start_unscheduled_contact'])

    def test_newer_reached_dialogue_applies_even_with_older_phase_contact(self):
        cs=[contact(8,'Neutral',purpose='second_purchase_due'),contact(1,'Positiv')]
        row,_=model(cs,orders=[order(24)])
        self.assertEqual(row['action_type'],'positive_buyer_followup_wait')

    def test_explicit_completion_on_delivery_day_counts_but_plain_dialogue_does_not(self):
        plain,_=model([contact(8,'Positiv')],orders=[order(8)])
        self.assertEqual(plain['action_type'],'first_order_onboarding')
        completed,_=model([contact(8,'Positiv',purpose='first_order_onboarding',onboarding_completed='Y')],orders=[order(8)])
        self.assertEqual(completed['action_type'],'first_order_onboarding_completed')


class TimestampAndIdentityRegressionTests(TestCase):
    def test_different_same_time_event_cannot_claim_later_agreement(self):
        stamp=(NOW-timedelta(days=5)).isoformat()
        cs=[contact(5,'Negativ',contact_id='negative',date_time=stamp),
            contact(5,'Order lagd!',contact_id='separate',date_time=stamp,
                    follow_up_date='2026-10-18',follow_up_agreement_confirmed=True)]
        row,_=model(cs)
        self.assertEqual(row['action_type'],'negative_contact_cooldown')
        self.assertFalse(row['can_start_unscheduled_contact'])
        self.assertFalse(row['list_guidance']['explicit_agreement_overrides_negative'])

    def test_broken_calendar_id_never_becomes_a_green_or_executable_booking(self):
        row,_=model(plans=[plan(1,planned_activity_id='')])
        self.assertEqual(row['action_type'],'invalid_planned_activity_identity')
        self.assertFalse(row['has_planned_contact'])
        self.assertFalse(row['can_start_unscheduled_contact'])
        self.assertEqual(row['work_priority_raw'],0)
