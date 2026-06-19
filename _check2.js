// ==============================
// CHART.JS GLOBALS (Premium defaults)
// ==============================
(function() {
  function setChartDefaults() {
    if (typeof Chart === 'undefined') { setTimeout(setChartDefaults, 50); return; }
    Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
    Chart.defaults.font.size = 11;
    Chart.defaults.color = '#94A3B8';
    Chart.defaults.plugins.tooltip.backgroundColor = '#1A1F3D';
    Chart.defaults.plugins.tooltip.titleColor = '#F1F5F9';
    Chart.defaults.plugins.tooltip.bodyColor = '#94A3B8';
    Chart.defaults.plugins.tooltip.borderColor = '#283052';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.animation = { duration: 800, easing: 'easeOutQuart' };
  }
  setChartDefaults();
})();
// ==============================
// CONFIG & STATE
// ==============================
const API_BASE = '';

// Magic numbers — loaded live from the backend
let BOT_MAGIC = null;
let BOT_NAMES = {};

async function loadMagicNumbers() {
  try {
    const res = await fetch(`${API_BASE}/api/config/magic-numbers`);
    const data = await res.json();
    BOT_MAGIC = data;
    // Build reverse lookup: magic -> display name
    BOT_NAMES = {};
    for (const [name, magic] of Object.entries(data)) {
      BOT_NAMES[magic] = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }
    // Populate the Trade Journal bot filter
    populateBotFilter();
  } catch (err) {
    console.warn('Failed to load magic numbers, using fallback:', err);
    BOT_MAGIC = { gold_bot: 777555, scalping_bot: 999111, streaming_bot: 888222 };
    BOT_NAMES = { 777555: 'Gold Bot', 999111: 'Scalping Bot', 888222: 'Streaming Bot', 123456: 'AgentX' };
  }
}

function populateBotFilter() {
  const sel = document.getElementById('journalBot');
  if (!sel) return;
  sel.innerHTML = '<option value="all">All Bots</option>';
  if (BOT_MAGIC) {
    for (const [name, magic] of Object.entries(BOT_MAGIC)) {
      const displayName = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      sel.innerHTML += `<option value="${magic}">${displayName}</option>`;
    }
  }
  sel.innerHTML += '<option value="123456">AgentX</option>';
}

const NAV_ITEMS = {
  cmd: { title: 'Command Center', hash: '#cmd' }, pf: { title: 'Portfolio', hash: '#pf' },
  journal: { title: 'Trade Journal', hash: '#journal' }, backtest: { title: 'Backtesting Lab', hash: '#backtest' },
  bots: { title: 'Bot Control', hash: '#bots' }, scripts: { title: 'Script Editor', hash: '#scripts' },
  orchestrator: { title: 'AI Orchestrator', hash: '#orchestrator' }, accounts: { title: 'Account Manager', hash: '#accounts' },
  analytics: { title: 'Analytics', hash: '#analytics' }, settings: { title: 'Settings', hash: '#settings' },
  ftmo: { title: 'FTMO Challenge', hash: '#ftmo' },
  fileConverter: { title: 'File Converter', hash: '#fileConverter' }
};

const TICKER_SYMBOLS = [
  { symbol: 'XAUUSD', status: 'neutral' }, { symbol: 'EURUSD', status: 'neutral' }, { symbol: 'BTCUSD', status: 'neutral' }
];
let tickerPriceCache = {}; // { symbol: { bid, ask, prevBid, prevAsk, time } }

let charts = {}, refreshIntervals = {}, cachedData = {};
let activeAccountId = null;
let backendOnline = true;
let equityZoom = { min: null, max: null, currentMin: null, currentMax: null };
let currentScriptPath = null, currentScriptContent = null;
let xauTickerState = { prevBid: null, prevAsk: null, dayOpen: null, dayHigh: null, dayLow: null, weeklyData: [], lastDay: null };

// ==============================
// API
// ==============================
async function api(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', ...options.headers }
    });
    if (!res.ok) { const e = await res.text().catch(()=>''); throw new Error(`HTTP ${res.status}: ${e.slice(0,100)}`); }
    return await res.json();
  } catch (err) {
    console.error(`API Error [${endpoint}]:`, err);
    // Show toast for API failures so user knows something went wrong
    const msg = err.message || 'Unknown error';
    if (!msg.includes('404') && !msg.includes('NetworkError') && !msg.includes('Failed to fetch')) {
      // 4xx/5xx errors - show toast but don't mark backend offline
      try { toast(`API: ${endpoint} - ${msg.slice(0,60)}`, 'warning', 3000); } catch(e) {}
    }
    throw err;
  }
}

// ==============================
// GRACEFUL DEGRADATION
// ==============================
function renderGlobalBanner() {
  const bannerEl = document.getElementById('backendOfflineBanner');
  if (!bannerEl) return;
  if (!backendOnline) {
    bannerEl.style.display = 'block';
    bannerEl.innerHTML = `
      <div class="backend-offline-banner">
        <span class="banner-icon">⚠️</span>
        <div class="banner-msg">
          <div>Backend Offline</div>
          <div class="banner-sub">The trading backend server is unreachable. Some features may be unavailable. Data will refresh automatically when the backend recovers.</div>
        </div>
      </div>`;
  } else {
    bannerEl.style.display = 'none';
  }
}

async function performHealthCheck() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch('/api/health', { signal: controller.signal });
    clearTimeout(timeoutId);
    backendOnline = res.ok;
  } catch {
    backendOnline = false;
  }
  renderGlobalBanner();
}

// ==============================
// GLOBAL ERROR HANDLING
// ==============================
window.onerror = function(message, source, lineno, colno, error) {
  const display = document.getElementById('jsErrorDisplay');
  if (!display) return;
  display.style.display = 'block';
  const text = error ? error.stack || error.message : String(message);
  display.innerHTML = `<div class="js-error-box">⚠️ <span>Unhandled JS Error: ${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span></div>`;
  console.error('Global error:', message, source, lineno, colno, error);
  return false;
};

window.addEventListener('unhandledrejection', function(event) {
  const display = document.getElementById('jsErrorDisplay');
  if (!display) return;
  display.style.display = 'block';
  const text = event.reason ? (event.reason.stack || event.reason.message || String(event.reason)) : 'Unknown Promise rejection';
  display.innerHTML = `<div class="js-error-box">⚠️ <span>Unhandled Promise Rejection: ${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span></div>`;
  console.error('Unhandled rejection:', event.reason);
  event.preventDefault();
});

// ==============================
// TOAST
// ==============================
function toast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-msg">${message}</span>`;
  container.appendChild(el);
  setTimeout(() => { el.classList.add('toast-out'); setTimeout(() => el.remove(), 300); }, duration);
}

// ==============================
// MODALS
// ==============================
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// ==============================
// THEME
// ==============================
function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved ? saved === 'dark' : prefersDark;
  document.body.classList.toggle('dark', isDark); document.body.classList.toggle('light', !isDark);
  document.getElementById('themeToggle').textContent = isDark ? '☀️' : '🌙';
}

function toggleTheme() {
  const isDark = document.body.classList.contains('dark');
  document.body.classList.toggle('dark', !isDark); document.body.classList.toggle('light', isDark);
  localStorage.setItem('theme', isDark ? 'light' : 'dark');
  document.getElementById('themeToggle').textContent = isDark ? '🌙' : '☀️';
  Object.values(charts).forEach(c => { if (c && c.update) c.update(); });
}

// ==============================
// PARTICLES (Mesh Network)
// ==============================
function initParticles() {
  const canvas = document.getElementById('particle-canvas');
  const ctx = canvas.getContext('2d');
  let particles = [], w, h, mouse = { x: -9999, y: -9999 };
  const PARTICLE_COUNT = 70;
  const CONNECT_DIST = 140;
  const MOUSE_RADIUS = 180;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; });

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 2 + 1, a: Math.random() * 0.4 + 0.1
    });
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    const isDark = document.body.classList.contains('dark');

    // Update and draw particles
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      // Mouse attraction
      const dx = mouse.x - p.x, dy = mouse.y - p.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < MOUSE_RADIUS && dist > 0) {
        const force = (MOUSE_RADIUS - dist) / MOUSE_RADIUS * 0.2;
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
      }

      p.x += p.vx;
      p.y += p.vy;

      // Damping
      p.vx *= 0.99;
      p.vy *= 0.99;

      // Wrap around edges
      if (p.x < -20) p.x = w + 20;
      if (p.x > w + 20) p.x = -20;
      if (p.y < -20) p.y = h + 20;
      if (p.y > h + 20) p.y = -20;

      // Draw particle
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = isDark ? `rgba(0,212,170,${p.a * 0.6})` : `rgba(0,212,170,${p.a * 0.3})`;
      ctx.fill();

      // Draw connections
      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j];
        const dx2 = p.x - p2.x, dy2 = p.y - p2.y;
        const dist2 = Math.sqrt(dx2 * dx2 + dy2 * dy2);
        if (dist2 < CONNECT_DIST) {
          const alpha = (1 - dist2 / CONNECT_DIST) * 0.3;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.strokeStyle = isDark ? `rgba(0,212,170,${alpha * 0.3})` : `rgba(0,212,170,${alpha * 0.15})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }

      // Draw mouse connection
      if (dist < MOUSE_RADIUS && dist > 0) {
        const alpha = (1 - dist / MOUSE_RADIUS) * 0.4;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.strokeStyle = isDark ? `rgba(0,212,170,${alpha * 0.2})` : `rgba(0,212,170,${alpha * 0.1})`;
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
}

// ==============================
// COUNTER
// ==============================
function animateCounter(el, target, suffix = '', duration = 1200) {
  if (!el) return;
  const start = performance.now();
  function update(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = 0 + (target - 0) * eased;
    el.textContent = (target % 1 === 0 ? Math.round(current).toLocaleString() : current.toFixed(2)) + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

// ==============================
// ROUTING
// ==============================
function navigate(sectionId) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const navBtn = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  if (navBtn) navBtn.classList.add('active');
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(`section-${sectionId}`);
  if (target) target.classList.add('active');
  const info = NAV_ITEMS[sectionId];
  if (info) { document.getElementById('pageTitle').textContent = info.title; window.location.hash = info.hash; }
  document.getElementById('sidebar').classList.remove('open');
  loadSection(sectionId);
}

function loadSection(sectionId) {
  // When backend is offline, show offline message instead of trying to render data-driven sections
  if (!backendOnline) {
    const target = document.getElementById(`section-${sectionId}`);
    if (target) {
      // Find the first bento-grid or content div to inject offline state
      const contentArea = target.querySelector('.bento-grid') || target.querySelector('[id$="Content"]') || target;
      // Only inject if it's a container that would hold dynamic data
      if (contentArea && contentArea !== target) {
        contentArea.innerHTML = `
          <div class="offline-state col-span-12">
            <div class="offline-icon">🔌</div>
            <div class="offline-text">Backend Offline</div>
            <div class="offline-sub">The trading backend server is currently unreachable. Your data will automatically appear once the connection is restored.</div>
          </div>`;
      }
    }
    return;
  }
  switch (sectionId) {
    case 'cmd': renderCommandCenter(); break; case 'pf': renderPortfolio(); break;
    case 'journal': renderTradeJournal(); break; case 'backtest': renderBacktestDefaults(); break;
    case 'bots': renderBotControl(); break; case 'scripts': renderScriptEditor(); break;
    case 'orchestrator': renderOrchestrator(); break; case 'accounts': renderAccounts(); break;
    case 'analytics': renderAnalytics(); break; case 'settings': renderSettings(); break;
    case 'fileConverter': renderFileConverter(); break;
    case 'ftmo': renderFtmo(); break;
  }
}

function handleHash() {
  const hash = window.location.hash.slice(1) || 'cmd';
  for (const [key, val] of Object.entries(NAV_ITEMS)) { if (val.hash === `#${hash}` || key === hash) { navigate(key); return; } }
  navigate('cmd');
}

