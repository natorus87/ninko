// Message Hub Tab — Vanilla JS (kein ES-Module-Syntax)

const MessageHubTab = {
  _routes: [],

  async init() {
    await this.loadStatus();
  },

  async loadStatus() {
    try {
      const resp = await fetch('/api/message_hub/status');
      if (!resp.ok) return;
      const data = await resp.json();
      this._renderWorkers(data);
      document.getElementById('mh-route-count').textContent = data.active_route_count || '0';
    } catch (e) {
      console.error('MessageHub: Status laden fehlgeschlagen', e);
    }
    await this.loadRoutes();
  },

  _renderWorkers(data) {
    const workers = data.workers || [];
    const workerMap = {};
    for (const w of workers) {
      workerMap[w.channel_type] = w;
    }

    const channels = ['email', 'discord', 'telegram'];
    for (const ch of channels) {
      const icon = document.getElementById(`mh-${ch}-icon`);
      const statusEl = document.getElementById(`mh-${ch}-status`);
      if (!icon || !statusEl) continue;

      const w = workerMap[ch];
      if (!w) {
        icon.textContent = '—';
        statusEl.textContent = 'N/A';
        statusEl.style.color = '';
        continue;
      }

      if (w.running) {
        icon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#4caf50" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12l2.5 2.5L16 9"/></svg>';
        statusEl.textContent = 'Aktiv';
        statusEl.style.color = 'var(--accent-green, #4caf50)';
      } else if (w.next_retry_in !== null) {
        icon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#ff9800" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
        statusEl.textContent = `Retry in ${Math.round(w.next_retry_in)}s`;
        statusEl.style.color = '#ff9800';
      } else {
        icon.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#f44336" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
        statusEl.textContent = 'Gestoppt';
        statusEl.style.color = '#f44336';
      }
    }
  },

  async loadRoutes() {
    try {
      const resp = await fetch('/api/message_hub/routes');
      if (!resp.ok) return;
      this._routes = await resp.json();
      this._renderRoutes();
    } catch (e) {
      console.error('MessageHub: Routen laden fehlgeschlagen', e);
    }
  },

  _renderRoutes() {
    const container = document.getElementById('mh-routes-table');
    if (!container) return;

    if (!this._routes || this._routes.length === 0) {
      container.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:2rem;font-size:0.875rem;">Keine Routen konfiguriert. Füge eine Route hinzu um zu beginnen.</div>';
      return;
    }

    const capColors = {
      READONLY: '#9e9e9e',
      COMMUNICATE: '#2196f3',
      WRITE_DATA: '#4caf50',
      WRITE_SYSTEM: '#ff9800',
      ADMIN: '#f44336',
    };

    const typeIcons = {
      telegram: '✈',
      discord: '🎮',
      email: '✉',
    };

    const rows = this._routes.map(r => {
      const enabled = r.enabled;
      const capColor = capColors[r.permission_cap] || '#9e9e9e';
      const icon = typeIcons[r.channel_type] || '📡';
      return `
        <tr style="border-bottom: 1px solid var(--border-color); ${!enabled ? 'opacity:0.5;' : ''}">
          <td style="padding: 0.6rem 0.75rem; font-size: 0.875rem;">${icon} ${r.channel_type}</td>
          <td style="padding: 0.6rem 0.75rem; font-size: 0.875rem; font-family: monospace;">${r.channel_id}</td>
          <td style="padding: 0.6rem 0.75rem; font-size: 0.875rem;">${r.label || '—'}</td>
          <td style="padding: 0.6rem 0.75rem; font-size: 0.8rem; font-family: monospace;">${r.session_id}</td>
          <td style="padding: 0.6rem 0.75rem;">
            <span style="font-size:0.75rem; padding:0.2rem 0.5rem; border-radius:3px; background:${capColor}22; color:${capColor}; font-weight:600;">
              ${r.permission_cap}
            </span>
          </td>
          <td style="padding: 0.6rem 0.75rem; text-align:center;">
            <button class="btn btn-outline btn-sm" style="padding:0.2rem 0.5rem; font-size:0.75rem;"
              onclick="MessageHubTab.toggleRoute('${r.id}', ${!enabled})">
              ${enabled ? 'Deaktivieren' : 'Aktivieren'}
            </button>
            <button class="btn btn-sm" style="padding:0.2rem 0.5rem; font-size:0.75rem; background:#f4433622; color:#f44336; border:1px solid #f44336; border-radius:4px; margin-left:0.25rem;"
              onclick="MessageHubTab.deleteRoute('${r.id}', '${r.channel_type}', '${r.channel_id}')">
              Löschen
            </button>
          </td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table style="width:100%; border-collapse:collapse; font-size:0.875rem;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border-color);">
            <th style="padding:0.5rem 0.75rem; text-align:left; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Typ</th>
            <th style="padding:0.5rem 0.75rem; text-align:left; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Channel-ID</th>
            <th style="padding:0.5rem 0.75rem; text-align:left; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Label</th>
            <th style="padding:0.5rem 0.75rem; text-align:left; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Session</th>
            <th style="padding:0.5rem 0.75rem; text-align:left; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Cap</th>
            <th style="padding:0.5rem 0.75rem; text-align:center; font-size:0.75rem; color:var(--text-muted); font-weight:600;">Aktionen</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  showAddRoute() {
    const form = document.getElementById('mh-add-form');
    if (form) form.style.display = 'block';
  },

  hideAddRoute() {
    const form = document.getElementById('mh-add-form');
    if (form) form.style.display = 'none';
    // Felder leeren
    ['mh-new-channel-id', 'mh-new-session-id', 'mh-new-label'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
  },

  async saveRoute() {
    const channelType = document.getElementById('mh-new-type')?.value || '';
    const channelId = document.getElementById('mh-new-channel-id')?.value?.trim() || '';
    const sessionId = document.getElementById('mh-new-session-id')?.value?.trim() || '';
    const permissionCap = document.getElementById('mh-new-cap')?.value || 'WRITE_DATA';
    const label = document.getElementById('mh-new-label')?.value?.trim() || '';

    if (!channelId || !sessionId) {
      alert('Bitte Channel-ID und Session-ID angeben.');
      return;
    }

    try {
      const resp = await fetch('/api/message_hub/routes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel_type: channelType, channel_id: channelId, session_id: sessionId, permission_cap: permissionCap, label }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        alert(`Fehler: ${err.detail || resp.statusText}`);
        return;
      }
      this.hideAddRoute();
      await this.loadRoutes();
    } catch (e) {
      alert(`Fehler: ${e.message}`);
    }
  },

  async toggleRoute(routeId, enable) {
    try {
      await fetch(`/api/message_hub/routes/${routeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enable }),
      });
      await this.loadRoutes();
    } catch (e) {
      console.error('MessageHub: Toggle fehlgeschlagen', e);
    }
  },

  async deleteRoute(routeId, channelType, channelId) {
    if (!confirm(`Route [${channelType}] ${channelId} wirklich löschen?`)) return;
    try {
      await fetch(`/api/message_hub/routes/${routeId}`, { method: 'DELETE' });
      await this.loadRoutes();
    } catch (e) {
      console.error('MessageHub: Löschen fehlgeschlagen', e);
    }
  },

  async restartWorkers() {
    const btn = event?.target;
    if (btn) { btn.disabled = true; btn.textContent = 'Neustart…'; }
    try {
      const resp = await fetch('/api/message_hub/workers/restart', { method: 'POST' });
      if (!resp.ok) {
        alert('Worker-Neustart fehlgeschlagen.');
      } else {
        await this.loadStatus();
      }
    } catch (e) {
      alert(`Fehler: ${e.message}`);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:0.4rem;"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>Worker neu starten'; }
    }
  },
};

// Plugin-Registrierung (Katalog-Modul)
if (typeof Ninko !== 'undefined') Ninko._pluginTabs['message_hub'] = MessageHubTab;
