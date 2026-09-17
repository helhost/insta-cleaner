const test = require('node:test'),
  assert = require('node:assert/strict');
const dates = require('../../extension/dates');
const activity = {
  main_authors_state_value: '',
  main_filter_to_visible_on_facebook_value: false,
  main_includes_location_value: false,
  main_liked_privately_value: false,
  main_content_type_value: 0,
  main_content_types_value: 'Posts, Reels',
  main_account_history_events_state_value: '',
  main_filter_to_visible_from_facebook_value: false,
};
const expr =
  '"com.instagram.privacy.activity_center.liked_refresh", (bk.action.map.Make, (bk.action.array.Make, "content_container_id", "content_element_id", "content_spinner_id", "main_order_state_value"), (bk.action.array.Make, (bk.action.i32.Const, 101), (bk.action.i32.Const, 102), (bk.action.i32.Const, 103)';
const body = JSON.stringify({ payload: { layout: { bloks_payload: [expr] } } }),
  next = { activity_center_params: JSON.stringify(activity) };
test('dates reject invalid calendar values and reversed bounds', () => {
  for (const v of [
    { startDate: '2026-02-30' },
    { startDate: '2026-09-02', endDate: '2026-09-01' },
    { order: 'sideways' },
  ])
    assert.throws(() => dates.options(v));
  assert.equal(dates.options({ startDate: '2024-02-29' }).startDate, '2024-02-29');
});
test('refresh uses live container IDs and local calendar dates, without a previous cursor', () => {
  const result = dates.refreshParams(body, next, {
    startDate: '2026-09-01',
    endDate: '2026-10-01',
    order: 'oldest_to_newest',
  });
  assert.equal(result.content_spinner_id, 103);
  assert.equal(result.main_order_state_value, false);
  assert.equal(result.main_date_start_state_value, new Date(2026, 8, 1).getTime() / 1000);
  assert.equal(result.main_date_end_state_value, new Date(2026, 9, 1).getTime() / 1000);
  assert.equal(result.cursor, undefined);
  assert.equal(result.main_content_types_value, 'Posts, Reels');
});
test('missing and ambiguous refresh templates fail instead of silently using all dates', () => {
  assert.throws(() => dates.refreshParams('{}', next, {}));
  assert.throws(() => dates.refreshParams(body, { activity_center_params: '{}' }, {}));
  const ambiguous = JSON.stringify({
    payload: { layout: { bloks_payload: [expr, expr.replace('103', '104')] } },
  });
  assert.throws(() => dates.refreshParams(ambiguous, next, {}));
});
function pickerRange(start, end) {
  return JSON.stringify({
    payload: {
      layout: {
        bloks_payload: {
          tree: [
            ...['start', 'end'].map((key, i) => ({
              'ig.component.DatePicker': {
                on_date_picked: `(bk.action.bloks.WriteGlobalConsistencyStore, "dtl:ig_activity_center:ac_bottom_date_${key}", (bk.action.core.GetArg, 0))`,
                on_bind: `(bk.action.core.Pattern, (bk.action.i32.Const, 1), (bk.action.core.FuncConst, (bk.action.i32.Const, ${i ? end : start})))`,
              },
            })),
          ],
        },
      },
    },
  });
}
test('automatic range reads picker defaults and includes the entire last day', () => {
  const start = new Date(2020, 0, 1, 12).getTime() / 1000,
    end = new Date(2020, 0, 31, 12).getTime() / 1000;
  assert.deepEqual(dates.defaultRange(pickerRange(start, end)), {
    startDate: '2020-01-01',
    endDate: '2020-02-01',
    order: 'newest_to_oldest',
  });
  assert.equal(dates.defaultRange(pickerRange(end, start)), null);
  assert.equal(dates.defaultRange('{}'), null);
  assert.equal(dates.defaultRange('invalid'), null);
});
