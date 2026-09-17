/* Pure filter and confirmation rules shared by the worker and tests. */
(() => {
  function filters(value) {
    if (
      !value ||
      !['all', 'reels', 'posts'].includes(value.content) ||
      !['all', 'followed', 'not-followed'].includes(value.relationship)
    )
      throw Error('Choose valid filters.');
    return {
      content: value.content,
      relationship: value.relationship,
      ...InstaCleanerDates.options(value),
    };
  }
  function matches(state) {
    return InstaCleanerFollowing.filter(
      state.items || [],
      state.following,
      state.accountId,
      state.filters.content,
      state.filters.relationship,
    );
  }
  function prepare(state, ids) {
    if (
      state.status !== 'ready' ||
      !Array.isArray(ids) ||
      !ids.length ||
      new Set(ids).size !== ids.length
    )
      throw Error('Select matches from a finished scan.');
    const allowed = new Map(matches(state).map((x) => [x.mediaId, x]));
    if (ids.some((id) => !allowed.has(id)))
      throw Error('Selection is no longer part of this scan.');
    return ids.map((id) => allowed.get(id));
  }
  globalThis.InstaCleanerWorkflow = { filters, matches, prepare };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerWorkflow;
})();
