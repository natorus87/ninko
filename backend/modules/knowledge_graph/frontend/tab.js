/**
 * Knowledge Graph Visualization Tab
 * 
 * Zeigt den Knowledge Graph als interaktives Netzwerk-Diagramm.
 * Nutzt Cytoscape.js für Graph-Rendering.
 * 
 * @module KnowledgeGraphTab
 */

(function initKnowledgeGraphTab() {
  const TAB_ID = 'knowledge_graph';

  // Warte bis Ninko-API verfügbar
  if (typeof window.Ninko === 'undefined') {
    setTimeout(initKnowledgeGraphTab, 100);
    return;
  }

  const KnowledgeGraphTab = {
    cy: null,
    selectedNode: null,

    async init() {
      this.container = document.getElementById('tab-knowledge_graph');
      if (!this.container) return;

      this.renderLayout();
      await this.loadGraph();
      this.setupEventListeners();
    },

    renderLayout() {
      this.container.innerHTML = `
        <div class="kg-layout">
          <div class="kg-sidebar">
            <h3>${this._t('Knowledge Graph', 'Knowledge Graph')}</h3>
            
            <div class="kg-section">
              <label>${this._t('Filter', 'Filter')}</label>
              <select id="kg-filter-type">
                <option value="">${this._t('Alle Typen', 'All Types')}</option>
                <option value="module">Module</option>
                <option value="service">Services</option>
                <option value="host">Hosts</option>
                <option value="incident">Incidents</option>
                <option value="configuration">Configurations</option>
              </select>
            </div>

            <div class="kg-section">
              <button id="kg-btn-reload" class="btn btn-primary">
                ${this._t('Neu laden', 'Reload')}
              </button>
              <button id="kg-btn-stats" class="btn btn-secondary">
                ${this._t('Statistiken', 'Statistics')}
              </button>
            </div>

            <div class="kg-section" id="kg-node-details">
              <h4>${this._t('Details', 'Details')}</h4>
              <p class="kg-placeholder">${this._t('Klicke auf einen Node...', 'Click a node...')}</p>
            </div>

            <div class="kg-section" id="kg-related">
              <h4>${this._t('Verwandte', 'Related')}</h4>
              <div id="kg-related-list"></div>
            </div>
          </div>

          <div class="kg-main">
            <div id="kg-cy-container"></div>
            <div class="kg-legend">
              <span class="kg-legend-item"><span class="kg-dot" style="background:#3498db"></span> Module</span>
              <span class="kg-legend-item"><span class="kg-dot" style="background:#2ecc71"></span> Service</span>
              <span class="kg-legend-item"><span class="kg-dot" style="background:#e74c3c"></span> Host</span>
              <span class="kg-legend-item"><span class="kg-dot" style="background:#9b59b6"></span> Incident</span>
              <span class="kg-legend-item"><span class="kg-dot" style="background:#f39c12"></span> Config</span>
            </div>
          </div>
        </div>

        <style>
          .kg-layout {
            display: flex;
            height: 100%;
            gap: 1rem;
          }
          .kg-sidebar {
            width: 300px;
            min-width: 300px;
            background: var(--surface-1);
            border-radius: var(--radius-lg);
            padding: 1rem;
            overflow-y: auto;
          }
          .kg-sidebar h3 {
            margin: 0 0 1rem 0;
            font-size: 1.1rem;
          }
          .kg-section {
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--surface-2);
          }
          .kg-section:last-child {
            border-bottom: none;
          }
          .kg-section label {
            display: block;
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            color: var(--text-secondary);
          }
          .kg-section select,
          .kg-section button {
            width: 100%;
            margin-bottom: 0.5rem;
          }
          .kg-main {
            flex: 1;
            position: relative;
            background: var(--surface-1);
            border-radius: var(--radius-lg);
            overflow: hidden;
          }
          #kg-cy-container {
            width: 100%;
            height: 100%;
          }
          .kg-legend {
            position: absolute;
            bottom: 1rem;
            left: 1rem;
            background: var(--surface-0);
            padding: 0.5rem 1rem;
            border-radius: var(--radius-md);
            display: flex;
            gap: 1rem;
            font-size: 0.8rem;
          }
          .kg-legend-item {
            display: flex;
            align-items: center;
            gap: 0.3rem;
          }
          .kg-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
          }
          .kg-placeholder {
            color: var(--text-secondary);
            font-style: italic;
          }
          #kg-node-details h4 {
            margin: 0 0 0.5rem 0;
          }
          #kg-node-details .kg-detail-row {
            display: flex;
            justify-content: space-between;
            padding: 0.3rem 0;
            border-bottom: 1px solid var(--surface-2);
            font-size: 0.9rem;
          }
          #kg-related-list .kg-related-item {
            padding: 0.5rem;
            background: var(--surface-2);
            border-radius: var(--radius-sm);
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
            cursor: pointer;
          }
          #kg-related-list .kg-related-item:hover {
            background: var(--surface-3);
          }
        </style>
      `;
    },

    async loadGraph() {
      try {
        const filterType = document.getElementById('kg-filter-type')?.value || '';
        const response = await fetch(
          `/api/knowledge-graph/visualization?${filterType ? `entity_type=${filterType}&` : ''}limit=300`,
          { credentials: 'include' }
        );
        const result = await response.json();

        if (!result.success) {
          this.showError(result.error || 'Failed to load graph');
          return;
        }

        this.renderGraph(result.data.elements);
      } catch (err) {
        this.showError(err.message);
      }
    },

    renderGraph(elements) {
      const container = document.getElementById('kg-cy-container');
      if (!container) return;

      // Cytoscape laden (falls nicht vorhanden, lazy-load)
      if (typeof cytoscape === 'undefined') {
        this.loadCytoscape(() => this.renderGraph(elements));
        return;
      }

      if (this.cy) {
        this.cy.destroy();
      }

      this.cy = cytoscape({
        container: container,
        elements: elements,
        style: [
          {
            selector: 'node',
            style: {
              'background-color': 'data(color)',
              'label': 'data(label)',
              'width': 40,
              'height': 40,
              'font-size': '12px',
              'text-valign': 'bottom',
              'text-halign': 'center',
              'text-margin-y': 8,
              'color': 'var(--text-primary)',
              'text-background-color': 'var(--surface-0)',
              'text-background-opacity': 0.8,
              'text-background-padding': 3,
              'text-background-shape': 'roundrectangle',
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 2,
              'line-color': 'var(--text-secondary)',
              'target-arrow-color': 'var(--text-secondary)',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'label': 'data(label)',
              'font-size': '10px',
              'color': 'var(--text-secondary)',
              'text-background-color': 'var(--surface-0)',
              'text-background-opacity': 0.8,
            }
          },
          {
            selector: ':selected',
            style: {
              'border-width': 3,
              'border-color': '#fff',
              'border-opacity': 1,
            }
          }
        ],
        layout: {
          name: 'cose',
          padding: 20,
          nodeRepulsion: 400000,
          edgeElasticity: 100,
          nestingFactor: 5,
          gravity: 80,
          numIter: 1000,
          initialTemp: 200,
          coolingFactor: 0.95,
          minTemp: 1.0,
        }
      });

      this.cy.on('tap', 'node', (evt) => {
        this.onNodeSelect(evt.target);
      });

      this.cy.on('tap', (evt) => {
        if (evt.target === this.cy) {
          this.onBackgroundTap();
        }
      });
    },

    loadCytoscape(callback) {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js';
      script.onload = callback;
      document.head.appendChild(script);
    },

    async onNodeSelect(node) {
      this.selectedNode = node;
      const data = node.data();

      const detailsHtml = `
        <h4>${this._t('Details', 'Details')}</h4>
        <div class="kg-detail-row">
          <span>ID:</span><code>${data.id}</code>
        </div>
        <div class="kg-detail-row">
          <span>${this._t('Name', 'Name')}:</span><span>${data.label}</span>
        </div>
        <div class="kg-detail-row">
          <span>${this._t('Typ', 'Type')}:</span><span>${data.type}</span>
        </div>
        ${Object.entries(data.properties || {}).map(([k, v]) => `
          <div class="kg-detail-row">
            <span>${k}:</span><span>${v}</span>
          </div>
        `).join('')}
      `;

      document.getElementById('kg-node-details').innerHTML = detailsHtml;

      // Lade verwandte Entitäten
      try {
        const response = await fetch(
          `/api/knowledge-graph/entities/${encodeURIComponent(data.id)}/suggestions`,
          { credentials: 'include' }
        );
        const result = await response.json();

        const relatedList = document.getElementById('kg-related-list');
        if (result.success && result.data.suggestions.length > 0) {
          relatedList.innerHTML = result.data.suggestions.map(s => `
            <div class="kg-related-item" data-id="${s.entity.id}">
              <strong>${s.entity.name}</strong>
              <small>(${s.reason})</small>
            </div>
          `).join('');

          // Click-Handler für verwandte Items
          relatedList.querySelectorAll('.kg-related-item').forEach(item => {
            item.addEventListener('click', () => {
              const id = item.dataset.id;
              const targetNode = this.cy.getElementById(id);
              if (targetNode.length > 0) {
                this.cy.fit(targetNode, 100);
                targetNode.select();
                this.onNodeSelect(targetNode);
              }
            });
          });
        } else {
          relatedList.innerHTML = `<p class="kg-placeholder">${this._t('Keine verwandten Entitäten', 'No related entities')}</p>`;
        }
      } catch (err) {
        console.error('Failed to load related:', err);
      }
    },

    onBackgroundTap() {
      this.selectedNode = null;
      document.getElementById('kg-node-details').innerHTML = `
        <h4>${this._t('Details', 'Details')}</h4>
        <p class="kg-placeholder">${this._t('Klicke auf einen Node...', 'Click a node...')}</p>
      `;
      document.getElementById('kg-related-list').innerHTML = '';
    },

    async showStats() {
      try {
        const response = await fetch('/api/knowledge-graph/stats', {
          credentials: 'include'
        });
        const result = await response.json();

        if (result.success) {
          const stats = result.data;
          alert(this._t(
            `Knowledge Graph Statistiken:\n\n` +
            `Nodes: ${stats.nodes}\n` +
            `Edges: ${stats.edges}\n` +
            `Density: ${stats.density.toFixed(4)}\n` +
            `Connected: ${stats.is_connected ? 'Ja' : 'Nein'}`,
            `Knowledge Graph Statistics:\n\n` +
            `Nodes: ${stats.nodes}\n` +
            `Edges: ${stats.edges}\n` +
            `Density: ${stats.density.toFixed(4)}\n` +
            `Connected: ${stats.is_connected ? 'Yes' : 'No'}`
          ));
        }
      } catch (err) {
        this.showError(err.message);
      }
    },

    setupEventListeners() {
      const reloadBtn = document.getElementById('kg-btn-reload');
      if (reloadBtn) {
        reloadBtn.addEventListener('click', () => this.loadGraph());
      }

      const statsBtn = document.getElementById('kg-btn-stats');
      if (statsBtn) {
        statsBtn.addEventListener('click', () => this.showStats());
      }

      const filterSelect = document.getElementById('kg-filter-type');
      if (filterSelect) {
        filterSelect.addEventListener('change', () => this.loadGraph());
      }
    },

    showError(msg) {
      const container = document.getElementById('kg-cy-container');
      if (container) {
        container.innerHTML = `<div class="error">${msg}</div>`;
      }
    },

    _t(de, en) {
      // Versuche I18n zu nutzen, fallback auf Deutsch
      if (typeof I18n !== 'undefined' && I18n.t) {
        return I18n.t(`knowledge_graph.${de}`) || de;
      }
      return de;
    },

    destroy() {
      if (this.cy) {
        this.cy.destroy();
        this.cy = null;
      }
    }
  };

  // Registriere Tab
  window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
  window.Ninko._pluginTabs[TAB_ID] = KnowledgeGraphTab;

  // Wenn Tab bereits aktiv, initialisiere sofort
  if (document.querySelector('.tab-btn.active[data-tab="knowledge_graph"]')) {
    KnowledgeGraphTab.init();
  }
})();
