from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import sys


WEB_APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_APP_DIR))

import app as app_module


class AdminAccessTests(TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="admin-test-secret")
        self.client = app_module.app.test_client()

    def login(self, *, admin=False):
        with self.client.session_transaction() as flask_session:
            flask_session["user"] = {
                "user_name": "test-user",
                "name": "Test User",
                "role": "Säljare",
                "admin": admin,
            }

    def test_public_user_exposes_admin_as_boolean(self):
        self.assertTrue(app_module.public_user({"admin": "Y"})["admin"])
        self.assertFalse(app_module.public_user({"admin": "N"})["admin"])
        self.assertFalse(app_module.public_user({})["admin"])

    def test_removed_email_settings_are_unavailable_to_non_admin(self):
        self.login(admin=False)
        self.assertEqual(self.client.get('/email-proposal-settings').status_code, 404)
        self.assertEqual(self.client.put('/email-proposal-settings/reminder', json={}).status_code, 404)

    def test_removed_email_settings_are_unavailable_to_admin(self):
        self.login(admin=True)
        with patch.object(app_module, 'get_spreadsheet_with_retry') as load:
            self.assertEqual(self.client.get('/email-proposal-settings').status_code, 404)
        load.assert_not_called()

    def test_logout_is_in_insights_without_retired_email_settings(self):
        html = (WEB_APP_DIR / "index.html").read_text(encoding="utf-8")
        insights_start = html.index('<div class="view" id="view-insights">')
        insights_end = html.index("<!-- ═══════════════ CONTACT LOG VIEW", insights_start)
        insights_html = html[insights_start:insights_end]

        self.assertIn('id="logout-btn"', insights_html)
        self.assertNotIn('id="settings-btn"', html)
        self.assertNotIn('id="view-settings"', html)


if __name__ == "__main__":
    main()
