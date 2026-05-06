(function initZabbixTab() {
  const TAB_ID = 'zabbix';
  let currentConnection = '';
  let pollingInterval = null;

  function esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  async function loadConnections() {
    try {
      const resp = await fetch('/api/connections/zabbix');
      const data = await resp.json();
      const select = document.getElementById('zabbix-connection-select');
      select.innerHTML = '<option value="">-- ' + I18n.t('modules.zabbix.selectConnection') + ' --</option>';
      if (data.connections) {
        data.connections.forEach(conn => {
          const opt = document.createElement('option');
          opt.value = conn.id;
          opt.textContent = conn.name;
          select.appendChild(opt);
        });
      }
      select.addEventListener('change', e => {
        currentConnection = e.target.value;
        if (currentConnection) loadDashboard();
      });
    } catch (err) {
      console.error('Failed to load connections:', err);
    }
  }

  async function loadDashboard() {
    if (!currentConnection) return;
    setLoading(true);
    try {
      const [hostsRes, problemsRes] = await Promise.all([
        fetch(`/api/zabbix/hosts?connection_id=${currentConnection}`),
        fetch(`/api/zabbix/problems?connection_id=${currentConnection}`)
      ]);
      const hostsData = await hostsRes.json();
      const problemsData = await problemsRes.json();
      updateStats(hostsData.data?.hosts?.length || 0, problemsData.data?.problems?.length || 0);
      renderProblems(problemsData.data?.problems || []);
      renderHosts(hostsData.data?.hosts || []);
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
    setLoading(false);
  }

  function updateStats(hostsCount, problemsCount) {
    const hostsEl = document.querySelector('#zabbix-hosts-stat .stat-value');
    const problemsEl = document.querySelector('#zabbix-problems-stat .stat-value');
    if (hostsEl) hostsEl.textContent = hostsCount;
    if (problemsEl) problemsEl.textContent = problemsCount;
  }

  function renderProblems(problems) {
    const container = document.getElementById('zabbix-problems-list');
    if (!container) return;
    if (!problems.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('modules.zabbix.noProblems') + '</div>';
      return;
    }
    container.innerHTML = problems.map(p => {
      const severityClass = p.severity >= 4 ? 'error' : p.severity >= 2 ? 'warning' : 'info';
      return `<div class="problem-row ${severityClass}">
        <div><strong>${esc(p.name) || esc(p.eventid)}</strong></div>
        <div style="font-size:0.8em;color:var(--text-secondary)">${esc(p.host) || ''} • ${new Date(p.clock * 1000).toLocaleString()}</div>
      </div>`;
    }).join('');
  }

  function renderHosts(hosts) {
    const container = document.getElementById('zabbix-hosts-list');
    if (!container) return;
    if (!hosts.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('modules.zabbix.hostsList') + '</div>';
      return;
    }
    container.innerHTML = hosts.map(h => {
      const statusClass = h.status == '0' ? 'success' : 'error';
      return `<div class="item-row">
        <span>${esc(h.name)}</span>
        <span style="color:var(--color-${statusClass})">${h.status == '0' ? '●' : '○'}</span>
      </div>`;
    }).join('');
  }

  function setLoading(loading) {
    const els = document.querySelectorAll('#zabbix-hosts-list, #zabbix-problems-list');
    els.forEach(el => {
      if (loading) el.innerHTML = '<div class="loading">' + I18n.t('modules.zabbix.loading') + '</div>';
    });
  }

  function startPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(() => {
      if (currentConnection) loadDashboard();
    }, 30000);
  }

  function init() {
    loadConnections().then(() => {
      const select = document.getElementById('zabbix-connection-select');
      if (select.options.length > 1) {
        select.selectedIndex = 1;
        currentConnection = select.value;
        loadDashboard();
        startPolling();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  Ninko._pluginTabs = Ninko._pluginTabs || {};
  Ninko._pluginTabs[TAB_ID] = {
    refresh: loadDashboard,
    destroy: () => { if (pollingInterval) clearInterval(pollingInterval); }
  };
})();
