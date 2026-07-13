// Knowledge Graph Tab — Vanilla JS (kein ES-Module-Syntax)

(function initKnowledgeGraphTab() {
  if (typeof window.Ninko === 'undefined') {
    setTimeout(initKnowledgeGraphTab, 100);
    return;
  }

  const KnowledgeGraphTab = {
    cy: null,
    selectedNode: null,
    _cytoscapeLoading: false,

    // ── Typ-Farben (sync mit routes_knowledge_graph.py) ─────────────────────
    TYPE_COLORS: {
      module:        '#3498db',
      service:       '#2ecc71',
      host:          '#e74c3c',
      configuration: '#f39c12',
      incident:      '#9b59b6',
      user:          '#1abc9c',
      tag:           '#95a5a6',
      runbook:       '#e67e22',
      workflow:      '#34495e',
      agent:         '#16a085',
    },

    _escapeHtml(str) {
      return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    },

    _injectStyles() {
      if (document.getElementById('kg-tab-styles')) return;
      const s = document.createElement('style');
      s.id = 'kg-tab-styles';
      s.textContent = `
        @keyframes kg-spin { to { transform: rotate(360deg); } }
        #kg-loading svg { animation: kg-spin 1s linear infinite; }
        #kg-node-details .kg-detail-row {
          display: flex; justify-content: space-between; align-items: flex-start;
          padding: 0.35rem 0; border-bottom: 1px solid var(--border-color);
          font-size: 0.82rem; gap: 0.5rem;
        }
        #kg-node-details .kg-detail-row:last-child { border-bottom: none; }
        #kg-node-details .kg-detail-key { color: var(--text-muted); font-size: 0.78rem; flex-shrink: 0; }
        #kg-node-details .kg-detail-val { text-align: right; word-break: break-all; font-family: monospace; font-size: 0.78rem; }
        #kg-node-details .kg-type-badge {
          display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.45rem;
          border-radius: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em;
        }
        .kg-related-item {
          padding: 0.45rem 0.6rem; background: var(--bg-card); border-radius: 4px;
          margin-bottom: 0.4rem; font-size: 0.82rem; cursor: pointer;
          border: 1px solid var(--border-color); transition: background 0.15s;
        }
        .kg-related-item:hover { background: var(--bg-tertiary, var(--bg-card)); }
      `;
      document.head.appendChild(s);
    },

    async init() {
      this.container = document.getElementById('tab-knowledge_graph');
      if (!this.container) return;

      this._injectStyles();
      this._setupEventListeners();
      await this._loadStats();
      await this.loadGraph();
    },

    // ── Stats ────────────────────────────────────────────────────────────────

    async _loadStats() {
      try {
        const resp = await fetch('/api/knowledge-graph/stats', { credentials: 'include' });
        const result = await resp.json();
        if (!result.success) return;
        this._renderStats(result.data);
      } catch (err) {
        console.error('KG: Stats laden fehlgeschlagen', err);
      }
    },

    _renderStats(stats) {
      const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
      };
      set('kg-stat-nodes', stats.nodes ?? '—');
      set('kg-stat-edges', stats.edges ?? '—');
      set('kg-stat-density', stats.density != null ? stats.density.toFixed(4) : '—');

      const components = stats.components ?? (stats.is_connected ? 1 : null);
      const connEl = document.getElementById('kg-stat-connected');
      if (connEl) {
        if (stats.nodes === 0) {
          connEl.textContent = '—';
          connEl.style.color = '';
        } else if (stats.is_connected) {
          connEl.textContent = '1';
          connEl.style.color = 'var(--accent-green, #4caf50)';
        } else {
          connEl.textContent = components != null ? String(components) : '—';
          connEl.style.color = 'var(--accent-yellow, #f39c12)';
        }
      }

      // Label anpassen
      const labelEl = connEl?.closest('.status-card')?.querySelector('.status-label');
      if (labelEl) {
        labelEl.textContent = stats.is_connected ? 'Komponente' : 'Komponenten';
      }
    },

    // ── Graph laden & rendern ────────────────────────────────────────────────

    async loadGraph() {
      this._setLoading(true);
      try {
        const filterType = document.getElementById('kg-filter-type')?.value || '';
        const url = `/api/knowledge-graph/visualization?limit=300${filterType ? `&entity_type=${filterType}` : ''}`;
        const resp = await fetch(url, { credentials: 'include' });
        const result = await resp.json();

        if (!result.success) {
          this._showError(result.error || 'Graph konnte nicht geladen werden');
          return;
        }

        this._renderGraph(result.data.elements);

        // Inline-Stats aus Visualization-Response (schneller als extra Request)
        if (result.data.stats) {
          const set = (id, val) => {
            const el = document.getElementById(id);
            if (el && el.textContent === '—') el.textContent = val;
          };
          set('kg-stat-nodes', result.data.stats.nodes);
          set('kg-stat-edges', result.data.stats.edges);
        }
      } catch (err) {
        this._showError(err.message);
      } finally {
        this._setLoading(false);
      }
    },

    _renderGraph(elements) {
      const container = document.getElementById('kg-cy-container');
      if (!container) return;

      if (typeof cytoscape === 'undefined') {
        if (this._cytoscapeLoading) return;
        this._loadCytoscape(() => this._renderGraph(elements));
        return;
      }

      if (this.cy) {
        this.cy.destroy();
        this.cy = null;
      }

      this.cy = cytoscape({
        container,
        elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': 'data(color)',
              'label': 'data(label)',
              'width': 36,
              'height': 36,
              'font-size': '11px',
              'text-valign': 'bottom',
              'text-halign': 'center',
              'text-margin-y': 6,
              'color': 'var(--text-color, #eee)',
              'text-background-color': 'var(--bg-body, #1a1a1a)',
              'text-background-opacity': 0.85,
              'text-background-padding': '3px',
              'text-background-shape': 'roundrectangle',
              'border-width': 0,
            },
          },
          {
            selector: 'edge',
            style: {
              'width': 1.5,
              'line-color': 'var(--border-color, #444)',
              'target-arrow-color': 'var(--border-color, #444)',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'label': 'data(label)',
              'font-size': '9px',
              'color': 'var(--text-muted, #888)',
              'text-background-color': 'var(--bg-body, #1a1a1a)',
              'text-background-opacity': 0.75,
              'text-background-padding': '2px',
            },
          },
          {
            selector: ':selected',
            style: {
              'border-width': 3,
              'border-color': 'var(--accent-blue, #3498db)',
              'border-opacity': 1,
            },
          },
          {
            selector: '.dimmed',
            style: {
              'opacity': 0.25,
            },
          },
          {
            selector: '.highlighted',
            style: {
              'border-width': 2,
              'border-color': '#fff',
              'opacity': 1,
            },
          },
        ],
        layout: {
          name: 'cose',
          padding: 30,
          nodeRepulsion: 450000,
          edgeElasticity: 100,
          nestingFactor: 5,
          gravity: 80,
          numIter: 1000,
          initialTemp: 200,
          coolingFactor: 0.95,
          minTemp: 1.0,
          animate: false,
        },
      });

      this.cy.on('tap', 'node', (evt) => this._onNodeSelect(evt.target));
      this.cy.on('tap', (evt) => {
        if (evt.target === this.cy) this._onBackgroundTap();
      });
    },

    _loadCytoscape(callback) {
      this._cytoscapeLoading = true;
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js';
      script.onload = () => {
        this._cytoscapeLoading = false;
        callback();
      };
      script.onerror = () => { this._cytoscapeLoading = false; };
      document.head.appendChild(script);
    },

    // ── Node Selection ───────────────────────────────────────────────────────

    async _onNodeSelect(node) {
      this.selectedNode = node;
      const data = node.data();

      // Highlight Nachbarn
      if (this.cy) {
        this.cy.elements().addClass('dimmed');
        node.addClass('highlighted');
        node.connectedEdges().removeClass('dimmed').addClass('highlighted');
        node.neighborhood('node').removeClass('dimmed').addClass('highlighted');
      }

      // Detail-Panel befüllen
      const typeColor = this.TYPE_COLORS[data.type] || '#7f8c8d';
      const props = Object.entries(data.properties || {});

      const e = this._escapeHtml.bind(this);
      const rows = [
        ['ID', `<code style="font-size:0.75rem;">${e(data.id)}</code>`],
        ['Name', e(data.label)],
        ['Typ', `<span class="kg-type-badge" style="background:${typeColor}22;color:${typeColor};">${e(data.type)}</span>`],
        ...props.map(([k, v]) => [e(k), e(v)]),
      ].map(([key, val]) => `
        <div class="kg-detail-row">
          <span class="kg-detail-key">${key}</span>
          <span class="kg-detail-val">${val}</span>
        </div>
      `).join('');

      const detailEl = document.getElementById('kg-node-details');
      if (detailEl) detailEl.innerHTML = rows;

      // Verwandte laden
      await this._loadRelated(data.id);
    },

    async _loadRelated(entityId) {
      const listEl = document.getElementById('kg-related-list');
      if (!listEl) return;

      listEl.innerHTML = '<p style="font-size:0.82rem;color:var(--text-muted);">Lade…</p>';

      try {
        const resp = await fetch(
          `/api/knowledge-graph/entities/${encodeURIComponent(entityId)}/suggestions`,
          { credentials: 'include' }
        );
        const result = await resp.json();

        if (result.success && result.data.suggestions.length > 0) {
          const e = this._escapeHtml.bind(this);
          listEl.innerHTML = result.data.suggestions.map(s => `
            <div class="kg-related-item" data-id="${e(s.entity.id)}">
              <strong style="font-size:0.82rem;">${e(s.entity.name)}</strong>
              <div style="font-size:0.75rem;color:var(--text-muted);margin-top:0.15rem;">${e(s.reason)}</div>
            </div>
          `).join('');

          listEl.querySelectorAll('.kg-related-item').forEach(item => {
            item.addEventListener('click', () => {
              const targetNode = this.cy?.getElementById(item.dataset.id);
              if (targetNode?.length > 0) {
                this.cy.fit(targetNode, 80);
                targetNode.select();
                this._onNodeSelect(targetNode);
              }
            });
          });
        } else {
          listEl.innerHTML = '<p style="font-size:0.82rem;color:var(--text-muted);font-style:italic;">Keine verwandten Entitäten</p>';
        }
      } catch (err) {
        listEl.innerHTML = '<p style="font-size:0.82rem;color:var(--accent-red,#e74c3c);">Fehler beim Laden</p>';
      }
    },

    _onBackgroundTap() {
      this.selectedNode = null;

      if (this.cy) {
        this.cy.elements().removeClass('dimmed highlighted');
      }

      const detailEl = document.getElementById('kg-node-details');
      if (detailEl) detailEl.innerHTML = '<p style="font-size:0.85rem;color:var(--text-muted);font-style:italic;">Klicke auf einen Node…</p>';

      const listEl = document.getElementById('kg-related-list');
      if (listEl) listEl.innerHTML = '<p style="font-size:0.85rem;color:var(--text-muted);font-style:italic;">—</p>';
    },

    // ── Centralität ──────────────────────────────────────────────────────────

    async showCentrality() {
      const panel = document.getElementById('kg-centrality-panel');
      if (!panel) return;

      panel.style.display = 'block';
      const listEl = document.getElementById('kg-centrality-list');
      if (listEl) listEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">Lade…</p>';

      try {
        const resp = await fetch('/api/knowledge-graph/centrality?top_k=10', { credentials: 'include' });
        const result = await resp.json();

        if (result.success && result.data.rankings.length > 0) {
          const maxScore = result.data.rankings[0]?.score || 1;
          const e = this._escapeHtml.bind(this);
          listEl.innerHTML = result.data.rankings.map((r, i) => {
            const bar = Math.round((r.score / maxScore) * 100);
            const nodeColor = this.TYPE_COLORS[r.type] || '#7f8c8d';
            return `
              <div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:6px;padding:0.6rem 0.75rem;">
                <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.35rem;">
                  <span style="font-size:0.7rem;font-weight:700;color:var(--text-muted);min-width:18px;">#${i + 1}</span>
                  <span style="flex:1;font-size:0.82rem;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${e(r.name)}">${e(r.name)}</span>
                  <span style="font-size:0.7rem;padding:0.1rem 0.4rem;border-radius:3px;background:${nodeColor}22;color:${nodeColor};font-weight:600;">${e(r.type)}</span>
                </div>
                <div style="height:4px;background:var(--bg-secondary);border-radius:2px;overflow:hidden;">
                  <div style="height:100%;width:${bar}%;background:${nodeColor};border-radius:2px;"></div>
                </div>
                <div style="font-size:0.72rem;color:var(--text-muted);margin-top:0.2rem;">Score: ${r.score.toFixed(6)}</div>
              </div>
            `;
          }).join('');
        } else {
          listEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">Keine Daten verfügbar</p>';
        }
      } catch (err) {
        listEl.innerHTML = `<p style="color:var(--accent-red,#e74c3c);font-size:0.85rem;">Fehler: ${this._escapeHtml(err.message)}</p>`;
      }
    },

    // ── Hilfsmethoden ────────────────────────────────────────────────────────

    _setupEventListeners() {
      document.getElementById('kg-btn-reload')?.addEventListener('click', () => {
        this.refresh();
      });

      document.getElementById('kg-btn-refresh')?.addEventListener('click', () => {
        this.refresh();
      });

      const seedBtn = document.getElementById('kg-btn-seed');
      if (seedBtn) {
        this._seedButton = seedBtn;
        this._seedOriginalHtml = seedBtn.innerHTML;
        seedBtn.addEventListener('click', () => this._handleSeed());
      }

      document.getElementById('kg-btn-fit')?.addEventListener('click', () => {
        this.cy?.fit(undefined, 30);
      });

      document.getElementById('kg-btn-centrality')?.addEventListener('click', () => {
        this.showCentrality();
      });

      document.getElementById('kg-btn-close-centrality')?.addEventListener('click', () => {
        const panel = document.getElementById('kg-centrality-panel');
        if (panel) panel.style.display = 'none';
      });

      document.getElementById('kg-filter-type')?.addEventListener('change', () => {
        this.loadGraph();
      });
    },

    refresh() {
      this._loadStats();
      this.loadGraph();
    },

    _seedingInProgress: false,

    async _handleSeed() {
      if (this._seedingInProgress) return;
      this._seedingInProgress = true;
      const btn = this._seedButton;
      const originalHtml = this._seedOriginalHtml;
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Seede…';
      }
      try {
        const resp = await fetch('/api/knowledge-graph/seed', {
          method: 'POST',
          credentials: 'include',
        });
        if (!resp.ok) {
          if (resp.status === 403) {
            if (btn) btn.innerHTML = '🔒 Nur Admins';
            if (btn) btn.disabled = true;
            this._seedingInProgress = false;
            return;
          }
          if (btn) btn.innerHTML = `❌ HTTP ${resp.status}`;
          setTimeout(() => {
            this._seedingInProgress = false;
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = originalHtml;
            }
          }, 3000);
          return;
        }
        const data = await resp.json();
        const d = data.data || {};
        if (btn) {
          btn.innerHTML = `✅ +${d.modules_seeded || 0}M / +${d.relationships_seeded || 0}R / +${d.incidents_seeded || 0}I`;
        }
        setTimeout(() => this.refresh(), 1200);
        setTimeout(() => {
          this._seedingInProgress = false;
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
          }
        }, 3000);
      } catch (err) {
        if (btn) btn.innerHTML = '❌ Fehler';
        console.warn('KG seed failed', err);
        setTimeout(() => {
          this._seedingInProgress = false;
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
          }
        }, 3000);
      }
    },

    _setLoading(visible) {
      const el = document.getElementById('kg-loading');
      if (!el) return;
      el.style.display = visible ? 'flex' : 'none';
    },

    _showError(msg) {
      const container = document.getElementById('kg-cy-container');
      if (container) {
        container.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:center;height:100%;flex-direction:column;gap:0.5rem;color:var(--accent-red,#e74c3c);">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span style="font-size:0.875rem;">${this._escapeHtml(msg)}</span>
          </div>
        `;
      }
    },

    destroy() {
      if (this.cy) {
        this.cy.destroy();
        this.cy = null;
      }
    },
  };

  // Registrierung
  window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
  window.Ninko._pluginTabs['knowledge_graph'] = KnowledgeGraphTab;

  if (document.querySelector('.tab-btn.active[data-tab="knowledge_graph"]')) {
    KnowledgeGraphTab.init();
  }
})();
