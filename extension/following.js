/* Read-only Following collection and provisional filtering, independent of the UI. */
(() => {
  function parsePage(data) {
    if (
      !data ||
      data.status !== 'ok' ||
      !Array.isArray(data.users) ||
      typeof data.has_more !== 'boolean'
    )
      throw Error('Unsupported Following response.');
    const cursor = data.next_max_id || '';
    if (typeof cursor !== 'string' || Boolean(cursor) !== data.has_more)
      throw Error('Unsupported Following pagination.');
    const accounts = {};
    for (const user of data.users) {
      const id = String(user.pk ?? '');
      if (
        !/^[1-9][0-9]{0,29}$/.test(id) ||
        typeof user.username !== 'string' ||
        !/^[A-Za-z0-9_.]{1,50}$/.test(user.username)
      )
        throw Error('Unsupported Following account.');
      accounts[id] = user.username;
    }
    return {
      accounts,
      cursor,
      more: data.has_more,
      unrestricted:
        data.should_limit_list_of_followings === false && data.hidden_following_account_count === 0,
    };
  }
  async function collect({
    accountId,
    request,
    checkAccount,
    progress,
    delay = () => new Promise((r) => setTimeout(r, 1500)),
  }) {
    const result = {
      accountId,
      accounts: {},
      pages: 0,
      complete: false,
      reason: 'Following traversal has not finished.',
    };
    const seen = new Set();
    let cursor = '',
      stalled = 0;
    for (let i = 0; ; i++) {
      if (i) await delay();
      await checkAccount();
      const query = new URLSearchParams({ count: '100' });
      if (cursor) query.set('max_id', cursor);
      let page;
      try {
        const response = await request(
          `https://www.instagram.com/api/v1/friendships/${accountId}/following/?${query}`,
        );
        await checkAccount();
        if (response.status !== 200) {
          result.reason = `Following request returned HTTP ${response.status}.`;
          break;
        }
        page = parsePage(await response.json());
      } catch {
        result.reason = 'Following could not be loaded. Check login or try again.';
        break;
      }
      const before = Object.keys(result.accounts).length;
      Object.assign(result.accounts, page.accounts);
      result.pages++;
      if (!page.unrestricted) {
        result.reason = 'Instagram restricted this Following list.';
        break;
      }
      if (!page.more) {
        result.complete = true;
        result.reason = 'Final Following page reached.';
        break;
      }
      seen.add(cursor);
      if (seen.has(page.cursor)) {
        result.reason = 'Repeated Following cursor.';
        break;
      }
      stalled = Object.keys(result.accounts).length === before ? stalled + 1 : 0;
      if (stalled >= 3) {
        result.reason = 'No new accounts in three pages.';
        break;
      }
      cursor = page.cursor;
      await progress({ ...result });
    }
    await checkAccount();
    return result;
  }
  function relationship(item, following, accountId) {
    if (!item.authorId || !following || following.accountId !== accountId) return 'unknown';
    if (Object.hasOwn(following.accounts, item.authorId)) return 'followed';
    return following.complete ? 'not-followed' : 'unknown';
  }
  function filter(items, following, accountId, content, relation) {
    return items.filter(
      (item) =>
        (content === 'all' ||
          (content === 'reels'
            ? item.product === 'clips'
            : ['feed', 'carousel_container'].includes(item.product))) &&
        (relation === 'all' || relationship(item, following, accountId) === relation),
    );
  }
  globalThis.InstaCleanerFollowing = { parsePage, collect, relationship, filter };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerFollowing;
})();
