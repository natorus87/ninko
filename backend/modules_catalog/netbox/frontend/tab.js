(function initNetboxTab() {
  const TAB_ID = 'netbox';
  let currentConnection = '';
  let pollingInterval = null;

  async function loadConnections() {
    try {
      const resp = await fetch('/api/connections/netbox');
      const data = await resp.json();
      const select = document.getElementById('netbox-connection-select');
      select.innerHTML = '<option value="">-- ' + I18n.t('modules.netbox.selectConnection') + ' --</option>';
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
      const [sitesRes, devicesRes] = await Promise.all([
        fetch(`/api/netbox/sites?connection_id=${currentConnection}`),
        fetch(`/api/netbox/devices?connection_id=${currentConnection}`)
      ]);
      const sitesData = await sitesRes.json();
      const devicesData = await devicesRes.json();
      updateStats(sitesData.data?.sites?.length || 0, devicesData.data?.devices?.length || 0);
      renderSites(sitesData.data?.sites || []);
      renderDevices(devicesData.data?.devices || []);
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
    setLoading(false);
  }

  function updateStats(sitesCount, devicesCount) {
    const sitesEl = document.querySelector('#netbox-sites-stat .stat-value');
    const devicesEl = document.querySelector('#netbox-devices-stat .stat-value');
    if (sitesEl) sitesEl.textContent = sitesCount;
    if (devicesEl) devicesEl.textContent = devicesCount;
  }

  function renderSites(sites) {
    const container = document.getElementById('netbox-sites-list');
    if (!container) return;
    if (!sites.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('modules.netbox.sitesList') + '</div>';
      return;
    }
    container.innerHTML = sites.map(s => `<div class="item-row">
      <span>${s.name}</span>
      <span style="color:var(--text-secondary)">${s.slug}</span>
    </div>`).join('');
  }

  function renderDevices(devices) {
    const container = document.getElementById('netbox-devices-list');
    if (!container) return;
    if (!devices.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('modules.netbox.devicesList') + '</div>';
      return;
    }
    container.innerHTML = devices.slice(0, 20).map(d => {
      const statusClass = d.status === 'Active' ? 'success' : 'warning';
      return `<div class="item-row">
        <span>${d.name}</span>
        <span style="color:var(--color-${statusClass})">${d.status}</span>
      </div>`;
    }).join('');
  }

  function setLoading(loading) {
    const els = document.querySelectorAll('#netbox-sites-list, #netbox-devices-list');
    els.forEach(el => {
      if (loading) el.innerHTML = '<div class="loading">' + I18n.t('modules.netbox.loading') + '</div>';
    });
  }

  function startPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(() => {
      if (currentConnection) loadDashboard();
    }, 60000);
  }

  function init() {
    loadConnections().then(() => {
      const select = document.getElementById('netbox-connection-select');
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
