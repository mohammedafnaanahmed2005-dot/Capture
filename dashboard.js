/**
 * VisionAI Dashboard — JavaScript
 * Handles Socket.IO feed, Chart.js graphs, and UI interactions
 */

'use strict';

// ─── Color Palette (matches Python detector) ───────────────────────────────
const CLASS_COLORS = {
  'book':       '#00ff94',
  'person':     '#0ea5e9',
  'face':       '#f97316',
  'remote':     '#a855f7',
  'cell phone': '#ec4899',
  'keyboard':   '#fbbf24',
  'mouse':      '#14b8a6',
  'laptop':     '#fb923c',
  'backpack':   '#84cc16',
  'handbag':    '#f472b6',
  'scissors':   '#60a5fa',
  'bottle':     '#34d399',
  'cup':        '#facc15',
  'hand':       '#e879f9',
  'body':       '#38bdf8',
};

function getColor(label) {
  return CLASS_COLORS[label] || '#8899bb';
}

function hexToRgba(hex, alpha = 1) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ─── State ─────────────────────────────────────────────────────────────────
let stats = { total_counts: {}, timeline: [], line_data: { labels: [], datasets: {} } };
let logRows = [];
let chartInstances = {};

// ─── Socket.IO Connection ──────────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
  setStatus('online', 'Connected', 'Live Stream');
  showToast('Connected to VisionAI stream', 'success');
});

socket.on('disconnect', () => {
  setStatus('error', 'Disconnected', '—');
  showToast('Stream disconnected', 'error');
});

socket.on('frame', (data) => {
  updateFeed(data);
  updateSidebarStats(data);
  updateDetectionTags(data.detections);
  appendLogRows(data.detections);
});

// ─── Live Feed ─────────────────────────────────────────────────────────────
function updateFeed(data) {
  const img = document.getElementById('videoFeed');
  const overlay = document.getElementById('videoOverlay');

  if (data.frame) {
    img.src = 'data:image/jpeg;base64,' + data.frame;
    overlay.classList.add('hidden');
  }

  document.getElementById('feedFpsBadge').textContent = `${data.fps} FPS`;
  document.getElementById('kpiFPSVal').textContent = data.fps;
  document.getElementById('kpiFramesVal').textContent = formatNum(data.frame_count);
  document.getElementById('sidebarFPS').textContent = data.fps;
  document.getElementById('sidebarFrames').textContent = formatNum(data.frame_count);
}

function updateSidebarStats(data) {
  // Objects in current frame
  document.getElementById('sidebarObjects').textContent = data.detections.length;
}

// ─── Detection Tags ─────────────────────────────────────────────────────────
function updateDetectionTags(detections) {
  const container = document.getElementById('detectionTags');
  container.innerHTML = '';

  const counts = {};
  detections.forEach(d => { counts[d.label] = (counts[d.label] || 0) + 1; });

  Object.entries(counts).forEach(([label, count]) => {
    const color = getColor(label);
    const tag = document.createElement('span');
    tag.className = 'det-tag';
    tag.textContent = `${label} ×${count}`;
    tag.style.background = hexToRgba(color, 0.1);
    tag.style.color = color;
    tag.style.border = `1px solid ${hexToRgba(color, 0.3)}`;
    container.appendChild(tag);
  });
}

// ─── Stats Polling ──────────────────────────────────────────────────────────
function fetchStats() {
  fetch('/api/stats')
    .then(r => r.json())
    .then(data => {
      stats = data;
      updateKPIs(data);
      updateCountsList(data.total_counts);
      updateCharts(data);
    })
    .catch(console.error);
}

setInterval(fetchStats, 2000);
fetchStats();

// ─── KPIs ───────────────────────────────────────────────────────────────────
function updateKPIs(data) {
  document.getElementById('kpiTotalVal').textContent = formatNum(data.total_objects || 0);
  document.getElementById('kpiClassesVal').textContent = Object.keys(data.total_counts || {}).length;
  document.getElementById('activeCountBadge').textContent =
    Object.keys(data.total_counts || {}).length + ' Types';
}