// ==============================
// TICKER & BRIDGE
// ==============================
function initTicker() {
  document.getElementById('ticker').innerHTML = TICKER_SYMBOLS.map(s =>
    `<span class="ticker-item" id="ticker-${s.symbol}"><span class="ticker-dot dot-${s.symbol} neutral"></span><span class="ticker-sym">${s.symbol}</span> <span class="ticker-price" id="tprice-${s.symbol}">--.--</span></span>`
  ).join('');
  updateTickerPrices();
  setInterval(updateTickerPrices, 10000);
}

async function updateTickerPrices() {
  for (const s of TICKER_SYMBOLS) {
    try {
      const data = await api(`/api/bridge/accounts/default/tick/${s.symbol}`);
      if (!data || (!data.bid && data.bid !== 0)) continue;
      const cached = tickerPriceCache[s.symbol] || {};
      const direction = cached.prevBid !== undefined
        ? (data.bid > cached.prevBid ? 'up' : data.bid < cached.prevBid ? 'down' : 'flat')
        : 'neutral';
      tickerPriceCache[s.symbol] = { bid: data.bid, ask: data.ask, prevBid: cached.bid, prevAsk: cached.ask, time: data.time };
      const priceEl = document.getElementById(`tprice-${s.symbol}`);
      const dotEl = document.getElementById(`ticker-${s.symbol}`).querySelector('.ticker-dot');
      if (priceEl) priceEl.textContent = `${data.bid.toFixed(data.bid < 100 ? 5 : 2)}/${data.ask.toFixed(data.ask < 100 ? 5 : 2)}`;
      if (dotEl) { dotEl.className = `ticker-dot dot-${s.symbol} ${direction}`; }
    } catch(e) {
      const dotEl = document.getElementById(`ticker-${s.symbol}`).querySelector('.ticker-dot');
      if (dotEl) dotEl.className = `ticker-dot dot-${s.symbol} neutral`;
    }
  }
}

async function updateBridgeStatus() {
  try {
    const health = await api('/api/health');
    const dot = document.getElementById('bridgeDot'); const text = document.getElementById('bridgeText');
    if (health.bridge && health.bridge.connected) {
      dot.className = 'bridge-dot'; text.textContent = `Bridge: Online · ${health.version || 'v1.0'}`;
    } else { dot.className = 'bridge-dot disconnected'; text.textContent = 'Bridge: Offline'; }
  } catch { document.getElementById('bridgeDot').className = 'bridge-dot disconnected'; document.getElementById('bridgeText').textContent = 'Bridge: Offline'; }
}

async function updateActiveAccount() {
  try {
    const data = await api('/api/accounts/active');
    if (data.active_account_id) {
      activeAccountId = data.active_account_id;
      document.getElementById('activeAccountName').textContent = data.account?.name || data.active_account_id;
    } else {
      activeAccountId = 'default';
      document.getElementById('activeAccountName').textContent = 'default';
    }
  } catch { activeAccountId = 'default'; document.getElementById('activeAccountName').textContent = 'default'; }
}

// ==============================
// COMMAND CENTER
// ==============================
async function renderCommandCenter() {
  try {
    const accountId = activeAccountId || 'default';
    const stats = await api(`/api/bridge/accounts/${accountId}/stats?days=30`);
    cachedData.stats = stats;
    if (stats.total_trades !== undefined) animateCounter(document.getElementById('statTotalTrades'), stats.total_trades);
    if (stats.win_rate !== undefined) animateCounter(document.getElementById('statWinRate'), stats.win_rate, '%');
    if (stats.net_profit !== undefined) {
      const el = document.getElementById('statNetProfit'); animateCounter(el, stats.net_profit, '');
      el.className = `stat-value ${stats.net_profit >= 0 ? 'up' : 'down'}`;
    }
    if (stats.profit_factor !== undefined) animateCounter(document.getElementById('statProfitFactor'), stats.profit_factor, '');
    renderEquityChart(); renderWinLossChart(stats); renderPLDistChart(); renderTradeTypeChart(); renderRadarChart(stats);
    renderCmdBots(); renderCmdAgents();
    // Render XAUUSD ticker widget
    renderXauTicker();
  } catch (err) {
    toast('Failed to load Command Center', 'error');
    ['statTotalTrades','statWinRate','statNetProfit','statProfitFactor'].forEach(id => {
      const el = document.getElementById(id); if (el) el.innerHTML = '<span class="text-muted text-sm">No data</span>';
    });
  }
}

async function renderEquityChart() {
  try {
    const accountId = activeAccountId || 'default';
    const data = await api(`/api/bridge/accounts/${accountId}/equity?days=30`);
    cachedData.equity = data;
    if (!data || data.length === 0) {
      document.querySelector('#cmdEquityChart .chart-container').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📉</div><div class="empty-state-text">No equity data</div></div>';
      return;
    }
    const labels = data.map(d => { const t = new Date(d.time); return t.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); });
    const values = data.map(d => d.equity);
    const ctx = document.getElementById('equityChart').getContext('2d');
    if (charts.equity) { charts.equity.destroy(); }

    // Apply zoom range if set
    let slicedLabels = labels, slicedValues = values;
    if (equityZoom.currentMin !== null && equityZoom.currentMax !== null) {
      const idxMin = Math.max(0, Math.floor((labels.length - 1) * equityZoom.currentMin));
      const idxMax = Math.min(labels.length - 1, Math.floor((labels.length - 1) * equityZoom.currentMax));
      slicedLabels = labels.slice(idxMin, idxMax + 1);
      slicedValues = values.slice(idxMin, idxMax + 1);
    }

    const isDark = document.body.classList.contains('dark');
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(0,212,170,0.3)'); gradient.addColorStop(1, 'rgba(0,212,170,0.01)');

    charts.equity = new Chart(ctx, {
      type: 'line',
      data: { labels: slicedLabels, datasets: [{ label: 'Equity', data: slicedValues, borderColor: '#00d4aa', backgroundColor: gradient, fill: true, tension: 0.3, pointRadius: 2, pointHoverRadius: 6, pointBackgroundColor: '#00d4aa', borderWidth: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: isDark ? '#1E293B' : '#FFFFFF', titleColor: isDark ? '#F1F5F9' : '#0F172A', bodyColor: isDark ? '#94A3B8' : '#475569', borderColor: isDark ? '#334155' : '#E2E8F0', borderWidth: 1, cornerRadius: 8, padding: 12 }
        },
        scales: {
          x: { grid: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.05)', drawBorder: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', maxTicksLimit: 10 } },
          y: { grid: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.05)', drawBorder: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', callback: v => '$' + v.toLocaleString() } }
        }
      }
    });
  } catch (err) {
    console.error('Equity chart error:', err);
    document.querySelector('#cmdEquityChart .chart-container').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📉</div><div class="empty-state-text">Failed to load</div></div>';
  }
}

// Equity chart zoom/pan controls
function zoomEquityChart(dir) {
  const range = equityZoom.currentMax !== null ? equityZoom.currentMax - equityZoom.currentMin : 1;
  const center = equityZoom.currentMin !== null ? (equityZoom.currentMin + equityZoom.currentMax) / 2 : 0.5;
  const factor = dir > 0 ? 0.7 : 1.3; // zoom in reduces range, zoom out increases
  let newRange = Math.min(Math.max(range * factor, 0.1), 1);
  let newMin = Math.max(0, center - newRange / 2);
  let newMax = Math.min(1, center + newRange / 2);
  if (newMax - newMin < 0.05) { newMin = Math.max(0, center - 0.025); newMax = Math.min(1, center + 0.025); }
  equityZoom.currentMin = newMin; equityZoom.currentMax = newMax;
  renderEquityChart();
}

function panEquityChart(dir) {
  const range = (equityZoom.currentMax !== null ? equityZoom.currentMax - equityZoom.currentMin : 1);
  const step = range * 0.2;
  let newMin = Math.max(0, (equityZoom.currentMin || 0) + (dir > 0 ? step : -step));
  let newMax = Math.min(1, newMin + range);
  if (newMax - newMin < range) newMin = newMax - range;
  if (newMin < 0) { newMin = 0; newMax = Math.min(1, range); }
  equityZoom.currentMin = newMin; equityZoom.currentMax = newMax;
  renderEquityChart();
}

function resetEquityZoom() { equityZoom.currentMin = null; equityZoom.currentMax = null; renderEquityChart(); }

function renderWinLossChart(stats) {
  const wins = stats.wins || 0, losses = stats.losses || 0, total = wins + losses || 1;
  const ctx = document.getElementById('winLossChart').getContext('2d');
  if (charts.winLoss) charts.winLoss.destroy();
  const isDark = document.body.classList.contains('dark');
  charts.winLoss = new Chart(ctx, {
    type: 'doughnut',
    data: { labels: ['Wins', 'Losses'], datasets: [{ data: [wins, losses], backgroundColor: ['#22C55E', '#EF4444'], borderWidth: 0, hoverOffset: 8 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: '65%', animation: { animateRotate: true, duration: 1000 }, plugins: { legend: { position: 'bottom', labels: { color: isDark ? '#94A3B8' : '#475569', padding: 12, usePointStyle: true, font: { size: 11 } } }, tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed} (${((ctx.parsed/total)*100).toFixed(1)}%)` } } } }
  });
}

async function renderPLDistChart() {
  try {
    const accountId = activeAccountId || 'default';
    const history = await api(`/api/bridge/accounts/${accountId}/history?days=30`);
    cachedData.history = history;
    if (!history || history.length === 0) { document.querySelector('#cmdPLDist .chart-container').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📊</div><div class="empty-state-text">No trade history</div></div>'; return; }
    const daily = {};
    history.forEach(t => { const d = new Date(t.close_time || t.open_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); daily[d] = (daily[d] || 0) + (t.net_profit || t.profit || 0); });
    const labels = Object.keys(daily), values = Object.values(daily);
    const colors = values.map(v => v >= 0 ? '#22C55E' : '#EF4444');
    const ctx = document.getElementById('plDistChart').getContext('2d');
    if (charts.plDist) charts.plDist.destroy();
    const isDark = document.body.classList.contains('dark');
    charts.plDist = new Chart(ctx, {
      type: 'bar', data: { labels, datasets: [{ label: 'Daily P&L', data: values, backgroundColor: colors, borderRadius: 3, borderSkipped: false }] },
      options: { responsive: true, maintainAspectRatio: false, animation: { duration: 800, easing: 'easeOutBounce' }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => '$' + ctx.parsed.y.toFixed(2) } } }, scales: { x: { grid: { display: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', maxTicksLimit: 12 } }, y: { grid: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.05)', drawBorder: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', callback: v => '$' + v } } } }
    });
  } catch (err) { console.error('P&L chart error:', err); }
}

async function renderTradeTypeChart() {
  try {
    const accountId = activeAccountId || 'default';
    const history = cachedData.history || await api(`/api/bridge/accounts/${accountId}/history?days=30`);
    cachedData.history = history;
    if (!history || history.length === 0) return;
    let buys = 0, sells = 0;
    history.forEach(t => {
      const type = (t.type || '').toUpperCase();
      if (type === 'BUY') buys++; else if (type === 'SELL') sells++;
    });
    if (buys === 0 && sells === 0) { history.forEach(t => { if (t.comment && t.comment.toLowerCase().includes('buy')) buys++; else if (t.comment && t.comment.toLowerCase().includes('sell')) sells++; else buys++; }); }
    const total = buys + sells || 1;
    const ctx = document.getElementById('tradeTypeChart').getContext('2d');
    if (charts.tradeType) charts.tradeType.destroy();
    const isDark = document.body.classList.contains('dark');
    charts.tradeType = new Chart(ctx, {
      type: 'doughnut', data: { labels: ['BUY', 'SELL'], datasets: [{ data: [buys || 1, sells || 1], backgroundColor: ['#06B6D4', '#F59E0B'], borderWidth: 0, hoverOffset: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '65%', animation: { animateRotate: true, duration: 1000 }, plugins: { legend: { position: 'bottom', labels: { color: isDark ? '#94A3B8' : '#475569', padding: 12, usePointStyle: true, font: { size: 11 } } }, tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed} (${((ctx.parsed/total)*100).toFixed(1)}%)` } } } }
    });
  } catch (err) { console.error('Trade type chart error:', err); }
}

