const test = require('node:test'),
  assert = require('node:assert/strict'),
  vm = require('node:vm'),
  fs = require('node:fs');
function bridge(sendMessage) {
  const posted = [];
  let listener;
  const window = {
    addEventListener: (type, fn) => {
      listener = fn;
    },
    postMessage: (message) => posted.push(message),
  };
  const ctx = vm.createContext({
    window,
    location: { origin: 'https://www.instagram.com' },
    chrome: { runtime: { sendMessage, onMessage: { addListener() {} } } },
  });
  vm.runInContext(fs.readFileSync('extension/bridge.js', 'utf8'), ctx);
  return {
    posted,
    emit: () =>
      listener({
        source: window,
        origin: 'https://www.instagram.com',
        data: { source: 'insta-cleaner-preview-v1', scanToken: 'scan1', page: 1, items: [] },
      }),
  };
}
for (const mode of ['throw', 'reject'])
  test(`invalidated bridge handles ${mode} and stops its collector once`, async () => {
    let calls = 0;
    const b = bridge(() => {
      calls++;
      if (mode === 'throw') throw Error('Extension context invalidated.');
      return Promise.reject(Error('Disconnected'));
    });
    await b.emit();
    await b.emit();
    assert.equal(calls, 1);
    assert.equal(b.posted.length, 1);
    assert.equal(b.posted[0].type, 'STOP');
    assert.equal(b.posted[0].scanToken, 'scan1');
  });
test('worker rejection stops collection; successful capture continues', async () => {
  const b = bridge(async () => ({ ok: false, error: 'Unsupported data' }));
  await b.emit();
  assert.equal(b.posted[1].type, 'STOP');
  const good = bridge(async () => ({ ok: true, stop: false }));
  await good.emit();
  assert.equal(good.posted.length, 1);
  assert.equal(good.posted[0].source, 'insta-cleaner-ack');
});
