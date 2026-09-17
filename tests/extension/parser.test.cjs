const test = require('node:test');
const assert = require('node:assert/strict');
const { parse, isInitialLikes, validateItems } = require('../../extension/parser.js');
const tuple = '(bk.action.array.Make, "100_42", "ABC", "clips", (bk.action.i32.Const, 2))';
const body = JSON.stringify({ payload: { layout: { bloks_payload: { x: [tuple, tuple] } } } });
test('deduplicates exact captured tuples and labels authors inferred', () => {
  assert.deepEqual(parse('for (;;);' + body), [
    { mediaId: '100', authorId: '42', code: 'ABC', product: 'clips', evidence: 'inferred' },
  ]);
});
test('accepts only initial read endpoint on Instagram', () => {
  const url =
    'https://www.instagram.com/async/wbloks/fetch/?appid=com.instagram.privacy.activity_center.liked_media_screen';
  assert.equal(isInitialLikes(url), true);
  for (const other of [
    url.replace('liked_media_screen', 'liked_unlike'),
    url.replace('liked_media_screen', 'liked_next'),
    url.replace('www.instagram.com', 'evil.test'),
  ])
    assert.equal(isInitialLikes(other), false);
});
test('rejects server errors, empty and malformed data', () => {
  for (const b of [
    'null',
    'bad',
    '{"payload":null}',
    JSON.stringify({ payload: { layout: { bloks_payload: [] } } }),
  ])
    assert.throws(() => parse(b));
});
test('bridge validation strips extra fields and rejects forged evidence and links', () => {
  const row = parse(body)[0];
  assert.deepEqual(validateItems([{ ...row, sessionid: 'private' }]), [row]);
  assert.throws(() => validateItems([{ ...row, code: '<script>' }]));
  assert.throws(() => validateItems([{ ...row, evidence: 'matched' }]));
});
