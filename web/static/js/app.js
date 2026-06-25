/**
 * AppPilot JavaScript
 * Core functionality for the dashboard
 */

// Global state
let refreshInterval = null;
const REFRESH_INTERVAL_MS = 30000;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    console.log('AppPilot dashboard initialized');
});

// App Actions
async function startApp(appId) {
    try {
        const response = await fetch(`/api/apps/${appId}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        showNotification(result.success ? 'success' : 'error', result.message);
        if (result.success) {
            refreshAppGrid();
        }
    } catch (err) {
        console.error('Failed to start app:', err);
        showNotification('error', `Failed to start ${appId}`);
    }
}

async function stopApp(appId) {
    try {
        const response = await fetch(`/api/apps/${appId}/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        showNotification(result.success ? 'success' : 'error', result.message);
        if (result.success) {
            refreshAppGrid();
        }
    } catch (err) {
        console.error('Failed to stop app:', err);
        showNotification('error', `Failed to stop ${appId}`);
    }
}

async function restartApp(appId) {
    try {
        const response = await fetch(`/api/apps/${appId}/restart`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        showNotification(result.success ? 'success' : 'error', result.message);
        if (result.success) {
            refreshAppGrid();
        }
    } catch (err) {
        console.error('Failed to restart app:', err);
        showNotification('error', `Failed to restart ${appId}`);
    }
}

async function viewLogs(appId, lines = 100) {
    try {
        const response = await fetch(`/api/apps/${appId}/logs?lines=${lines}`);
        const result = await response.json();
        showLogModal(appId, result.logs);
    } catch (err) {
        console.error('Failed to load logs:', err);
        showNotification('error', 'Failed to load logs');
    }
}

// Refresh functions
function refreshAppGrid() {
    fetch('/api/apps')
        .then(r => r.json())
        .then(data => {
            renderApps(data.apps);
            updateOverallStatus();
        })
        .catch(err => console.error('Failed to refresh apps:', err));
}

function refreshSystemStats() {
    fetch('/api/system/stats')
        .then(r => r.json())
        .then(data => {
            updateSystemStats(data);
        })
        .catch(err => console.error('Failed to refresh system stats:', err));
}

function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(() => {
        refreshAppGrid();
        refreshSystemStats();
    }, REFRESH_INTERVAL_MS);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Render functions
function renderApps(apps) {
    const grid = document.getElementById('apps-grid');
    if (!grid) return;

    if (!apps || apps.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <p>No apps configured. Add apps to apps.json to get started.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = apps.map(app => createAppCardHTML(app)).join('');

    // Update counts
    const totalCount = document.getElementById('total-count');
    const runningCount = document.getElementById('running-count');
    if (totalCount) totalCount.textContent = apps.length;
    if (runningCount) runningCount.textContent = apps.filter(a => a.running).length;
}

function createAppCardHTML(app) {
    const icon = getAppIcon(app.type);
    const statusClass = app.running ? 'online' : 'offline';
    const statusText = app.running ? 'Online' : 'Offline';

    return `
        <div class="app-card ${app.running ? 'running' : ''}" data-app-id="${app.id}">
            <div class="app-header">
                <span class="app-icon">${icon}</span>
                <div class="app-info">
                    <h3 class="app-name">${escapeHtml(app.name)}</h3>
                    <span class="app-type">${app.type}</span>
                </div>
                <span class="status-badge ${statusClass}">${statusText}</span>
            </div>

            <div class="app-body">
                ${app.description ? `<p class="app-description">${escapeHtml(app.description)}</p>` : ''}

                ${app.running ? `
                    <div class="app-metrics">
                        <div class="metric">
                            <span class="metric-label">PID</span>
                            <span class="metric-value">${app.pid || '-'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">CPU</span>
                            <span class="metric-value">${app.cpu_percent ? app.cpu_percent.toFixed(1) + '%' : '-'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Memory</span>
                            <span class="metric-value">${app.memory_mb ? app.memory_mb.toFixed(1) + ' MB' : '-'}</span>
                        </div>
                        <div class="metric">
                            <span class="metric-label">Uptime</span>
                            <span class="metric-value">${formatUptime(app.uptime_sec)}</span>
                        </div>
                    </div>
                    ${app.health_status ? `
                        <div class="health-status health-${app.health_status}">
                            Health: ${app.health_status}
                        </div>
                    ` : ''}
                ` : `
                    <div class="app-metrics">
                        <div class="metric">
                            <span class="metric-label">Port</span>
                            <span class="metric-value">${app.port || '-'}</span>
                        </div>
                        ${app.url ? `
                            <div class="metric">
                                <span class="metric-label">URL</span>
                                <span class="metric-value">
                                    <a href="${app.url}" target="_blank" onclick="event.stopPropagation()">
                                        ${app.port || 'N/A'}
                                    </a>
                                </span>
                            </div>
                        ` : ''}
                    </div>
                `}
            </div>

            <div class="app-actions">
                ${app.running ? `
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); stopApp('${app.id}')">■ Stop</button>
                    <button class="btn btn-sm btn-warning" onclick="event.stopPropagation(); restartApp('${app.id}')">↻ Restart</button>
                    ${app.url ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation(); openUrl('${app.url}')">🌐 Open</button>` : ''}
                ` : `
                    <button class="btn btn-sm btn-success" onclick="event.stopPropagation(); startApp('${app.id}')">▶ Start</button>
                `}
                <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); viewLogs('${app.id}')">📋 Logs</button>
            </div>
        </div>
    `;
}

function updateSystemStats(stats) {
    const cpuUsage = document.getElementById('cpu-usage');
    const cpuBar = document.getElementById('cpu-bar');
    const memUsage = document.getElementById('mem-usage');
    const memBar = document.getElementById('mem-bar');
    const diskUsage = document.getElementById('disk-usage');
    const diskBar = document.getElementById('disk-bar');
    const appUptime = document.getElementById('app-uptime');

    if (cpuUsage) cpuUsage.textContent = stats.cpu_percent.toFixed(1) + '%';
    if (cpuBar) cpuBar.style.width = stats.cpu_percent + '%';
    if (memUsage) memUsage.textContent = stats.memory_percent.toFixed(1) + '%';
    if (memBar) memBar.style.width = stats.memory_percent + '%';
    if (diskUsage) diskUsage.textContent = stats.disk_usage_percent.toFixed(1) + '%';
    if (diskBar) diskBar.style.width = stats.disk_usage_percent + '%';
    if (appUptime) appUptime.textContent = formatUptime(stats.uptime_seconds);
}

function updateOverallStatus() {
    const cards = document.querySelectorAll('.app-card.running');
    const runningCount = document.getElementById('running-count');
    if (runningCount) runningCount.textContent = cards.length;
}

// Modal functions
function showLogModal(appId, logs) {
    // Remove existing modal
    const existing = document.querySelector('.modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content modal-xl">
            <div class="modal-header">
                <h3>📋 Logs: ${escapeHtml(appId)}</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <div class="modal-body">
                <pre class="log-content">${escapeHtml(logs.join('\n'))}</pre>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Close on background click
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.remove();
        }
    });

    // Close on escape key
    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
            modal.remove();
            document.removeEventListener('keydown', escHandler);
        }
    });
}

