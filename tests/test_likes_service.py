import asyncio
import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from insta_cleaner.likes import collect_likes
from test_probe_likes import payload


def media_body(pk, cursor='next'):
    doc = json.loads(payload([cursor]))
    doc['payload']['layout']['bloks_payload'].append(
        f'(bk.action.array.Make, "{pk}_42", "CODE{pk}", "clips", (bk.action.i32.Const, 2))')
    return json.dumps(doc)


class LikesServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_seed_and_browser_continuation_deduplicate(self):
        handlers = {}
        seed = SimpleNamespace(status=200, text=AsyncMock(return_value=media_body('100')),
            url='https://www.instagram.com/async/wbloks/fetch/?appid=com.instagram.privacy.activity_center.liked_media_screen',
            request=SimpleNamespace(post_data='params=%7B%7D&fb_dtsg=PRIVATE', all_headers=AsyncMock(return_value={})))
        async def navigate(*args, **kwargs):
            handlers['response'](seed)
        page = SimpleNamespace(on=lambda name, fn: handlers.update({name: fn}),
            remove_listener=Mock(), goto=navigate, url='https://www.instagram.com/your_activity/interactions/likes/',
            evaluate=AsyncMock(return_value={'status': 200, 'body': media_body('200')}), close=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        with patch('insta_cleaner.likes.session_identity', AsyncMock(return_value=('1', None))), \
             patch('insta_cleaner.likes.asyncio.sleep', new_callable=AsyncMock), contextlib.redirect_stdout(io.StringIO()):
            tracker, result = await collect_likes(context, pages=2)
        self.assertEqual(len(tracker.likes), 2)
        self.assertEqual(result['pages'], 2)
        self.assertFalse(result['complete'])
        args = page.evaluate.call_args.args[1]
        self.assertIn('liked_next', args['url'])
        self.assertNotIn('liked_unlike', args['url'])
        self.assertEqual(json.loads(args['form']['params'])['cursor'], 'next')
        page.close.assert_awaited_once()
