import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalApiKeySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", "")

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_get_settings_exposes_external_api_key_status_and_masked_value(self):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", "abcdef1234567890")

        client = self.app.test_client()
        self._login(client)
        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        settings = data.get("settings", {})
        self.assertIn("external_api_key_set", settings)
        self.assertIn("external_api_key_masked", settings)
        self.assertTrue(settings.get("external_api_key_set"))
        self.assertNotEqual(settings.get("external_api_key_masked"), "abcdef1234567890")

    def test_put_settings_can_update_external_api_key(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"external_api_key": "new-key-123"})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))

        resp2 = client.get("/api/settings")
        self.assertEqual(resp2.status_code, 200)
        settings = resp2.get_json().get("settings", {})
        self.assertTrue(settings.get("external_api_key_set"))

    def test_clearing_external_api_key_marks_open_api_as_not_configured(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.put("/api/settings", json={"external_api_key": ""})

        self.assertEqual(resp.status_code, 200)
        resp2 = client.get("/api/settings")
        settings = resp2.get_json().get("settings", {})
        self.assertFalse(settings.get("external_api_key_set"))

    def test_put_settings_does_not_overwrite_when_sending_masked_placeholder(self):
        original = "abcdef1234567890"
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", original)

        client = self.app.test_client()
        self._login(client)

        resp1 = client.get("/api/settings")
        self.assertEqual(resp1.status_code, 200)
        masked = resp1.get_json().get("settings", {}).get("external_api_key_masked")
        self.assertTrue(masked)
        self.assertNotEqual(masked, original)

        resp2 = client.put("/api/settings", json={"external_api_key": masked})
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.get_json().get("success"))

        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            self.assertEqual(settings_repo.get_external_api_key(), original)


if __name__ == "__main__":
    unittest.main()
