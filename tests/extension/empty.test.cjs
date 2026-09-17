const test = require('node:test'),
  assert = require('node:assert/strict'),
  p = require('../../extension/parser');
function fixture(label = 'Ingen treff') {
  return {
    data: [
      {
        data: {
          key: 'dtl:ig_activity_center:ya_has_items_rendered',
          initial_lispy: '(bk.action.bool.Const, false)',
        },
      },
    ],
    embedded_payloads: [
      {
        'ig.components.Icon': { resource_name: 'error_outline_96' },
        'bk.components.AccessibilityExtension': { role: 'Header', label },
      },
    ],
  };
}
const body = (x) => JSON.stringify({ payload: { layout: { bloks_payload: x } } });
test('recognizes observed empty range without treating generic errors as empty', () => {
  assert.deepEqual(p.parse(body(fixture())), []);
  assert.throws(() => p.parse(body(fixture('Something went wrong'))));
  const missing = fixture();
  delete missing.data;
  assert.throws(() => p.parse(body(missing)));
});
