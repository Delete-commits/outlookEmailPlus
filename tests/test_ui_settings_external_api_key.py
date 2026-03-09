import unittest

from tests._import_app import import_web_app_module


class ExternalApiKeySettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    def test_settings_page_has_external_api_key_input(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn('id="settingsExternalApiKey"', html)

    def test_main_js_loads_masked_external_api_key_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/static/js/main.js")
        self.assertEqual(resp.status_code, 200)
        js = resp.data.decode("utf-8")
        self.assertIn("external_api_key_masked", js)
        self.assertIn("settingsExternalApiKey", js)
        self.assertIn("dataset.maskedValue", js)


if __name__ == "__main__":
    unittest.main()

