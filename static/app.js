'use strict';
const menu = document.querySelector('#menu-toggle');
menu?.addEventListener('click', () => {
  const expanded = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(expanded));
  const navigation = document.querySelector('#navigation');
  navigation.classList.toggle('hidden', !expanded);
  navigation.classList.toggle('flex', expanded);
});
document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
const activity = document.querySelector('#activity-select');
activity?.addEventListener('change', () => {
  document.querySelector('#score-value').max = activity.selectedOptions[0].dataset.max;
});
document.querySelector('#print-report')?.addEventListener('click', () => window.print());
const board = document.querySelector('[data-leaderboard]');
if (board) {
  const status = board.querySelector('[data-refresh-status]');
  let pending = false;
  const refresh = async () => {
    if (document.hidden || pending) return;
    pending = true;
    try {
      const response = await fetch('/api/leaderboard', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw new Error('refresh failed');
      const teams = await response.json();
      const body = document.createDocumentFragment();
      for (const team of teams) {
        const row = document.createElement('tr');
        for (const [index, value] of [team.rank, team.name, team.total_score, team.activities_completed].entries()) {
          const cell = document.createElement('td');
          if (index === 1 && team.image_filename) {
            const group = document.createElement('div');
            group.className = 'flex gap-3 items-center';
            const image = document.createElement('img');
            image.src = '/uploads/' + encodeURIComponent(team.image_filename);
            image.alt = ''; image.width = 40; image.height = 40;
            image.className = 'w-10 h-10 rounded-lg object-cover';
            const name = document.createElement('span');
            name.textContent = value;
            group.append(image, name); cell.append(group);
          } else cell.textContent = value;
          row.append(cell);
        }
        body.append(row);
      }
      if (!teams.length) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 4;
        cell.textContent = 'No teams have been configured yet.';
        row.append(cell); body.append(row);
      }
      board.querySelector('[data-standings-body]').replaceChildren(body);
      const open = response.headers.get('X-Scoring-Open') === '1';
      board.querySelector('[data-scoring-status]').textContent = open ? 'Scoring open — provisional results' : 'Scoring closed';
      status.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (_error) {
      status.textContent = 'Connection interrupted — showing the last received standings.';
    } finally { pending = false; }
  };
  setInterval(refresh, 10000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
}
