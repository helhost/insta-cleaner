import json
import unittest
from probe_likes import next_params, envelope_error


def payload(cursors):
    expressions = []
    for cursor in cursors:
        values = ', '.join(json.dumps(x) for x in ['9', '{"test":"escaped value"}', cursor, '1', '2'])
        expressions.append('(bk.action.bloks.AsyncActionWithDataManifest, '
            '"com.instagram.privacy.activity_center.liked_next", '
            '(bk.action.map.Make, (bk.action.array.Make, "page_size", "activity_center_params", '
            '"cursor", "container_id", "element_id"), (bk.action.array.Make, ' + values + ')))')
    return json.dumps({'payload': {'layout': {'bloks_payload': expressions}}})


class PaginationTests(unittest.TestCase):
    def test_extracts_escaped_json_without_evaluation(self):
        params = next_params('for (;;);' + payload(['cursor']))
        self.assertEqual(params['cursor'], 'cursor')
        self.assertEqual(json.loads(params['activity_center_params']), {'test': 'escaped value'})

    def test_ambiguous_or_absent_cursor_stops(self):
        for cursors in [[], ['a', 'b'], ['']]:
            with self.assertRaises(ValueError):
                next_params(payload(cursors))

    def test_identical_instructions_deduplicate(self):
        self.assertEqual(next_params(payload(['a', 'a']))['cursor'], 'a')

    def test_mutation_action_is_never_accepted(self):
        with self.assertRaises(ValueError):
            next_params(payload(['a']).replace('liked_next', 'liked_unlike'))


class EnvelopeTests(unittest.TestCase):
    def test_server_error_is_reported_without_private_details(self):
        body = json.dumps({'payload': None, 'error': 1357054, 'errorDescription': 'PRIVATE'})
        self.assertEqual(envelope_error(body), 'unsupported page envelope; server error 1357054')

    def test_non_object_and_non_numeric_errors_are_redacted(self):
        for body in ['null', '[]', '{"error":"PRIVATE"}']:
            self.assertEqual(envelope_error(body), 'unsupported page envelope; server error unknown')

    def test_supported_envelope(self):
        self.assertIsNone(envelope_error(payload(['cursor'])))

class AuthorSampleTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_joins_exact_identity_only(self):
        import contextlib
        import io
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        from author_check import AuthorTracker
        from probe_likes import check_authors
        tracker = AuthorTracker()
        tracker.add_likes({'100_42': ('ABC', 'clips', '2'), '200_43': ('DEF', 'feed', '1')})
        data = json.dumps({'items': [
            {'pk': '100', 'code': 'ABC', 'user': {'pk': '42'}},
            {'pk': '200', 'code': 'DEF', 'user': {'pk': '99'}}]})
        page = SimpleNamespace(on=Mock(), remove_listener=Mock(), goto=AsyncMock(),
                               content=AsyncMock(return_value=data), close=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        with patch('probe_likes.asyncio.sleep', new_callable=AsyncMock), contextlib.redirect_stdout(io.StringIO()):
            await check_authors(context, tracker, 1)
        self.assertEqual([row['evidence'] for row in tracker.preview()], ['matched', 'inferred'])
        page.goto.assert_awaited_once()
        page.close.assert_awaited_once()
