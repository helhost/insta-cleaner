/* Local calendar UI. Dates are committed only when Apply is pressed. */
(() => {
  const el = (id) => document.getElementById(id),
    dialog = el('date-picker');
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const parse = (s) => {
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d, 12);
  };
  const format = (s) =>
    s
      ? parse(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
      : 'Any time';
  let draft = { startDate: '', endDate: '' },
    field = 'startDate',
    view = new Date();
  for (let m = 0; m < 12; m++) {
    const option = new Option(
      new Date(2024, m, 1).toLocaleDateString(undefined, { month: 'long' }),
      m,
    );
    el('calendar-month').add(option);
  }
  for (let y = 1970; y <= new Date().getFullYear() + 1; y++)
    el('calendar-year').add(new Option(y, y));
  function render() {
    el('draft-start').textContent = format(draft.startDate);
    el('draft-end').textContent = format(draft.endDate);
    el('pick-start').classList.toggle('active', field === 'startDate');
    el('pick-end').classList.toggle('active', field === 'endDate');
    el('pick-start').setAttribute('aria-pressed', field === 'startDate');
    el('pick-end').setAttribute('aria-pressed', field === 'endDate');
    el('calendar-month').value = view.getMonth();
    el('calendar-year').value = view.getFullYear();
    const first = new Date(view.getFullYear(), view.getMonth(), 1, 12),
      offset = (first.getDay() + 6) % 7;
    const today = iso(new Date());
    const buttons = [];
    for (let i = 0; i < 42; i++) {
      const date = new Date(first);
      date.setDate(1 - offset + i);
      const value = iso(date),
        button = document.createElement('button');
      button.type = 'button';
      button.textContent = date.getDate();
      button.dataset.date = value;
      button.setAttribute(
        'aria-label',
        date.toLocaleDateString(undefined, {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        }),
      );
      button.classList.toggle('outside', date.getMonth() !== view.getMonth());
      button.classList.toggle('selected', value === draft.startDate || value === draft.endDate);
      button.classList.toggle(
        'between',
        Boolean(
          draft.startDate && draft.endDate && value > draft.startDate && value < draft.endDate,
        ),
      );
      button.classList.toggle('today', value === today);
      button.setAttribute('aria-pressed', value === draft[field]);
      button.addEventListener('click', () => {
        draft[field] = value;
        if (field === 'startDate') field = 'endDate';
        el('date-error').textContent = '';
        render();
      });
      button.addEventListener('keydown', (e) => {
        const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
        if (!(e.key in steps)) return;
        e.preventDefault();
        const target = new Date(date);
        target.setDate(target.getDate() + steps[e.key]);
        view = new Date(target.getFullYear(), target.getMonth(), 1, 12);
        render();
        el('calendar-grid')
          .querySelector(`[data-date="${iso(target)}"]`)
          ?.focus();
      });
      buttons.push(button);
    }
    el('calendar-grid').replaceChildren(...buttons);
  }
  function open() {
    draft = { startDate: el('startDate').value, endDate: el('endDate').value };
    field = 'startDate';
    const d = draft.startDate ? parse(draft.startDate) : new Date();
    view = new Date(d.getFullYear(), d.getMonth(), 1, 12);
    el('date-error').textContent = '';
    render();
    dialog.showModal();
  }
  function commit(value) {
    el('startDate').value = value.startDate;
    el('endDate').value = value.endDate;
    el('startDate').dispatchEvent(new Event('change'));
    dialog.close();
  }
  el('open-dates').addEventListener('click', open);
  el('date-close').addEventListener('click', () => dialog.close());
  el('pick-start').addEventListener('click', () => {
    field = 'startDate';
    render();
  });
  el('pick-end').addEventListener('click', () => {
    field = 'endDate';
    render();
  });
  for (const [id, delta] of [
    ['prev-month', -1],
    ['next-month', 1],
  ])
    el(id).addEventListener('click', () => {
      view.setMonth(view.getMonth() + delta);
      render();
    });
  for (const id of ['calendar-month', 'calendar-year'])
    el(id).addEventListener('change', () => {
      view = new Date(Number(el('calendar-year').value), Number(el('calendar-month').value), 1, 12);
      render();
    });
  el('apply-dates').addEventListener('click', () => {
    try {
      InstaCleanerDates.options(draft);
      commit(draft);
    } catch {
      el('date-error').textContent = 'Choose an end date on or after your start date.';
    }
  });
  el('any-dates').addEventListener('click', () => commit({ startDate: '', endDate: '' }));
  el('clear-dates').addEventListener('click', () => commit({ startDate: '', endDate: '' }));
  for (const button of document.querySelectorAll('[data-days]'))
    button.addEventListener('click', () => {
      const end = new Date(),
        start = new Date();
      start.setDate(start.getDate() - Number(button.dataset.days));
      commit({ startDate: iso(start), endDate: iso(end) });
    });
  globalThis.InstaCleanerCalendar = { format };
})();
