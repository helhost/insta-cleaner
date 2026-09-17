const test = require('node:test'),
  assert = require('node:assert/strict'),
  q = require('../../extension/queue');
test('equal date chunks preserve endpoints, boundaries, and direction', () => {
  for (const [start, end] of [
    ['2024-02-01', '2024-03-01'],
    ['2014-01-01', '2024-01-01'],
  ]) {
    const p = q.plan({ startDate: start, endDate: end, order: 'oldest_to_newest' });
    assert.equal(p.chunks[0].startDate, start);
    assert.equal(p.chunks.at(-1).endDate, end);
    const widths = p.chunks.map((c, i) => {
      if (i) assert.equal(c.startDate, p.chunks[i - 1].endDate);
      return (Date.parse(c.endDate) - Date.parse(c.startDate)) / 86400000;
    });
    assert.ok(Math.max(...widths) - Math.min(...widths) <= 1);
    assert.ok(p.workers <= 24);
    const newest = q.plan({ startDate: start, endDate: end, order: 'newest_to_oldest' });
    assert.deepEqual(
      newest.chunks.map((x) => x.startDate),
      p.chunks.map((x) => x.startDate).reverse(),
    );
  }
  assert.equal(q.plan({ startDate: '2024-01-01' }), null);
});
test('worker policy grows monthly then tapers at year anchors including leap years', () => {
  for (const [end, workers] of [
    ['2024-01-08', 1],
    ['2024-02-01', 2],
    ['2024-04-01', 3],
    ['2024-07-01', 6],
    ['2025-01-01', 12],
    ['2026-01-01', 16],
    ['2029-01-01', 20],
    ['2034-01-01', 24],
    ['2044-01-01', 24],
  ]) {
    assert.equal(q.plan({ startDate: '2024-01-01', endDate: end }).workers, workers, end);
  }
  const year = q.plan({ startDate: '2025-01-01', endDate: '2026-01-01' });
  assert.equal(year.chunks.length, 53);
  assert.equal(year.workers, 12);
});
test('free worker starts next chunk while another is still busy', async () => {
  let release;
  const slow = new Promise((r) => (release = r)),
    seen = [];
  const run = q.run({
    plan: { chunks: [0, 1, 2, 3], workers: 2 },
    work: async (c) => {
      seen.push(c);
      if (c === 0) await slow;
    },
  });
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(seen, [0, 1, 2, 3]);
  release();
  assert.equal((await run).completed, 4);
});
test('queue respects concurrency cap and runs each chunk once', async () => {
  let active = 0,
    peak = 0;
  const seen = [],
    progress = [];
  await q.run({
    plan: { chunks: Array.from({ length: 50 }, (_, i) => i), workers: 24 },
    progress: (x) => progress.push(x),
    work: async (c) => {
      active++;
      peak = Math.max(peak, active);
      await new Promise((r) => setImmediate(r));
      seen.push(c);
      active--;
    },
  });
  assert.equal(new Set(seen).size, 50);
  assert.equal(peak, 24);
  assert.equal(progress.at(-1).completed, 50);
});
test('stop and request failure do not start queued work', async () => {
  let stop = false,
    calls = 0;
  const p = { chunks: [0, 1, 2, 3], workers: 2 };
  await q.run({
    plan: p,
    stopped: () => stop,
    work: async () => {
      calls++;
      stop = true;
    },
  });
  assert.equal(calls, 1);
  calls = 0;
  await assert.rejects(
    q.run({
      plan: p,
      work: async () => {
        calls++;
        throw Error('429');
      },
    }),
  );
  assert.equal(calls, 2);
});
