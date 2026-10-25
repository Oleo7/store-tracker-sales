"""No provider calls, no retired worksheets, manual email remains an ordinary channel."""
import inspect
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta

import app as application
import priority
import value_prioritization
from test_planning import PlanningApiTestCase, NOW, FakeWorksheet

RETIRED = {'email_messages', 'email_recipients', 'email_events'}
CID = '11111111-1111-4111-8111-111111111111'


class RemovedEmailIntegrationTests(PlanningApiTestCase):
    def setUp(self):
        super().setUp()
        application._sheet_read_cache.clear()
        application.invalidate_priority_snapshot()
        self.accesses = []
        original = self.spreadsheet.worksheet
        def guarded(title):
            self.accesses.append(title)
            if title in RETIRED:
                raise AssertionError('Retired worksheet accessed: ' + title)
            return original(title)
        self.spreadsheet.worksheet = guarded

    def tearDown(self):
        application._sheet_read_cache.clear()
        application.invalidate_priority_snapshot()
        super().tearDown()

    def snapshot(self):
        return application.get_authoritative_priority_snapshot(
            self.spreadsheet, today=NOW.date(), as_of=NOW)

    def test_route_registry_has_no_sending_webhook_reconcile_or_template_endpoints(self):
        for rule in application.app.url_map.iter_rules():
            self.assertFalse(any(s in str(rule) for s in ('brevo', 'email-proposal', 'reminder-email')),
                             str(rule))
        with patch.object(application, 'get_spreadsheet_with_retry') as load:
            for url, method in [('/email-proposal-settings', 'get'),
                                ('/customers/2/email-proposal-draft', 'get'),
                                ('/customers/2/email-proposal/send', 'post'),
                                ('/api/brevo/webhook/test', 'post')]:
                self.assertEqual(getattr(self.client, method)(url).status_code, 404)
            load.assert_not_called()

    def test_core_reads_do_not_require_or_create_email_sheets(self):
        for url in ('/customers', '/customer-insights', '/customers/Butik%20A/stats',
                    '/contact-log', '/planning/suggestions',
                    '/planning/attention', '/planning/activities?start=2026-07-27&end=2026-08-02'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(RETIRED.isdisjoint(self.spreadsheet.sheets))
        self.assertTrue(RETIRED.isdisjoint(self.accesses))

    def test_sales_analytics_does_not_require_email_sheets(self):
        self.login('admin')
        response = self.client.get('/sales-coaching-insights')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(RETIRED.isdisjoint(self.accesses))

    def test_priority_public_contract_has_no_tracking_inputs_or_outputs(self):
        self.assertNotIn('email_features', inspect.signature(priority.build_priority_customers).parameters)
        self.assertNotIn('qualified_email_trigger', inspect.signature(value_prioritization.store_contact_guidance).parameters)
        self.assertNotIn('message_rows', inspect.signature(application.build_current_priority_snapshot).parameters)
        snapshot = self.snapshot()
        self.assertNotIn('email_engagement', snapshot)
        for row in snapshot['priorities']:
            self.assertFalse(any(k.startswith('email_') or 'email_intent' in k for k in row))
        payload = self.client.get('/customer-insights').get_json()
        for row in payload.values():
            self.assertFalse(any(k.startswith('email_') or k.startswith('reminder_email') for k in row))

    def test_legacy_tracking_rows_have_no_effect_even_if_old_tabs_exist(self):
        before = self.snapshot()['priorities']
        for title in RETIRED:
            self.spreadsheet.sheets[title] = FakeWorksheet(title, ['customer_id', 'stockfiller_click_count'],
                                                          [{'customer_id': CID, 'stockfiller_click_count': 999}])
        application.invalidate_priority_snapshot()
        self.assertEqual(self.snapshot()['priorities'], before)
        self.assertTrue(RETIRED.isdisjoint(self.accesses))

    def test_legacy_automatic_mail_is_never_a_human_dialogue(self):
        self.append_contact_row(customer_id=CID, follow_up_date='', contact_id='human',
                                result='Neutral', date_time=(NOW-timedelta(days=30)).isoformat())
        self.append_contact_row(customer_id=CID, follow_up_date='', contact_id='old-system-mail',
                                result='Positiv', email_id='historic-mail', contact_channel='Mejl',
                                date_time=(NOW-timedelta(days=1)).isoformat())
        features = priority.build_contact_features(application.get_contact_rows(self.spreadsheet),
                         priority.build_order_features([]), customers=application.get_customer_rows(self.spreadsheet), as_of=NOW)
        target = next(row for row in features.values() if row.get('customer_id') == CID)
        self.assertEqual(target['latest_reached_date'], (NOW-timedelta(days=30)).date())
        self.assertFalse(priority.is_human_contact({'email_id': 'historic-mail'}))
        self.assertFalse(priority.is_human_contact({'activity_source': 'crm_email'}))
        self.assertTrue(priority.is_human_contact({'contact_channel': 'Mejl', 'activity_source': 'manual'}))

    def test_manual_email_contact_keeps_pre_contact_priority_and_is_idempotent(self):
        data = {'customer_id': CID, 'contact_channel': 'Mejl', 'result': 'Neutral',
                'date_time': NOW.isoformat(), 'comment': 'Manual email logged by the seller',
                'client_request_id': 'manual-email-no-provider'}
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No network permitted')):
            response = self.client.post('/customers/Butik%20A/contacts', json=data)
            self.assertEqual(response.status_code, 200, response.get_json())
            replay = self.client.post('/customers/Butik%20A/contacts', json=data)
            self.assertEqual(replay.status_code, 200, replay.get_json())
        rows = self.contact_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['contact_channel'], 'Mejl')
        self.assertEqual(rows[0]['priority_score_version'], priority.SCORE_VERSION)
        self.assertEqual(rows[0]['priority_snapshot_quality'], 'exact')
        self.assertTrue(priority.is_human_contact(rows[0]))
        self.assertTrue(RETIRED.isdisjoint(self.accesses))

    def test_manually_planned_email_can_be_completed_without_sending(self):
        planned = self.append_planning_row(contact_type='email', scheduled_at=NOW.isoformat())
        data = {'customer_id': CID, 'contact_channel': 'Mejl', 'result': 'Neutral',
                'date_time': NOW.isoformat(), 'comment': 'Completed manual email',
                'planned_activity_id': planned['planned_activity_id'],
                'client_request_id': 'planned-manual-email-no-provider'}
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No network permitted')):
            response = self.client.post('/customers/Butik%20A/contacts', json=data)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.planning_rows()[0]['status'], 'completed')
        self.assertEqual(self.contact_rows()[0]['planned_activity_id'], planned['planned_activity_id'])
        self.assertTrue(RETIRED.isdisjoint(self.accesses))

    def test_runtime_files_do_not_reference_retired_worksheet_names(self):
        root = Path(__file__).resolve().parents[2]
        files = list((root/'web-app').glob('*.py')) + list((root/'scripts').glob('*.py'))
        files += list((root/'customer_master_sync').glob('*.py'))
        for path in files:
            for title in RETIRED:
                self.assertNotIn(title, path.read_text(), str(path))
        self.assertFalse((root/'web-app/reminder_email.py').exists())
        self.assertFalse((root/'web-app/legacy_email_identity.py').exists())
        self.assertNotIn('BREVO_', (root/'.env.example').read_text())
