const DataVizTab = {
    charts: [],
    
    async init() {
        this.setupEventListeners();
        this.loadHistory();
        
        // Mermaid.js laden falls noch nicht vorhanden
        if (!window.mermaid) {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
            script.onload = () => {
                mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
            };
            document.head.appendChild(script);
        }
    },
    
    setupEventListeners() {
        // Tab Switching
        document.querySelectorAll('.dataviz-tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabId = e.target.dataset.tab;
                this.switchTab(tabId);
            });
        });
        
        // Chart Generation
        const generateBtn = document.getElementById('generate-chart');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.generateChart());
        }
        
        // Mermaid Rendering
        const renderBtn = document.getElementById('render-mermaid');
        if (renderBtn) {
            renderBtn.addEventListener('click', () => this.renderMermaid());
        }
    },
    
    switchTab(tabId) {
        document.querySelectorAll('.dataviz-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });
        document.querySelectorAll('.dataviz-panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `${tabId}-tab`);
        });
    },
    
    async generateChart() {
        const type = document.getElementById('chart-type').value;
        const title = document.getElementById('chart-title').value;
        const dataStr = document.getElementById('chart-data').value;
        const xLabel = document.getElementById('chart-xlabel').value;
        const yLabel = document.getElementById('chart-ylabel').value;
        const format = document.getElementById('chart-format').value;
        
        try {
            const data = JSON.parse(dataStr);
            const outputDiv = document.getElementById('chart-output');
            outputDiv.innerHTML = '<p>Generiere Diagramm...</p>';
            
            if (format === 'html') {
                // Interaktives Plotly-Diagramm
                const response = await fetch('/api/dataviz/chart/interactive', {
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
                const html = await response.text();
                outputDiv.innerHTML = html;
            } else {
                // Statisches Bild (PNG/SVG)
                const response = await fetch('/api/dataviz/chart', {
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
                const result = await response.json();
                
                if (result.success) {
                    if (format === 'png') {
                        outputDiv.innerHTML = `<img src="${result.data}" alt="${title}" style="max-width:100%">`;
                    } else if (format === 'svg') {
                        outputDiv.innerHTML = result.data;
                    }
                    this.saveToHistory(title, type, result.data);
                } else {
                    outputDiv.innerHTML = `<p class="error">Fehler: ${result.error}</p>`;
                }
            }
        } catch (e) {
            document.getElementById('chart-output').innerHTML = 
                `<p class="error">Fehler: ${e.message}</p>`;
        }
    },
    
    async renderMermaid() {
        const code = document.getElementById('mermaid-code').value;
        const type = document.getElementById('mermaid-type').value;
        const title = document.getElementById('mermaid-title').value;
        const outputDiv = document.getElementById('mermaid-output');
        
        if (!code.trim()) {
            outputDiv.innerHTML = '<p class="error">Bitte Mermaid-Code eingeben</p>';
            return;
        }
        
        try {
            outputDiv.innerHTML = '<p>Rendere Diagramm...</p>';
            
            const response = await fetch('/api/dataviz/mermaid', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    diagram_type: type,
                    code,
                    title,
                    format: 'svg'
                })
            });
            const html = await response.text();
            
            // In einem iframe anzeigen für Isolation
            outputDiv.innerHTML = `
                <iframe srcdoc="${html.replace(/"/g, '&quot;')}" 
                        style="width:100%;height:500px;border:none;">
                </iframe>
            `;
            
            this.saveToHistory(title || 'Mermaid Diagramm', 'mermaid', code);
        } catch (e) {
            outputDiv.innerHTML = `<p class="error">Fehler: ${e.message}</p>`;
        }
    },
    
    saveToHistory(title, type, data) {
        const chart = {
            id: Date.now(),
            title: title || 'Unbenannt',
            type,
            data,
            timestamp: new Date().toLocaleString()
        };
        this.charts.unshift(chart);
        if (this.charts.length > 20) this.charts.pop();
        localStorage.setItem('dataviz_charts', JSON.stringify(this.charts));
        this.updateHistoryUI();
    },
    
    loadHistory() {
        const saved = localStorage.getItem('dataviz_charts');
        if (saved) {
            this.charts = JSON.parse(saved);
            this.updateHistoryUI();
        }
    },
    
    updateHistoryUI() {
        const container = document.getElementById('chart-history-list');
        if (this.charts.length === 0) {
            container.innerHTML = '<p class="placeholder">Noch keine Diagramme erstellt...</p>';
            return;
        }
        
        container.innerHTML = this.charts.map(chart => `
            <div class="history-item" data-id="${chart.id}">
                <div class="history-title">${chart.title}</div>
                <div class="history-meta">
                    <span class="history-type">${chart.type}</span>
                    <span class="history-time">${chart.timestamp}</span>
                </div>
                <div class="history-actions">
                    <button onclick="DataVizTab.loadChart(${chart.id})">Laden</button>
                    <button onclick="DataVizTab.deleteChart(${chart.id})">Löschen</button>
                </div>
            </div>
        `).join('');
    },
    
    loadChart(id) {
        const chart = this.charts.find(c => c.id === id);
        if (!chart) return;
        
        if (chart.type === 'mermaid') {
            document.getElementById('mermaid-code').value = chart.data;
            this.switchTab('mermaid');
        } else {
            // Für Bild-Diagramme: Zeige im Output
            const outputDiv = document.getElementById('chart-output');
            outputDiv.innerHTML = `<img src="${chart.data}" style="max-width:100%">`;
            this.switchTab('chart');
        }
    },
    
    deleteChart(id) {
        this.charts = this.charts.filter(c => c.id !== id);
        localStorage.setItem('dataviz_charts', JSON.stringify(this.charts));
        this.updateHistoryUI();
    }
};

// Für Core-Module: Registrierung erfolgt in app.js:getTabObject()
// Diese Variable wird dort verwendet
if (typeof Ninko !== 'undefined') {
    Ninko.DataVizTab = DataVizTab;
}
