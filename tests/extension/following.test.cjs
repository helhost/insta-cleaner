const test = require('node:test'),
  assert = require('node:assert/strict');
const { collect, parsePage, relationship, filter } = require('../../extension/following.js');
const page = (id, more = false, cursor = '') => ({
  status: 'ok',
  users: [{ pk: id, username: 'example' }],
  has_more: more,
  next_max_id: cursor,
  should_limit_list_of_followings: false,
  hidden_following_account_count: 0,
});
test('collects sequential pages and ends only at unrestricted terminal', async () => {
  const urls = [];
  let i = 0;
  const result = await collect({
    accountId: '42',
    request: async (url) => {
      urls.push(url);
      return { status: 200, json: async () => (i++ ? page('2') : page('1', true, 'next')) };
    },
    checkAccount: async () => {},
    progress: async () => {},
    delay: async () => {},
  });
  assert.equal(result.complete, true);
  assert.equal(Object.keys(result.accounts).length, 2);
  assert.match(urls[1], /max_id=next/);
});
test('HTTP failure and restrictions cannot establish negative membership', async () => {
  for (const response of [
    { status: 429 },
    { status: 200, json: async () => ({ ...page('1'), should_limit_list_of_followings: true }) },
  ]) {
    const result = await collect({
      accountId: '42',
      request: async () => response,
      checkAccount: async () => {},
      progress: async () => {},
      delay: async () => {},
    });
    assert.equal(result.complete, false);
    assert.equal(relationship({ authorId: '9' }, result, '42'), 'unknown');
  }
});
test('account mismatches and incomplete absence remain unknown; membership is provisional', () => {
  const following = { accountId: '42', accounts: { 1: 'example' }, complete: true };
  assert.equal(relationship({ authorId: '1' }, following, '42'), 'followed');
  assert.equal(relationship({ authorId: '2' }, following, '42'), 'not-followed');
  assert.equal(relationship({ authorId: '1' }, following, '43'), 'unknown');
  assert.equal(relationship({ authorId: '2' }, { ...following, complete: false }, '42'), 'unknown');
  assert.equal(
    filter(
      [
        { product: 'clips', authorId: '2' },
        { product: 'feed', authorId: '2' },
      ],
      following,
      '42',
      'reels',
      'not-followed',
    ).length,
    1,
  );
});
test('rejects malformed Following pages', () => {
  for (const data of [
    null,
    {},
    { ...page('1'), has_more: true },
    { ...page('1'), users: [{ pk: 'bad', username: 'x' }] },
  ])
    assert.throws(() => parsePage(data));
});