// ─── Counts List ─────────────────────────────────────────────────────────────
function updateCountsList(counts) {
  const list = document.getElementById('countsList');

  if (!counts || !Object.keys(counts).length) {
    list.innerHTML = `<div class="counts-empty">
      <svg viewBox="0 0 48 48" fill="none" width="48" height="48">
        <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="2" opacity="0.3"/>
        <path d="M15 24h18M24 15v18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg><p>No detections yet</p></div>`;
    return;
  }

  const total = Object.values(counts).reduce((a,b) => a+b, 0);
  const sorted = Object.entries(counts).sort((a,b) => b[1]-a[1]);
  const max = sorted[0]?.[1] || 1;

  list.innerHTML = sorted.map(([label, count]) => {
    const color = getColor(label);
    const pct = ((count / max) * 100).toFixed(0);
    return `<div class="count-row">
      <div class="count-dot" style="background:${color};box-shadow:0 0 6px ${color}"></div>
      <div class="count-label">${label}</div>
      <div class="count-bar-wrap">
        <div class="count-bar" style="width:${pct}%;background:${color}"></div>
      </div>
      <div class="count-num" style="color:${color}">${formatNum(count)}</div>
    </div>`;
  }).join('');
}

// ─── Charts ──────────────────────────────────────────────────────────────────
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: { color: '#8899bb', font: { family: 'Inter', size: 11 }, boxWidth: 12, padding: 14 }
    },
    tooltip: {
      backgroundColor: '#111827',
      borderColor: 'rgba(255,255,255,0.08)',
      borderWidth: 1,
      titleColor: '#f0f4ff',
      bodyColor: '#8899bb',
      padding: 10,
      cornerRadius: 8,
    }
  },
  animation: { duration: 400, easing: 'easeInOutQuart' },
};

function updateCharts(data) {
  updateMiniBar(data.total_counts);
  updatePie(data.total_counts, 'pieChart');
  updateLine(data.line_data, 'lineChart');

  // Analytics panel charts
  updateBar(data.total_counts, 'barChartFull');
  updatePie(data.total_counts, 'pieChartFull');
  updateLine(data.line_data, 'lineChartFull');
}

// Mini bar in counts card
function updateMiniBar(counts) {
  const canvas = document.getElementById('miniBarChart');
  const ctx = canvas.getContext('2d');

  if (!counts || !Object.keys(counts).length) return;

  const labels = Object.keys(counts);
  const values = Object.values(counts);
  const colors = labels.map(getColor);

  if (chartInstances['miniBar']) {
    chartInstances['miniBar'].data.labels = labels;
    chartInstances['miniBar'].data.datasets[0].data = values;
    chartInstances['miniBar'].data.datasets[0].backgroundColor = colors.map(c => hexToRgba(c,0.7));
    chartInstances['miniBar'].data.datasets[0].borderColor = colors;
    chartInstances['miniBar'].update('none');
    return;
  }

  chartInstances['miniBar'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Count',
        data: values,
        backgroundColor: colors.map(c => hexToRgba(c,0.7)),
        borderColor: colors,
        borderWidth: 1,
        borderRadius: 4,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } },
      scales: {
        x: { ticks: { color: '#8899bb', font: { size: 9 } }, grid: { display: false } },
        y: { ticks: { color: '#8899bb', font: { size: 9 } }, grid: { color: 'rgba(255,255,255,0.04)' } }
      }
    }
  });
}

// Pie chart
function updatePie(counts, canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (!counts || !Object.keys(counts).length) return;

  const labels = Object.keys(counts);
  const values = Object.values(counts);
  const colors = labels.map(getColor);

  const key = 'pie_' + canvasId;
  if (chartInstances[key]) {
    chartInstances[key].data.labels = labels;
    chartInstances[key].data.datasets[0].data = values;
    chartInstances[key].data.datasets[0].backgroundColor = colors.map(c => hexToRgba(c, 0.75));
    chartInstances[key].data.datasets[0].borderColor = colors;
    chartInstances[key].update('none');
    return;
  }

  chartInstances[key] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors.map(c => hexToRgba(c, 0.75)),
        borderColor: colors,
        borderWidth: 2,
        hoverOffset: 8,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      cutout: '62%',
      plugins: {
        ...CHART_DEFAULTS.plugins,
        legend: {
          position: 'right',
          labels: { color: '#8899bb', font: { family: 'Inter', size: 10 }, boxWidth: 10, padding: 10 }
        }
      }
    }
  });
}