function renderRadarChart(stats) {
  const ctx = document.getElementById('radarChart').getContext('2d');
  if (charts.radar) charts.radar.destroy();
  const isDark = document.body.classList.contains('dark');
  const winRate = (stats.win_rate || 0) / 100;
  const pf = Math.min((stats.profit_factor || 0) / 5, 1);
  const avgTrade = Math.min(Math.abs(stats.avg_profit || 0) / 200, 1);
  const consistency = (stats.wins && stats.losses && (stats.wins + stats.losses) > 0) ? stats.wins / (stats.wins + stats.losses) : 0.5;
  const grossScore = Math.min(Math.abs(stats.gross_profit || 0) / (Math.abs(stats.gross_profit || 1) + Math.abs(stats.gross_loss || 1)), 1);
  charts.radar = new Chart(ctx, {
    type: 'radar', data: { labels: ['Win Rate', 'Profit Factor', 'Avg Trade', 'Consistency', 'Gross Score'], datasets: [{ label: 'Performance', data: [winRate, pf, avgTrade, consistency, grossScore], backgroundColor: 'rgba(0,212,170,0.15)', borderColor: '#00d4aa', borderWidth: 2, pointBackgroundColor: '#00d4aa', pointBorderColor: '#fff', pointBorderWidth: 1, pointRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: { duration: 1000, easing: 'easeOutQuart' }, plugins: { legend: { display: false } }, scales: { r: { grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }, angleLines: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' }, pointLabels: { color: isDark ? '#94A3B8' : '#475569', font: { size: 11 } }, ticks: { display: false }, min: 0, max: 1 } } }
  });
}

// ==============================
// XAUUSD TICKER WIDGET
// ==============================
async function renderXauTicker() {
  const accountId = activeAccountId || 'default';
  try {
    const tick = await api(`/api/bridge/accounts/${accountId}/tick/XAUUSD`);
    if (!tick || tick.bid === undefined) return;
    const bid = tick.bid, ask = tick.ask;
    const prevBid = xauTickerState.prevBid;
    const prevAsk = xauTickerState.prevAsk;
    // Reset day stats if it's a new day
    if (xauTickerState.lastDay) {
      const today = new Date().toDateString();
      if (xauTickerState.lastDay !== today) {
        xauTickerState.dayOpen = bid;
        xauTickerState.dayHigh = bid;
        xauTickerState.dayLow = bid;
      }
    }
    xauTickerState.lastDay = new Date().toDateString();
    const bidEl = document.getElementById('xauBid');
    const askEl = document.getElementById('xauAsk');
    if (bidEl) {
      bidEl.textContent = bid.toFixed(2);
      if (prevBid !== null) {
        if (bid > prevBid) { bidEl.style.color = 'var(--profit)'; bidEl.style.textShadow = '0 0 20px var(--profit-glow)'; }
        else if (bid < prevBid) { bidEl.style.color = 'var(--loss)'; bidEl.style.textShadow = '0 0 20px var(--loss-glow)'; }
        else { bidEl.style.color = ''; bidEl.style.textShadow = ''; }
      }
    }
    if (askEl) {
      askEl.textContent = ask.toFixed(2);
      if (prevAsk !== null) {
        if (ask > prevAsk) { askEl.style.color = 'var(--profit)'; askEl.style.textShadow = '0 0 20px var(--profit-glow)'; }
        else if (ask < prevAsk) { askEl.style.color = 'var(--loss)'; askEl.style.textShadow = '0 0 20px var(--loss-glow)'; }
        else { askEl.style.color = ''; askEl.style.textShadow = ''; }
      }
    }
    xauTickerState.prevBid = bid;
    xauTickerState.prevAsk = ask;
    const timeEl = document.getElementById('xauTickerTime');
    if (timeEl && tick.time) {
      const t = new Date(tick.time);
      timeEl.textContent = t.toLocaleTimeString('en-US', { hour12: false }) + ' \u00b7 ' + t.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
    const spread = ((ask - bid) * 100).toFixed(1);
    const spreadEl = document.getElementById('xauSpread');
    if (spreadEl) spreadEl.textContent = 'Spread ' + spread;
    if (xauTickerState.dayOpen === null) {
      xauTickerState.dayOpen = bid;
      xauTickerState.dayHigh = bid;
      xauTickerState.dayLow = bid;
    }
    if (bid > xauTickerState.dayHigh) xauTickerState.dayHigh = bid;
    if (bid < xauTickerState.dayLow) xauTickerState.dayLow = bid;
    const dayChange = bid - xauTickerState.dayOpen;
    const dayChangePct = (dayChange / xauTickerState.dayOpen) * 100;
    const dayChangeEl = document.getElementById('xauDayChange');
    if (dayChangeEl) {
      const sign = dayChange >= 0 ? '+' : '';
      dayChangeEl.textContent = sign + dayChange.toFixed(2) + ' (' + sign + dayChangePct.toFixed(2) + '%)';
      dayChangeEl.className = 'stat-value' + (dayChange >= 0 ? ' up' : ' down');
      dayChangeEl.style.fontSize = '18px';
    }
    const dayRange = xauTickerState.dayHigh - xauTickerState.dayLow || 1;
    const dayLowEl = document.getElementById('xauDayLow');
    const dayHighEl = document.getElementById('xauDayHigh');
    if (dayLowEl) dayLowEl.textContent = xauTickerState.dayLow.toFixed(2);
    if (dayHighEl) dayHighEl.textContent = xauTickerState.dayHigh.toFixed(2);
    const rangeBar = document.getElementById('xauDayRangeBar');
    const priceMarker = document.getElementById('xauPriceMarker');
    if (rangeBar && priceMarker) {
      const pct = ((bid - xauTickerState.dayLow) / dayRange) * 100;
      rangeBar.style.width = '100%';
      rangeBar.style.background = 'linear-gradient(90deg, var(--loss) 0%, var(--warning) 50%, var(--profit) 100%)';
      priceMarker.style.left = Math.max(0, Math.min(100, pct)) + '%';
    }
    if (!xauTickerState.weeklyData || xauTickerState.weeklyData.length === 0) {
      await loadXauWeeklyChart(accountId);
    }
  } catch (err) {
    console.error('XAUUSD ticker error:', err);
  }
}

async function loadXauWeeklyChart(accountId) {
  try {
    const equityData = await api('/api/bridge/accounts/' + accountId + '/equity?days=7');
    if (!equityData || equityData.length === 0) return;
    xauTickerState.weeklyData = equityData;
    renderXauWeeklyChart();
  } catch (err) {
    console.error('Weekly chart load error:', err);
  }
}

function renderXauWeeklyChart() {
  const data = xauTickerState.weeklyData;
  if (!data || data.length === 0) return;
  const canvas = document.getElementById('xauWeeklyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (charts.xauWeekly) { charts.xauWeekly.destroy(); }
  const isDark = document.body.classList.contains('dark');
  const hasClose = data[0] && data[0].close !== undefined;
  const hasMid = data[0] && data[0].mid !== undefined;
  let labels, values;
  if (hasClose || hasMid) {
    labels = data.map(function(d) { var t = new Date(d.time || d.timestamp); return t.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }); });
    values = data.map(function(d) { return d.close || d.mid; });
  } else {
    labels = data.map(function(d) { var t = new Date(d.time || d.timestamp); return t.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }); });
    values = data.map(function(d) { return d.equity || d.value || d.price; });
  }
  if (labels.length === 0 || values.length === 0) return;
  var startVal = values[0];
  var endVal = values[values.length - 1];
  var change = endVal - startVal;
  var changePct = (change / startVal) * 100;
  var isUp = change >= 0;
  var labelEl = document.getElementById('xauWeeklyLabel');
  if (labelEl) {
    var sign = isUp ? '+' : '';
    labelEl.textContent = '\u00b7 ' + sign + change.toFixed(2) + ' (' + sign + changePct.toFixed(2) + '%) ' + (isUp ? '\ud83d\udcc8' : '\ud83d\udcc9');
    labelEl.style.color = isUp ? 'var(--profit)' : 'var(--loss)';
  }
  var lineColor = isUp ? '#22C55E' : '#EF4444';
  var fillColor = isUp ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)';
  charts.xauWeekly = new Chart(ctx, {
    type: 'line',
    data: { labels: labels, datasets: [{ label: 'XAUUSD', data: values, borderColor: lineColor, backgroundColor: fillColor, fill: true, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: isDark ? '#1E293B' : '#FFFFFF', titleColor: isDark ? '#F1F5F9' : '#0F172A', bodyColor: isDark ? '#94A3B8' : '#475569', borderColor: isDark ? '#334155' : '#E2E8F0', borderWidth: 1, cornerRadius: 6, padding: 8, callbacks: { label: function(ctx) { return '$' + ctx.parsed.y.toFixed(2); } } }
      },
      scales: {
        x: { display: true, grid: { display: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', maxTicksLimit: 3, font: { size: 9 } } },
        y: { display: true, grid: { color: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)', drawBorder: false }, ticks: { color: isDark ? '#64748B' : '#94A3B8', maxTicksLimit: 4, font: { size: 9 }, callback: function(v) { return '$' + v.toFixed(0); } } }
      }
    }
  });
}

async function renderCmdBots() {
  try {
    const bots = await api('/api/bots');
    cachedData.bots = bots;
    const container = document.getElementById('cmdBotsContent');
    const runningCount = document.getElementById('cmdRunningCount');
    const running = bots.filter(b => b.running).length;
    if (runningCount) runningCount.textContent = `${running} running`;
    if (!bots || bots.length === 0) { container.innerHTML = '<div class="empty-state-text text-sm">No bots running</div>'; return; }
    container.innerHTML = bots.map(b => `
      <div class="flex items-center justify-between" style="padding:8px 0;border-bottom:1px solid var(--border-color)">
        <div class="flex items-center gap-8">
          <span>🤖</span>
          <span class="font-bold">${b.display_name || b.name}</span>
          <span class="text-xs text-muted">${b.script ? b.script.split('/').pop() : ''}</span>
          ${b.pid ? `<span class="text-xs text-muted">PID:${b.pid}</span>` : ''}
        </div>
        <span class="badge ${b.running ? 'badge-running' : 'badge-stopped'}">${b.running ? '● Running' : '○ Stopped'}</span>
      </div>
    `).join('');
  } catch (err) { document.getElementById('cmdBotsContent').innerHTML = '<div class="text-muted text-sm">Unable to load bots</div>'; }
}

async function renderCmdAgents() {
  try {
    const data = await api('/api/orchestrator/agents');
    const agents = data.agents || data || [];
    cachedData.agents = agents;
    const container = document.getElementById('cmdAgentsContent');
    const badge = document.getElementById('agentCountBadge');
    if (!agents || agents.length === 0) { container.innerHTML = '<div class="text-muted text-sm">No AI agents active</div>'; if (badge) badge.textContent = '0 agents'; return; }
    if (badge) badge.textContent = `${agents.length} agents`;
    container.innerHTML = agents.slice(0, 4).map(a => `
      <div class="flex items-center justify-between" style="padding:6px 0;border-bottom:1px solid var(--border-color)">
        <div class="flex items-center gap-8">
          <span>🧠</span>
          <span class="font-bold text-sm">${a.name}</span>
          <span class="text-xs text-muted">${a.role || ''}</span>
        </div>
        <span class="badge ${a.status === 'active' || a.status === 'running' ? 'badge-active' : 'badge-idle'}">${a.status || 'idle'}</span>
      </div>
    `).join('');
    if (agents.length > 4) container.innerHTML += `<div class="text-xs text-muted mt-8 text-center">+${agents.length - 4} more agents</div>`;
  } catch (err) { document.getElementById('cmdAgentsContent').innerHTML = '<div class="text-muted text-sm">Unable to load agents</div>'; }
}

// ==============================
// PORTFOLIO
// ==============================
async function renderPortfolio() {
  const content = document.getElementById('pfAccountContent');
  const posContent = document.getElementById('pfPositionsContent');
  try {
    const accounts = await api('/api/accounts');
    const positions = await api('/api/positions');
    cachedData.accounts = accounts; cachedData.positions = positions;
    const accountId = activeAccountId || 'default';
    const acct = accounts && accounts.length > 0 ? accounts[0] : null;
    if (acct) {
      let detail = null;
      try { detail = await api(`/api/accounts/${accountId}`); } catch {}
      content.innerHTML = `
        <div class="flex flex-col gap-16">
          <div class="acct-info" style="display:flex;flex-wrap:wrap;gap:12px">
            <span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;background:var(--bg-secondary);border:1px solid var(--border-color)">🔑 ${acct.login || '5051185832'}</span>
            <span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;background:var(--bg-secondary);border:1px solid var(--border-color)">🖥️ ${acct.server || 'MetaQuotes-Demo'}</span>
            <span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;background:var(--bg-secondary);border:1px solid var(--border-color)">${acct.connected ? '🟢 Connected' : '🔴 Disconnected'}</span>
            ${detail ? `<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;background:var(--bg-secondary);border:1px solid var(--border-color)">💰 Balance: $${(detail.balance || 0).toLocaleString()}</span>` : ''}
            ${detail ? `<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;font-size:12px;font-weight:500;background:var(--bg-secondary);border:1px solid var(--border-color)">📈 Equity: $${(detail.equity || 0).toLocaleString()}</span>` : ''}
          </div>
          ${detail ? `
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px">
            <div><span class="text-xs text-muted">Balance</span><div class="font-bold text-lg">$${(detail.balance || 0).toLocaleString()}</div></div>
            <div><span class="text-xs text-muted">Equity</span><div class="font-bold text-lg">$${(detail.equity || 0).toLocaleString()}</div></div>
            <div><span class="text-xs text-muted">Margin</span><div class="font-bold text-lg">$${(detail.margin || 0).toLocaleString()}</div></div>
            <div><span class="text-xs text-muted">Free Margin</span><div class="font-bold text-lg">$${(detail.margin_free || 0).toLocaleString()}</div></div>
            <div><span class="text-xs text-muted">Margin Level</span><div class="font-bold text-lg">${(detail.margin_level || 0).toFixed(2)}%</div></div>
            <div><span class="text-xs text-muted">Leverage</span><div class="font-bold text-lg">1:${detail.leverage || 0}</div></div>
          </div>` : ''}
        </div>
      `;
    } else { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">💼</div><div class="empty-state-text">No accounts found</div></div>`; }
    if (positions && positions.length > 0) {
      posContent.innerHTML = `<div class="table-wrapper"><table><thead><tr><th>Symbol</th><th>Type</th><th>Volume</th><th>Entry</th><th>Current</th><th>Profit</th><th>Duration</th></tr></thead><tbody>${positions.map(p => `<tr><td class="font-bold">${p.symbol || '-'}</td><td><span class="badge ${(p.type||'').toUpperCase() === 'BUY' ? 'badge-active' : 'badge-idle'}">${p.type || '-'}</span></td><td>${p.volume || p.vol || '-'}</td><td>$${(p.entry_price || p.price_open || 0).toFixed(5)}</td><td>$${(p.current_price || p.price_current || 0).toFixed(5)}</td><td class="${(p.profit||0) >= 0 ? 'text-green' : 'text-red'} font-bold">$${(p.profit||0).toFixed(2)}</td><td class="text-muted">${p.duration || '-'}</td></tr>`).join('')}</tbody></table></div>`;
    } else { posContent.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📭</div><div class="empty-state-text">No open positions</div><div class="empty-state-sub">All positions have been closed</div></div>`; }
  } catch (err) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">💼</div><div class="empty-state-text">Failed to load portfolio</div></div>`; }
}

// ==============================
// TRADE JOURNAL (filtered)
// ==============================
async function renderTradeJournal() {
  const content = document.getElementById('journalContent');
  const countEl = document.getElementById('journalTradeCount');
  const days = document.getElementById('journalDays').value;
  const botMagic = document.getElementById('journalBot').value;
  const accountId = activeAccountId || 'default';
  try {
    let trades;
    if (botMagic !== 'all') {
      // Use the filter endpoint for specific bot
      trades = await api(`/api/trades/filter?days=${days}&magic=${botMagic}&account_id=${accountId}`);
    } else {
      trades = await api(`/api/bridge/accounts/${accountId}/history?days=${days}`);
    }
    const stats = cachedData.stats || await api(`/api/bridge/accounts/${accountId}/stats?days=${days}`);
    cachedData.history = trades;
    cachedData.stats = stats;
    countEl.textContent = `${(stats && stats.total_trades) || (trades ? trades.length : 0)} total trades`;

    if (!trades || trades.length === 0) {
      content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📓</div><div class="empty-state-text">No trades found for this filter</div></div>`;
      return;
    }
    content.innerHTML = `<div class="table-wrapper"><table><thead><tr><th>ID</th><th>Symbol</th><th>Type</th><th>Vol</th><th>Entry</th><th>Exit</th><th>Profit</th><th>Net</th><th>Bot</th><th>Open</th><th>Duration</th></tr></thead><tbody>${trades.slice(-100).reverse().map(t => {
      const botName = BOT_NAMES[t.magic] || (t.magic ? `Bot#${t.magic}` : '—');
      return `<tr>
        <td class="text-muted">${t.position_id || '—'}</td>
        <td class="font-bold">${t.symbol || '—'}</td>
        <td><span class="badge ${(t.type||'').toLowerCase().includes('buy') ? 'badge-active' : 'badge-idle'}">${t.type || '—'}</span></td>
        <td>${t.volume || '—'}</td>
        <td>$${(t.entry_price||0).toFixed(t.entry_price < 10 ? 5 : 2)}</td>
        <td>$${(t.exit_price||0).toFixed(t.exit_price < 10 ? 5 : 2)}</td>
        <td class="${(t.profit||0) >= 0 ? 'text-green' : 'text-red'} font-bold">$${(t.profit||0).toFixed(2)}</td>
        <td class="${(t.net_profit||0) >= 0 ? 'text-green' : 'text-red'} font-bold">$${(t.net_profit||0).toFixed(2)}</td>
        <td><span class="tag tag-accent">${botName}</span></td>
        <td class="text-muted">${t.open_time ? new Date(t.open_time).toLocaleDateString('en-US',{month:'short',day:'numeric'}) : '—'}</td>
        <td class="text-muted">${t.duration || '—'}</td>
      </tr>`;
    }).join('')}</tbody></table></div>${trades.length > 100 ? `<div class="text-xs text-muted mt-8">Showing latest 100 of ${trades.length} trades</div>` : ''}`;
  } catch (err) {
    content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📓</div><div class="empty-state-text">Failed to load trade history</div></div>`;
  }
}

// ==============================
// BACKTESTING LAB
// ==============================
function renderBacktestDefaults() {
  const now = new Date();
  const from = new Date(now); from.setMonth(from.getMonth() - 3);  // 3 months default — more reliable data availability
  document.getElementById('btDateFrom').value = from.toISOString().split('T')[0];
  document.getElementById('btDateTo').value = now.toISOString().split('T')[0];
  // Load sample strategy code
  document.getElementById('btCode').value = `# Sample: Golden Cross Strategy
class golden_cross_strategy:
    """EMA 9/21 crossover strategy for XAUUSD"""
    def __init__(self):
        self.fast_period = 9
        self.slow_period = 21

    def on_data(self, df):
        df['ema_fast'] = df['close'].ewm(span=self.fast_period).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period).mean()
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1
        df.loc[df['ema_fast'] <= df['ema_slow'], 'signal'] = -1
        return df`;
}

function updateSymbolInfo() {
  const sel = document.getElementById('btSymbol');
  const opt = sel.options[sel.selectedIndex];
  const source = opt.dataset.source || 'MT5';
  const el = document.getElementById('btSymbolInfo');
  if (source === 'Yahoo') {
    el.textContent = '📡 Yahoo Finance data (limited history)';
    el.style.color = '#F59E0B';
  } else {
    el.textContent = '📡 MT5 live data';
    el.style.color = '#94A3B8';
  }
}

async function runBacktest() {
  const code = document.getElementById('btCode').value.trim();
  if (!code) { toast('Please enter strategy code', 'warning'); return; }
  const symbol = document.getElementById('btSymbol').value;
  const timeframe = document.getElementById('btTimeframe').value;
  const date_from = document.getElementById('btDateFrom').value;
  const date_to = document.getElementById('btDateTo').value;
  const capital = parseFloat(document.getElementById('btCapital').value) || 10000;
  if (!date_from || !date_to) { toast('Select date range', 'warning'); return; }

  toast('Running backtest...', 'info', 60000);
  // Show loading state
  document.getElementById('btResults').innerHTML = '<div class="text-center py-16"><div class="text-2xl mb-8">⏳</div><div class="text-muted">Running backtest... analyzing ' + (date_to && date_from ? ((new Date(date_to) - new Date(date_from)) / (1000*60*60*24)).toFixed(0) + ' days' : '') + ' of data</div></div>';
  try {
    const result = await api('/api/backtest/custom', {
      method: 'POST',
      body: JSON.stringify({ code, symbol, timeframe, date_from, date_to, capital, ftmo_mode: true })
    });
    _lastBacktestResult = result;
    const m = result.metrics || {};
    
    // Helper to format values
    const fmt = (v, d=2) => (v || 0).toFixed(d);
    const pct = (v) => (v >= 0 ? '+' : '') + fmt(v) + '%';
    const usd = (v) => '$' + fmt(Math.abs(v), 2);
    const badge = (cond, t, f) => `<span class="badge ${cond ? 'badge-active' : 'badge-idle'}">${cond ? t : f}</span>`;
    
    document.getElementById('btResults').innerHTML = `
      <div class="mb-12">
        <div class="stat-label mb-4">📊 Performance Summary</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
          <div class="stat-card"><span class="stat-label">Total Return</span><span class="stat-value ${m.total_return_pct >= 0 ? 'up' : 'down'}">${pct(m.total_return_pct)}</span></div>
          <div class="stat-card"><span class="stat-label">Net Profit</span><span class="stat-value ${m.net_profit >= 0 ? 'up' : 'down'}">${m.net_profit >= 0 ? '+' : '-'}$${fmt(Math.abs(m.net_profit))}</span></div>
          <div class="stat-card"><span class="stat-label">Final Balance</span><span class="stat-value ${result.final_equity >= capital ? 'up' : 'down'}">$${fmt(result.final_equity)}</span></div>
          <div class="stat-card"><span class="stat-label">Sharpe Ratio</span><span class="stat-value ${m.sharpe_ratio >= 1 ? 'up' : m.sharpe_ratio >= 0 ? 'neutral' : 'down'}">${fmt(m.sharpe_ratio)}</span></div>
          <div class="stat-card"><span class="stat-label">Profit Factor</span><span class="stat-value ${m.profit_factor >= 1.5 ? 'up' : m.profit_factor >= 1 ? 'neutral' : 'down'}">${fmt(m.profit_factor)}</span></div>
          <div class="stat-card"><span class="stat-label">Max Drawdown</span><span class="stat-value down">${fmt(m.max_drawdown_pct)}%</span></div>
          <div class="stat-card"><span class="stat-label">Total Trades</span><span class="stat-value neutral">${m.total_trades || 0}</span></div>
          <div class="stat-card"><span class="stat-label">Win Rate</span><span class="stat-value ${m.win_rate_pct >= 50 ? 'up' : 'down'}">${fmt(m.win_rate_pct)}%</span></div>
          <div class="stat-card"><span class="stat-label">Loss Rate</span><span class="stat-value ${m.loss_rate_pct && m.loss_rate_pct < 50 ? 'up' : 'down'}">${fmt(m.loss_rate_pct)}%</span></div>
          <div class="stat-card"><span class="stat-label">R:R Ratio</span><span class="stat-value ${m.risk_reward_ratio >= 1.5 ? 'up' : 'neutral'}">${fmt(m.risk_reward_ratio)}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Win</span><span class="stat-value up">${usd(m.avg_win)}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Loss</span><span class="stat-value down">${usd(m.avg_loss)}</span></div>
          <div class="stat-card"><span class="stat-label">Expectancy</span><span class="stat-value ${m.expectancy >= 0 ? 'up' : 'down'}">${usd(m.expectancy)}/trade</span></div>
          <div class="stat-card"><span class="stat-label">Expectancy Ratio</span><span class="stat-value ${(m.expectancy_ratio||0) >= 0.5 ? 'up' : 'down'}">${fmt(m.expectancy_ratio)}</span></div>
          <div class="stat-card"><span class="stat-label">Best Trade</span><span class="stat-value up">${usd(m.best_trade)}</span></div>
          <div class="stat-card"><span class="stat-label">Worst Trade</span><span class="stat-value down">${usd(m.worst_trade)}</span></div>
          <div class="stat-card"><span class="stat-label">Calmar Ratio</span><span class="stat-value neutral">${fmt(m.calmar_ratio)}</span></div>
          <div class="stat-card"><span class="stat-label">Consec Wins</span><span class="stat-value up">${m.max_consecutive_wins || 0}</span></div>
          <div class="stat-card"><span class="stat-label">Consec Losses</span><span class="stat-value down">${m.max_consecutive_losses || 0}</span></div>
          <div class="stat-card"><span class="stat-label">Active Days</span><span class="stat-value neutral">${m.active_trading_days || 0}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Profit/Trade</span><span class="stat-value ${(m.avg_profit_per_trade||0) >= 0 ? 'up' : 'down'}">$${fmt(Math.abs(m.avg_profit_per_trade||0))}</span></div>
          <div class="stat-card"><span class="stat-label">Gross Profit</span><span class="stat-value up">${usd(m.gross_profit)}</span></div>
          <div class="stat-card"><span class="stat-label">Gross Loss</span><span class="stat-value down">${usd(m.gross_loss)}</span></div>
          <div class="stat-card"><span class="stat-label">Total Pips</span><span class="stat-value ${(m.total_pips||0) >= 0 ? 'up' : 'down'}">${(m.total_pips||0) >= 0 ? '+' : ''}${fmt(m.total_pips,1)}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Pips/Trade</span><span class="stat-value ${(m.avg_pips_per_trade||0) >= 0 ? 'up' : 'down'}">${(m.avg_pips_per_trade||0) >= 0 ? '+' : ''}${fmt(m.avg_pips_per_trade,1)}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Win Pips</span><span class="stat-value up">+${fmt(m.avg_win_pips,1)}</span></div>
          <div class="stat-card"><span class="stat-label">Avg Loss Pips</span><span class="stat-value down">-${fmt(m.avg_loss_pips,1)}</span></div>
        </div>
      </div>
      <div class="mb-12">
        <div class="stat-label mb-4">🏆 FTMO Challenge Assessment</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          ${result.ftmo ? \`
            <div class="stat-card col-span-2" style="border-left:3px solid \${result.ftmo.passed ? 'var(--profit)' : 'var(--loss)'}">
              <span class="stat-label">Phase 1</span>
              <span class="stat-value \${result.ftmo.passed ? 'up' : 'down'}">
                \${result.ftmo.passed ? '✅ PASSED' : '❌ FAILED'} 
                — DD: \${fmt(result.ftmo.max_drawdown_pct)}% / 10% max, 
                Profit: \${fmt(result.ftmo.profit_pct)}% / 10% target, 
                Days: \${result.ftmo.trading_days} / 10 min
              </span>
            </div>
          \` : ''}
          \${result.ftmo_phase2 ? \`
            <div class="stat-card col-span-2" style="border-left:3px solid \${result.ftmo_phase2.passed ? 'var(--profit)' : 'var(--loss)'}">
              <span class="stat-label">Phase 2</span>
              <span class="stat-value \${result.ftmo_phase2.passed ? 'up' : 'down'}">
                \${result.ftmo_phase2.passed ? '✅ PASSED' : '❌ FAILED'} 
                — DD: \${fmt(result.ftmo_phase2.max_drawdown_pct)}% / 5% max, 
                Profit: \${fmt(result.ftmo_phase2.profit_pct)}% / 5% target, 
                Days: \${result.ftmo_phase2.trading_days} / 10 min
              </span>
            </div>
          \` : ''}
        </div>
      </div>
      <div class="mb-12">
        <div class="stat-label mb-4">📋 Deploy Recommendation</div>
        <div class="stat-card" style="border-left:3px solid \${m.deploy_score >= 8 ? 'var(--profit)' : m.deploy_score >= 5 ? 'var(--warning)' : 'var(--loss)'}">
          <span class="stat-value" style="font-size:16px">\${m.deploy_verdict || 'N/A'} (Score: \${fmt(m.deploy_score, 1)}/10)</span>
          <div class="mt-8" style="font-size:12px;color:var(--text-secondary)">
            \${(m.deploy_details || []).map(f => '<div>' + f + '</div>').join('')}
          </div>
        </div>
      </div>
      \${result.trades && result.trades.length > 0 ? \`<div class="mt-16"><div class="stat-label mb-8">📝 Recent Trades (last 10)</div>
        <div class="table-wrapper compact-table" style="max-height:300px;overflow-y:auto">
          <table><thead><tr>
            <th>#</th><th>Side</th><th>Entry</th><th>Exit</th><th>Entry Price</th><th>Exit Price</th><th>Pips</th><th>P&L</th><th>Reason</th>
          </tr></thead><tbody>
          \${result.trades.slice(-10).map((t, i) => \`
            <tr>
              <td class="text-muted">\${result.trades.length - 10 + i + 1}</td>
              <td><span class="badge \${(t.side||'').toUpperCase() === 'BUY' ? 'badge-active' : 'badge-idle'}">\${t.side || '—'}</span></td>
              <td class="text-sm">\${(t.entry_time || '—').slice(0,16)}</td>
              <td class="text-sm">\${(t.exit_time || '—').slice(0,16)}</td>
              <td class="text-sm">\$\${fmt(t.entry_price, t.entry_price < 10 ? 5 : 2)}</td>
              <td class="text-sm">\$\${fmt(t.exit_price, t.exit_price < 10 ? 5 : 2)}</td>
              <td class="text-sm \${t.pnl_pips >= 0 ? 'text-green' : 'text-red'}">\${t.pnl_pips >= 0 ? '+' : ''}\${fmt(t.pnl_pips, 1)}</td>
              <td class="\${(t.pnl||0) >= 0 ? 'text-green' : 'text-red'} font-bold">\$\${fmt(Math.abs(t.pnl))}</td>
              <td><span class="text-xs text-muted">\${t.exit_reason || '—'}</span></td>
            </tr>\`).join('')}
          </tbody></table>
        </div></div>
      <div class="flex gap-8 mt-12">
        <button class="btn btn-sm" onclick="exportResultsCSV()">📥 Export CSV</button>
        <button class="btn btn-sm" onclick="exportResultsJSON()">📥 Export JSON</button>
      </div>
    \` : ''}
    `;
    // Render equity curve
    if (result.equity_curve && result.equity_curve.length > 0) {
      document.getElementById('btEquityContainer').style.display = 'block';
      const ctx = document.getElementById('btEquityChart').getContext('2d');
      if (charts.btEquity) charts.btEquity.destroy();
      const isDark = document.body.classList.contains('dark');
      const labels = result.equity_curve.map(e => e.time);
      const values = result.equity_curve.map(e => e.equity);
      // Calculate drawdown for fill coloring
      const peak = Math.max(...values);
      charts.btEquity = new Chart(ctx, {
        type: 'line',
        data: { 
          labels, 
          datasets: [{ 
            label: 'Equity', 
            data: values, 
            borderColor: '#00d4aa', 
            backgroundColor: function(context) {
              const chart = context.chart;
              const {ctx, chartArea} = chart;
              if (!chartArea) return 'rgba(0,212,170,0.1)';
              const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
              const finalEq = values[values.length - 1];
              if (finalEq >= capital) {
                gradient.addColorStop(0, 'rgba(0,212,170,0.25)');
                gradient.addColorStop(1, 'rgba(0,212,170,0.02)');
              } else {
                gradient.addColorStop(0, 'rgba(239,68,68,0.15)');
                gradient.addColorStop(1, 'rgba(239,68,68,0.02)');
              }
              return gradient;
            },
            fill: true, 
            tension: 0.3, 
            pointRadius: 0, 
            borderWidth: 2 
          }] 
        },
        options: { 
          responsive: true, 
          maintainAspectRatio: false, 
          animation: { duration: 1000 }, 
          plugins: { 
            legend: { display: false },
            tooltip: { 
              callbacks: {
                label: ctx => '$' + fmt(ctx.parsed.y)
              }
            }
          }, 
          scales: { 
            x: { 
              grid: { display: false }, 
              ticks: { 
                color: isDark ? '#64748B' : '#94A3B8', 
                maxTicksLimit: 8,
                font: { size: 10 }
              } 
            }, 
            y: { 
              grid: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.05)' }, 
              ticks: { 
                color: isDark ? '#64748B' : '#94A3B8', 
                callback: v => '$' + v,
                font: { size: 10 }
              } 
            } 
          } 
        }
      });
    }
    toast('Backtest complete!', 'success');
  } catch (err) {
    document.getElementById('btResults').innerHTML = \`<div class="alert alert-error" style="white-space:pre-wrap;word-break:break-word">❌ <strong>Backtest Failed</strong><br>\${err.message}</div>\`;
    toast('Backtest failed', 'error');
  }
}


let _lastBacktestResult = null;

function exportResultsCSV() {
  if (!_lastBacktestResult) { toast("Run a backtest first", "warning"); return; }
  const res = _lastBacktestResult;
  const m = res.metrics || {};
  const trades = res.trades || [];
  
  let csv = "Metric,Value\n";
  csv += "Total Return," + (m.total_return_pct || 0) + "%\n";
  csv += "Net Profit,$" + (m.net_profit || 0).toFixed(2) + "\n";
  csv += "Final Balance,$" + (res.final_equity || 0).toFixed(2) + "\n";
  csv += "Sharpe Ratio," + (m.sharpe_ratio || 0).toFixed(2) + "\n";
  csv += "Profit Factor," + (m.profit_factor || 0).toFixed(2) + "\n";
  csv += "Max Drawdown," + (m.max_drawdown_pct || 0).toFixed(2) + "%\n";
  csv += "Total Trades," + (m.total_trades || 0) + "\n";
  csv += "Win Rate," + (m.win_rate_pct || 0).toFixed(1) + "%\n";
  csv += "R:R Ratio," + (m.risk_reward_ratio || 0).toFixed(2) + "\n";
  csv += "Expectancy,$" + (m.expectancy || 0).toFixed(2) + "\n";
  csv += "Calmar Ratio," + (m.calmar_ratio || 0).toFixed(2) + "\n";
  csv += "Deploy Score," + (m.deploy_score || 0).toFixed(1) + "/10\n";
  csv += "Deploy Verdict," + (m.deploy_verdict || "N/A") + "\n";
  csv += "\nTrade#,Side,Entry Time,Exit Time,Entry Price,Exit Price,Pips,P&L,Exit Reason\n";
  trades.forEach(function(t, i) {
    csv += (i+1) + "," + (t.side||"") + "," + (t.entry_time||"").slice(0,16) + "," + (t.exit_time||"").slice(0,16) + "," + (t.entry_price||0) + "," + (t.exit_price||0) + "," + (t.pnl_pips||0) + "," + (t.pnl||0).toFixed(2) + "," + (t.exit_reason||"") + "\n";
  });
  
  var blob = new Blob([csv], { type: "text/csv" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a"); a.href = url; a.download = "backtest_results.csv"; a.click();
  URL.revokeObjectURL(url);
  toast("CSV exported!", "success");
}

function exportResultsJSON() {
  if (!_lastBacktestResult) { toast("Run a backtest first", "warning"); return; }
  var blob = new Blob([JSON.stringify(_lastBacktestResult, null, 2)], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a"); a.href = url; a.download = "backtest_results.json"; a.click();
  URL.revokeObjectURL(url);
  toast("JSON exported!", "success");
}

function showSaveStrategyModal() {
  const code = document.getElementById('btCode').value.trim();
  if (!code) { toast('Write strategy code first', 'warning'); return; }
  openModal('saveStrategyModal');
}

async function saveStrategy() {
  const name = document.getElementById('stratName').value.trim();
  const code = document.getElementById('btCode').value.trim();
  if (!name) { toast('Enter a strategy name', 'warning'); return; }
  try {
    await api('/api/backtest/strategies', { method: 'POST', body: JSON.stringify({ name, code }) });
    toast(`Strategy "${name}" saved!`, 'success');
    closeModal('saveStrategyModal');
  } catch (err) { toast('Failed to save: ' + err.message, 'error'); }
}

function showCompareModal() {
  const now = new Date(); const from = new Date(now); from.setFullYear(from.getFullYear() - 1);
  document.getElementById('cmpFrom').value = from.toISOString().split('T')[0];
  document.getElementById('cmpTo').value = now.toISOString().split('T')[0];
  document.getElementById('cmpResults').innerHTML = '';
  openModal('compareModal');
}

async function runComparison() {
  const strategies = document.getElementById('cmpStrategies').value.split(',').map(s => s.trim()).filter(Boolean);
  const symbol = document.getElementById('cmpSymbol').value;
  const timeframe = document.getElementById('cmpTF').value;
  const date_from = document.getElementById('cmpFrom').value;
  const date_to = document.getElementById('cmpTo').value;
  if (strategies.length < 2) { toast('Enter at least 2 strategies to compare', 'warning'); return; }
  document.getElementById('cmpResults').innerHTML = '<div class=\"text-center py-16\"><div class=\"text-2xl mb-8\">⏳</div><div class=\"text-muted\">Running comparison across strategies...</div></div>';
  toast('Running comparison...', 'info', 120000);
  try {
    const result = await api('/api/backtest/compare', {
      method: 'POST', body: JSON.stringify({ strategy_keys: strategies, symbol, timeframe, date_from, date_to, capital: 10000 })
    });
    const results = result.results || [];
    document.getElementById('cmpResults').innerHTML = `
      <div class="table-wrapper compact-table" style="margin-top:16px">
        <table>
          <thead><tr><th>Strategy</th><th>Return</th><th>Sharpe</th><th>Trades</th><th>Win Rate</th><th>Max DD</th><th>Final Equity</th></tr></thead>
          <tbody>${results.map(r => {
            const m = r.metrics || {};
            const best = results.reduce((a,b) => ((b.metrics?.sharpe_ratio || 0) > (a.metrics?.sharpe_ratio || 0) ? b : a), results[0]);
            const isBest = r.name === best.name;
            return `<tr${isBest ? ' style="background:rgba(0,212,170,0.05)"' : ''}>
              <td class="font-bold">${r.name || '—'} ${isBest ? '🏆' : ''}</td>
              <td class="${(m.total_return_pct||0) >= 0 ? 'up' : 'down'}">${(m.total_return_pct || 0).toFixed(2)}%</td>
              <td class="neutral">${(m.sharpe_ratio || 0).toFixed(2)}</td>
              <td>${m.total_trades || 0}</td>
              <td>${(m.win_rate_pct || 0).toFixed(1)}%</td>
              <td class="down">${(m.max_drawdown_pct || 0).toFixed(2)}%</td>
              <td class="${r.final_equity >= 10000 ? 'up' : 'down'}">$${(r.final_equity || 0).toFixed(2)}</td>
            </tr>`;
          }).join('')}</tbody></table>
        </div>
        <div class="text-xs text-muted mt-8">🏆 = Best strategy (highest Sharpe)</div>
    `;
    toast('Comparison complete!', 'success');
  } catch (err) { document.getElementById('cmpResults').innerHTML = `<div class="alert alert-error mt-8">❌ Comparison failed: ${err.message}</div>`; toast('Comparison failed', 'error'); }
}

// ==============================
// BOT CONTROL (Live)
// ==============================
async function renderBotControl() {
  const content = document.getElementById('botsListContent');
  try {
    const bots = await api('/api/bots');
    cachedData.bots = bots;
    if (!bots || bots.length === 0) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🤖</div><div class="empty-state-text">No trading bots configured</div></div>`; return; }
    content.innerHTML = '<div style="display:grid;gap:16px">' + bots.map(b => `
      <div class="bot-card">
        <div class="bot-card-header">
          <div class="bot-card-name">${b.display_name || b.name}</div>
          <div class="bot-status-indicator">
            <span class="service-dot ${b.running ? 'running' : 'stopped'}"></span>
            <span class="badge ${b.running ? 'badge-running' : 'badge-stopped'}">${b.running ? '● Running' : '○ Stopped'}</span>
          </div>
        </div>
        <div class="bot-card-meta">
          <span>📄 ${b.script ? b.script.split('/').pop().split('\\').pop() : '—'}</span>
          <span>🆔 ${BOT_MAGIC[b.name] || '—'}</span>
          ${b.pid ? `<span>🔢 PID: ${b.pid}</span>` : ''}
        </div>
        <div class="bot-card-actions">
          <button class="btn btn-sm ${b.running ? 'btn-danger' : 'btn-primary'}" onclick="toggleBot('${b.name}', ${b.running})">
            ${b.running ? '⏹ Stop' : '▶ Start'}
          </button>
          <button class="btn btn-sm" onclick="deleteBot('${b.name}')">🗑 Delete</button>
          <button class="btn btn-sm" onclick="viewBotLogs('${b.name}')">📋 Logs</button>
        </div>
      </div>
    `).join('') + '</div>';
  } catch (err) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🤖</div><div class="empty-state-text">Bot data unavailable</div></div>`; }
}

async function toggleBot(name, isRunning) {
  try {
    if (isRunning) {
      await api(`/api/bots/${name}/stop`, { method: 'POST' });
      toast(`${name} stopped`, 'success');
    } else {
      await api(`/api/bots/${name}/start`, { method: 'POST' });
      toast(`${name} started`, 'success');
    }
    renderBotControl();
  } catch (err) { toast(`Failed: ${err.message}`, 'error'); }
}

async function deleteBot(name) {
  if (!confirm(`Delete bot "${name}"?`)) return;
  try {
    await api(`/api/bots/${name}`, { method: 'DELETE' });
    toast(`${name} deleted`, 'success');
    renderBotControl();
  } catch (err) { toast(`Failed: ${err.message}`, 'error'); }
}

function viewBotLogs(name) {
  toast(`Logs for ${name}: (enable logging in backend)`, 'info', 3000);
}

function refreshBots() { renderBotControl(); }

// ==============================
// SCRIPT EDITOR
// ==============================
async function renderScriptEditor() {
  const fileTree = document.getElementById('scriptFileTree');
  try {
    const data = await api('/api/editor/files');
    const files = data.files || [];
    if (files.length === 0) { fileTree.innerHTML = '<div class="text-muted text-sm p-8">No script files found</div>'; return; }
    fileTree.innerHTML = buildFileTreeHTML(files);
  } catch (err) { fileTree.innerHTML = '<div class="text-muted text-sm p-8">Unable to load files</div>'; }
}

function buildFileTreeHTML(items, depth = 0) {
  let html = '';
  items.forEach(item => {
    const pad = depth * 16;
    if (item.type === 'folder') {
      html += `<div style="padding:6px ${8 + pad}px;font-size:12px;font-weight:600;color:var(--text-secondary)">📁 ${item.name}</div>`;
      if (item.children) html += buildFileTreeHTML(item.children, depth + 1);
    } else {
      const statusIcon = item.git_status === 'modified' ? '✏️' : item.git_status === 'untracked' ? '🆕' : '📄';
      html += `<div class="file-item" style="padding:6px ${8 + pad}px;font-size:12px;cursor:pointer;border-radius:4px;transition:background 0.15s;display:flex;align-items:center;gap:6px" onclick="loadScriptFile('${item.path}')" onmouseover="this.style.background='var(--bg-card)'" onmouseout="this.style.background='transparent'">
        <span>${statusIcon}</span>
        <span>${item.name}</span>
        ${item.git_status !== 'clean' ? `<span class="tag" style="font-size:10px;padding:1px 6px">${item.git_status}</span>` : ''}
      </div>`;
    }
  });
  return html;
}

async function loadScriptFile(path) {
  try {
    const data = await api(`/api/editor/files/${path}`);
    currentScriptPath = path;
    currentScriptContent = data.content;
    document.getElementById('scriptFileName').textContent = path.split('/').pop();
    document.getElementById('scriptEditor').value = data.content;
    document.getElementById('scriptEditor').readOnly = false;
    document.getElementById('scriptSaveBtn').disabled = false;
    document.getElementById('scriptDeployBtn').disabled = false;
  } catch (err) { toast('Failed to load file: ' + err.message, 'error'); }
}

async function saveScript() {
  if (!currentScriptPath) { toast('Select a file first', 'warning'); return; }
  const content = document.getElementById('scriptEditor').value;
  try {
    await api(`/api/editor/files/${currentScriptPath}`, {
      method: 'PUT', body: JSON.stringify({ content })
    });
    currentScriptContent = content;
    toast('Script saved!', 'success');
  } catch (err) { toast('Save failed: ' + err.message, 'error'); }
}

async function deployScript() {
  if (!currentScriptPath) { toast('Select a file first', 'warning'); return; }
  // Save first, then deploy
  const content = document.getElementById('scriptEditor').value;
  try {
    await api(`/api/editor/files/${currentScriptPath}`, {
      method: 'PUT', body: JSON.stringify({ content })
    });
    const result = await api(`/api/editor/deploy/${currentScriptPath}`, { method: 'POST' });
    toast('Script deployed! Bot restarted.', 'success');
  } catch (err) { toast('Deploy failed: ' + err.message, 'error'); }
}

// ==============================
// AI ORCHESTRATOR
// ==============================
async function renderOrchestrator() {
  const agentsEl = document.getElementById('orchAgentsContent');
  const timelineEl = document.getElementById('orchTimelineContent');
  try {
    const [agentsData, timelineData] = await Promise.all([
      api('/api/orchestrator/agents'),
      api('/api/orchestrator/timeline')
    ]);
    const agents = agentsData.agents || agentsData || [];
    const events = timelineData.events || timelineData || [];
    cachedData.agents = agents; cachedData.timeline = events;

    if (agents && agents.length > 0) {
      agentsEl.innerHTML = `<div class="agent-grid">${agents.map(a => `
        <div class="agent-card">
          <div class="agent-name">${a.avatar || '🧠'} ${a.name}</div>
          <div class="agent-role">${a.role || 'Assistant'}</div>
          <div><span class="agent-status badge ${a.status === 'active' || a.status === 'running' ? 'badge-active' : 'badge-idle'}">${a.status || 'idle'}</span></div>
          <div class="agent-time">Last: ${a.last_action ? new Date(a.last_action).toLocaleString() : 'N/A'}</div>
          ${a.uptime ? `<div class="agent-time">Uptime: ${Math.floor(a.uptime / 3600)}h ${Math.floor((a.uptime % 3600) / 60)}m</div>` : ''}
        </div>
      `).join('')}</div>`;
    } else { agentsEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🧠</div><div class="empty-state-text">No AI agents</div></div>`; }

    if (events && events.length > 0) {
      timelineEl.innerHTML = `<div class="timeline">${events.slice(-20).reverse().map(t => `
        <div class="timeline-item ${t.outcome === 'warning' ? 'outcome-warning' : t.outcome === 'error' ? 'outcome-error' : ''}">
          <div class="timeline-time">${t.time || '—'}</div>
          <div class="timeline-text">${t.action || t.event || t.message || '—'}</div>
          <div class="timeline-agent">${t.agent_avatar || ''} ${t.agent_name || ''} · ${t.detail || ''}</div>
        </div>
      `).join('')}</div>`;
    } else { timelineEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><div class="empty-state-text">No timeline events</div></div>`; }
  } catch (err) {
    agentsEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🧠</div><div class="empty-state-text">Orchestrator unavailable</div></div>`;
    timelineEl.innerHTML = '';
  }
}

async function sendOrchCommand() {
  const input = document.getElementById('orchCommand');
  const responseEl = document.getElementById('orchResponse');
  const cmd = input.value.trim();
  if (!cmd) { toast('Enter a command', 'warning'); return; }
  responseEl.innerHTML = '<span class="text-muted">Thinking...</span>';
  try {
    const result = await api('/api/orchestrator/command', {
      method: 'POST', body: JSON.stringify({ command: cmd })
    });
    responseEl.innerHTML = `<div class="alert alert-info" style="margin-bottom:0"><span>${result.agent_avatar || '🤖'}</span><span><strong>${result.agent_name || 'Agent'}:</strong> ${result.response}</span></div>`;
    input.value = '';
  } catch (err) { responseEl.innerHTML = `<div class="alert alert-error" style="margin-bottom:0">❌ ${err.message}</div>`; }
}

function refreshOrchestrator() { renderOrchestrator(); }

// ==============================
// ACCOUNT MANAGER
// ==============================
async function renderAccounts() {
  const content = document.getElementById('accountsListContent');
  try {
    const accounts = await api('/api/accounts');
    cachedData.accounts = accounts;
    if (!accounts || accounts.length === 0) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🏦</div><div class="empty-state-text">No accounts</div><div class="empty-state-sub">Add an account to get started</div></div>`; return; }
    content.innerHTML = `<div class="account-grid">${accounts.map(a => {
      const isActive = a.id === activeAccountId;
      return `<div class="account-card ${isActive ? 'active' : ''}" onclick="switchToAccount('${a.id}')">
        <div class="font-bold" style="font-size:16px;margin-bottom:8px">${a.name || 'Account'}</div>
        <div class="bot-card-meta" style="margin-bottom:8px">
          <span>🔑 ${a.login || '—'}</span>
          <span>🖥️ ${a.server || '—'}</span>
          <span>🆔 ${a.id || '—'}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="badge ${a.connected ? 'badge-running' : 'badge-stopped'}">${a.connected ? '🟢 Connected' : '🔴 Disconnected'}</span>
          ${!isActive ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();switchToAccount('${a.id}')">🔀 Switch</button>` : '<span class="badge badge-active">Active</span>'}
        </div>
      </div>`;
    }).join('')}</div>`;
  } catch (err) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🏦</div><div class="empty-state-text">Accounts unavailable</div></div>`; }
}

async function switchToAccount(accountId) {
  try {
    await api(`/api/accounts/${accountId}/switch`, { method: 'POST' });
    activeAccountId = accountId;
    document.getElementById('activeAccountName').textContent = accountId;
    toast(`Switched to ${accountId}`, 'success');
    closeModal('accountsModal');
    // Refresh all data with new context
    renderAccounts();
    // If on cmd, refresh cmd data with new account
    const activeSection = document.querySelector('.section.active');
    if (activeSection) {
      const sectionId = activeSection.id.replace('section-', '');
      if (sectionId === 'cmd') renderCommandCenter();
      else if (sectionId === 'pf') renderPortfolio();
      else if (sectionId === 'journal') renderTradeJournal();
    }
  } catch (err) { toast('Switch failed: ' + err.message, 'error'); }
}

function showAccountSwitcher() {
  openModal('accountsModal');
  const content = document.getElementById('accountsModalContent');
  const accounts = cachedData.accounts || [];
  if (accounts.length === 0) { content.innerHTML = '<div class="text-muted text-sm">No accounts available</div>'; return; }
  content.innerHTML = `<div style="display:grid;gap:12px">${accounts.map(a => {
    const isActive = a.id === activeAccountId;
    return `<div class="flex items-center justify-between" style="padding:12px 16px;border-radius:8px;border:1px solid ${isActive ? 'var(--accent-primary)' : 'var(--border-color)'};background:var(--bg-secondary);cursor:pointer;transition:all 0.2s" onclick="switchToAccount('${a.id}')" onmouseover="this.style.borderColor='var(--accent-primary)'" onmouseout="this.style.borderColor='${isActive ? 'var(--accent-primary)' : 'var(--border-color)'}'">
      <div><div class="font-bold">${a.name || a.id}</div><div class="text-xs text-muted">${a.login || ''} @ ${a.server || '—'}</div></div>
      <div class="flex items-center gap-8">
        <span class="badge ${a.connected ? 'badge-running' : 'badge-stopped'}">${a.connected ? '●' : '○'}</span>
        ${isActive ? '<span class="badge badge-active">Active</span>' : '<span class="btn btn-sm">🔀</span>'}
      </div>
    </div>`;
  }).join('')}</div>`;
}

function showAddAccountModal() { openModal('addAccountModal'); }

async function addAccount() {
  const id = document.getElementById('acctId').value.trim();
  const name = document.getElementById('acctName').value.trim();
  const login = parseInt(document.getElementById('acctLogin').value);
  const password = document.getElementById('acctPassword').value;
  const server = document.getElementById('acctServer').value.trim();
  if (!id || !login) { toast('Account ID and Login are required', 'warning'); return; }
  try {
    await api('/api/accounts', {
      method: 'POST', body: JSON.stringify({ id, name: name || id, login, password: password || '', server: server || 'MetaQuotes-Demo' })
    });
    toast('Account added!', 'success');
    closeModal('addAccountModal');
    renderAccounts();
  } catch (err) { toast('Failed: ' + err.message, 'error'); }
}

// ==============================
// ANALYTICS
// ==============================
async function renderAnalytics() {
  const content = document.getElementById('analyticsContent');
  try {
    const accountId = activeAccountId || 'default';
    const stats = cachedData.stats || await api(`/api/bridge/accounts/${accountId}/stats?days=30`);
    cachedData.stats = stats;
    content.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px">
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon green">🏆</div><div class="stat-label">Total Trades</div><div class="stat-value neutral">${stats.total_trades || '—'}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon blue">🎯</div><div class="stat-label">Win Rate</div><div class="stat-value neutral">${(stats.win_rate || 0).toFixed(1)}%</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon gold">💰</div><div class="stat-label">Gross Profit</div><div class="stat-value up">$${(stats.gross_profit || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon red">📉</div><div class="stat-label">Gross Loss</div><div class="stat-value down">$${(stats.gross_loss || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon blue">⚡</div><div class="stat-label">Profit Factor</div><div class="stat-value neutral">${(stats.profit_factor || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon red">📊</div><div class="stat-label">Max Drawdown</div><div class="stat-value down">${(stats.max_drawdown || 0).toFixed(2)}%</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon gold">🔥</div><div class="stat-label">Best Trade</div><div class="stat-value up">$${(stats.best_trade || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon red">💀</div><div class="stat-label">Worst Trade</div><div class="stat-value down">$${(stats.worst_trade || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon blue">📈</div><div class="stat-label">Net Profit</div><div class="stat-value ${(stats.net_profit||0) >= 0 ? 'up' : 'down'}">$${(stats.net_profit || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon green">📊</div><div class="stat-label">Avg Profit</div><div class="stat-value neutral">$${(stats.avg_profit || 0).toFixed(2)}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon blue">✅</div><div class="stat-label">Wins</div><div class="stat-value up">${stats.wins || '—'}</div></div>
      <div class="bento-item" style="animation:none;opacity:1;padding:24px"><div class="stat-icon red">❌</div><div class="stat-label">Losses</div><div class="stat-value down">${stats.losses || '—'}</div></div>
    </div>`;
  } catch (err) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📈</div><div class="empty-state-text">Analytics unavailable</div></div>`; }
}

// ==============================
// SETTINGS
// ==============================
async function renderSettings() {
  const content = document.getElementById('settingsContent');
  try {
    const settings = await api('/api/settings/system');
    cachedData.settings = settings;
    if (!settings) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚙️</div><div class="empty-state-text">Settings unavailable</div></div>`; return; }
    content.innerHTML = `<div class="bento-grid" style="gap:16px">
      <div class="bento-item col-span-4" style="animation:none;opacity:1;padding:24px">
        <div class="chart-title" style="margin-bottom:12px">CPU Usage</div>
        <div style="display:flex;align-items:center;gap:12px"><div style="flex:1;height:10px;background:var(--bg-secondary);border-radius:5px;overflow:hidden"><div style="width:${settings.cpu || 0}%;height:100%;background:linear-gradient(90deg,var(--accent-primary),var(--accent-secondary));border-radius:5px;transition:width 1s ease"></div></div><span class="font-bold text-mono">${settings.cpu || 0}%</span></div>
      </div>
      <div class="bento-item col-span-4" style="animation:none;opacity:1;padding:24px">
        <div class="chart-title" style="margin-bottom:12px">RAM Usage</div>
        <div style="display:flex;align-items:center;gap:12px"><div style="flex:1;height:10px;background:var(--bg-secondary);border-radius:5px;overflow:hidden"><div style="width:${settings.ram || 0}%;height:100%;background:linear-gradient(90deg,var(--warning),var(--loss));border-radius:5px;transition:width 1s ease"></div></div><span class="font-bold text-mono">${settings.ram || 0}%</span></div>
      </div>
      <div class="bento-item col-span-4" style="animation:none;opacity:1;padding:24px">
        <div class="chart-title" style="margin-bottom:12px">Disk Usage</div>
        <div style="display:flex;align-items:center;gap:12px"><div style="flex:1;height:10px;background:var(--bg-secondary);border-radius:5px;overflow:hidden"><div style="width:${settings.disk || 0}%;height:100%;background:linear-gradient(90deg,var(--accent-secondary),var(--accent-primary));border-radius:5px;transition:width 1s ease"></div></div><span class="font-bold text-mono">${settings.disk || 0}%</span></div>
      </div>
      <div class="bento-item col-span-12" style="animation:none;opacity:1;padding:24px">
        <div class="chart-title" style="margin-bottom:12px">Services</div>
        <div class="service-grid">${(settings.services && typeof settings.services === 'object' ? Object.entries(settings.services) : []).map(([name, status]) => `<div class="service-item"><span class="service-dot ${status === 'running' || status === true ? 'running' : 'stopped'}"></span><span>${name}</span></div>`).join('')}</div>
      </div>
    </div>`;
  } catch (err) { content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚙️</div><div class="empty-state-text">System settings unavailable</div></div>`; }
}

// ==============================
// FILE CONVERTER
// ==============================
let _lastMarkdownOutput = '';

function renderFileConverter() {
  // Initialize drag-and-drop zone
  const zone = document.getElementById('fileUploadZone');
  if (!zone) return;
  zone.onclick = () => document.getElementById('fileInput').click();
  zone.ondragover = (e) => { e.preventDefault(); zone.style.borderColor = 'var(--accent-primary)'; zone.style.background = 'rgba(0,212,170,0.05)'; };
  zone.ondragleave = () => { zone.style.borderColor = 'var(--border-color)'; zone.style.background = 'transparent'; };
  zone.ondrop = (e) => { e.preventDefault(); zone.style.borderColor = 'var(--border-color)'; zone.style.background = 'transparent'; const f = e.dataTransfer.files[0]; if (f) uploadFile(f); };
}

async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (file) uploadFile(file);
}

async function uploadFile(file) {
  const maxSize = 50 * 1024 * 1024; // 50 MB
  if (file.size > maxSize) { toast('File too large (max 50MB)', 'error'); return; }

  // Show progress
  document.getElementById('fileUploadProgress').style.display = 'block';
  document.getElementById('uploadProgressBar').style.width = '30%';
  document.getElementById('uploadStatusText').textContent = `Uploading ${file.name}...`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    document.getElementById('uploadProgressBar').style.width = '60%';
    document.getElementById('uploadStatusText').textContent = 'Converting...';

    const res = await fetch(`${API_BASE}/api/convert/file`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
    }

    document.getElementById('uploadProgressBar').style.width = '100%';
    document.getElementById('uploadStatusText').textContent = '✓ Done!';

    const data = await res.json();
    _lastMarkdownOutput = data.markdown || '';

    // Show output
    document.getElementById('fileOutputBox').style.display = 'block';
    document.getElementById('fileOutputPre').textContent = _lastMarkdownOutput;
    document.getElementById('outputCharCount').textContent = `${_lastMarkdownOutput.length.toLocaleString()} chars`;

    // Show file info
    const sizeStr = data.size < 1024 ? `${data.size} B` :
      data.size < 1048576 ? `${(data.size / 1024).toFixed(1)} KB` :
      `${(data.size / 1048576).toFixed(2)} MB`;

    document.getElementById('fileInfoBox').innerHTML = `
      <div style="display:grid;gap:8px;font-size:13px;">
        <div><strong>Name:</strong> ${data.filename}</div>
        <div><strong>Type:</strong> ${data.content_type}</div>
        <div><strong>Size:</strong> ${sizeStr}</div>
        <div><strong>Output:</strong> ${_lastMarkdownOutput.length.toLocaleString()} chars</div>
      </div>
    `;

    // Show copy/download actions
    const actions = document.getElementById('copyDownloadActions');
    actions.style.display = 'flex';

    toast('File converted successfully!', 'success');
  } catch (err) {
    document.getElementById('uploadProgressBar').style.width = '0%';
    document.getElementById('uploadStatusText').textContent = '✗ Failed';
    document.getElementById('fileOutputBox').style.display = 'none';
    toast('Conversion failed: ' + err.message, 'error');
  }

  // Reset progress after delay
  setTimeout(() => {
    document.getElementById('fileUploadProgress').style.display = 'none';
    document.getElementById('uploadProgressBar').style.width = '0%';
  }, 3000);

  // Reset file input
  document.getElementById('fileInput').value = '';
}

function copyMarkdownOutput() {
  if (!_lastMarkdownOutput) { toast('Nothing to copy', 'warning'); return; }
  navigator.clipboard.writeText(_lastMarkdownOutput).then(() => {
    toast('Copied to clipboard!', 'success');
  }).catch(() => {
    toast('Copy failed', 'error');
  });
}

function downloadMarkdownOutput() {
  if (!_lastMarkdownOutput) { toast('Nothing to download', 'warning'); return; }
  const blob = new Blob([_lastMarkdownOutput], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'converted.md';
  a.click();
  URL.revokeObjectURL(url);
  toast('File downloaded!', 'success');
}

// ==============================
// REFRESH & AUTO
// ==============================
async function refreshAll() {
  if (!backendOnline) {
    // Re-check health first
    await performHealthCheck();
    if (!backendOnline) {
      toast('Backend is still offline. Cannot refresh.', 'error', 3000);
      return;
    }
  }
  toast('Refreshing all data...', 'info', 2000);
  await Promise.all([updateBridgeStatus(), updateActiveAccount(), renderCommandCenter()]);
}

function startAutoRefresh() {
  Object.values(refreshIntervals).forEach(clearInterval);
  refreshIntervals = {};
  refreshIntervals.health = setInterval(updateBridgeStatus, 15000);
  refreshIntervals.equity = setInterval(() => {
    if (!backendOnline) return;
    if (document.getElementById('section-cmd').classList.contains('active')) renderEquityChart();
  }, 30000);
  refreshIntervals.activeAcct = setInterval(() => {
    if (!backendOnline) return;
    updateActiveAccount();
  }, 60000);
  refreshIntervals.xauTicker = setInterval(() => {
    if (!backendOnline) return;
    if (document.getElementById('section-cmd').classList.contains('active')) renderXauTicker();
  }, 5000);
}

// ==============================
// FTMO CHALLENGE MANAGER
// ==============================
async function renderFtmo() {
  const el = document.getElementById('ftmoContent');
  if (!el) return;
  try {
    // Load challenges and profiles
    const [challengesRes, profilesRes] = await Promise.all([
      api('/api/ftmo/challenges').catch(() => ({ challenges: [], summary: {} })),
      api('/api/ftmo/profiles').catch(() => ({ bot_profiles: {} }))
    ]);
    const challenges = challengesRes.challenges || [];
    const summary = challengesRes.summary || {};
    const profiles = profilesRes.bot_profiles || {};

    const accountSizes = ['10k', '25k', '50k', '100k', '200k'];
    const botOptions = Object.keys(profiles).length > 0 ? Object.keys(profiles) : ['gold_bot', 'scalping_bot', 'streaming_bot'];

    let html = '';

    // Summary cards
    html += '<div class="bento-item col-span-8"><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;">';
    html += `<div class="stat-card"><span class="stat-label">Active Challenges</span><span class="stat-value">${summary.active_challenges || 0}</span></div>`;
    html += `<div class="stat-card"><span class="stat-label">Funded Accounts</span><span class="stat-value">${summary.funded_accounts || 0}</span></div>`;
    html += `<div class="stat-card"><span class="stat-label">Total Capital</span><span class="stat-value">$${(summary.total_capital || 0).toLocaleString()}</span></div>`;
    html += `<div class="stat-card"><span class="stat-label ${(summary.total_pnl || 0) >= 0 ? 'up' : 'down'}">Total P&L</span><span class="stat-value ${(summary.total_pnl || 0) >= 0 ? 'up' : 'down'}">$${(summary.total_pnl || 0).toFixed(0)}</span></div>`;
    html += '</div></div>';

    // Create new challenge form
    html += '<div class="bento-item col-span-4"><h3 style="margin-bottom:12px;font-size:16px;">🚀 New Challenge</h3>';
    html += '<div class="flex flex-col gap-8">';
    html += '<label class="form-label">Account Size</label>';
    html += '<select id="ftmoAccountSize" style="padding:10px 12px;border-radius:10px;border:1px solid var(--glass-border);background:var(--bg-card);color:var(--text-primary);font-size:14px;">';
    for (const s of accountSizes) html += `<option value="${s}">$${s.toUpperCase()} (Fee: ${{'10k':155,'25k':325,'50k':540,'100k':1080,'200k':2160}[s] || '?'})</option>`;
    html += '</select>';
    html += '<label class="form-label">Bot</label>';
    html += '<select id="ftmoBot" style="padding:10px 12px;border-radius:10px;border:1px solid var(--glass-border);background:var(--bg-card);color:var(--text-primary);font-size:14px;">';
    for (const b of botOptions) html += `<option value="${b}">${b.replace('_bot','').replace('_',' ').toUpperCase()} Bot</option>`;
    html += '</select>';
    html += '<label class="form-label">Notes</label>';
    html += '<input id="ftmoNotes" class="form-input" placeholder="Optional notes..." style="padding:10px 12px;">';
    html += '<button class="btn btn-primary w-full" onclick="createFtmoChallenge()">Start Challenge</button>';
    html += '</div></div>';

    // Challenges list
    if (challenges.length === 0) {
      html += '<div class="bento-item col-span-12" style="text-align:center;padding:40px 24px;"><p style="color:var(--text-muted);font-size:15px;">No FTMO challenges yet. Create your first one above! 📈</p></div>';
    } else {
      for (const c of challenges) {
        const phaseIcon = c.phase === 'phase1' ? '📋' : c.phase === 'phase2' ? '📈' : '💰';
        const statusColor = c.status === 'failed' ? 'var(--loss)' : c.phase === 'funded' ? 'var(--profit)' : 'var(--accent-primary)';
        html += `<div class="bento-item col-span-6"><div style="border-left:3px solid ${statusColor};padding-left:12px;">`;
        html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">`;
        html += `<span style="font-weight:600;font-size:15px;">${phaseIcon} $${c.account_size.toUpperCase()} · Bot: ${(c.bot_name||'').replace('_bot','')}</span>`;
        html += `<span style="font-size:12px;padding:3px 10px;border-radius:8px;background:${statusColor}22;color:${statusColor};font-weight:600;">${c.phase.toUpperCase()}${c.status === 'failed' ? ' ❌' : c.phase === 'funded' ? ' ✅' : ' 🔄'}</span>`;
        html += '</div>';
        html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;color:var(--text-secondary);">`;
        html += `<span>Balance: <strong>$${c.current_balance.toFixed(0)}</strong></span>`;
        html += `<span>P&L: <strong style="color:${(c.profit_pct||0) >= 0 ? 'var(--profit)' : 'var(--loss)'}">${(c.profit_pct||0) >= 0 ? '+' : ''}${(c.profit_pct||0).toFixed(2)}%</strong></span>`;
        html += `<span>Drawdown: <strong>${(c.max_drawdown_pct||0).toFixed(1)}%</strong></span>`;
        html += `<span>Trading Days: <strong>${c.trading_days||0}/10</strong></span>`;
        html += '</div>';
        if (c.notes) html += `<p style="font-size:12px;color:var(--text-muted);margin-top:6px;">📝 ${c.notes}</p>`;
        html += '</div></div>';
      }
    }

    // FTMO Rules Reference
    html += '<div class="bento-item col-span-12"><h3 style="margin-bottom:12px;font-size:16px;">📋 FTMO Rules Reference</h3>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;font-size:13px;">';
    html += '<div style="padding:12px;background:var(--glass-bg);border-radius:12px;"><strong>Phase 1</strong><br>Profit: +10%<br>DD: max 10%<br>Min 10 trading days</div>';
    html += '<div style="padding:12px;background:var(--glass-bg);border-radius:12px;"><strong>Phase 2</strong><br>Profit: +5%<br>DD: max 5%<br>Min 10 trading days</div>';
    html += '<div style="padding:12px;background:var(--glass-bg);border-radius:12px;"><strong>Funded</strong><br>80% profit split<br>DD: max 10%<br>No profit target</div>';
    html += '<div style="padding:12px;background:var(--glass-bg);border-radius:12px;"><strong>Leverage</strong><br>1:30 for Forex<br>1:10 for Gold (XAUUSD)<br>News trading: Allowed</div>';
    html += '</div></div>';

    el.innerHTML = html;
  } catch (err) {
    el.innerHTML = `<div class="bento-item col-span-8" style="text-align:center;padding:40px;"><p style="color:var(--loss);">Failed to load: ${err.message}</p></div>`;
  }
}

