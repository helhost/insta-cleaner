importScripts('queue.js', 'dates.js', 'parser.js', 'following.js', 'workflow.js', 'batch.js');
const LIKES = 'https://www.instagram.com/your_activity/interactions/likes/';
const key = (id) => `scan:${id}`,
  jobs = new Set();
async function account() {
  const c = await chrome.cookies.get({ url: 'https://www.instagram.com/', name: 'ds_user_id' });
  if (!c || !/^[1-9][0-9]+$/.test(c.value)) throw Error('Log in to Instagram first.');
  return c.value;
}
async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url?.startsWith('https://www.instagram.com/'))
    throw Error('Switch to an Instagram tab first.');
  return tab;
}
async function read(id) {
  return (await chrome.storage.session.get(key(id)))[key(id)];
}
async function put(id, state) {
  await chrome.storage.session.set({ [key(id)]: { ...state, updated: Date.now() } });
}
async function stateFor(id) {
  let s = await read(id);
  if (!s) return null;
  let current;
  try {
    current = await account();
  } catch {}
  if (current !== s.accountId) {
    await chrome.storage.session.remove(key(id));
    return { status: 'error', message: 'Account changed. Find matches again.', items: [] };
  }
  if (s.status === 'removing' && !jobs.has(s.token)) {
    s = {
      ...s,
      status: 'halted',
      approval: null,
      message:
        'Removal was interrupted. Check any unverified batch manually; it will not be retried.',
    };
    await put(id, s);
  }
  if (s.status === 'scanning' && Date.now() - s.updated > 60000) {
    s = {
      ...s,
      status: 'ready',
      scanIssue: true,
      partial: true,
      message: s.pages
        ? 'Scan interrupted. Showing only collected matches.'
        : 'No Likes page was captured. Reload the extension, then click Find matches again.',
    };
    await put(id, s);
  }
  return s;
}
async function ensure(id, token) {
  const s = await read(id);
  if (!s || s.token !== token || s.accountId !== (await account()))
    throw Error('Account or scan changed.');
  return s;
}
async function following(id, token) {
  const s = await ensure(id, token);
  return InstaCleanerFollowing.collect({
    accountId: s.accountId,
    request: (url) =>
      fetch(url, {
        credentials: 'include',
        redirect: 'error',
        headers: { 'x-ig-app-id': '936619743392459', accept: 'application/json' },
        signal: AbortSignal.timeout(20000),
      }),
    checkAccount: async () => {
      const current = await ensure(id, token);
      if (current.stopRequested) throw Error('Stopped.');
    },
    progress: async (f) => {
      const current = await ensure(id, token);
      await put(id, {
        ...current,
        following: f,
        message: `Loading Following… ${Object.keys(f.accounts).length} accounts`,
      });
    },
  });
}
async function startScan(id, tab, filters) {
  const old = await stateFor(id);
  if (old?.status === 'removing') throw Error('Stop the current removal first.');
  const token = crypto.randomUUID(),
    accountId = await account();
  const rangePlan = InstaCleanerQueue.plan(filters);
  await put(id, {
    startedAt: Date.now(),
    rangeCount: rangePlan?.chunks.length > 1 ? rangePlan.chunks.length : 0,
    token,
    accountId,
    filters,
    status: 'scanning',
    items: [],
    pages: 0,
    partial: true,
    stopRequested: false,
    message: 'Preparing scan…',
  });
  try {
    if (filters.relationship !== 'all') {
      const f = await following(id, token),
        s = await ensure(id, token);
      if (s.stopRequested) return;
      await put(id, { ...s, following: f });
    }
    const s = await ensure(id, token);
    if (s.stopRequested) return;
    await put(id, { ...s, message: 'Scanning Likes…' });
    // A unique query forces a new document. A hash-only update followed by reload
    // can race: the new hook may start with the previous scan's token.
    const fragment = new URLSearchParams({
      'ic-preview': token,
      ...InstaCleanerDates.options(filters),
    });
    await chrome.tabs.update(id, { url: `${LIKES}?ic_scan=${token}#${fragment}` });
  } catch {
    const s = await read(id);
    if (s?.token === token)
      await put(id, {
        ...s,
        status: 'ready',
        message: 'Scan stopped. Check Instagram or try again.',
      });
  }
}
async function executeRemoval(id, token) {
  try {
    let s = await ensure(id, token),
      freshFollowing = null;
    if (s.filters.relationship !== 'all') freshFollowing = await following(id, token);
    // One confirmed selection produces one unlike request.
    for (const selection of [s.queue]) {
      s = await ensure(id, token);
      if (s.stopRequested) break;
      const batch = [];
      for (const item of selection) {
        if (
          s.filters.relationship !== 'all' &&
          InstaCleanerFollowing.relationship(item, freshFollowing, s.accountId) !==
            s.filters.relationship
        ) {
          s = {
            ...s,
            results: [
              ...s.results,
              { mediaId: item.mediaId, code: item.code, status: 'skipped-relationship-changed' },
            ],
          };
        } else batch.push(item);
      }
      await put(id, s);
      s = await ensure(id, token);
      if (s.stopRequested) break;
      if (!batch.length) continue;
      const invoke = (execute) =>
        chrome.scripting.executeScript({
          target: { tabId: id },
          world: 'MAIN',
          func: InstaCleanerBatch.send,
          args: [token, s.accountId, batch, s.filters, execute],
        });
      const prepared = await invoke(false);
      if (prepared?.[0]?.result?.status !== 'ready') {
        await put(id, { ...s, batchDiagnostic: prepared?.[0]?.result || { status: 'no-result' } });
        throw Error('Live batch request unavailable');
      }
      s = await ensure(id, token);
      if (s.stopRequested) break;
      await put(id, {
        ...s,
        clickPending: true,
        current: batch.map((x) => x.mediaId),
        message: `Unliking ${batch.length} confirmed matches…`,
      });
      const replies = await invoke(true),
        result = replies?.[0]?.result;
      s = await ensure(id, token);
      // Keep only structured diagnostics, never raw responses or session details.
      await put(id, { ...s, batchDiagnostic: result || { status: 'no-result' } });
      s = await ensure(id, token);
      if (result?.sent === false) {
        await put(id, { ...s, clickPending: false, current: null });
        throw Error('Batch not sent');
      }
      if (result?.status !== 'batch-confirmed' || result.count !== batch.length)
        throw Error('Batch outcome unverified');
      await put(id, {
        ...s,
        clickPending: false,
        current: null,
        results: [
          ...s.results,
          ...batch.map((x) => ({
            mediaId: x.mediaId,
            code: x.code,
            status: 'unliked-server-confirmed',
          })),
        ],
      });
    }
    s = await ensure(id, token);
    await put(id, {
      ...s,
      status: 'finished',
      approval: null,
      message: s.stopRequested
        ? 'Stopped. Submitted batch results are shown below.'
        : `Finished. ${s.results.filter((x) => x.status === 'unliked-server-confirmed').length} likes removed. No cleanup is running.`,
    });
  } catch (error) {
    const s = await read(id);
    if (s?.token === token)
      await put(id, {
        ...s,
        errorType: error?.name || 'Error',
        status: 'halted',
        approval: null,
        message: s.clickPending
          ? 'Stopped: the last batch has an uncertain outcome. Check those items before trying again; no automatic retry.'
          : 'Stopped before sending the next batch. The account, filter, or live request could not be checked.',
      });
  } finally {
    jobs.delete(token);
  }
}
async function handleUnsafe(message, sender) {
  if (message.type === 'CAPTURE') {
    const id = sender.tab?.id;
    if (!id || sender.frameId !== 0 || !sender.url?.startsWith(LIKES)) return { stop: true };
    const s = await stateFor(id);
    if (!s || s.status !== 'scanning' || s.stopRequested || s.token !== message.scanToken)
      return { stop: true };
    if (message.error) {
      await put(id, {
        ...s,
        scanIssue: true,
        status: 'ready',
        message: 'Scan stopped after a failed or unsupported response. Collected matches only.',
      });
      return { stop: true };
    }
    if (message.resolvedRange) {
      if (s.pages || s.rangeCount || s.filters.startDate || s.filters.endDate || s.resolvedRange)
        throw Error('Unexpected automatic date range');
      const range = InstaCleanerDates.options(message.resolvedRange);
      if (!range.startDate || !range.endDate) throw Error('Missing automatic date range');
      const plan = InstaCleanerQueue.plan(range);
      await put(id, {
        ...s,
        resolvedRange: range,
        rangeCount: plan.chunks.length > 1 ? plan.chunks.length : 0,
      });
      return { stop: false };
    }
    if (message.progressOnly === true) {
      const p = message.queueProgress;
      if (
        !s.rangeCount ||
        !p ||
        p.total !== s.rangeCount ||
        !Number.isInteger(p.completed) ||
        p.completed < 0 ||
        p.completed > s.rangeCount ||
        !Number.isInteger(p.workers) ||
        p.workers < 1 ||
        p.workers > 24
      )
        throw Error('Invalid progress');
      const completed = Math.max(s.queueProgress?.completed || 0, p.completed);
      await put(id, { ...s, queueProgress: { completed, total: p.total, workers: p.workers } });
      return { stop: false };
    }
    if (message.queueDone === true) {
      if (
        !s.rangeCount ||
        message.page !== s.pages ||
        message.queueProgress?.completed !== s.rangeCount
      )
        throw Error('Invalid queue completion');
      await put(id, {
        ...s,
        status: 'ready',
        queueProgress: { ...s.queueProgress, completed: s.rangeCount },
        message: s.items.length
          ? 'Date ranges scanned. Review the collected matches.'
          : 'Instagram returned no matches for these date ranges.',
      });
      return { stop: true };
    }
    if (message.queue === true) {
      const p = message.queueProgress;
      if (
        !s.rangeCount ||
        !p ||
        p.total !== s.rangeCount ||
        !Number.isInteger(p.completed) ||
        p.completed < 0 ||
        p.completed > s.rangeCount ||
        !Number.isInteger(p.workers) ||
        p.workers < 1 ||
        p.workers > 24 ||
        !Number.isInteger(message.chunk) ||
        message.chunk < 0 ||
        message.chunk >= s.rangeCount ||
        !Number.isInteger(message.chunkPage) ||
        message.chunkPage < 1 ||
        message.page !== s.pages + 1
      )
        throw Error('Invalid range progress');
      const rows =
        Array.isArray(message.items) && message.items.length === 0
          ? []
          : InstaCleanerParser.validateItems(message.items);
      const map = new Map(s.items.map((x) => [x.mediaId, x])),
        order = { ...s.queueOrder };
      const compare = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
      rows.forEach((x, i) => {
        map.set(x.mediaId, x);
        const position = [message.chunk, message.chunkPage, i];
        if (!order[x.mediaId] || compare(position, order[x.mediaId]) < 0)
          order[x.mediaId] = position;
      });
      const items = [...map.values()].sort((a, b) => compare(order[a.mediaId], order[b.mediaId]));
      await put(id, {
        ...s,
        items,
        queueOrder: order,
        pages: message.page,
        queueProgress: {
          completed: Math.max(s.queueProgress?.completed || 0, p.completed),
          total: p.total,
          workers: p.workers,
        },
        message: `Scanning date ranges… ${items.length} items collected`,
      });
      return { stop: false };
    }
    if (message.page !== s.pages + 1) return { stop: true };
    if (
      message.emptyRange === true &&
      message.finished === true &&
      Array.isArray(message.items) &&
      message.items.length === 0
    ) {
      await put(id, {
        ...s,
        pages: message.page,
        status: 'ready',
        message: s.items.length
          ? 'Instagram returned an empty page. Showing collected matches only.'
          : 'Instagram returned no matches for these filters.',
      });
      return { stop: true };
    }
    const rows = InstaCleanerParser.validateItems(message.items),
      map = new Map(s.items.map((x) => [x.mediaId, x]));
    rows.forEach((x) => map.set(x.mediaId, x));
    const stalled = map.size === s.items.length,
      finished = message.finished || stalled;
    const requested = message.page > 1 && message.requestedPageSize === 100 ? 100 : null;
    const batch = requested ? ` Last batch: ${rows.length} items; requested ${requested}.` : '';
    await put(id, {
      ...s,
      items: [...map.values()],
      pages: message.page,
      lastBatchSize: rows.length,
      requestedPageSize: requested,
      status: finished ? 'ready' : 'scanning',
      scanIssue: message.incomplete === true || (stalled && !message.finished),
      message:
        (finished
          ? 'Scan stopped. These matches cover the collected items only.'
          : `Scanning Likes… ${map.size} items collected`) + batch,
    });
    return { stop: finished };
  }
  if (sender.url !== chrome.runtime.getURL('panel.html'))
    throw Error('Unsupported message source.');
  const tab = await activeTab(),
    id = tab.id;
  if (message.type === 'STATE') return { tabId: id, state: await stateFor(id) };
  if (message.type === 'SCAN') {
    await startScan(id, tab, InstaCleanerWorkflow.filters(message.filters));
    return {};
  }
  const s = await stateFor(id);
  if (!s) throw Error('Find matches first.');
  if (message.type === 'STOP') {
    await put(id, {
      ...s,
      stopRequested: true,
      approval: null,
      status: s.status === 'scanning' ? 'ready' : s.status,
      message: 'Stopping. Already sent actions will be verified.',
    });
    await chrome.tabs.sendMessage(id, { type: 'STOP_SCAN', token: s.token }).catch(() => {});
    return {};
  }
  if (message.type === 'PREPARE') {
    const queue = InstaCleanerWorkflow.prepare(s, message.ids),
      approval = {
        token: crypto.randomUUID(),
        ids: queue.map((x) => x.mediaId),
        created: Date.now(),
      };
    await put(id, { ...s, approval });
    return { approval };
  }
  if (message.type === 'CONFIRM') {
    if (
      s.status !== 'ready' ||
      !s.approval ||
      s.approval.token !== message.approval ||
      Date.now() - s.approval.created > 300000
    )
      throw Error('Confirmation expired. Review the matches again.');
    const queue = InstaCleanerWorkflow.prepare(s, s.approval.ids);
    jobs.add(s.token);
    await put(id, {
      ...s,
      status: 'removing',
      queue,
      results: [],
      approval: null,
      stopRequested: false,
      clickPending: false,
      message: 'Verifying confirmed matches…',
    });
    executeRemoval(id, s.token);
    return {};
  }
  throw Error('Unsupported command.');
}
const controlLocks = new Set();
async function handle(message, sender) {
  if (!['SCAN', 'PREPARE', 'CONFIRM'].includes(message.type)) return handleUnsafe(message, sender);
  if (sender.url !== chrome.runtime.getURL('panel.html'))
    throw Error('Unsupported message source.');
  const tab = await activeTab();
  if (controlLocks.has(tab.id)) throw Error('An operation is already being prepared.');
  controlLocks.add(tab.id);
  try {
    return await handleUnsafe(message, sender);
  } finally {
    controlLocks.delete(tab.id);
  }
}
chrome.runtime.onMessage.addListener((m, s, reply) => {
  handle(m, s)
    .then((result) => reply({ ok: true, ...result }))
    .catch((e) => reply({ ok: false, error: e.message }));
  return true;
});
chrome.runtime.onInstalled.addListener(() =>
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }),
);
chrome.tabs.onRemoved.addListener((id) => chrome.storage.session.remove(key(id)));
