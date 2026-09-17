/* Read-only experiment. Uses live browser request parameters, never HAR credentials. */
globalThis.runMonthRange = async ({ body, url, form, headers, settings, maxPages }) => {
  const parser = globalThis.InstaCleanerParser,
    dates = globalThis.InstaCleanerDates;
  const seed = parser.continuation(body);
  if (!seed) throw Error('Initial pagination parameters unavailable');
  const params = dates.refreshParams(body, seed, settings),
    ids = new Set(),
    cursors = new Set();
  let requestMs = 0,
    reason = 'page limit',
    pages = 0,
    requestCount = 0;
  async function request(action, params) {
    const target = new URL(url);
    target.searchParams.set('appid', `com.instagram.privacy.activity_center.${action}`);
    if (target.origin !== location.origin || target.pathname !== '/async/wbloks/fetch/')
      throw Error('Unexpected endpoint');
    const data = new URLSearchParams(form);
    data.set('params', JSON.stringify(params));
    const start = performance.now();
    const response = await fetch(target.href, {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'error',
      headers,
      body: data,
      signal: AbortSignal.timeout(20000),
    });
    const text = await response.text();
    requestMs += performance.now() - start;
    requestCount++;
    if (response.status !== 200) throw Error('Read request failed');
    return text;
  }
  body = await request('liked_refresh', params);
  for (let i = 0; i < maxPages; i++) {
    const items = parser.parse(body),
      next = parser.continuation(body);
    pages++;
    if (!items.length && next) throw Error('Conflicting empty response');
    const before = ids.size;
    for (const x of items) ids.add(x.mediaId);
    if (!next) {
      reason = items.length ? 'no next instruction' : 'recognized empty';
      break;
    }
    if (ids.size === before || cursors.has(next.cursor)) {
      reason = 'stalled pagination';
      break;
    }
    // Every continuation must retain the requested bounds and order.
    const activity = JSON.parse(next.activity_center_params);
    for (const k of [
      'main_date_start_state_value',
      'main_date_end_state_value',
      'main_order_state_value',
    ])
      if (activity[k] !== params[k]) throw Error('Date range changed');
    cursors.add(next.cursor);
    if (i + 1 < maxPages) body = await request('liked_next', { ...next, page_size: '100' });
  }
  return { ids: [...ids].sort(), pages, reason, requestCount, requestMs: Math.round(requestMs) };
};

void 0;
