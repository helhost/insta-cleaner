import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from observe_likes import PREFIX, Reporter, activity_action, selected_authors, summarize, close_context


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_driver_disconnect_during_close(self):
        context = AsyncMock()
        context.close.side_effect = Exception('BrowserContext.close: Connection closed while reading from the driver')
        await close_context(context)
        context.close.assert_awaited_once()

    async def test_unexpected_errors_remain_visible(self):
        context = AsyncMock()
        context.close.side_effect = RuntimeError('unexpected failure')
        with self.assertRaises(RuntimeError):
            await close_context(context)

    async def test_normal_close(self):
        context = AsyncMock()
        await close_context(context)
        context.close.assert_awaited_once()


def request(value, nested=False):
    params = {"main_authors_state_value": value}
    if nested:
        params = {"activity_center_params": json.dumps(params)}
    return urlencode({"params": json.dumps(params), "fb_dtsg": "SECRET_MARKER"})


def body(ids=("100_42", "200_42")):
    expressions = [f'(bk.action.array.Make, "{i}", "Example", "clips", (bk.action.i32.Const, 2))' for i in ids]
    return "for (;;);" + json.dumps({"payload": {"layout": {"bloks_payload": {"data": expressions}}}})


class ObserverTests(unittest.TestCase):
    def test_allowlist_excludes_mutations_and_other_hosts(self):
        url = "https://www.instagram.com/async/wbloks/fetch/?appid=" + PREFIX
        self.assertEqual(activity_action(url + "liked_next"), "liked_next")
        self.assertIsNone(activity_action(url + "liked_unlike"))
        self.assertIsNone(activity_action((url + "liked_next").replace("instagram.com", "instagram.com.evil.test")))

    def test_filter_formats_and_nested_pagination(self):
        for value in (42, "42", "42, 43", ["42", "43"], '["42", "43"]'):
            for nested in (True, False):
                state, ids = selected_authors(request(value, nested))
                self.assertEqual(state, "filtered")
                self.assertIn("42", ids)

    def test_unknown_is_not_unfiltered_or_guessed(self):
        for value in (None, True, {"id": "42"}, "username42", ["42", None], "[broken", "0"):
            self.assertEqual(selected_authors(request(value)), ("unknown", set()))
        self.assertEqual(selected_authors(""), ("unknown", set()))
        self.assertEqual(selected_authors(request("")), ("unfiltered", set()))

    def test_comparison_is_per_request_and_deduplicated(self):
        b = body(("100_42", "100_42", "200_42"))
        match = summarize("liked_refresh", "filtered", {"42"}, 200, b)
        other = summarize("liked_next", "filtered", {"43"}, 200, b)
        self.assertEqual((match["items"], match["matching_items"]), (2, 2))
        self.assertEqual(other["comparison"], "mismatch")

    def test_error_or_empty_never_verifies(self):
        for status, text in ((429, body()), (200, "SECRET_MARKER"), (200, body(()))):
            result = summarize("liked_next", "filtered", {"42"}, status, text)
            self.assertEqual(result["comparison"], "not_checked")

    def test_summary_does_not_expose_private_identifiers(self):
        reporter = Reporter()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            reporter.show(summarize("liked_next", *selected_authors(request("42")), 200, body()))
            reporter.show(summarize("liked_next", "unknown", set(), 200, "SECRET_MARKER"))
            reporter.finish()
        for private in ("SECRET_MARKER", "100_42", "200_42", "Example"):
            self.assertNotIn(private, out.getvalue())
        self.assertIn("not independently verified", out.getvalue())


if __name__ == "__main__":
    unittest.main()