function showSessionsModal(appId, sessions) {
    const existing = document.querySelector('.modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content modal-lg">
            <div class="modal-header">
                <h3>Sessions: ${escapeHtml(appId)}</h3>
                <button class="modal-close" onclick="this.closest('.modal').remove()">×</button>
            </div>
            <div class="modal-body">
                ${sessions.length === 0 ? '<p>No sessions recorded</p>' : `
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Started</th>
                                <th>Ended</th>
                                <th>Duration</th>
                                <th>Exit</th>
                                <th>Crash</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sessions.map(s => `
                                <tr>
                                    <td>${formatDateTime(s.started_at)}</td>
                                    <td>${s.stopped_at ? formatDateTime(s.stopped_at) : 'Running'}</td>
                                    <td>${s.duration_sec ? formatDuration(s.duration_sec) : '-'}</td>
                                    <td>${s.exit_code ?? '-'}</td>
                                    <td>${s.crash_detected ? 'Yes' : 'No'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    modal.addEventListener('click', function(e) {
        if (e.target === modal) modal.remove();
    });
}

// Utility functions
function openUrl(url) {
    window.open(url, '_blank');
}

function getAppIcon(type) {
    const icons = {
        'desktop': '🖥️',
        'web': '🌐',
        'api': '⚙️',
        'background': '🔄',
        'external': '🔗',
        'mcp': '🔌'
    };
    return icons[type] || '📦';
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
    const d = new Date(timestamp);
    return d.toLocaleString();
}

function formatTime(timestamp) {
    if (!timestamp) return '-';
    const d = new Date(timestamp);
    return d.toLocaleTimeString();
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

// Notification system
function showNotification(type, message) {
    // Remove existing notification
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `<span>${escapeHtml(message)}</span>`;
    document.body.appendChild(notification);

    // Trigger animation
    setTimeout(() => notification.classList.add('show'), 10);

    // Auto remove
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// HTMX event handlers
if (typeof htmx !== 'undefined') {
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        if (evt.detail.target && evt.detail.target.id === 'apps-grid') {
            updateOverallStatus();
        }
    });
}