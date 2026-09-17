const test = require('node:test');
const assert = require('node:assert/strict');
global.InstaCleanerFollowing = require('../../extension/following');
global.InstaCleanerDates = require('../../extension/dates');
const workflow = require('../../extension/workflow');
const reel = { mediaId: '100', code: 'ABC', authorId: '42', product: 'clips' };
const post = { mediaId: '101', code: 'DEF', authorId: '43', product: 'feed' };
const state = () => ({
  status: 'ready',
  accountId: '1',
  items: [reel, post],
  filters: { content: 'all', relationship: 'all' },
});
test('confirmation preserves the exact selected items', () => {
  assert.deepEqual(workflow.prepare(state(), ['101']), [post]);
  assert.throws(() => workflow.prepare(state(), ['999']));
  assert.throws(() => workflow.prepare(state(), ['100', '100']));
  assert.throws(() => workflow.prepare(state(), []));
  assert.throws(() => workflow.prepare({ ...state(), status: 'scanning' }, ['100']));
});
test('selection must still match the content filter', () => {
  const value = state();
  value.filters.content = 'reels';
  assert.deepEqual(workflow.matches(value), [reel]);
  assert.throws(() => workflow.prepare(value, ['101']));
});
test('negative membership requires a complete snapshot for the same account', () => {
  const value = state();
  value.filters.relationship = 'not-followed';
  value.following = { accountId: '1', accounts: { 42: 'someone' }, complete: false };
  assert.deepEqual(workflow.matches(value), []);
  value.following.complete = true;
  assert.deepEqual(workflow.matches(value), [post]);
  value.following.accountId = '2';
  assert.deepEqual(workflow.matches(value), []);
});
test('invalid filters are rejected', () => {
  assert.throws(() => workflow.filters({ content: 'video', relationship: 'all' }));
  assert.throws(() => workflow.filters({ content: 'all', relationship: 'friends' }));
});
