const $ = (id) => document.getElementById(id);
let state = null,
  version = 0,
  scanKey = '',
  approval = null,
  refreshTimer = null,
  pending = false;
const filterIds = ['content', 'relationship', 'startDate', 'endDate'];
function filtersFromForm() {
  return Object.fromEntries(filterIds.map((id) => [id, $(id).value]));
}
function chosen() {
  return state?.filters ? InstaCleanerWorkflow.matches(state) : [];
}
function render() {
  const scanning = state?.status === 'scanning',
    removing = state?.status === 'removing',
    running = scanning || removing || pending;
  const finished = state?.status === 'finished',
    halted = state?.status === 'halted',
    ready = state?.status === 'ready';
  const rows = chosen(),
    removed = (state?.results || []).filter((x) => x.status === 'unliked-server-confirmed').length;
  const changed =
    state?.filters && filterIds.some((id) => (state.filters[id] || '') !== $(id).value);
  $('scan').disabled = running;
  $('stop').hidden = !scanning && !removing;
  $('stop').textContent = removing ? 'Stop cleanup' : 'Stop search';
  for (const id of filterIds) $(id).disabled = running;
  for (const button of document.querySelectorAll(
    '[data-content], [data-days], #open-dates, #clear-dates',
  ))
    button.disabled = running;
  for (const button of document.querySelectorAll('[data-content]'))
    button.setAttribute('aria-pressed', button.dataset.content === $('content').value);
  const from = $('startDate').value,
    to = $('endDate').value,
    format = InstaCleanerCalendar.format;
  $('date-label').textContent =
    from && to
      ? `${format(from)} — ${format(to)}`
      : from
        ? `From ${format(from)}`
        : to
          ? `Until ${format(to)}`
          : 'Any time';
  $('clear-dates').hidden = !from && !to;
  $('review').hidden = !ready || !rows.length || Boolean(changed);
  $('review').disabled = !ready || !rows.length || Boolean(changed) || pending;
  $('review').textContent =
    `Remove ${rows.length.toLocaleString()} ${rows.length === 1 ? 'like' : 'likes'}`;
  $('account').textContent = state?.accountId ? `Account ${state.accountId}` : '';
  $('phase').textContent = finished
    ? 'ALL DONE'
    : halted
      ? 'NEEDS YOUR ATTENTION'
      : scanning
        ? 'FINDING YOUR LIKES'
        : removing
          ? 'MAKING ROOM'
          : ready
            ? 'YOUR MATCHES'
            : 'YOUR FRESH START';
  $('activity-icon').textContent = finished ? '✓' : '✧';
  $('activity').classList.toggle('complete', finished);
  $('count').textContent = finished
    ? `${removed.toLocaleString()} ${removed === 1 ? 'like' : 'likes'} removed`
    : state
      ? `${rows.length.toLocaleString()} matches`
      : 'Ready when you are';
  let status = 'Choose your filters to find your likes.';
  if (pending) status = 'Getting things ready…';
  else if (scanning)
    status = state.message?.startsWith('Loading Following')
      ? 'Getting your connections ready…'
      : 'Finding the likes that fit your filters.';
  else if (removing) status = 'Removing your confirmed likes…';
  else if (finished)
    status = state.stopRequested
      ? 'Cleanup stopped. Completed removals are saved.'
      : 'A little lighter. You’re all done.';
  else if (halted)
    status = state.clickPending
      ? 'We couldn’t confirm the removal. Check Instagram before trying again.'
      : 'Cleanup was interrupted before the next request.';
  else if (ready)
    status = state.stopRequested
      ? 'Search stopped. Here’s what we found so far.'
      : state.scanIssue
        ? 'Search interrupted. Some likes may be missing.'
        : rows.length
          ? 'Your matches are ready. The next step is up to you.'
          : 'No likes found. Try a different date range or filter.';
  if (changed && !running) status = 'Filters updated. Search again to see your matches.';
  $('status').textContent = status;
  $('scope').textContent =
    ready && rows.length
      ? 'Only likes found in this search will be removed.'
      : halted && removed
        ? `${removed} likes were already removed.`
        : '';
  $('progress-area').hidden = !scanning && !removing;
  const p = state?.queueProgress,
    determinate = scanning && p && p.total > 0;
  $('progress').classList.toggle('indeterminate', !determinate);
  if (determinate) {
    const percentage = Math.max(0, Math.min(100, Math.floor((100 * p.completed) / p.total)));
    $('percent').textContent = `${percentage}%`;
    $('progress-fill').style.width = `${percentage}%`;
    $('progress').setAttribute('aria-valuenow', percentage);
  } else {
    $('percent').textContent = '';
    $('progress').removeAttribute('aria-valuenow');
  }
  $('progress-label').textContent = removing ? 'Removing likes' : 'Searching your dates';
  const elapsed = state?.startedAt ? Math.floor((Date.now() - state.startedAt) / 1000) : 0;
  $('time-hint').textContent =
    scanning && elapsed > 2
      ? `${elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`} elapsed · timing varies by date range`
      : '';
}
async function refresh() {
  clearTimeout(refreshTimer);
  refreshTimer = null;
  const v = ++version,
    result = await chrome.runtime.sendMessage({ type: 'STATE' });
  if (v !== version) return;
  if (!result.ok) {
    state = null;
    render();
    $('status').textContent = 'Open Instagram and sign in to get started.';
    return;
  }
  state = result.state;
  const next = `${result.tabId}:${state?.accountId}:${state?.token}`;
  if (next !== scanKey) {
    scanKey = next;
    approval = null;
    $('confirm').close();
    if (state?.filters) for (const id of filterIds) $(id).value = state.filters[id] || '';
  }
  render();
  if (['scanning', 'removing'].includes(state?.status))
    refreshTimer = setTimeout(() => refresh().catch(() => {}), 700);
}
async function command(message) {
  pending = true;
  render();
  try {
    const result = await chrome.runtime.sendMessage(message);
    if (!result.ok) throw Error();
    pending = false;
    await refresh();
    return result;
  } catch {
    pending = false;
    render();
    $('status').textContent = 'We couldn’t complete that step. Check Instagram, then try again.';
    return null;
  }
}
$('scan').addEventListener('click', () => command({ type: 'SCAN', filters: filtersFromForm() }));
$('stop').addEventListener('click', () => command({ type: 'STOP' }));
for (const id of filterIds) $(id).addEventListener('change', render);
for (const button of document.querySelectorAll('[data-content]'))
  button.addEventListener('click', () => {
    $('content').value = button.dataset.content;
    render();
  });
$('review').addEventListener('click', async () => {
  const result = await command({ type: 'PREPARE', ids: chosen().map((x) => x.mediaId) });
  if (!result) return;
  approval = result.approval;
  $('confirm-text').textContent =
    `Remove ${approval.ids.length.toLocaleString()} ${approval.ids.length === 1 ? 'like' : 'likes'} matching your filters?`;
  $('confirm').showModal();
});
$('cancel').addEventListener('click', () => {
  $('confirm').close();
  approval = null;
});
$('execute').addEventListener('click', () => {
  if (!approval) return;
  const token = approval.token;
  approval = null;
  $('confirm').close();
  command({ type: 'CONFIRM', approval: token });
});
window.addEventListener('focus', () => refresh().catch(() => {}));
chrome.tabs.onActivated.addListener(() => refresh().catch(() => {}));
render();
refresh().catch(() => {
  $('status').textContent = 'Reopen the extension to reconnect.';
});