async function createFtmoChallenge() {
  const size = document.getElementById('ftmoAccountSize')?.value || '10k';
  const bot = document.getElementById('ftmoBot')?.value || 'gold_bot';
  const notes = document.getElementById('ftmoNotes')?.value || '';
  try {
    const res = await api('/api/ftmo/challenges', {
      method: 'POST',
      body: JSON.stringify({ account_size: size, bot_name: bot, notes })
    });
    toast(res.message || 'Challenge created!', 'success');
    renderFtmo(); // Refresh
  } catch (err) {
    toast('Error: ' + err.message, 'error');
  }
}

// ==============================
// INIT
// ==============================
function init() {
  performHealthCheck().then(() => {
    initTheme(); initParticles(); initTicker(); updateBridgeStatus(); updateActiveAccount();
    loadMagicNumbers();
    document.querySelectorAll('.nav-item').forEach(item => {
      item.addEventListener('click', () => { const s = item.dataset.section; if (s) navigate(s); });
    });
    document.getElementById('themeToggle').addEventListener('click', toggleTheme);
    document.getElementById('sidebarToggle').addEventListener('click', () => { document.getElementById('sidebar').classList.toggle('open'); });
    document.querySelector('.main-content').addEventListener('click', () => { if (window.innerWidth <= 768) document.getElementById('sidebar').classList.remove('open'); });
    window.addEventListener('hashchange', handleHash);
    startAutoRefresh();
    handleHash();
    // Bento mouse tracking glow
    document.querySelectorAll('.bento-item').forEach(el => {
      el.addEventListener('mousemove', e => {
        const rect = el.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * 100;
        const y = ((e.clientY - rect.top) / rect.height) * 100;
        el.style.setProperty('--mx', x + '%');
        el.style.setProperty('--my', y + '%');
      });
    });
  });
}

function waitForChartJS(callback, attempts = 0) {
  if (typeof Chart !== 'undefined') callback();
  else if (attempts < 50) setTimeout(() => waitForChartJS(callback, attempts + 1), 100);
  else { console.error('Chart.js failed to load'); callback(); }
}

waitForChartJS(init);