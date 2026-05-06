(function initMcpServerTab() {
  const TAB_ID = 'mcp_server';
  let currentConnection = '';
  let currentTools = [];

  function byId(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  function renderList(containerId, items, emptyText, pickLabel) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!Array.isArray(items) || !items.length) {
      container.innerHTML = `<div class="mcp-item">${esc(emptyText)}</div>`;
      return;
    }
    container.innerHTML = items.slice(0, 20).map((item, index) => {
      const label = pickLabel(item);
      return `<div class="mcp-item" data-index="${index}">${esc(label)}</div>`;
    }).join('');
  }

  async function loadConnections() {
    const select = document.getElementById('mcp-server-connection-select');
    if (!select) return;
    try {
      const res = await fetch('/api/connections/mcp_server');
      const data = await res.json();
      select.innerHTML = '<option value="">Verbindung wählen...</option>';
      (data.connections || []).forEach(conn => {
        const option = document.createElement('option');
        option.value = conn.id;
        option.textContent = conn.name;
        select.appendChild(option);
      });
      select.addEventListener('change', (event) => {
        currentConnection = event.target.value;
        refresh();
      });
    } catch (error) {
      console.error('Failed to load MCP connections:', error);
    }
  }

  async function refresh() {
    const statusEl = byId('mcp-server-status');
    if (!statusEl) return;
    if (!currentConnection) {
      statusEl.textContent = 'Keine Verbindung ausgewählt.';
      renderList('mcp-server-tools', [], 'Keine Daten.', () => '');
      renderList('mcp-server-resources', [], 'Keine Daten.', () => '');
      currentTools = [];
      return;
    }

    statusEl.textContent = 'Lade...';
    try {
      const [statusRes, toolsRes, resourcesRes] = await Promise.all([
        fetch(`/api/mcp-server/status?connection_id=${currentConnection}`),
        fetch(`/api/mcp-server/tools?connection_id=${currentConnection}`),
        fetch(`/api/mcp-server/resources?connection_id=${currentConnection}`)
      ]);
      const statusData = await statusRes.json();
      const toolsData = await toolsRes.json();
      const resourcesData = await resourcesRes.json();

      statusEl.textContent = JSON.stringify(statusData.data || {}, null, 2);
      currentTools = Array.isArray(toolsData.data) ? toolsData.data : [];
      renderList(
        'mcp-server-tools',
        currentTools,
        'Keine Tools gefunden.',
        (item) => `<strong>${item.name || 'unnamed'}</strong><br><span>${item.description || ''}</span>`
      );
      renderList(
        'mcp-server-resources',
        Array.isArray(resourcesData.data) ? resourcesData.data : [],
        'Keine Resources gefunden.',
        (item) => `<strong>${item.name || item.uri || 'resource'}</strong><br><span>${item.uri || ''}</span>`
      );
      bindToolSelection();
    } catch (error) {
      statusEl.textContent = `Fehler: ${error}`;
      console.error('Failed to load MCP dashboard:', error);
    }
  }

  function bindToolSelection() {
    const container = byId('mcp-server-tools');
    if (!container) return;
    container.querySelectorAll('.mcp-item[data-index]').forEach((node) => {
      node.addEventListener('click', () => {
        const index = Number(node.getAttribute('data-index'));
        const tool = currentTools[index];
        if (!tool) return;
        const input = byId('mcp-server-tool-name');
        if (input) input.value = tool.name || '';
      });
    });
  }

  async function validateConnection() {
    const statusEl = byId('mcp-server-status');
    if (!currentConnection || !statusEl) return;
    statusEl.textContent = 'Validiere...';
    try {
      const res = await fetch('/api/mcp-server/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connection_id: currentConnection })
      });
      const data = await res.json();
      statusEl.textContent = JSON.stringify(data.data || {}, null, 2);
    } catch (error) {
      statusEl.textContent = `Fehler: ${error}`;
    }
  }

  async function callTool() {
    const resultEl = byId('mcp-server-call-result');
    const nameEl = byId('mcp-server-tool-name');
    const argsEl = byId('mcp-server-tool-args');
    if (!resultEl || !nameEl || !argsEl) return;
    if (!currentConnection) {
      resultEl.textContent = 'Bitte zuerst eine Verbindung auswählen.';
      return;
    }
    const toolName = nameEl.value.trim();
    if (!toolName) {
      resultEl.textContent = 'Bitte einen Tool-Namen angeben.';
      return;
    }

    let args = {};
    try {
      args = JSON.parse(argsEl.value || '{}');
    } catch (error) {
      resultEl.textContent = `Ungültiges JSON: ${error}`;
      return;
    }

    resultEl.textContent = 'Führe Tool aus...';
    try {
      const res = await fetch('/api/mcp-server/tool-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          connection_id: currentConnection,
          tool_name: toolName,
          arguments: args
        })
      });
      const data = await res.json();
      resultEl.textContent = JSON.stringify(data.data || {}, null, 2);
    } catch (error) {
      resultEl.textContent = `Fehler: ${error}`;
    }
  }

  function init() {
    loadConnections();
    const validateBtn = byId('mcp-server-validate-btn');
    const refreshBtn = byId('mcp-server-refresh-btn');
    const callBtn = byId('mcp-server-call-btn');
    if (validateBtn) validateBtn.addEventListener('click', validateConnection);
    if (refreshBtn) refreshBtn.addEventListener('click', refresh);
    if (callBtn) callBtn.addEventListener('click', callTool);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  Ninko._pluginTabs = Ninko._pluginTabs || {};
  Ninko._pluginTabs[TAB_ID] = { refresh };
})();
