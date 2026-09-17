let bridgeActive = true;
window.addEventListener('message', async (event) => {
  if (!bridgeActive) return;
  if (
    event.source !== window ||
    event.origin !== 'https://www.instagram.com' ||
    event.data?.source !== 'insta-cleaner-preview-v1'
  )
    return;
  const d = event.data;
  try {
    const reply = await chrome.runtime.sendMessage({
      type: 'CAPTURE',
      scanToken: d.scanToken,
      items: d.items,
      page: d.page,
      progressOnly: d.progressOnly === true,
      queue: d.queue === true,
      queueDone: d.queueDone === true,
      chunk: d.chunk,
      chunkPage: d.chunkPage,
      queueProgress: d.queueProgress,
      emptyRange: d.emptyRange === true,
      requestedPageSize: d.requestedPageSize,
      finished: d.finished === true,
      error: Boolean(d.error),
    });
    window.postMessage(
      {
        source: 'insta-cleaner-ack',
        scanToken: d.scanToken,
        requestId: d.requestId,
        stop: reply?.stop || reply?.ok === false,
      },
      location.origin,
    );
    if (reply?.stop || reply?.ok === false)
      window.postMessage(
        { source: 'insta-cleaner-control', scanToken: d.scanToken, type: 'STOP' },
        location.origin,
      );
  } catch {
    // Reloading the extension invalidates scripts in existing tabs. This can
    // throw synchronously, before sendMessage returns a promise.
    bridgeActive = false;
    window.postMessage(
      { source: 'insta-cleaner-control', scanToken: d.scanToken, type: 'STOP' },
      location.origin,
    );
  }
});
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'STOP_SCAN')
    window.postMessage(
      { source: 'insta-cleaner-control', scanToken: message.token, type: 'STOP' },
      location.origin,
    );
});