// Line chart
function updateLine(lineData, canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (!lineData || !lineData.labels || lineData.labels.length === 0) return;

  const { labels, datasets } = lineData;
  const allLabels = Object.keys(datasets);

  const chartDatasets = allLabels.map(label => {
    const color = getColor(label);
    return {
      label,
      data: datasets[label],
      borderColor: color,
      backgroundColor: hexToRgba(color, 0.08),
      borderWidth: 2,
      fill: true,
      tension: 0.4,
      pointRadius: 2,
      pointHoverRadius: 5,
      pointBackgroundColor: color,
    };
  });

  const key = 'line_' + canvasId;
  if (chartInstances[key]) {
    chartInstances[key].data.labels = labels;
    chartInstances[key].data.datasets = chartDatasets;
    chartInstances[key].update('none');
    return;
  }

  chartInstances[key] = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: chartDatasets },
    options: {
      ...CHART_DEFAULTS,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          ticks: { color: '#8899bb', font: { size: 10 }, maxTicksLimit: 8 },
          grid: { color: 'rgba(255,255,255,0.03)' }
        },
        y: {
          ticks: { color: '#8899bb', font: { size: 10 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
          beginAtZero: true,
        }
      }
    }
  });
}

// Full bar chart for analytics panel
function updateBar(counts, canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (!counts || !Object.keys(counts).length) return;

  const sorted = Object.entries(counts).sort((a,b) => b[1]-a[1]);
  const labels = sorted.map(e => e[0]);
  const values = sorted.map(e => e[1]);
  const colors = labels.map(getColor);

  const key = 'bar_' + canvasId;
  if (chartInstances[key]) {
    chartInstances[key].data.labels = labels;
    chartInstances[key].data.datasets[0].data = values;
    chartInstances[key].data.datasets[0].backgroundColor = colors.map(c => hexToRgba(c,0.6));
    chartInstances[key].data.datasets[0].borderColor = colors;
    chartInstances[key].update('none');
    return;
  }

  chartInstances[key] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Total Detections',
        data: values,
        backgroundColor: colors.map(c => hexToRgba(c, 0.6)),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
        borderSkipped: false,
      }]
    },
    options: {
      ...CHART_DEFAULTS,
      plugins: { ...CHART_DEFAULTS.plugins, legend: { display: false } },
      scales: {
        x: {
          ticks: { color: '#8899bb', font: { size: 11 } },
          grid: { display: false }
        },
        y: {
          ticks: { color: '#8899bb', font: { size: 11 } },
          grid: { color: 'rgba(255,255,255,0.04)' },
          beginAtZero: true,
        }
      }
    }
  });
}

// ─── Detection Log ────────────────────────────────────────────────────────────
const MAX_LOG_ROWS = 200;

function appendLogRows(detections) {
  if (!detections || !detections.length) return;

  const now = new Date().toLocaleTimeString('en-GB');
  detections.forEach(det => {
    logRows.unshift({
      time: now,
      label: det.label,
      confidence: det.confidence,
      bbox: det.bbox,
    });
  });

  if (logRows.length > MAX_LOG_ROWS) logRows.splice(MAX_LOG_ROWS);

  const activePanel = document.querySelector('.panel.active');
  if (activePanel && activePanel.id === 'panel-log') renderLog();
}

