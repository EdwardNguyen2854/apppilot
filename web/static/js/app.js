let refreshInterval = null;
const REFRESH_INTERVAL_MS = 30000;

// Dashboard view state
let currentView = 'card';
let allApps = [];
let sortField = 'name';
let sortDir = 'asc';

document.addEventListener('DOMContentLoaded', function() {
  setActiveNav();
});

function setActiveNav() {
  const current = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav a').forEach(a => {
    const href = a.getAttribute('href').split('/').pop();
    if (href === current) a.classList.add('active');
  });
}

// -- App Actions --
async function startApp(appId) {
  try {
    const r = await fetch(`/api/apps/${appId}/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const result = await r.json();
    showNotification(result.success ? 'success' : 'error', result.message);
    if (result.success) refreshAppGrid();
  } catch (err) {
    showNotification('error', `Failed to start ${appId}`);
  }
}

async function stopApp(appId) {
  try {
    const r = await fetch(`/api/apps/${appId}/stop`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const result = await r.json();
    showNotification(result.success ? 'success' : 'error', result.message);
    if (result.success) refreshAppGrid();
  } catch (err) {
    showNotification('error', `Failed to stop ${appId}`);
  }
}

async function restartApp(appId) {
  try {
    const r = await fetch(`/api/apps/${appId}/restart`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const result = await r.json();
    showNotification(result.success ? 'success' : 'error', result.message);
    if (result.success) refreshAppGrid();
  } catch (err) {
    showNotification('error', `Failed to restart ${appId}`);
  }
}

async function viewLogs(appId, lines) {
  if (lines === undefined) lines = 100;
  try {
    const r = await fetch(`/api/apps/${appId}/logs?lines=${lines}`);
    const result = await r.json();
    showLogModal(appId, result.logs);
  } catch (err) {
    showNotification('error', 'Failed to load logs');
  }
}

// -- Refresh --
function refreshAppGrid() {
  fetch('/api/apps')
    .then(r => r.json())
    .then(data => { renderApps(data.apps); updateOverallStatus(); })
    .catch(err => console.error('Failed to refresh apps:', err));
}

function refreshSystemStats() {
  fetch('/api/system/stats')
    .then(r => r.json())
    .then(data => updateSystemStats(data))
    .catch(err => console.error('Failed to refresh stats:', err));
}

function startAutoRefresh() {
  if (refreshInterval) clearInterval(refreshInterval);
  refreshInterval = setInterval(() => { refreshAppGrid(); refreshSystemStats(); }, REFRESH_INTERVAL_MS);
}

function stopAutoRefresh() {
  if (refreshInterval) { clearInterval(refreshInterval); refreshInterval = null; }
}

// -- View Toggle --
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.view-toggle .btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const grid = document.getElementById('apps-grid');
  const listView = document.getElementById('apps-list-view');
  const tableView = document.getElementById('apps-table-view');
  if (grid) grid.style.display = view === 'card' ? '' : 'none';
  if (listView) listView.style.display = view === 'list' ? '' : 'none';
  if (tableView) tableView.style.display = view === 'table' ? '' : 'none';
  updateSortArrows();
  renderCurrentView();
}

// -- Filter & Sort --
function applyFilters() {
  const sortSelect = document.getElementById('dash-sort-field');
  if (sortSelect) sortField = sortSelect.value;
  updateSortArrows();
  renderCurrentView();
}

function toggleSortDir() {
  sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  const btn = document.getElementById('dash-sort-dir');
  if (btn) btn.textContent = sortDir === 'asc' ? '\u25B2' : '\u25BC';
  renderCurrentView();
}

function updateSortArrows() {
  document.querySelectorAll('.dashboard-table th.sortable').forEach(th => {
    th.classList.remove('sorted');
    const arrow = th.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = '';
  });
  const activeTh = document.querySelector(`.dashboard-table th.sortable[onclick*="'${sortField}'"]`);
  if (activeTh) {
    activeTh.classList.add('sorted');
    const arrow = activeTh.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = sortDir === 'asc' ? '\u25B2' : '\u25BC';
  }
}

function setSortField(field) {
  if (sortField === field) {
    toggleSortDir();
  } else {
    sortField = field;
    sortDir = 'asc';
    const select = document.getElementById('dash-sort-field');
    if (select) select.value = field;
    const btn = document.getElementById('dash-sort-dir');
    if (btn) btn.textContent = '\u25B2';
    updateSortArrows();
    renderCurrentView();
  }
}

function getFilteredAndSortedApps() {
  const searchInput = document.getElementById('dash-search');
  const typeSelect = document.getElementById('dash-filter-type');
  const statusSelect = document.getElementById('dash-filter-status');
  const sortSelect = document.getElementById('dash-sort-field');

  const search = (searchInput ? searchInput.value : '').toLowerCase();
  const typeFilter = typeSelect ? typeSelect.value : '';
  const statusFilter = statusSelect ? statusSelect.value : '';
  if (sortSelect) sortField = sortSelect.value;

  let filtered = allApps.filter(app => {
    const matchSearch = !search || app.name.toLowerCase().includes(search) || app.id.toLowerCase().includes(search) || (app.description||'').toLowerCase().includes(search);
    const matchType = !typeFilter || app.type === typeFilter;
    const matchStatus = !statusFilter || (statusFilter === 'running' && app.running) || (statusFilter === 'stopped' && !app.running);
    return matchSearch && matchType && matchStatus;
  });

  filtered.sort((a, b) => {
    let cmp = 0;
    switch (sortField) {
      case 'name': cmp = (a.name || '').localeCompare(b.name || ''); break;
      case 'type': cmp = (a.type || '').localeCompare(b.type || ''); break;
      case 'status': cmp = (a.running === b.running ? 0 : a.running ? -1 : 1); break;
      case 'cpu': cmp = (a.cpu_percent || 0) - (b.cpu_percent || 0); break;
      case 'memory': cmp = (a.memory_mb || 0) - (b.memory_mb || 0); break;
      case 'uptime': cmp = (a.uptime_sec || 0) - (b.uptime_sec || 0); break;
      case 'pid': cmp = (a.pid || 0) - (b.pid || 0); break;
      case 'port': cmp = ((a.port || '')+'').localeCompare((b.port || '')+''); break;
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return filtered;
}

function renderCurrentView() {
  const apps = getFilteredAndSortedApps();
  if (currentView === 'card') renderAppsGrid(apps);
  else if (currentView === 'list') renderAppsList(apps);
  else renderAppsTable(apps);
  updateFilterCount(apps.length);
}

function updateFilterCount(count) {
  const h2 = document.querySelector('.apps-section .section-header h2 span');
  if (h2) h2.textContent = count > 0 ? `(${count})` : '';
}

// -- Render Apps (Dashboard) --
function renderApps(apps) {
  allApps = apps || [];
  renderCurrentView();
  updateOverallStatus();
}

function renderAppsGrid(apps) {
  const grid = document.getElementById('apps-grid');
  if (!grid) return;
  if (!apps || apps.length === 0) {
    grid.innerHTML = '<div class="empty-state"><p>No apps configured. Add apps to apps.json to get started.</p></div>';
    return;
  }
  grid.innerHTML = apps.map(app => createAppCardHTML(app)).join('');
  const tc = document.getElementById('total-count');
  const rc = document.getElementById('running-count');
  if (tc) tc.textContent = allApps.length;
  if (rc) rc.textContent = allApps.filter(a => a.running).length;
}

function createAppCardHTML(app) {
  const running = app.running;
  return `
    <div class="app-card${running ? ' running' : ''}" data-app-id="${app.id}">
      <div class="app-card-header">
        <div class="app-card-icon">${getAppIcon(app.type)}</div>
        <div class="app-card-info">
          <div class="app-card-name">${escapeHtml(app.name)}</div>
          <div class="app-card-type">${app.type}</div>
        </div>
        <span class="status-badge${running ? ' online' : ' offline'}"><span class="dot"></span>${running ? 'Online' : 'Offline'}</span>
      </div>
      <div class="app-card-body">
        ${app.description ? `<p class="app-card-desc">${escapeHtml(app.description)}</p>` : ''}
        <div class="app-card-metrics">
          ${running ? `
            <div class="metric"><span class="metric-label">PID</span><span class="metric-value">${app.pid || '-'}</span></div>
            <div class="metric"><span class="metric-label">CPU</span><span class="metric-value">${app.cpu_percent ? app.cpu_percent.toFixed(1) + '%' : '-'}</span></div>
            <div class="metric"><span class="metric-label">RAM</span><span class="metric-value">${app.memory_mb ? app.memory_mb.toFixed(1) + ' MB' : '-'}</span></div>
            <div class="metric"><span class="metric-label">Uptime</span><span class="metric-value">${formatUptime(app.uptime_sec)}</span></div>
          ` : `
            <div class="metric"><span class="metric-label">Port</span><span class="metric-value">${app.port || '-'}</span></div>
            <div class="metric"><span class="metric-label">Type</span><span class="metric-value">${app.type}</span></div>
          `}
        </div>
        ${running && app.health_status ? `<div class="health-status health-${app.health_status}">Health: ${app.health_status}</div>` : ''}
      </div>
      <div class="app-card-footer">
        ${running ? `
          <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); stopApp('${app.id}')">Stop</button>
          <button class="btn btn-sm btn-warning" onclick="event.stopPropagation(); restartApp('${app.id}')">Restart</button>
          ${app.url ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); openUrl('${app.url}')">Open</button>` : ''}
        ` : `
          <button class="btn btn-sm btn-success" onclick="event.stopPropagation(); startApp('${app.id}')">Start</button>
        `}
        <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); viewLogs('${app.id}')">Logs</button>
      </div>
    </div>
  `;
}

function renderAppsList(apps) {
  const container = document.getElementById('apps-list-view');
  if (!container) return;
  if (!apps || apps.length === 0) {
    container.innerHTML = '<div class="empty-state"><p>No matching apps</p></div>';
    return;
  }
  container.innerHTML = apps.map(app => {
    const running = app.running;
    return `
      <div class="list-row${running ? ' running' : ''}">
        <div class="list-row-icon">${getAppIcon(app.type)}</div>
        <div class="list-row-info">
          <span class="list-row-name">${escapeHtml(app.name)}</span>
          <span class="list-row-id">${escapeHtml(app.id)}</span>
        </div>
        <div class="list-row-type"><span class="type-badge type-${app.type}">${app.type}</span></div>
        <div class="list-row-status"><span class="status-badge${running ? ' online' : ' offline'}"><span class="dot"></span>${running ? 'Online' : 'Offline'}</span></div>
        <div class="list-row-metrics">
          <div class="list-row-metric">
            <span class="list-row-metric-label">PID</span>
            <span class="list-row-metric-value">${app.pid || '-'}</span>
          </div>
          <div class="list-row-metric">
            <span class="list-row-metric-label">CPU</span>
            <span class="list-row-metric-value">${app.cpu_percent ? app.cpu_percent.toFixed(1) + '%' : '-'}</span>
          </div>
          <div class="list-row-metric">
            <span class="list-row-metric-label">RAM</span>
            <span class="list-row-metric-value">${app.memory_mb ? app.memory_mb.toFixed(1) + ' MB' : '-'}</span>
          </div>
        </div>
        <div class="list-row-actions">
          ${running ? `
            <button class="btn btn-sm btn-danger" onclick="stopApp('${app.id}')">Stop</button>
            <button class="btn btn-sm btn-warning" onclick="restartApp('${app.id}')">Restart</button>
            ${app.url ? `<button class="btn btn-sm btn-primary" onclick="openUrl('${app.url}')">Open</button>` : ''}
          ` : `
            <button class="btn btn-sm btn-success" onclick="startApp('${app.id}')">Start</button>
          `}
          <button class="btn btn-sm btn-secondary" onclick="viewLogs('${app.id}')">Logs</button>
        </div>
      </div>
    `;
  }).join('');
}

function renderAppsTable(apps) {
  const tbody = document.getElementById('dashboard-table-body');
  if (!tbody) return;
  if (!apps || apps.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No matching apps</td></tr>';
    return;
  }
  tbody.innerHTML = apps.map(app => {
    const running = app.running;
    return `
      <tr class="${running ? 'row-running' : ''}">
        <td>
          <div class="app-name-cell">
            <span style="font-size:1rem">${getAppIcon(app.type)}</span>
            <div class="app-name-info">
              <span class="app-name">${escapeHtml(app.name)}</span>
              <span class="app-id">${escapeHtml(app.id)}</span>
            </div>
          </div>
        </td>
        <td><span class="type-badge type-${app.type}">${app.type}</span></td>
        <td><span class="status-badge${running ? ' online' : ' offline'}"><span class="dot"></span>${running ? 'Online' : 'Offline'}</span></td>
        <td class="mono">${app.pid || '-'}</td>
        <td class="mono">${app.cpu_percent ? app.cpu_percent.toFixed(1) + '%' : '-'}</td>
        <td class="mono">${app.memory_mb ? app.memory_mb.toFixed(1) + ' MB' : '-'}</td>
        <td class="mono">${app.port || '-'}</td>
        <td class="mono">${formatUptime(app.uptime_sec)}</td>
        <td class="actions-cell">
          ${running ? `
            <button class="btn btn-sm btn-danger" onclick="stopApp('${app.id}')">Stop</button>
            <button class="btn btn-sm btn-warning" onclick="restartApp('${app.id}')">Restart</button>
            ${app.url ? `<button class="btn btn-sm btn-primary" onclick="openUrl('${app.url}')">Open</button>` : ''}
          ` : `
            <button class="btn btn-sm btn-success" onclick="startApp('${app.id}')">Start</button>
          `}
          <button class="btn btn-sm btn-secondary" onclick="viewLogs('${app.id}')">Logs</button>
        </td>
      </tr>
    `;
  }).join('');
}

function updateSystemStats(stats) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const bar = (id, pct) => { const el = document.getElementById(id); if (el) el.style.width = pct + '%'; };
  set('cpu-usage', stats.cpu_percent.toFixed(1) + '%');
  bar('cpu-bar', stats.cpu_percent);
  set('mem-usage', stats.memory_percent.toFixed(1) + '%');
  bar('mem-bar', stats.memory_percent);
  set('disk-usage', stats.disk_usage_percent.toFixed(1) + '%');
  bar('disk-bar', stats.disk_usage_percent);
  set('app-uptime', formatUptime(stats.uptime_seconds));
}

function updateOverallStatus() {
  const total = allApps.length;
  const running = allApps.filter(a => a.running).length;
  const el = document.getElementById('running-count');
  if (el) el.textContent = running;
  const tc = document.getElementById('total-count');
  if (tc) tc.textContent = total;
}

// -- Modal --
function showLogModal(appId, logs) {
  const existing = document.querySelector('.modal');
  if (existing) existing.remove();
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-content modal-xl">
      <div class="modal-header"><h3>Logs: ${escapeHtml(appId)}</h3><button class="modal-close" onclick="this.closest('.modal').remove()">\u00d7</button></div>
      <div class="modal-body"><pre class="log-content">${escapeHtml(logs.join('\n'))}</pre></div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', function(e) { if (e.target === modal) modal.remove(); });
  const handler = function(e) { if (e.key === 'Escape') { modal.remove(); document.removeEventListener('keydown', handler); } };
  document.addEventListener('keydown', handler);
}

function showSessionsModal(appId, sessions) {
  const existing = document.querySelector('.modal');
  if (existing) existing.remove();
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.innerHTML = `
    <div class="modal-content modal-lg">
      <div class="modal-header"><h3>Sessions: ${escapeHtml(appId)}</h3><button class="modal-close" onclick="this.closest('.modal').remove()">\u00d7</button></div>
      <div class="modal-body">
        ${sessions.length === 0 ? '<p>No sessions recorded</p>' : `
          <table class="data-table">
            <thead><tr><th>Started</th><th>Ended</th><th>Duration</th><th>Exit</th><th>Crash</th></tr></thead>
            <tbody>${sessions.map(s => `
              <tr>
                <td>${formatDateTime(s.started_at)}</td>
                <td>${s.stopped_at ? formatDateTime(s.stopped_at) : 'Running'}</td>
                <td>${s.duration_sec ? formatDuration(s.duration_sec) : '-'}</td>
                <td class="mono">${s.exit_code ?? '-'}</td>
                <td>${s.crash_detected ? 'Yes' : 'No'}</td>
              </tr>`).join('')}</tbody>
          </table>`}
      </div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', function(e) { if (e.target === modal) modal.remove(); });
}

// -- Utilities --
function openUrl(url) { window.open(url, '_blank'); }

function getAppIcon(type) {
  const icons = { desktop: '\uD83D\uDDA5\uFE0F', web: '\uD83C\uDF10', api: '\u2699\uFE0F', background: '\uD83D\uDD04', external: '\uD83D\uDD17', mcp: '\uD83D\uDD0C' };
  return icons[type] || '\uD83D\uDCE6';
}

function formatUptime(seconds) {
  if (!seconds) return '-';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatDuration(seconds) {
  if (!seconds || seconds === 0) return '0s';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatDateTime(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleString();
}

function formatTime(timestamp) {
  if (!timestamp) return '-';
  return new Date(timestamp).toLocaleTimeString();
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// -- Notification --
function showNotification(type, message) {
  const existing = document.querySelector('.notification');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = `notification notification-${type}`;
  el.innerHTML = `<span>${escapeHtml(message)}</span>`;
  document.body.appendChild(el);
  setTimeout(() => el.classList.add('show'), 10);
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// -- HTMX --
if (typeof htmx !== 'undefined') {
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'apps-grid') updateOverallStatus();
  });
}
