/* Called only by privileged executeScript after panel confirmation. No message listener. */
(() => {
  async function send(token, accountId, items, filters, execute = false) {
    let sent = false,
      stage = 'page';
    try {
      const seed = globalThis.__instaCleanerReadSeed;
      if (
        location.origin !== 'https://www.instagram.com' ||
        location.pathname !== '/your_activity/interactions/likes/' ||
        !seed ||
        seed.token !== token
      )
        throw Error('Scan page changed');
      stage = 'account';
      const own = document.cookie
        .split(';')
        .map((x) => x.trim())
        .find((x) => x.startsWith('ds_user_id='))
        ?.slice(11);
      if (own !== accountId) throw Error('Account changed');
      stage = 'items';
      if (
        !Array.isArray(items) ||
        !items.length ||
        new Set(items.map((x) => x.mediaId)).size !== items.length
      )
        throw Error('Invalid batch');
      for (const x of items)
        if (!/^[1-9][0-9]{0,29}$/.test(x.mediaId) || !/^[1-9][0-9]{0,29}$/.test(x.authorId))
          throw Error('Invalid item');
      stage = 'parameters';
      const parser = globalThis.InstaCleanerParser,
        dates = globalThis.InstaCleanerDates;
      const params = dates.refreshParams(seed.body, parser.continuation(seed.body), filters);
      params.items_for_action = items.map((x) => `${x.mediaId}_${x.authorId}`).join(',');
      params.number_of_items = items.length;
      stage = 'endpoint';
      const target = new URL(seed.url, location.origin);
      if (target.origin !== location.origin || target.pathname !== '/async/wbloks/fetch/')
        throw Error('Invalid endpoint');
      target.searchParams.set('appid', 'com.instagram.privacy.activity_center.liked_unlike');
      const form = new URLSearchParams(seed.form);
      if (!form.has('params')) throw Error('Missing live form');
      form.set('params', JSON.stringify(params));
      if (!execute) return { status: 'ready', sent: false };
      sent = true;
      const response = await fetch(target.href, {
        method: 'POST',
        credentials: 'same-origin',
        redirect: 'error',
        headers: seed.headers,
        body: form,
        signal: AbortSignal.timeout(20000),
      });
      const text = await response.text();
      if (response.status !== 200)
        return { status: 'unverified', sent: true, httpStatus: response.status };
      const data = JSON.parse(text.trim().replace(/^for \(;;\);/, ''));
      if (data.error || data.errorSummary || !data.payload?.layout?.bloks_payload)
        return { status: 'unverified', sent: true };
      // Inspect the executed response handler, not embedded UI templates which
      // can contain unrelated toasts for other actions.
      const handler =
        data.payload.layout.bloks_payload.tree?.['bk.components.internal.Action']?.handler;
      if (typeof handler !== 'string') return { status: 'unverified', sent: true };
      const pattern = /\(bk\.action\.io\.Toast,\s*("(?:\\.|[^"\\])*")\s*\)/g;
      const counts = [];
      for (const m of handler.matchAll(pattern)) {
        const toast = JSON.parse(m[1]);
        const match =
          /^Du har sluttet å like (\d+) innlegg\.$/.exec(toast) ||
          /^You(?:'ve| have)? unliked (\d+) posts?\.$/.exec(toast);
        if (match) counts.push(Number(match[1]));
      }
      return counts.length === 1 && counts[0] === items.length
        ? { status: 'batch-confirmed', sent: true, count: counts[0] }
        : { status: 'unverified', sent: true };
    } catch {
      return { status: sent ? 'unverified' : 'not-sent', sent, stage };
    }
  }
  globalThis.InstaCleanerBatch = { send };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerBatch;
})();
