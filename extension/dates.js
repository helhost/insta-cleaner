/* Date filter request format observed in the Likes refresh flow. */
(() => {
  function options(value = {}) {
    const result = {
      startDate: value.startDate || '',
      endDate: value.endDate || '',
      order: value.order || 'newest_to_oldest',
    };
    for (const key of ['startDate', 'endDate']) {
      const s = result[key];
      if (
        s &&
        (typeof s !== 'string' ||
          !/^\d{4}-\d{2}-\d{2}$/.test(s) ||
          !Number.isFinite(Date.parse(s)) ||
          new Date(s).toISOString().slice(0, 10) !== s)
      )
        throw Error('Choose valid dates.');
    }
    if (result.startDate && result.endDate && result.startDate > result.endDate)
      throw Error('Start date must be before end date.');
    if (!['newest_to_oldest', 'oldest_to_newest'].includes(result.order))
      throw Error('Choose a valid sort order.');
    return result;
  }
  function timestamp(s) {
    if (!s) return -1;
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d).getTime() / 1000;
  }
  function refreshParams(body, next, settings) {
    const opt = options(settings),
      a = JSON.parse(next.activity_center_params);
    const data = JSON.parse(body.trim().replace(/^for \(;;\);/, '')),
      stack = [data?.payload?.layout?.bloks_payload],
      ids = new Set();
    const pattern =
      /"com\.instagram\.privacy\.activity_center\.liked_refresh",\s*\(bk\.action\.map\.Make,\s*\(bk\.action\.array\.Make,\s*"content_container_id",\s*"content_element_id",\s*"content_spinner_id"[^)]*\),\s*\(bk\.action\.array\.Make,\s*\(bk\.action\.i32\.Const,\s*(\d+)\),\s*\(bk\.action\.i32\.Const,\s*(\d+)\),\s*\(bk\.action\.i32\.Const,\s*(\d+)\)/g;
    while (stack.length) {
      const v = stack.pop();
      if (typeof v === 'string') {
        for (const m of v.matchAll(pattern)) ids.add(JSON.stringify(m.slice(1).map(Number)));
      } else if (v && typeof v === 'object') stack.push(...Object.values(v));
    }
    if (ids.size !== 1) throw Error('Date filter request unavailable.');
    const [container, element, spinner] = JSON.parse([...ids][0]);
    const result = {
      content_container_id: container,
      content_element_id: element,
      content_spinner_id: spinner,
    };
    for (const k of [
      'main_authors_state_value',
      'main_filter_to_visible_on_facebook_value',
      'main_includes_location_value',
      'main_liked_privately_value',
      'main_content_type_value',
      'main_content_types_value',
      'main_account_history_events_state_value',
      'main_filter_to_visible_from_facebook_value',
    ]) {
      if (!(k in a)) throw Error('Date filter parameters unavailable.');
      result[k] = a[k];
    }
    return {
      ...result,
      main_order_state_value: opt.order === 'newest_to_oldest',
      main_attribute_order_state_value: opt.order,
      main_date_start_state_value: timestamp(opt.startDate),
      main_date_end_state_value: timestamp(opt.endDate),
      entrypoint: '',
      shared_user_id: '',
    };
  }
  globalThis.InstaCleanerDates = { options, refreshParams };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerDates;
})();
