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
  // Read the same fallback timestamps used by Instagram's own date pickers.
  // Missing or ambiguous metadata leaves the all-time scan unbounded.
  function defaultRange(body) {
    try {
      const data = JSON.parse(body.trim().replace(/^for \(;;\);/, ''));
      const stack = [data?.payload?.layout?.bloks_payload];
      const values = { start: new Set(), end: new Set() };
      while (stack.length) {
        const value = stack.pop();
        if (!value || typeof value !== 'object') continue;
        const picker = value['ig.component.DatePicker'];
        if (picker) {
          const key = /"dtl:ig_activity_center:ac_bottom_date_(start|end)"/.exec(
            picker.on_date_picked || '',
          )?.[1];
          const matches = [
            ...(picker.on_bind || '').matchAll(
              /\(bk\.action\.core\.Pattern,\s*\(bk\.action\.i32\.Const,\s*1\),\s*\(bk\.action\.core\.FuncConst,\s*\(bk\.action\.i32\.Const,\s*(\d+)\)\)/g,
            ),
          ];
          if (key && matches.length === 1) values[key].add(Number(matches[0][1]));
        }
        stack.push(...Object.values(value));
      }
      if (values.start.size !== 1 || values.end.size !== 1) return null;
      const start = [...values.start][0],
        end = [...values.end][0];
      if (start < 0 || start > end || end > Date.now() / 1000 + 86400) return null;
      const date = (seconds) => {
        const d = new Date(seconds * 1000);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      };
      // The range requests use midnight boundaries; include the entire final day.
      const tomorrow = new Date(end * 1000);
      tomorrow.setDate(tomorrow.getDate() + 1);
      return options({ startDate: date(start), endDate: date(tomorrow.getTime() / 1000) });
    } catch {
      return null;
    }
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
  globalThis.InstaCleanerDates = { options, refreshParams, defaultRange };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerDates;
})();
