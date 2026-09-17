/* Bounded date work queue. Cursor sequences stay sequential within each chunk. */
(() => {
  function workerCount(days, months) {
    if (days <= 7) return 1;
    if (months <= 12) return Math.max(2, Math.ceil(months));
    if (months <= 24) return 12 + Math.ceil((months - 12) / 3);
    if (months <= 60) return 16 + Math.ceil((months - 24) / 9);
    return Math.min(24, 20 + Math.ceil((months - 60) / 15));
  }
  function plan(settings) {
    if (!settings.startDate || !settings.endDate) return null;
    const start = Date.parse(settings.startDate),
      end = Date.parse(settings.endDate),
      day = 86400000;
    const days = Math.round((end - start) / day);
    if (days < 0 || !Number.isFinite(days)) throw Error('Invalid date interval');
    const a = new Date(start),
      b = new Date(end);
    const months =
      (b.getUTCFullYear() - a.getUTCFullYear()) * 12 +
      b.getUTCMonth() -
      a.getUTCMonth() +
      (b.getUTCDate() - a.getUTCDate()) / 31;
    const count = days <= 7 ? 1 : Math.min(512, Math.max(2, Math.ceil(days / 7)));
    const chunks = Array.from({ length: count }, (_, i) => ({
      ...settings,
      startDate: new Date(start + Math.floor((days * i) / count) * day).toISOString().slice(0, 10),
      endDate: new Date(start + Math.floor((days * (i + 1)) / count) * day)
        .toISOString()
        .slice(0, 10),
    }));
    if (settings.order !== 'oldest_to_newest') chunks.reverse();
    return { chunks, workers: Math.min(count, workerCount(days, months)) };
  }
  async function run({ plan, work, stopped = () => false, progress = () => {} }) {
    const workers = Math.min(plan.workers, plan.chunks.length);
    if (!Number.isInteger(workers) || workers < 1 || workers > 24)
      throw Error('Invalid worker count');
    let index = 0,
      completed = 0,
      failure = null;
    const report = () => progress({ completed, total: plan.chunks.length, workers });
    await report();
    async function worker() {
      while (index < plan.chunks.length && !stopped() && !failure) {
        const i = index++;
        try {
          await work(plan.chunks[i], i);
          if (stopped() || failure) return;
          completed++;
          await report();
        } catch (error) {
          failure = failure || error;
          return;
        }
      }
    }
    await Promise.all(Array.from({ length: workers }, () => worker()));
    if (failure) throw failure;
    return { completed, total: plan.chunks.length };
  }
  globalThis.InstaCleanerQueue = { plan, workerCount, run };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerQueue;
})();
