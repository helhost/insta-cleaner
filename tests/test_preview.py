import contextlib
import io
import unittest
from unittest.mock import AsyncMock, patch

from insta_cleaner.authors import AuthorTracker
from insta_cleaner.following import FollowingSnapshot, LoginRequired
from insta_cleaner.preview import build_preview, select_items


def items():
    return [dict(media_id=str(i), code=f'CODE{i}', product=product, author_id=author, evidence=evidence)
        for i, product, author, evidence in [
            (1, 'clips', '42', 'matched'), (2, 'clips', '43', 'matched'),
            (3, 'clips', '44', 'inferred'), (4, 'feed', '43', 'matched'),
            (5, 'carousel_container', None, 'conflicting')]]


def following(complete=True, account='1'):
    return FollowingSnapshot(account, 'now', {'42': 'example'}, complete, 1, 'final page reached')


class SelectionTests(unittest.TestCase):
    def test_only_explicit_unfollowed_reels_selected(self):
        selected, unknown = select_items(items(), account_id='1', following=following(), content='reels', relationship='not-followed')
        self.assertEqual([x['media_id'] for x in selected], ['2'])
        self.assertEqual([x['media_id'] for x in unknown], ['3'])

    def test_incomplete_following_never_establishes_absence(self):
        selected, unknown = select_items(items(), account_id='1', following=following(False), relationship='not-followed')
        self.assertEqual(selected, [])
        self.assertEqual(len(unknown), 4)

    def test_other_account_cannot_classify_membership(self):
        selected, unknown = select_items(items(), account_id='2', following=following(), relationship='followed')
        self.assertEqual(selected, [])
        self.assertEqual(len(unknown), 5)

    def test_posts_include_carousels(self):
        selected, unknown = select_items(items(), account_id='1', content='posts')
        self.assertEqual([x['media_id'] for x in selected], ['4', '5'])
        self.assertEqual([x['media_id'] for x in unknown], ['5'])


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_following_is_loaded_only_when_needed(self):
        for relationship in ['all', 'not-followed']:
            tracker = AuthorTracker()
            tracker.add_likes({'100_43': ('ABC', 'clips', '2'), '200_42': ('DEF', 'feed', '1')})
            async def resolve(context, target, limit, **kwargs):
                self.assertEqual(limit, 1)
                target.add_details([('100', 'ABC', {'43'})])
            with patch('insta_cleaner.preview.session_identity', AsyncMock(return_value=('1', None))), \
                 patch('insta_cleaner.preview.collect_likes', AsyncMock(return_value=(tracker, {'account_id': '1', 'pages': 1, 'complete': False, 'stop_reason': 'page limit reached'}))), \
                 patch('insta_cleaner.preview.check_authors', AsyncMock(side_effect=resolve)), \
                 patch('insta_cleaner.preview.collect_following', AsyncMock(return_value=following())) as collect, contextlib.redirect_stdout(io.StringIO()):
                report = await build_preview(None, pages=1, content='reels', relationship=relationship)
            self.assertEqual(collect.await_count, int(relationship != 'all'))
            self.assertEqual(len(report['selected']), 1)
            self.assertTrue(report['read_only'])
            self.assertFalse(report['likes_collection']['complete'])

    async def test_account_switch_rejects_preview(self):
        with patch('insta_cleaner.preview.session_identity', AsyncMock(return_value=('1', None))), \
             patch('insta_cleaner.preview.collect_likes', AsyncMock(return_value=(AuthorTracker(), {'account_id': '2'}))):
            with self.assertRaises(LoginRequired):
                await build_preview(None)
