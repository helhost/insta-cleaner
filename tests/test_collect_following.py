import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_following_check import body
from tools.following_check import FollowingTracker
from tools import collect_following


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    async def run_collection(self, responses):
        tracker = FollowingTracker()
        tracker.add(("42", "", True), 200, body())
        seed = SimpleNamespace(
            url="https://www.instagram.com/api/v1/friendships/42/following/?count=12",
            request=SimpleNamespace(
                all_headers=AsyncMock(return_value={"x-ig-app-id": "test"})
            ),
        )
        replies = [
            SimpleNamespace(
                status=status, text=AsyncMock(return_value=data), dispose=AsyncMock()
            )
            for status, data in responses
        ]
        context = SimpleNamespace(
            request=SimpleNamespace(get=AsyncMock(side_effect=replies))
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                collect_following, "OUTPUT", Path(directory)
            ), patch.object(
                collect_following.asyncio, "sleep", new_callable=AsyncMock
            ), contextlib.redirect_stdout(
                io.StringIO()
            ):
                await collect_following.collect(context, seed, tracker)
            snapshot = json.loads(next(Path(directory).glob("*.json")).read_text())
        return snapshot, context.request.get

    async def test_terminal_export_and_cursor(self):
        snapshot, get = await self.run_collection([(200, body("2", False, ""))])
        self.assertTrue(snapshot["complete"])
        self.assertEqual([a["id"] for a in snapshot["accounts"]], ["1", "2"])
        self.assertFalse(snapshot["session_identity_verified"])
        self.assertIn("max_id=next", get.call_args.args[0])
        self.assertIn("count=50", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["max_redirects"], 0)
        self.assertEqual(get.await_count, 1)

    async def test_http_failure_exports_partial_without_retry(self):
        snapshot, get = await self.run_collection([(429, "")])
        self.assertFalse(snapshot["complete"])
        self.assertIn("HTTP 429", snapshot["reasons"])
        self.assertEqual(get.await_count, 1)

    async def test_stops_without_new_members(self):
        snapshot, get = await self.run_collection(
            [(200, body("1", True, str(i))) for i in range(3)]
        )
        self.assertFalse(snapshot["complete"])
        self.assertEqual(get.await_count, 3)

    async def test_direct_start_uses_session_owner_and_requested_size(self):
        tracker = FollowingTracker()
        cookies = [
            {"name": "ds_user_id", "value": "42"},
            {"name": "sessionid", "value": "PRIVATE_SESSION"},
            {"name": "csrftoken", "value": "PRIVATE_CSRF"},
        ]
        reply = SimpleNamespace(
            status=200,
            text=AsyncMock(return_value=body("1", False, "")),
            dispose=AsyncMock(),
        )
        context = SimpleNamespace(
            cookies=AsyncMock(return_value=cookies),
            request=SimpleNamespace(get=AsyncMock(return_value=reply)),
        )
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                collect_following, "OUTPUT", Path(directory)
            ), contextlib.redirect_stdout(io.StringIO()) as output:
                await collect_following.collect_signed_in(context, tracker, 100)
            saved = next(Path(directory).glob("*.json")).read_text()
        self.assertEqual(
            context.request.get.call_args.args[0],
            "https://www.instagram.com/api/v1/friendships/42/following/?count=100",
        )
        self.assertEqual(context.request.get.await_count, 1)
        self.assertEqual(json.loads(saved)["list_owner_id"], "42")
        self.assertNotIn("PRIVATE_", saved + output.getvalue())
        reply.dispose.assert_awaited_once()

    async def test_missing_session_does_not_request_an_account(self):
        context = SimpleNamespace(
            cookies=AsyncMock(return_value=[{"name": "ds_user_id", "value": "42"}]),
            request=SimpleNamespace(get=AsyncMock()),
        )
        with patch.object(
            collect_following.asyncio, "sleep", new_callable=AsyncMock
        ), contextlib.redirect_stdout(io.StringIO()):
            await collect_following.collect_signed_in(context, FollowingTracker())
        context.request.get.assert_not_awaited()

    async def test_headless_missing_login_exits_without_waiting(self):
        context = SimpleNamespace(
            cookies=AsyncMock(return_value=[]), request=SimpleNamespace(get=AsyncMock())
        )
        with patch.object(
            collect_following.asyncio, "sleep", new_callable=AsyncMock
        ) as sleep, contextlib.redirect_stdout(io.StringIO()) as output:
            await collect_following.collect_signed_in(
                context, FollowingTracker(), wait_for_login=False
            )
        sleep.assert_not_awaited()
        context.request.get.assert_not_awaited()
        self.assertIn("without --headless", output.getvalue())
