const test = require('node:test'),
  assert = require('node:assert/strict'),
  vm = require('node:vm'),
  fs = require('node:fs');
function worker() {
  const values = {},
    changed = [],
    reloaded = [],
    event = { addListener() {} };
  let account = '42',
    tabUrl = 'https://www.instagram.com/',
    token = 0,
    clicked = 0,
    liked = true;
  const chrome = {
    cookies: { get: async () => (account ? { value: account } : null) },
    runtime: {
      getURL: (p) => 'chrome-extension://test/' + p,
      onMessage: event,
      onInstalled: event,
    },
    storage: {
      session: {
        get: async (k) => ({ [k]: values[k] }),
        set: async (x) => Object.assign(values, x),
        remove: async (k) => {
          delete values[k];
        },
      },
    },
    tabs: {
      query: async () => [{ id: 1, url: tabUrl }],
      update: async (...x) => changed.push(x),
      reload: async (id) => reloaded.push(id),
      onRemoved: event,
      sendMessage: async () => {},
      create: async () => ({ id: 2 }),
      get: async () => ({ status: 'complete' }),
      remove: async () => {},
    },
    scripting: {
      executeScript: async (options) => {
        if (!options.args[4]) return [{ result: { status: 'ready' } }];
        clicked++;
        liked = false;
        return [
          { result: { status: 'batch-confirmed', sent: true, count: options.args[2].length } },
        ];
      },
    },
    sidePanel: { setPanelBehavior: async () => {} },
  };
  const ctx = vm.createContext({
    chrome,
    crypto: { randomUUID: () => 'token' + ++token },
    URL,
    URLSearchParams,
    Date,
    console,
    AbortSignal,
    setTimeout: (f) => {
      f();
    },
    importScripts: () => {},
    fetch: async () => ({
      status: 200,
      json: async () => ({
        status: 'ok',
        items: [
          {
            pk: '100',
            code: 'ABC',
            user: { pk: '42' },
            has_liked: liked,
            media_type: 2,
            product_type: 'clips',
          },
        ],
      }),
    }),
  });
  for (const file of ['queue', 'dates', 'parser', 'following', 'workflow', 'batch'])
    vm.runInContext(fs.readFileSync(`extension/${file}.js`, 'utf8'), ctx);
  vm.runInContext(fs.readFileSync('extension/background.js', 'utf8'), ctx);
  return {
    ctx,
    chrome,
    values,
    changed,
    reloaded,
    clicks: () => clicked,
    setUrl: (v) => (tabUrl = v),
    setAccount: (v) => (account = v),
    call: (m, s) => ctx.handle(m, s),
  };
}
const panel = { url: 'chrome-extension://test/panel.html' },
  sender = {
    tab: { id: 1 },
    frameId: 0,
    url: 'https://www.instagram.com/your_activity/interactions/likes/',
  };
