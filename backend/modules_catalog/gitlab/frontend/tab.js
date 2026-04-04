(function initGitLabTab() {
  const TAB_ID = 'gitlab';
  let currentConnection = '';
  let pollingInterval = null;

  async function loadConnections() {
    try {
      const resp = await fetch('/api/connections?module=gitlab');
      const data = await resp.json();
      const select = document.getElementById('gitlab-connection-select');
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
      const [projectsRes, pipelinesRes, mrsRes] = await Promise.all([
        fetch(`/api/gitlab/projects?connection_id=${currentConnection}`),
        fetch(`/api/gitlab/projects/0/pipelines?connection_id=${currentConnection}`).catch(() => ({json: () => ({data: {pipelines: []}})})),
        fetch(`/api/gitlab/projects/0/merge-requests?connection_id=${currentConnection}`).catch(() => ({json: () => ({data: {merge_requests: []}})}))
      ]);
      const projectsData = await projectsRes.json();
      const pipelinesData = await pipelinesRes.json();
      const mrsData = await mrsRes.json();
      
      updateStats(projectsData.data?.projects?.length || 0, pipelinesData.data?.pipelines?.length || 0, mrsData.data?.merge_requests?.length || 0);
      renderPipelines(pipelinesData.data?.pipelines || []);
      renderMergeRequests(mrsData.data?.merge_requests || []);
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
    setLoading(false);
  }

  function updateStats(projectsCount, pipelinesCount, mrsCount) {
    const projectsEl = document.querySelector('#gitlab-projects-stat .stat-value');
    const pipelinesEl = document.querySelector('#gitlab-pipelines-stat .stat-value');
    const mrsEl = document.querySelector('#gitlab-mrs-stat .stat-value');
    if (projectsEl) projectsEl.textContent = projectsCount;
    if (pipelinesEl) pipelinesEl.textContent = pipelinesCount;
    if (mrsEl) mrsEl.textContent = mrsCount;
  }

  function renderPipelines(pipelines) {
    const container = document.getElementById('gitlab-pipelines-list');
    if (!container) return;
    if (!pipelines.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('discord.noMessages') + '</div>';
      return;
    }
    container.innerHTML = pipelines.slice(0, 10).map(p => `<div class="pipeline-row">
      <span class="status ${p.status}">${p.status}</span>
      <span>${p.ref}</span>
      <span style="color:var(--text-secondary);font-size:0.75rem">${p.sha?.substring(0, 8)}</span>
    </div>`).join('');
  }

  function renderMergeRequests(mrs) {
    const container = document.getElementById('gitlab-mrs-list');
    if (!container) return;
    if (!mrs.length) {
      container.innerHTML = '<div class="empty">' + I18n.t('discord.noMessages') + '</div>';
      return;
    }
    container.innerHTML = mrs.slice(0, 10).map(mr => `<div class="mr-row">
      <div><strong>!${mr.iid}</strong> ${mr.title}</div>
      <div style="font-size:0.75rem;color:var(--text-secondary)">${mr.source_branch} → ${mr.target_branch}</div>
    </div>`).join('');
  }

  function setLoading(loading) {
    const els = document.querySelectorAll('#gitlab-pipelines-list, #gitlab-mrs-list');
    els.forEach(el => {
      if (loading) el.innerHTML = '<div class="loading">' + I18n.t('discord.loading') + '</div>';
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
      const select = document.getElementById('gitlab-connection-select');
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