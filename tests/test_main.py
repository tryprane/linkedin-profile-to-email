import json
import unittest
from unittest.mock import MagicMock, patch

from src.main import build_api_request, query_mailmeteor, validate_and_normalize_linkedin_url


class LinkedInUrlTests(unittest.TestCase):
    def test_normalizes_bare_handle(self):
        valid, normalized, error = validate_and_normalize_linkedin_url("satyanadella")

        self.assertTrue(valid)
        self.assertEqual(normalized, "https://www.linkedin.com/in/satyanadella")
        self.assertEqual(error, "")

    def test_rejects_non_profile_url(self):
        valid, _, error = validate_and_normalize_linkedin_url(
            "https://www.linkedin.com/company/microsoft"
        )

        self.assertFalse(valid)
        self.assertIn("Invalid LinkedIn profile URL", error)


class ApiRequestTests(unittest.TestCase):
    def test_request_contains_token_once_and_minimal_body(self):
        request = build_api_request(
            "https://www.linkedin.com/in/satyanadella",
            "token+with/special=chars",
        )

        self.assertIn(
            "cf-turnstile-response=token%2Bwith%2Fspecial%3Dchars",
            request.full_url,
        )
        self.assertEqual(
            json.loads(request.data),
            {"linkedin_url": "https://www.linkedin.com/in/satyanadella"},
        )
        self.assertNotIn(b"token", request.data)

    @patch("src.main.urllib.request.build_opener")
    def test_direct_request_uses_default_verified_tls_opener(self, build_opener):
        response = MagicMock()
        response.read.return_value = b'{"found":false}'
        build_opener.return_value.open.return_value.__enter__.return_value = response

        result, transfer_bytes, _ = query_mailmeteor(
            "https://www.linkedin.com/in/satyanadella",
            "token",
            None,
        )

        build_opener.assert_called_once_with()
        self.assertEqual(result, {"found": False})
        self.assertGreater(transfer_bytes, len(response.read.return_value))


if __name__ == "__main__":
    unittest.main()