const item = {
  mediaId: '100',
  authorId: '42',
  code: 'ABC',
  product: 'clips',
  evidence: 'inferred',
};
async function scan(w) {
  await w.call({ type: 'SCAN', filters: { content: 'all', relationship: 'all' } }, panel);
}
async function ready(w) {
  await scan(w);
  await w.call(
    { type: 'CAPTURE', scanToken: 'token1', items: [item], page: 1, finished: true },
    sender,
  );
}
test('capture is account and scan scoped; pagination deduplicates', async () => {
  const w = worker();
  await scan(w);
  await w.call({ type: 'CAPTURE', scanToken: 'old', items: [item], page: 1 }, sender);
  assert.equal(w.values['scan:1'].pages, 0);
  await w.call(
    { type: 'CAPTURE', scanToken: 'token1', items: [{ ...item, secret: 'x' }], page: 1 },
    sender,
  );
  await w.call({ type: 'CAPTURE', scanToken: 'token1', items: [item], page: 2 }, sender);
  assert.equal(w.values['scan:1'].items.length, 1);
  assert.equal(w.values['scan:1'].status, 'ready');
  assert.equal(w.values['scan:1'].items[0].secret, undefined);
});
test('account changes discard scan; website cannot request removal', async () => {
  const w = worker();
  await ready(w);
  w.setAccount('43');
  assert.equal((await w.call({ type: 'STATE' }, panel)).state.status, 'error');
  await assert.rejects(w.call({ type: 'CONFIRM' }, sender));
  assert.equal(w.clicks(), 0);
});
test('batch status distinguishes requested size from returned items', async () => {
  const w = worker();
  await scan(w);
  await w.call({ type: 'CAPTURE', scanToken: 'token1', items: [item], page: 1 }, sender);
  await w.call(
    {
      type: 'CAPTURE',
      scanToken: 'token1',
      items: [{ ...item, mediaId: '200' }],
      page: 2,
      requestedPageSize: 100,
    },
    sender,
  );
  assert.equal(w.values['scan:1'].lastBatchSize, 1);
  assert.match(w.values['scan:1'].message, /Last batch: 1 items; requested 100/);
});
test('only prepared fixed selection can be confirmed; duplicate confirm cannot click twice', async () => {
  const w = worker();
  await ready(w);
  await assert.rejects(w.call({ type: 'CONFIRM', approval: 'fake' }, panel));
  await assert.rejects(w.call({ type: 'PREPARE', ids: ['999'] }, panel));
  const { approval } = await w.call({ type: 'PREPARE', ids: ['100'] }, panel);
  await w.call({ type: 'CONFIRM', approval: approval.token }, panel);
  await assert.rejects(w.call({ type: 'CONFIRM', approval: approval.token }, panel));
  for (let i = 0; i < 50 && w.values['scan:1'].status === 'removing'; i++)
    await new Promise((r) => setImmediate(r));
  assert.equal(w.clicks(), 1);
  assert.equal(w.values['scan:1'].results[0].status, 'unliked-server-confirmed');
});
test('uncertain click halts with no retry', async () => {
  const w = worker();
  await ready(w);
  let attempts = 0;
  w.chrome.scripting.executeScript = async (options) => {
    if (!options.args[4]) return [{ result: { status: 'ready' } }];
    attempts++;
    throw Error('timeout');
  };
  const { approval } = await w.call({ type: 'PREPARE', ids: ['100'] }, panel);
  await w.call({ type: 'CONFIRM', approval: approval.token }, panel);
  for (let i = 0; i < 50 && w.values['scan:1'].status === 'removing'; i++)
    await new Promise((r) => setImmediate(r));
  assert.equal(attempts, 1);
  assert.equal(w.values['scan:1'].status, 'halted');
  assert.equal(w.values['scan:1'].clickPending, true);
});
test('each scan navigates to a unique document without racing a reload', async () => {
  const w = worker();
  await scan(w);
  w.setUrl('https://www.instagram.com/your_activity/interactions/likes/#old');
  await scan(w);
  assert.equal(w.reloaded.length, 0);
  const first = new URL(w.changed[0][1].url),
    second = new URL(w.changed[1][1].url);
  assert.equal(first.searchParams.get('ic_scan'), 'token1');
  assert.equal(second.searchParams.get('ic_scan'), 'token2');
  assert.equal(new URLSearchParams(second.hash.slice(1)).get('ic-preview'), 'token2');
});
test('missing initial capture explains how to restart instead of reporting an empty scan', async () => {
  const w = worker();
  await scan(w);
  w.values['scan:1'].updated = Date.now() - 61000;
  const { state } = await w.call({ type: 'STATE' }, panel);
  assert.equal(state.status, 'ready');
  assert.match(state.message, /No Likes page was captured/);
});
test('stop scan retains partial matches and refuses late responses', async () => {
  const w = worker();
  await scan(w);
  await w.call({ type: 'STOP' }, panel);
  const result = await w.call(
    { type: 'CAPTURE', scanToken: 'token1', items: [item], page: 1 },
    sender,
  );
  assert.equal(result.stop, true);
  assert.equal(w.values['scan:1'].items.length, 0);
});
test('parallel chunks merge overlaps in date order and finish only after queue completion', async () => {
  const w = worker();
  await w.call(
    {
      type: 'SCAN',
      filters: {
        content: 'all',
        relationship: 'all',
        startDate: '2014-08-01',
        endDate: '2014-11-01',
      },
    },
    panel,
  );
  const total = w.values['scan:1'].rangeCount;
  const capture = (page, chunk, rows) =>
    w.call(
      {
        type: 'CAPTURE',
        scanToken: 'token1',
        queue: true,
        page,
        chunk,
        chunkPage: 1,
        items: rows,
        queueProgress: { completed: 0, total, workers: 2 },
      },
      sender,
    );
  await capture(1, 1, [{ ...item, mediaId: '200' }]);
  await capture(2, 0, [item, { ...item, mediaId: '200' }]);
  assert.equal(w.values['scan:1'].status, 'scanning');
  assert.equal(w.values['scan:1'].items.map((x) => x.mediaId).join(','), '100,200');
  await capture(3, 2, []);
  assert.equal(w.values['scan:1'].status, 'scanning');
  await w.call(
    {
      type: 'CAPTURE',
      scanToken: 'token1',
      queueDone: true,
      page: 3,
      queueProgress: { completed: total },
    },
    sender,
  );
  assert.equal(w.values['scan:1'].status, 'ready');
  assert.equal(w.values['scan:1'].queueProgress.completed, total);
});
test('all-author removal sends the entire selection once without post checks', async () => {
  const w = worker();
  await scan(w);
  const items = Array.from({ length: 42 }, (_, i) => ({ ...item, mediaId: String(100 + i) }));
  await w.call({ type: 'CAPTURE', scanToken: 'token1', items, page: 1, finished: true }, sender);
  let reads = 0;
  w.ctx.fetch = async () => {
    reads++;
    throw Error('Unexpected post check');
  };
  const sizes = [];
  w.chrome.scripting.executeScript = async (options) => {
    if (!options.args[4]) return [{ result: { status: 'ready' } }];
    sizes.push(options.args[2].length);
    await w.call({ type: 'STOP' }, panel);
    return [{ result: { status: 'batch-confirmed', sent: true, count: options.args[2].length } }];
  };
  const { approval } = await w.call({ type: 'PREPARE', ids: items.map((x) => x.mediaId) }, panel);
  await w.call({ type: 'CONFIRM', approval: approval.token }, panel);
  for (let i = 0; i < 50 && w.values['scan:1'].status === 'removing'; i++)
    await new Promise((r) => setImmediate(r));
  assert.deepEqual(sizes, [42]);
  assert.equal(reads, 0);
  assert.equal(w.values['scan:1'].results.length, 42);
  assert.equal(w.values['scan:1'].status, 'finished');
});
test('relationship selection uses captured author IDs without per-post metadata', async () => {
  const w = worker();
  await ready(w);
  w.values['scan:1'].filters.relationship = 'followed';
  w.values['scan:1'].following = { accountId: '42', accounts: { 42: 'example' }, complete: true };
  w.ctx.InstaCleanerFollowing.collect = async () => ({
    accountId: '42',
    accounts: { 42: 'example' },
    complete: true,
  });
  w.ctx.fetch = async () => {
    throw Error('Per-post requests must not be made');
  };
  const { approval } = await w.call({ type: 'PREPARE', ids: ['100'] }, panel);
  await w.call({ type: 'CONFIRM', approval: approval.token }, panel);
  for (let i = 0; i < 50 && w.values['scan:1'].status === 'removing'; i++)
    await new Promise((r) => setImmediate(r));
  assert.equal(w.values['scan:1'].status, 'finished');
  assert.equal(w.clicks(), 1);
  assert.equal(w.values['scan:1'].results[0].status, 'unliked-server-confirmed');
});
test('period progress updates independently of item pages and never regresses', async () => {
  const w = worker();
  await w.call(
    {
      type: 'SCAN',
      filters: {
        content: 'all',
        relationship: 'all',
        startDate: '2025-01-01',
        endDate: '2026-01-01',
      },
    },
    panel,
  );
  const total = w.values['scan:1'].rangeCount;
  assert.equal(total, 53);
  const progress = (completed) =>
    w.call(
      {
        type: 'CAPTURE',
        scanToken: 'token1',
        progressOnly: true,
        queueProgress: { completed, total, workers: 12 },
      },
      sender,
    );
  await progress(10);
  await progress(9);
  assert.equal(w.values['scan:1'].queueProgress.completed, 10);
  assert.equal(w.values['scan:1'].pages, 0);
  await w.call({ type: 'STOP' }, panel);
  assert.equal((await progress(11)).stop, true);
});

