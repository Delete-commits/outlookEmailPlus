import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests._import_app import clear_login_attempts, import_web_app_module


class ExternalApiBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            clear_login_attempts()
            from outlook_web.db import get_db
            from outlook_web.repositories import settings as settings_repo

            db = get_db()
            db.execute("DELETE FROM audit_logs WHERE resource_type = 'external_api'")
            db.execute("DELETE FROM accounts WHERE email LIKE '%@extapi.test'")
            db.commit()
            settings_repo.set_setting("external_api_key", "")

    def _set_external_api_key(self, value: str):
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            settings_repo.set_setting("external_api_key", value)

    def _insert_outlook_account(self, email_addr: str | None = None) -> str:
        email_addr = email_addr or f"{uuid.uuid4().hex}@extapi.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", "cid-test", "rt-test", 1, "active", "outlook", "outlook"),
            )
            db.commit()
        return email_addr

    def _insert_imap_account(self, email_addr: str | None = None) -> str:
        email_addr = email_addr or f"{uuid.uuid4().hex}@extapi.test"
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            db.execute(
                """
                INSERT INTO accounts (
                    email, password, client_id, refresh_token, group_id, status,
                    account_type, provider, imap_host, imap_port, imap_password
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (email_addr, "pw", "cid-test", "rt-test", 1, "active", "imap", "custom", "imap.test.com", 993, "imap-pass"),
            )
            db.commit()
        return email_addr

    @staticmethod
    def _auth_headers(value: str = "abc123"):
        return {"X-API-Key": value}

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))

    @staticmethod
    def _utc_iso(minutes_delta: int = 0) -> str:
        dt = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=minutes_delta)
        return dt.isoformat().replace("+00:00", "Z")

    @classmethod
    def _graph_email(
        cls,
        message_id: str = "msg-1",
        subject: str = "Your verification code",
        sender: str = "noreply@example.com",
        received_at: str | None = None,
    ):
        return {
            "id": message_id,
            "subject": subject,
            "from": {"emailAddress": {"address": sender}},
            "receivedDateTime": received_at or cls._utc_iso(),
            "isRead": False,
            "hasAttachments": False,
            "bodyPreview": "Your code is 123456",
        }

    @classmethod
    def _graph_detail(
        cls,
        message_id: str = "msg-1",
        body_text: str = "Your code is 123456",
        html_text: str = "<p>Your code is 123456</p>",
        received_at: str | None = None,
    ):
        return {
            "id": message_id,
            "subject": "Your verification code",
            "from": {"emailAddress": {"address": "noreply@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "user@outlook.com"}}],
            "receivedDateTime": received_at or cls._utc_iso(),
            "body": {"content": body_text if body_text else html_text, "contentType": "text" if body_text else "html"},
        }

    def _external_audit_logs(self):
        with self.app.app_context():
            from outlook_web.db import get_db

            db = get_db()
            rows = db.execute("""
                SELECT action, resource_id, details
                FROM audit_logs
                WHERE resource_type = 'external_api'
                ORDER BY id ASC
                """).fetchall()
        return [dict(row) for row in rows]


class ExternalApiAuthTests(ExternalApiBaseTest):
    def test_external_health_requires_api_key(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/health")

        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "UNAUTHORIZED")

    def test_external_health_returns_403_when_api_key_not_configured(self):
        client = self.app.test_client()

        resp = client.get("/api/external/health", headers=self._auth_headers("abc123"))

        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertEqual(data.get("code"), "API_KEY_NOT_CONFIGURED")

    def test_external_health_accepts_valid_api_key(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/health", headers=self._auth_headers("abc123"))

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")


class ExternalApiMessageTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_latest_message_returns_filtered_latest_email(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        newer = self._graph_email(message_id="msg-new", subject="Target mail", received_at=self._utc_iso())
        older = self._graph_email(message_id="msg-old", subject="Ignore mail", received_at=self._utc_iso(minutes_delta=-2))
        mock_get_emails_graph.return_value = {"success": True, "emails": [older, newer]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/latest?email={email_addr}&subject_contains=Target",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("id"), "msg-new")

    def test_external_messages_returns_account_not_found(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get(
            "/api/external/messages?email=missing@extapi.test",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "ACCOUNT_NOT_FOUND")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_returns_list_when_graph_succeeds(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("code"), "OK")
        self.assertEqual(len(data.get("data", {}).get("emails", [])), 1)

    @patch("outlook_web.services.imap.get_emails_imap_with_server")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_messages_falls_back_to_imap_when_graph_fails(self, mock_get_emails_graph, mock_get_emails_imap):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": False, "error": "graph failed"}
        mock_get_emails_imap.return_value = {
            "success": True,
            "emails": [
                {
                    "id": "imap-1",
                    "subject": "IMAP Subject",
                    "from": "imap@example.com",
                    "date": "2026-03-08T12:00:00Z",
                    "is_read": False,
                    "has_attachments": False,
                    "body_preview": "preview",
                }
            ],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("data", {}).get("emails", [])), 1)

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_external_message_detail_returns_message_content(self, mock_get_email_detail_graph, mock_get_email_raw_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_email_detail_graph.return_value = self._graph_detail()
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("content", data.get("data", {}))
        self.assertIn("raw_content", data.get("data", {}))
        self.assertEqual(data.get("data", {}).get("raw_content"), "RAW MIME CONTENT")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    def test_external_message_raw_returns_raw_content_and_audits(self, mock_get_email_detail_graph, mock_get_email_raw_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="raw test")
        mock_get_email_raw_graph.return_value = "MIME-Version: 1.0\r\nraw test"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/messages/msg-1/raw?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("raw_content"), "MIME-Version: 1.0\r\nraw test")

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/messages/{message_id}/raw", audit_logs[0]["details"])


class ExternalApiVerificationTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_returns_code(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="Your code is 123456")
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("verification_code"), "123456")

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_code_defaults_to_recent_10_minutes(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(received_at=self._utc_iso(minutes_delta=-20))],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-code?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")

    @patch("outlook_web.services.graph.get_email_raw_graph")
    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_link_returns_preferred_link(
        self,
        mock_get_emails_graph,
        mock_get_email_detail_graph,
        mock_get_email_raw_graph,
    ):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify your email")],
        }
        mock_get_email_detail_graph.return_value = self._graph_detail(
            body_text="Click https://example.com/verify?token=abc to continue",
        )
        mock_get_email_raw_graph.return_value = "RAW MIME CONTENT"

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("verify", data.get("data", {}).get("verification_link", ""))

    @patch("outlook_web.services.graph.get_emails_graph")
    def test_external_verification_link_defaults_to_recent_10_minutes(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        mock_get_emails_graph.return_value = {
            "success": True,
            "emails": [self._graph_email(subject="Please verify your email", received_at=self._utc_iso(minutes_delta=-30))],
        }

        client = self.app.test_client()
        resp = client.get(
            f"/api/external/verification-link?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json().get("code"), "MAIL_NOT_FOUND")

    @patch("outlook_web.services.external_api.time.sleep")
    @patch("outlook_web.services.external_api.time.time")
    @patch("outlook_web.services.external_api.get_latest_message_for_external")
    def test_wait_for_message_only_returns_new_messages(self, mock_get_latest_message, mock_time, mock_sleep):
        from outlook_web.services import external_api as external_api_service

        mock_time.side_effect = [100, 100, 100]
        mock_get_latest_message.side_effect = [
            {"id": "old", "timestamp": 99, "method": "Graph API"},
            {"id": "new", "timestamp": 101, "method": "Graph API"},
        ]

        result = external_api_service.wait_for_message(email_addr="user@example.com", timeout_seconds=30, poll_interval=5)

        self.assertEqual(result.get("id"), "new")
        mock_sleep.assert_called_once_with(5)

    def test_external_wait_message_rejects_too_large_timeout(self):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/wait-message?email={email_addr}&timeout_seconds=999",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("code"), "INVALID_PARAM")


class ExternalApiSystemTests(ExternalApiBaseTest):
    def test_external_capabilities_returns_feature_list_and_audits(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/capabilities", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("service", data.get("data", {}))
        self.assertIn("version", data.get("data", {}))
        self.assertIn("features", data.get("data", {}))

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/capabilities", audit_logs[0]["details"])

    def test_external_health_audits_access(self):
        client = self.app.test_client()
        self._set_external_api_key("abc123")

        resp = client.get("/api/external/health", headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/health", audit_logs[0]["details"])

    def test_external_account_status_returns_account_data_and_audits(self):
        email_addr = self._insert_outlook_account()
        self._set_external_api_key("abc123")
        client = self.app.test_client()

        resp = client.get(
            f"/api/external/account-status?email={email_addr}",
            headers=self._auth_headers(),
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("email"), email_addr)
        self.assertTrue(data.get("data", {}).get("exists"))
        self.assertEqual(data.get("data", {}).get("account_type"), "outlook")
        self.assertEqual(data.get("data", {}).get("provider"), "outlook")
        self.assertIn("preferred_method", data.get("data", {}))
        self.assertIn("last_refresh_at", data.get("data", {}))
        self.assertTrue(data.get("data", {}).get("can_read"))

        audit_logs = self._external_audit_logs()
        self.assertEqual(len(audit_logs), 1)
        self.assertIn("/api/external/account-status", audit_logs[0]["details"])


class ExternalApiRegressionTests(ExternalApiBaseTest):
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_email_list_api_still_works(self, mock_get_emails_graph):
        email_addr = self._insert_outlook_account()
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("emails", data)

    @patch("outlook_web.services.graph.get_email_detail_graph")
    @patch("outlook_web.services.graph.get_emails_graph")
    def test_internal_extract_verification_api_still_works(self, mock_get_emails_graph, mock_get_email_detail_graph):
        email_addr = self._insert_outlook_account()
        mock_get_emails_graph.return_value = {"success": True, "emails": [self._graph_email()]}
        mock_get_email_detail_graph.return_value = self._graph_detail(body_text="Your code is 123456")

        client = self.app.test_client()
        self._login(client)
        resp = client.get(f"/api/emails/{email_addr}/extract-verification")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("verification_code"), "123456")

    def test_internal_settings_api_still_returns_existing_fields(self):
        client = self.app.test_client()
        self._login(client)

        resp = client.get("/api/settings")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("refresh_interval_days", data.get("settings", {}))
        self.assertIn("gptmail_api_key_set", data.get("settings", {}))


if __name__ == "__main__":
    unittest.main()
