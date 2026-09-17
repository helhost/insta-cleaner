const test = require('node:test'),
  assert = require('node:assert/strict'),
  vm = require('node:vm'),
  fs = require('node:fs');
function setup({
  toast = 'Du har sluttet å like 2 innlegg.',
  status = 200,
  account = '42',
  error = false,
  timeout = false,
} = {}) {
  const requests = [];
  const ctx = vm.createContext({
    URL,
    URLSearchParams,
    AbortSignal,
    location: {
      origin: 'https://www.instagram.com',
      pathname: '/your_activity/interactions/likes/',
    },
    document: { cookie: `ds_user_id=${account}` },
    __instaCleanerReadSeed: {
      token: 'scan1',
      body: 'seed',
      url: 'https://www.instagram.com/async/wbloks/fetch/?appid=com.instagram.privacy.activity_center.liked_media_screen',
      form: 'params=%7B%7D',
      headers: {},
    },
    InstaCleanerParser: { continuation: () => ({}) },
    InstaCleanerDates: { refreshParams: () => ({ content_container_id: 1 }) },
    fetch: async (url, options) => {
      requests.push({ url, params: JSON.parse(options.body.get('params')) });
      if (timeout) throw Error('timeout');
      const tree = {
        'bk.components.internal.Action': {
          handler: `(bk.action.core.TakeLast, (bk.action.io.Toast, ${JSON.stringify(toast)}), null)`,
        },
      };
      const data = {
        error: error ? 1 : undefined,
        payload: { layout: { bloks_payload: { tree } } },
      };
      return { status, text: async () => JSON.stringify(data) };
    },
  });
  vm.runInContext(fs.readFileSync('extension/batch.js', 'utf8'), ctx);
  return {
    requests,
    send: (execute) =>
      ctx.InstaCleanerBatch.send(
        'scan1',
        '42',
        [
          { mediaId: '100', authorId: '43' },
          { mediaId: '200', authorId: '44' },
        ],
        {},
        execute,
      ),
  };
}
test('preflight never mutates; confirmed batch uses exact composite IDs and captured action', async () => {
  const s = setup();
  assert.equal((await s.send(false)).status, 'ready');
  assert.equal(s.requests.length, 0);
  const result = await s.send(true);
  assert.equal(result.status, 'batch-confirmed');
  assert.equal(result.count, 2);
  assert.equal(s.requests.length, 1);
  assert.equal(s.requests[0].params.items_for_action, '100_43,200_44');
  assert.equal(s.requests[0].params.number_of_items, 2);
  assert.equal(
    new URL(s.requests[0].url).searchParams.get('appid'),
    'com.instagram.privacy.activity_center.liked_unlike',
  );
});
test('HTTP 200 alone, wrong counts, errors and timeouts never imply success or retry', async () => {
  for (const options of [
    { toast: 'Done' },
    { toast: 'Du har sluttet å like 1 innlegg.' },
    { error: true },
    { status: 429 },
    { timeout: true },
  ]) {
    const s = setup(options),
      result = await s.send(true);
    assert.equal(result.status, 'unverified');
    assert.equal(result.sent, true);
    assert.equal(s.requests.length, 1);
  }
});
test('wrong account blocks request before sending', async () => {
  const s = setup({ account: '99' });
  assert.equal((await s.send(true)).sent, false);
  assert.equal(s.requests.length, 0);
});

test('server errors retain the HTTP status and never retry the removal', async () => {
  const s = setup({ status: 500 });
  const result = await s.send(true);
  assert.equal(result.status, 'unverified');
  assert.equal(result.httpStatus, 500);
  assert.equal(result.sent, true);
  assert.equal(s.requests.length, 1);
});