test('all-time scanning continues beyond the old page cap until the final page', async () => {
  const w = worker();
  await scan(w);
  for (let page = 1; page <= 105; page++) {
    const result = await w.call(
      {
        type: 'CAPTURE',
        scanToken: 'token1',
        items: [{ ...item, mediaId: String(1000 + page) }],
        page,
        finished: page === 105,
      },
      sender,
    );
    assert.equal(result.stop, page === 105);
  }
  assert.equal(w.values['scan:1'].items.length, 105);
  assert.equal(w.values['scan:1'].status, 'ready');
  assert.equal(w.values['scan:1'].scanIssue, false);
});
test('all-time date discovery initializes progress without changing user filters', async () => {
  const w = worker();
  await scan(w);
  await w.call(
    {
      type: 'CAPTURE',
      scanToken: 'token1',
      resolvedRange: { startDate: '2020-01-01', endDate: '2020-02-01' },
    },
    sender,
  );
  const s = w.values['scan:1'];
  assert.equal(s.rangeCount, 5);
  assert.equal(s.filters.startDate, '');
  await w.call(
    {
      type: 'CAPTURE',
      scanToken: 'token1',
      progressOnly: true,
      queueProgress: { completed: 1, total: 5, workers: 2 },
    },
    sender,
  );
  assert.equal(w.values['scan:1'].queueProgress.completed, 1);
  await assert.rejects(
    w.call(
      {
        type: 'CAPTURE',
        scanToken: 'token1',
        resolvedRange: { startDate: '2020-01-01', endDate: '2020-02-01' },
      },
      sender,
    ),
  );
});