function renderLog(filter = '') {
  const tbody = document.getElementById('logTableBody');
  const rows = filter
    ? logRows.filter(r => r.label.toLowerCase().includes(filter.toLowerCase()))
    : logRows;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="log-empty">No matching detections</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.slice(0, 100).map(r => {
    const color = getColor(r.label);
    const confPct = (r.confidence * 100).toFixed(1);
    const confStyle = r.confidence > 0.8 ? `color:${getColor(r.label)}` : 'color:#8899bb';
    const bbox = r.bbox ? `[${r.bbox.map(v=>Math.round(v)).join(', ')}]` : '—';
    return `<tr>
      <td style="color:#8899bb;font-family:var(--mono);font-size:11px">${r.time}</td>
      <td>
        <span style="display:inline-flex;align-items:center;gap:6px;">
          <span style="width:8px;height:8px;border-radius:50%;background:${color};box-shadow:0 0 5px ${color}"></span>
          <span style="font-weight:600;text-transform:capitalize">${r.label}</span>
        </span>
      </td>
      <td>
        <span class="log-conf" style="${confStyle};background:${hexToRgba(color,0.08)}">${confPct}%</span>
      </td>
      <td class="log-bbox">${bbox}</td>
      <td><span class="log-status">✓ Detected</span></td>
    </tr>`;
  }).join('');
}

function filterLog() {
  const val = document.getElementById('logSearch').value;
  renderLog(val);
}

function clearLog() {
  logRows = [];
  document.getElementById('logTableBody').innerHTML =
    `<tr><td colspan="5" class="log-empty">Log cleared</td></tr>`;
}

// ─── Navigation ──────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    const panel = item.dataset.panel;

    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));

    item.classList.add('active');
    document.getElementById(`panel-${panel}`).classList.add('active');

    const titles = { dashboard: 'Live Detection Feed', analytics: 'Analytics', log: 'Detection Log' };
    document.getElementById('pageTitle').textContent = titles[panel] || panel;

    if (panel === 'log') renderLog();
    if (panel === 'analytics') setTimeout(() => fetchStats(), 100);
  });
});

// ─── Actions ──────────────────────────────────────────────────────────────────
function resetData() {
  if (!confirm('Reset all detection data? This cannot be undone.')) return;
  fetch('/api/reset', { method: 'POST' })
    .then(r => r.json())
    .then(() => {
      stats = { total_counts: {}, timeline: [], line_data: { labels: [], datasets: {} } };
      logRows = [];
      Object.values(chartInstances).forEach(c => c.destroy());
      chartInstances = {};
      updateCountsList({});
      renderLog();
      showToast('Detection data has been reset', 'info');
    });
}

function exportData() {
  fetch('/api/export')
    .then(r => r.json())
    .then(data => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `visionai_export_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('Data exported successfully', 'success');
    });
}

// ─── Status Helpers ───────────────────────────────────────────────────────────
function setStatus(state, label, mode) {
  const dot = document.getElementById('statusDot');
  dot.className = 'status-dot ' + state;
  document.getElementById('statusLabel').textContent = label;
  document.getElementById('statusMode').textContent = mode;

  const badge = document.getElementById('feedModeBadge');
  if (mode && mode.toLowerCase().includes('sim')) {
    badge.textContent = 'Simulation';
    badge.className = 'badge badge-orange';
  } else {
    badge.textContent = 'YOLO v4';
    badge.className = 'badge badge-green';
  }
}

// Fetch & apply status mode
function fetchStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(d => {
      const modeStr = d.mode === 'simulation' ? 'Simulation Mode' : 'YOLO Live';
      setStatus('online', 'Live', modeStr);
    })
    .catch(() => {});
}
setInterval(fetchStatus, 5000);
fetchStatus();

// ─── Clock ────────────────────────────────────────────────────────────────────
function updateClock() {
  document.getElementById('timeDisplay').textContent =
    new Date().toLocaleTimeString('en-GB', { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ─── Toast ────────────────────────────────────────────────────────────────────
let toastTimer;
function showToast(msg, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = `toast ${type} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
}

// ─── Utility ──────────────────────────────────────────────────────────────────
function formatNum(n) {
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n/1_000).toFixed(1) + 'K';
  return String(n);
}
