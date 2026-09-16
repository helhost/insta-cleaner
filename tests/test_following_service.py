import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from insta_cleaner.following import collect_following, FollowingSnapshot, filter_by_following
from test_following_check import body


def context_for(responses):
    cookies = [{'name': 'ds_user_id', 'value': '42'}, {'name': 'sessionid', 'value': 'secret'}]
    return SimpleNamespace(cookies=AsyncMock(return_value=cookies), request=SimpleNamespace(
        get=AsyncMock(side_effect=[SimpleNamespace(status=status, text=AsyncMock(return_value=data),
                          dispose=AsyncMock()) for status, data in responses])))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_pagination(self):
        context = context_for([(200, body()), (200, body('2', False, ''))])
        snapshot = await collect_following(context, delay=0)
        self.assertTrue(snapshot.complete)
        self.assertEqual(snapshot.accounts, {'1': 'example', '2': 'example'})
        self.assertEqual(snapshot.pages, 2)
        self.assertIn('max_id=next', context.request.get.call_args.args[0])

    async def test_failure_keeps_partial_data(self):
        context = context_for([(200, body()), (429, '')])
        snapshot = await collect_following(context, delay=0)
        self.assertFalse(snapshot.complete)
        self.assertEqual(snapshot.accounts, {'1': 'example'})
        self.assertEqual(snapshot.stop_reason, 'HTTP 429')
        self.assertEqual(snapshot.membership('2', account_id='42'), 'unknown')

    async def test_repeated_cursor_stops(self):
        context = context_for([(200, body()), (200, body('2'))])
        snapshot = await collect_following(context, delay=0)
        self.assertFalse(snapshot.complete)
        self.assertEqual(snapshot.stop_reason, 'repeated pagination cursor')

    async def test_restricted_terminal_is_incomplete(self):
        data = json.loads(body('1', False, ''))
        data['should_limit_list_of_followings'] = True
        snapshot = await collect_following(context_for([(200, json.dumps(data))]), delay=0)
        self.assertFalse(snapshot.complete)

    async def test_session_change_stops_before_next_request(self):
        context = context_for([(200, body())])
        original = await context.cookies()
        context.cookies.side_effect = [original, original,
            [{'name': 'ds_user_id', 'value': '43'}, {'name': 'sessionid', 'value': 'secret'}]]
        snapshot = await collect_following(context, delay=0)
        self.assertFalse(snapshot.complete)
        self.assertEqual(context.request.get.await_count, 1)
        self.assertEqual(snapshot.stop_reason, 'session account changed')

    def test_filters_require_author_evidence_and_same_account(self):
        snapshot = FollowingSnapshot('42', 'now', {'1': 'example'}, True, 1, 'final page reached')
        items = [{'author_id': '1', 'evidence': 'matched'},
                 {'author_id': '2', 'evidence': 'matched'},
                 {'author_id': '3', 'evidence': 'inferred'},
                 {'author_id': None, 'evidence': 'conflicting'}]
        self.assertEqual(filter_by_following(items, snapshot, account_id='42', relationship='followed'), items[:1])
        self.assertEqual(filter_by_following(items, snapshot, account_id='42', relationship='not-followed'), items[1:2])
        self.assertEqual(filter_by_following(items, snapshot, account_id='42', relationship='unknown'), items[2:])
        self.assertEqual(filter_by_following(items, snapshot, account_id='43', relationship='unknown'), items)
