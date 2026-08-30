import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.solver import TurnstileSolver


class SolverTests(unittest.TestCase):
    def test_page_mints_token_without_calling_api(self):
        page_html = (Path(__file__).parents[1] / "page" / "index.html").read_text()

        self.assertIn("turnstile.execute(widgetId)", page_html)
        self.assertNotIn("fetch(", page_html)
        self.assertNotIn("linkedin_url", page_html)

    @patch.object(TurnstileSolver, "stop_local_server")
    @patch.object(TurnstileSolver, "start_local_server")
    @patch("src.solver.StealthyFetcher.fetch")
    def test_proxy_is_opt_in_for_browser(self, fetch, start_server, stop_server):
        page = MagicMock()
        page.evaluate.return_value = "solved-token"

        def run_page_action(_, **kwargs):
            kwargs["page_action"](page)

        fetch.side_effect = run_page_action

        token = TurnstileSolver().solve(proxy_url=None)

        self.assertEqual(token, "solved-token")
        self.assertNotIn("proxy", fetch.call_args.kwargs)
        self.assertEqual(fetch.call_args.kwargs["retries"], 1)
        self.assertFalse(
            any("disk-cache" in arg for arg in fetch.call_args.kwargs["additional_args"]["args"])
        )
        start_server.assert_called_once_with()
        stop_server.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
