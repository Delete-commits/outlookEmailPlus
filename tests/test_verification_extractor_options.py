import unittest

from outlook_web.services import verification_extractor as extractor


class VerificationExtractorOptionsTests(unittest.TestCase):
    def _require_new_api(self):
        func = getattr(extractor, "extract_verification_info_with_options", None)
        self.assertTrue(callable(func), "缺少 extract_verification_info_with_options()")
        return func

    def test_extract_with_default_options_returns_code(self):
        func = self._require_new_api()
        email = {
            "subject": "Your verification code",
            "body": "Your code is 123456",
            "body_html": "<p>Your code is 123456</p>",
        }

        result = func(email)

        self.assertEqual(result.get("verification_code"), "123456")

    def test_extract_with_code_length_prefers_specified_length(self):
        func = self._require_new_api()
        email = {
            "subject": "Your code",
            "body": "short 1234 and target 654321",
            "body_html": "",
        }

        result = func(email, code_length="6-6")

        self.assertEqual(result.get("verification_code"), "654321")

    def test_extract_with_code_regex_supports_alphanumeric_code(self):
        func = self._require_new_api()
        email = {
            "subject": "OTP",
            "body": "Use AB12CD to continue",
            "body_html": "",
        }

        result = func(email, code_regex=r"\b[A-Z0-9]{6}\b")

        self.assertEqual(result.get("verification_code"), "AB12CD")

    def test_extract_with_code_source_subject_only(self):
        func = self._require_new_api()
        email = {
            "subject": "Code 778899",
            "body": "no code here",
            "body_html": "",
        }

        result = func(email, code_source="subject")

        self.assertEqual(result.get("verification_code"), "778899")

    def test_extract_with_preferred_link_keywords_returns_verify_link_first(self):
        func = self._require_new_api()
        email = {
            "subject": "Please verify your email",
            "body": "Open https://example.com/home or https://example.com/verify?token=abc",
            "body_html": "",
        }

        result = func(email)

        self.assertIn("verify", result.get("verification_link", ""))


if __name__ == "__main__":
    unittest.main()
