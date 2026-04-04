(function initGitHubTab() {
  const TAB_ID = 'github';
  let currentConnection = '';
  let pollingInterval = null;

  async function loadConnections() {
    try {
      const resp = await fetch('/api/connections?module=github');
      const data = await resp.json();
      const select = document.getElementById('github-connection-select');
      select.innerHTML = '<option value="">-- ' + I18n.t('discord.selectConnection') + ' --</option>';
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
      const [reposRes] = await Promise.all([
        fetch(`/api/github/repos?connection_id=${currentConnection}`)
      ]);
      const reposData = await reposRes.json();
      updateStats(reposData.data?.repos?.length || 0, 0, 0, 0);
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
    setLoading(false);
  }

  function updateStats(reposCount, runsCount, prsCount, issuesCount) {
    const reposEl = document.querySelector('#github-repos-stat .stat-value');
    if (reposEl) reposEl.textContent = reposCount;
  }

  function setLoading(loading) {
    const els = document.querySelectorAll('#github-runs-list, #github-prs-list');
    els.forEach(el => {
      if (loading) el.innerHTML = '<div class="loading">' + I18n.t('discord.loading') + '</div>';
    });
  }

  function init() {
    loadConnections().then(() => {
      const select = document.getElementById('github-connection-select');
      if (select.options.length > 1) {
        select.selectedIndex = 1;
        currentConnection = select.value;
        loadDashboard();
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