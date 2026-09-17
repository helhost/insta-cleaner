/* Read-only pagination. Retains the live seed for the privileged batch executor. */
(() => {
  const parser = globalThis.InstaCleanerParser,
    scanToken = new URLSearchParams(location.hash.slice(1)).get('ic-preview');
  const originalFetch = window.fetch;
  // Request larger continuation pages; Instagram controls the actual result size.
  const requestedPageSize = '100';
  let started = false,
    stopped = false,
    serial = Promise.resolve(),
    sequence = 0;
  const aborter = new AbortController();
  function stop() {
    stopped = true;
    aborter.abort();
  }
  // Serialize delivery and await worker acknowledgement before advancing counters.
  function deliver(data) {
    const task = serial.then(
      () =>
        new Promise((resolve, reject) => {
          if (stopped) {
            resolve();
            return;
          }
          const requestId = ++sequence;
          const listener = (e) => {
            if (
              e.source !== window ||
              e.origin !== location.origin ||
              e.data?.source !== 'insta-cleaner-ack' ||
              e.data.scanToken !== scanToken ||
              e.data.requestId !== requestId
            )
              return;
            cleanup();
            if (e.data.stop) stop();
            resolve();
          };
          const timer = setTimeout(() => {
            cleanup();
            stop();
            reject(Error('Capture acknowledgement timed out'));
          }, 10000);
          function cleanup() {
            clearTimeout(timer);
            window.removeEventListener('message', listener);
          }
          window.addEventListener('message', listener);
          window.postMessage(
            { source: 'insta-cleaner-preview-v1', scanToken, requestId, ...data },
            location.origin,
          );
        }),
    );
    serial = task.catch(() => {});
    return task;
  }
  window.addEventListener('message', (e) => {
    if (
      e.source === window &&
      e.origin === location.origin &&
      e.data?.source === 'insta-cleaner-control' &&
      e.data.scanToken === scanToken &&
      e.data.type === 'STOP'
    )
      stop();
  });
  async function collect(body, status, url, rawForm, headers = {}) {
    if (started || !scanToken) return;
    started = true;
    const form = new URLSearchParams(
      typeof rawForm === 'string'
        ? rawForm
        : rawForm instanceof URLSearchParams
          ? rawForm.toString()
          : '',
    );
    globalThis.__instaCleanerReadSeed = {
      token: scanToken,
      body,
      url,
      form: form.toString(),
      headers: { ...headers },
    };
    const seen = new Set();
    let page = 0;
    try {
      let settings = InstaCleanerDates.options(
        Object.fromEntries(new URLSearchParams(location.hash.slice(1))),
      );
      if (!settings.startDate && !settings.endDate && status === 200) {
        const range = InstaCleanerDates.defaultRange(body);
        if (range && parser.continuation(body)) {
          settings = { ...settings, ...range };
          await deliver({ resolvedRange: range });
        }
      }
      const plan = InstaCleanerQueue.plan(settings);
      if (plan && plan.chunks.length > 1) {
        await collectQueue(body, status, url, form, headers, plan);
        return;
      }
      if (settings.startDate || settings.endDate || settings.order !== 'newest_to_oldest') {
        if (status !== 200 || !form.has('params')) throw Error('Date filter unavailable.');
        const next = parser.continuation(body);
        if (!next) throw Error('Date filter parameters unavailable.');
        form.set('params', JSON.stringify(InstaCleanerDates.refreshParams(body, next, settings)));
        const target = new URL(url, location.origin);
        target.searchParams.set('appid', 'com.instagram.privacy.activity_center.liked_refresh');
        if (stopped) return;
        const response = await Reflect.apply(originalFetch, window, [
          target.href,
          {
            method: 'POST',
            credentials: 'same-origin',
            redirect: 'error',
            headers,
            body: form,
            signal: AbortSignal.any([aborter.signal, AbortSignal.timeout(20000)]),
          },
        ]);
        status = response.status;
        body = await response.text();
      }
      while (!stopped) {
        if (status !== 200) throw Error('Likes request failed.');
        const items = parser.parse(body),
          next = parser.continuation(body);
        page++;
        let reason = !next
          ? 'No supported next-page instruction.'
          : seen.has(next.cursor)
            ? 'Repeated pagination cursor.'
            : '';
        if (!form.has('params') && !reason) reason = 'Live pagination form unavailable.';
        if (!items.length && next) throw Error('Conflicting empty response.');
        await deliver({
          items,
          page,
          emptyRange: !items.length && !next,
          requestedPageSize: page > 1 ? Number(requestedPageSize) : null,
          finished: Boolean(reason),
          incomplete: Boolean(reason && next),
          reason,
        });
        if (reason) return;
        seen.add(next.cursor);
        form.set('params', JSON.stringify({ ...next, page_size: requestedPageSize }));
        const target = new URL(url, location.origin);
        target.searchParams.set('appid', 'com.instagram.privacy.activity_center.liked_next');
        // Yield so Stop messages can run, without adding a fixed network delay.
        await new Promise((r) => setTimeout(r, 0));
        if (stopped) break;
        const response = await Reflect.apply(originalFetch, window, [
          target.href,
          {
            method: 'POST',
            credentials: 'same-origin',
            redirect: 'error',
            headers,
            body: form,
            signal: AbortSignal.any([aborter.signal, AbortSignal.timeout(20000)]),
          },
        ]);
        status = response.status;
        body = await response.text();
      }
    } catch {
      window.postMessage(
        { source: 'insta-cleaner-preview-v1', scanToken, error: true },
        location.origin,
      );
    }
  }
  async function collectQueue(seedBody, status, url, form, headers, plan) {
    if (status !== 200 || !form.has('params')) throw Error('Date filter unavailable');
    const seed = parser.continuation(seedBody);
    if (!seed) throw Error('Date filter unavailable');
    let pages = 0,
      completed = 0,
      workers = plan.workers;
    const ranges = new Map();
    await InstaCleanerQueue.run({
      plan,
      stopped: () => stopped,
      progress: async (p) => {
        completed = p.completed;
        workers = p.workers;
        await deliver({ progressOnly: true, queueProgress: p });
      },
      work: async (settings, index) => {
        let count = 0,
          body,
          action = 'liked_refresh',
          params = InstaCleanerDates.refreshParams(seedBody, seed, settings);
        const expected = params,
          seen = new Set(),
          ids = new Set();
        try {
          while (!stopped) {
            count++;
            const target = new URL(url, location.origin);
            target.searchParams.set('appid', `com.instagram.privacy.activity_center.${action}`);
            const data = new URLSearchParams(form);
            data.set('params', JSON.stringify(params));
            const response = await Reflect.apply(originalFetch, window, [
              target.href,
              {
                method: 'POST',
                credentials: 'same-origin',
                redirect: 'error',
                headers,
                body: data,
                signal: AbortSignal.any([aborter.signal, AbortSignal.timeout(20000)]),
              },
            ]);
            if (response.status !== 200) throw Error('Request failed');
            body = await response.text();
            const items = parser.parse(body),
              next = parser.continuation(body);
            if (!items.length && next) throw Error('Conflicting empty response');
            const before = ids.size;
            for (const item of items) ids.add(item.mediaId);
            if (next) {
              const activity = JSON.parse(next.activity_center_params);
              for (const key of [
                'main_date_start_state_value',
                'main_date_end_state_value',
                'main_order_state_value',
              ])
                if (activity[key] !== expected[key]) throw Error('Date scope changed');
              if (seen.has(next.cursor) || ids.size === before) throw Error('Pagination stalled');
              seen.add(next.cursor);
            }
            // Delivery itself is serialized, including numbering, across workers.
            ranges.set(index, (ranges.get(index) || 0) + 1);
            const capture = () =>
              deliver({
                items,
                page: ++pages,
                queue: true,
                chunk: index,
                chunkPage: ranges.get(index),
                queueProgress: { completed, total: plan.chunks.length, workers },
                requestedPageSize: action === 'liked_next' ? 100 : null,
              });
            // Reserve page number in response-completion order; deliver maintains it.
            await capture();
            if (stopped || !next) break;
            params = { ...next, page_size: requestedPageSize };
            action = 'liked_next';
          }
          return { requests: count };
        } catch (error) {
          stop();
          throw error;
        }
      },
    });
    if (!stopped)
      await deliver({
        queueDone: true,
        page: pages,
        queueProgress: { completed, total: plan.chunks.length, workers },
      });
  }
  window.fetch = function (...args) {
    const input = args[0],
      url = input instanceof Request ? input.url : String(input);
    const promise = Reflect.apply(originalFetch, this, args);
    if (parser.isInitialLikes(url)) {
      const requestBody =
        input instanceof Request ? input.clone().text() : Promise.resolve(args[1]?.body);
      const headers = Object.fromEntries(
        [...new Headers(input instanceof Request ? input.headers : args[1]?.headers)].filter(
          ([k]) => ['x-fb-lsd', 'x-ig-app-id', 'x-asbd-id', 'x-csrftoken'].includes(k),
        ),
      );
      promise
        .then(async (response) =>
          collect(await response.clone().text(), response.status, url, await requestBody, headers),
        )
        .catch(() => {});
    }
    return promise;
  };
  const urls = new WeakMap(),
    headers = new WeakMap(),
    setHeader = XMLHttpRequest.prototype.setRequestHeader,
    open = XMLHttpRequest.prototype.open,
    send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    urls.set(this, String(url));
    headers.set(this, {});
    return Reflect.apply(open, this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    if (
      ['x-fb-lsd', 'x-ig-app-id', 'x-asbd-id', 'x-csrftoken'].includes(
        String(name).toLowerCase(),
      ) &&
      headers.has(this)
    )
      headers.get(this)[name] = value;
    return Reflect.apply(setHeader, this, [name, value]);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    if (parser.isInitialLikes(urls.get(this)))
      this.addEventListener(
        'load',
        () => {
          try {
            collect(
              this.responseType === 'json' ? JSON.stringify(this.response) : this.responseText,
              this.status,
              urls.get(this),
              args[0],
              headers.get(this),
            );
          } catch {}
        },
        { once: true },
      );
    return Reflect.apply(send, this, args);
  };
})();
