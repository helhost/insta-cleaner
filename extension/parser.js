/* Pure parser shared by the page observer, worker validation, and offline tests. */
(() => {
  const media =
    /\(bk\.action\.array\.Make,\s*"(\d+_\d+)",\s*"([A-Za-z0-9_-]+)",\s*"([a-z_]+)",\s*\(bk\.action\.i32\.Const,\s*(\d+)\)/g;
  function isInitialLikes(url) {
    try {
      const u = new URL(url, 'https://www.instagram.com');
      return (
        u.origin === 'https://www.instagram.com' &&
        u.pathname === '/async/wbloks/fetch/' &&
        u.searchParams.get('appid') === 'com.instagram.privacy.activity_center.liked_media_screen'
      );
    } catch {
      return false;
    }
  }
  function parse(body) {
    if (typeof body !== 'string' || body.length > 10000000)
      throw Error('Unsupported response size.');
    const data = JSON.parse(body.trim().replace(/^for \(;;\);/, ''));
    const payload = data?.payload?.layout?.bloks_payload;
    if (!payload || typeof payload !== 'object')
      throw Error('Instagram returned an unsupported Likes response.');
    const stack = [payload],
      found = new Map();
    while (stack.length) {
      const value = stack.pop();
      if (typeof value === 'string') {
        for (const match of value.matchAll(media)) {
          const [id, authorId] = match[1].split('_');
          found.set(match[1], {
            mediaId: id,
            authorId,
            code: match[2],
            product: match[3],
            evidence: 'inferred',
          });
          if (found.size > 200) throw Error('Unexpected item count.');
        }
      } else if (value && typeof value === 'object') stack.push(...Object.values(value));
    }
    if (!found.size && !emptyRange(payload))
      throw Error('No supported items or recognized empty range found.');
    return [...found.values()];
  }
  function emptyRange(payload) {
    const state = payload.data?.some(
      (x) =>
        x?.data?.key === 'dtl:ig_activity_center:ya_has_items_rendered' &&
        x.data.initial_lispy === '(bk.action.bool.Const, false)',
    );
    if (!state) return false;
    const stack = [payload.embedded_payloads];
    let icon = false,
      heading = false;
    while (stack.length) {
      const v = stack.pop();
      if (!v || typeof v !== 'object') continue;
      if (v['ig.components.Icon']?.resource_name === 'error_outline_96') icon = true;
      const a = v['bk.components.AccessibilityExtension'];
      if (a?.role === 'Header' && ['Ingen treff', 'No results', 'No Results'].includes(a.label))
        heading = true;
      stack.push(...Object.values(v));
    }
    return Boolean(icon && heading);
  }
  function continuation(body) {
    const data = JSON.parse(body.trim().replace(/^for \(;;\);/, ''));
    const stack = [data?.payload?.layout?.bloks_payload],
      found = [];
    const string = '"(?:\\\\.|[^"\\\\])*"';
    const pattern = new RegExp(
      '\\(bk\\.action\\.bloks\\.AsyncActionWithDataManifest,\\s*"com\\.instagram\\.privacy\\.activity_center\\.liked_next",\\s*\\(bk\\.action\\.map\\.Make,\\s*\\(bk\\.action\\.array\\.Make,\\s*"page_size",\\s*"activity_center_params",\\s*"cursor",\\s*"container_id",\\s*"element_id"\\),\\s*\\(bk\\.action\\.array\\.Make,\\s*(' +
        string +
        '),\\s*(' +
        string +
        '),\\s*(' +
        string +
        '),\\s*(' +
        string +
        '),\\s*(' +
        string +
        ')\\)\\)',
      'g',
    );
    while (stack.length) {
      const value = stack.pop();
      if (typeof value === 'string')
        for (const match of value.matchAll(pattern)) {
          const params = Object.fromEntries(
            ['page_size', 'activity_center_params', 'cursor', 'container_id', 'element_id'].map(
              (k, i) => [k, JSON.parse(match[i + 1])],
            ),
          );
          if (!found.some((x) => JSON.stringify(x) === JSON.stringify(params))) found.push(params);
        }
      else if (value && typeof value === 'object') stack.push(...Object.values(value));
    }
    return found.length === 1 && found[0].cursor ? found[0] : null;
  }
  function validateItems(items) {
    if (!Array.isArray(items) || !items.length || items.length > 200)
      throw Error('Invalid preview items.');
    return items.map((x) => {
      if (
        !x ||
        !/^[1-9][0-9]{0,29}$/.test(x.mediaId) ||
        !/^[1-9][0-9]{0,29}$/.test(x.authorId) ||
        !/^[A-Za-z0-9_-]{1,50}$/.test(x.code) ||
        !/^[a-z_]{1,40}$/.test(x.product) ||
        x.evidence !== 'inferred'
      )
        throw Error('Invalid preview item.');
      return {
        mediaId: String(x.mediaId),
        authorId: String(x.authorId),
        code: x.code,
        product: x.product,
        evidence: 'inferred',
      };
    });
  }
  globalThis.InstaCleanerParser = { isInitialLikes, parse, validateItems, continuation };
  if (typeof module !== 'undefined') module.exports = globalThis.InstaCleanerParser;
})();
