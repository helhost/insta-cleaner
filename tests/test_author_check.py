import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from author_check import AuthorTracker, inspect_metadata, metadata, metadata_endpoint, post_code


class AuthorTests(unittest.TestCase):
    def test_preview_deduplicates_and_labels_inference(self):
        t = AuthorTracker()
        records = {'100_42': ('ABC', 'clips', '2')}
        t.add_likes(records)
        t.add_likes(records)
        self.assertEqual(len(t.preview()), 1)
        self.assertEqual(t.preview()[0]['evidence'], 'inferred')
        self.assertEqual(t.preview()[0]['product'], 'clips')
        self.assertEqual(len(t.preview('42')), 1)
        self.assertEqual(t.preview('43'), [])
        t.add_details([('100', 'ABC', {'42'})])
        self.assertEqual(t.preview()[0]['evidence'], 'matched')

    def test_preview_mismatch_uses_explicit_owner_and_conflict_is_unknown(self):
        t = AuthorTracker()
        t.add_likes({'100_42': ('ABC', 'clips', '2')})
        t.add_details([('100', 'ABC', {'43'})])
        self.assertEqual(t.preview('42'), [])
        self.assertEqual(t.preview('43')[0]['evidence'], 'mismatched')
        t.add_details([('100', 'ABC', {'44'})])
        self.assertIsNone(t.preview()[0]['author_id'])
        self.assertEqual(t.preview('43'), [])

    def test_route_instance_values_not_parameter_schema(self):
        result = {'route_match_infos': [{'instanceParams': {'shortcode': 'ABC'},
                   'routeParams': {'shortcode': {'coercibleType': 'string'}}}],
                  'exports': {'rootView': {'props': {'media_id': '100', 'media_owner_id': '42'}}}}
        self.assertEqual(metadata(json.dumps({'payload': {'result': result}})), [('100', 'ABC', {'42'})])
        result['route_match_infos'].append({'instanceParams': {'shortcode': 'OTHER'}})
        self.assertEqual(metadata(json.dumps(result)), [])

    def test_bulk_route_results_keep_authors_scoped(self):
        def route(code, pk, owner):
            return {'route_match_infos': [{'instanceParams': {'shortcode': code}}],
                    'exports': {'hostableView': {'props': {'media_id': pk, 'media_owner_id': owner}}}}
        body = json.dumps({'payloads': {'first': {'result': route('ABC', '100', '42')},
                                       'second': {'result': route('DEF', '200', '43')}}})
        self.assertCountEqual(metadata(body), [('100', 'ABC', {'42'}), ('200', 'DEF', {'43'})])
        self.assertEqual(metadata(body, 'ABC'), [('100', 'ABC', {'42'})])
        self.assertTrue(metadata_endpoint('https://www.instagram.com/ajax/route-definition/'))
        self.assertTrue(metadata_endpoint('https://www.instagram.com/ajax/navigation/'))

    def test_initial_document_embedded_json(self):
        node = {'id': '100', 'shortcode': 'ABC', 'owner': {'id': '42'}}
        html = '<html><script>throw "must not execute";</script><script type="application/json">' + json.dumps({'payload': json.dumps({'data': node})}) + '</script></html>'
        self.assertEqual(metadata(html), [('100', 'ABC', {'42'})])

    def test_incremental_json_and_no_url_dependency(self):
        node = {'id': '100', 'shortcode': 'ABC', 'owner': {'id': '42'}}
        stream = json.dumps({'data': None}) + '\n' + json.dumps({'data': node})
        self.assertEqual(metadata(stream), [('100', 'ABC', {'42'})])

    def test_diagnostics_are_counts_not_private_values(self):
        rows, counts = inspect_metadata(json.dumps({'secret': 'SECRET', 'data': {'code': 'ABC', 'user': {'username': 'PRIVATE'}}}))
        self.assertEqual(rows, [])
        self.assertEqual(counts['media_nodes'], 1)
        self.assertEqual(counts['with_author'], 0)
        self.assertTrue(all(type(v) is int for v in counts.values()))

    def test_explicit_author_only(self):
        body = json.dumps({'data': {'items': [
            {'pk': '100', 'code': 'ABC', 'user': {'pk': '42'}},
            {'id': '200_42', 'code': 'OTHER', 'user': {'pk': '42'}},
            {'id': '300_42', 'code': 'ABC'},
        ]}})
        self.assertEqual(metadata(body, 'ABC'), [('100', 'ABC', {'42'})])

    def test_graphql_owner_and_errors(self):
        node = {'id': '100', 'shortcode': 'ABC', 'owner': {'id': '42'}}
        self.assertEqual(metadata(json.dumps({'data': node}), 'ABC'), [('100', 'ABC', {'42'})])
        self.assertEqual(metadata(json.dumps({'data': node, 'errors': ['failure']}), 'ABC'), [])

    def test_exact_join_reverse_order_and_duplicate(self):
        t = AuthorTracker()
        self.assertEqual(t.add_details([('100', 'ABC', {'42'})]), [])
        self.assertEqual(t.add_likes({'100_42': ('ABC', 'clips', '2')}), [(1, 'matched')])
        self.assertEqual(t.add_details([('100', 'ABC', {'42'})]), [])
        self.assertEqual(t.add_likes({'100_42': ('WRONG', 'clips', '2')}), [])
        self.assertEqual(len(t.reported), 1)

    def test_mismatch_and_conflict_revoke_match(self):
        t = AuthorTracker()
        t.add_likes({'100_42': ('ABC', 'clips', '2')})
        self.assertEqual(t.add_details([('100', 'ABC', {'43'})]), [(1, 'mismatched')])
        self.assertEqual(t.add_details([('100', 'ABC', {'42'})]), [(1, 'conflicting')])

    def test_endpoint_and_page_scope(self):
        self.assertEqual(post_code('https://www.instagram.com/reel/ABC/?x=1'), 'ABC')
        self.assertIsNone(post_code('https://evil.test/p/ABC/'))
        self.assertTrue(metadata_endpoint('https://www.instagram.com/api/v1/media/100/info/'))
        self.assertFalse(metadata_endpoint('https://www.instagram.com/api/v1/media/100/delete/'))


if __name__ == '__main__':
    unittest.main()
