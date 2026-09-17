const test = require('node:test'),
  assert = require('node:assert/strict'),
  vm = require('node:vm'),
  fs = require('node:fs');
function setup({ empty = false, changed = false, failed = false } = {}) {
  const requests = [],
    params = {
      main_date_start_state_value: 1,
      main_date_end_state_value: 2,
      main_order_state_value: true,
    };
  const next = {
    cursor: 'a',
    activity_center_params: JSON.stringify({
      ...params,
      main_date_end_state_value: changed ? 3 : 2,
    }),
  };
  const parser = {
    continuation: (body) => (body === 'seed' || (body === 'first' && !empty) ? next : null),
    parse: (body) => (empty ? [] : [{ mediaId: body === 'first' ? '1' : '2' }]),
  };
  const ctx = vm.createContext({
    URL,
    URLSearchParams,
    AbortSignal,
    performance,
    location: { origin: 'https://www.instagram.com' },
    InstaCleanerParser: parser,
    InstaCleanerDates: { refreshParams: () => params },
    fetch: async (url, opt) => {
      requests.push({ url, params: JSON.parse(opt.body.get('params')) });
      return {
        status: failed ? 429 : 200,
        text: async () => (requests.length === 1 ? 'first' : 'second'),
      };
    },
  });
  vm.runInContext(fs.readFileSync('tools/probe_months.js', 'utf8'), ctx);
  return {
    requests,
    run: () =>
      ctx.runMonthRange({
        body: 'seed',
        url: 'https://www.instagram.com/async/wbloks/fetch/',
        form: { params: '{}' },
        headers: {},
        settings: {},
        maxPages: 3,
      }),
  };
}
test('month probe chains cursors and reports IDs and observed end', async () => {
  const s = setup(),
    r = await s.run();
  assert.equal(r.ids.join(','), '1,2');
  assert.equal(r.reason, 'no next instruction');
  assert.equal(s.requests[1].params.cursor, 'a');
  assert.equal(s.requests[1].params.page_size, '100');
});
test('empty month ends with one request', async () => {
  const s = setup({ empty: true }),
    r = await s.run();
  assert.equal(r.ids.length, 0);
  assert.equal(r.reason, 'recognized empty');
  assert.equal(s.requests.length, 1);
});
test('changed date scope and throttled requests stop without retries', async () => {
  for (const options of [{ changed: true }, { failed: true }]) {
    const s = setup(options);
    await assert.rejects(s.run());
    assert.equal(s.requests.length, 1);
  }
});
