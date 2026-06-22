const DataVizTab = {
    charts: [],
    currentFormat: 'png',
    _retryStatuses: new Set([405, 408, 429, 502, 503, 504]),

    async init() {
        this.setupEventListeners();
        this.loadHistory();
        this.refreshStats();

        if (!window.mermaid) {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
            script.onload = () => {
                mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'dark' });
            };
            document.head.appendChild(script);
        }
    },

    setupEventListeners() {
        const generateBtn = document.getElementById('generate-chart');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.generateChart());
        }

        const renderBtn = document.getElementById('render-mermaid');
        if (renderBtn) {
            renderBtn.addEventListener('click', () => this.renderMermaid());
        }
    },

    setFormat(format) {
        this.currentFormat = format;
        document.querySelectorAll('.format-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.format === format);
        });
    },

    async _fetchWithRetry(url, options = {}, retries = 2) {
        let lastError = null;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const response = await fetch(url, options);
                if (response.ok || !this._retryStatuses.has(response.status) || attempt === retries) {
                    return response;
                }
                // Kurzer Backoff für Rollout-/Warmup-Phasen im Backend
                await new Promise(resolve => setTimeout(resolve, 250 * (attempt + 1)));
            } catch (error) {
                lastError = error;
                if (attempt === retries) throw error;
                await new Promise(resolve => setTimeout(resolve, 250 * (attempt + 1)));
            }
        }
        throw lastError || new Error('Request failed');
    },

    async _buildHttpError(response) {
        const status = response?.status || 0;
        let detail = '';
        try {
            const text = await response.text();
            if (text) {
                try {
                    const parsed = JSON.parse(text);
                    detail = parsed.detail || parsed.error || '';
                } catch (_) {
                    detail = text.slice(0, 200);
                }
            }
        } catch (_) {
            // ignore read errors
        }
        return detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`;
    },

    async generateChart() {
        const type = document.getElementById('chart-type').value;
        const title = document.getElementById('chart-title').value;
        const dataStr = document.getElementById('chart-data').value;
        const xLabel = document.getElementById('chart-xlabel').value;
        const yLabel = document.getElementById('chart-ylabel').value;
        const format = this.currentFormat;

        const outputDiv = document.getElementById('chart-preview-container');

        if (!dataStr.trim()) {
            outputDiv.innerHTML = '<div class="empty-state" style="color: var(--color-red);"><p>Bitte Daten im JSON-Format eingeben</p></div>';
            return;
        }

        try {
            const data = JSON.parse(dataStr);
            outputDiv.innerHTML = '<div class="empty-state"><p>Generiere Diagramm...</p></div>';

            if (format === 'html') {
                const response = await this._fetchWithRetry('/api/dataviz/chart/interactive', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chart_type: type,
                        title,
                        data,
                        x_label: xLabel,
                        y_label: yLabel,
                        format: 'html'
                    })
                });
                if (!response.ok) {
                    throw new Error(await this._buildHttpError(response));
                }
                const html = await response.text();
                // XSS-Schutz: Interaktive Charts in isoliertem iframe anzeigen
                outputDiv.innerHTML = `<iframe srcdoc="${html.replace(/"/g, '&quot;')}" style="width:100%; height:400px; border:none; border-radius:4px;"></iframe>`;
            } else {
                const response = await this._fetchWithRetry('/api/dataviz/chart', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chart_type: type,
                        title,
                        data,
                        x_label: xLabel,
                        y_label: yLabel,
                        format
                    })
                });
                if (!response.ok) {
                    throw new Error(await this._buildHttpError(response));
                }
                const result = await response.json();

                if (result.success) {
                    if (format === 'png') {
                        outputDiv.innerHTML = `<img src="${result.data}" alt="${this.escapeHtml(title)}" style="max-width:100%; border-radius: 4px;">`;
                    } else if (format === 'svg') {
                        const wrapper = document.createElement('div');
                        wrapper.style.background = 'white';
                        wrapper.style.padding = '1rem';
                        wrapper.style.borderRadius = '4px';
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(result.data, 'image/svg+xml');
                        const svgEl = doc.documentElement;
                        if (svgEl && svgEl.nodeName.toLowerCase() === 'svg') {
                            const scripts = svgEl.querySelectorAll('script');
                            scripts.forEach(s => s.remove());
                            svgEl.querySelectorAll('*').forEach(el => {
                                Array.from(el.attributes).forEach(attr => {
                                    if (/^on/i.test(attr.name)) el.removeAttribute(attr.name);
                                });
                            });
                            wrapper.appendChild(document.importNode(svgEl, true));
                        }
                        outputDiv.innerHTML = '';
                        outputDiv.appendChild(wrapper);
                    }
                    this.saveToHistory(title || 'Chart', type, result.data, format);
                    this.refreshStats();
                } else {
                    outputDiv.innerHTML = `<div class="empty-state" style="color: var(--color-red);"><p>Fehler: ${this.escapeHtml(result.error)}</p></div>`;
                }
            }
        } catch (e) {
            outputDiv.innerHTML = `<div class="empty-state" style="color: var(--color-red);"><p>Fehler: ${this.escapeHtml(e.message)}</p></div>`;
        }
    },

    async renderMermaid() {
        const code = document.getElementById('mermaid-code').value;
        const type = document.getElementById('mermaid-type').value;
        const title = document.getElementById('mermaid-title').value;
        const outputDiv = document.getElementById('mermaid-preview-container');

        if (!code.trim()) {
            outputDiv.innerHTML = '<div class="empty-state" style="color: var(--color-red);"><p>Bitte Mermaid-Code eingeben</p></div>';
            return;
        }

        try {
            outputDiv.innerHTML = '<div class="empty-state"><p>Rendere Diagramm...</p></div>';

            const response = await this._fetchWithRetry('/api/dataviz/mermaid', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    diagram_type: type,
                    code,
                    title,
                    format: 'svg'
                })
            });

            if (!response.ok) {
                throw new Error(await this._buildHttpError(response));
            }

            const html = await response.text();

            outputDiv.innerHTML = `
                <iframe srcdoc="${html.replace(/"/g, '&quot;')}"
                        style="width:100%; height:400px; border:none; border-radius: 4px; background: white;">
                </iframe>
            `;

            this.saveToHistory(title || 'Mermaid Diagramm', 'mermaid', code, 'svg');
            this.refreshStats();
        } catch (e) {
            outputDiv.innerHTML = `<div class="empty-state" style="color: var(--color-red);"><p>Fehler: ${this.escapeHtml(e.message)}</p></div>`;
        }
    },

    saveToHistory(title, type, data, format) {
        const chart = {
            id: Date.now(),
            title: title || 'Unbenannt',
            type,
            format,
            data,
            timestamp: new Date().toLocaleString('de-DE')
        };
        this.charts.unshift(chart);
        if (this.charts.length > 50) this.charts.pop();
        localStorage.setItem('dataviz_charts', JSON.stringify(this.charts));
        this.updateHistoryUI();
    },

    loadHistory() {
        const saved = localStorage.getItem('dataviz_charts');
        if (saved) {
            try {
                this.charts = JSON.parse(saved);
                this.updateHistoryUI();
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        }
    },

    updateHistoryUI() {
        const tbody = document.getElementById('dv-history-tbody');
        if (!tbody) return;

        if (this.charts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Noch keine Diagramme erstellt</td></tr>';
            return;
        }

        tbody.innerHTML = this.charts.map(chart => {
            const typeLabels = {
                line: 'Linie',
                bar: 'Balken',
                pie: 'Kreis',
                scatter: 'Scatter',
                area: 'Fläche',
                mermaid: 'Mermaid'
            };
            const typeLabel = typeLabels[chart.type] || chart.type;
            const formatLabel = chart.format ? chart.format.toUpperCase() : '-';

            return `
                <tr>
                    <td>${this.escapeHtml(chart.title)}</td>
                    <td><span class="status-badge" style="font-size: 0.75rem;">${typeLabel}</span></td>
                    <td>${formatLabel}</td>
                    <td style="font-size: 0.8rem; color: var(--text-muted);">${chart.timestamp}</td>
                    <td>
                        <div style="display: flex; gap: 0.5rem;">
                            ${chart.format !== 'mermaid' && chart.data ? `
                                <button class="btn btn-sm btn-action" onclick="DataVizTab.downloadChart(${chart.id})">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                </button>
                            ` : ''}
                            <button class="btn btn-sm btn-action" onclick="DataVizTab.deleteChart(${chart.id})" style="color: var(--color-red);">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    },

    refreshStats() {
        const totalCharts = this.charts.filter(c => c.type !== 'mermaid').length;
        const mermaidCount = this.charts.filter(c => c.type === 'mermaid').length;
        const exportCount = this.charts.filter(c => c.format === 'png' || c.format === 'svg').length;

        const lastChart = this.charts.find(c => c.type !== 'mermaid');
        const lastChartLabel = lastChart ? (lastChart.type.charAt(0).toUpperCase() + lastChart.type.slice(1)) : '-';

        const elTotal = document.getElementById('dv-total-charts');
        const elMermaid = document.getElementById('dv-mermaid-count');
        const elLast = document.getElementById('dv-last-chart');
        const elExport = document.getElementById('dv-export-count');

        if (elTotal) elTotal.textContent = totalCharts;
        if (elMermaid) elMermaid.textContent = mermaidCount;
        if (elLast) elLast.textContent = lastChartLabel;
        if (elExport) elExport.textContent = exportCount;
    },

    downloadChart(id) {
        const chart = this.charts.find(c => c.id === id);
        if (!chart || !chart.data) return;

        if (chart.format === 'png' && chart.data.startsWith('data:image')) {
            const link = document.createElement('a');
            link.href = chart.data;
            link.download = `${chart.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.png`;
            link.click();
        } else if (chart.format === 'svg') {
            const blob = new Blob([chart.data], { type: 'image/svg+xml' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${chart.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.svg`;
            link.click();
            URL.revokeObjectURL(url);
        }
    },

    deleteChart(id) {
        this.charts = this.charts.filter(c => c.id !== id);
        localStorage.setItem('dataviz_charts', JSON.stringify(this.charts));
        this.updateHistoryUI();
        this.refreshStats();
    },

    clearHistory() {
        if (confirm('Alle Diagramme aus dem Verlauf löschen?')) {
            this.charts = [];
            localStorage.removeItem('dataviz_charts');
            this.updateHistoryUI();
            this.refreshStats();
        }
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

if (typeof Ninko !== 'undefined') {
    Ninko.DataVizTab = DataVizTab;
}
