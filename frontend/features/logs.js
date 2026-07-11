/**
 * Ninko Logs Feature Module
 *
 * Log-Viewer (Settings → Logs): Polling, Level-/Kategorie-/Zeit-Filter,
 * Tabellen-Rendering, Detail-Panel, CSV-/JSON-Export. Aus app.js
 * extrahiert; via Object.assign gemergt. Start/Stop des Pollings ruft
 * app.js beim Tab-Wechsel via this.*. Die geteilten Escape-Helfer
 * (_escapeHtml, _escapeAttr, _esc) bleiben in app.js.
 */

(function() {
    'use strict';

    const LogsFeature = {
        _logActiveLevels: new Set(['INFO', 'WARN', 'ERROR', 'CRIT']),
        _logAutoScroll: true,
        _logPollTimer: null,
        _logCache: [],

        async startLogPolling() {
            clearInterval(this._logPollTimer);
            await this.applyLogFilters();
            this._logPollTimer = setInterval(() => this.applyLogFilters(), 2000);
        },

        stopLogPolling() { clearInterval(this._logPollTimer); },

        toggleLogLevel(level, btn) {
            if (this._logActiveLevels.has(level)) {
                this._logActiveLevels.delete(level);
                btn.classList.remove('active');
            } else {
                this._logActiveLevels.add(level);
                btn.classList.add('active');
            }
            this.applyLogFilters();
        },

        async applyLogFilters() {
            const params = new URLSearchParams();
            if (this._logActiveLevels.size < 4 && this._logActiveLevels.size > 0) {
                params.set('level', [...this._logActiveLevels].join(','));
            }
            const cat = document.getElementById('log-filter-category')?.value;
            if (cat) params.set('category', cat);
            const search = document.getElementById('log-filter-search')?.value;
            if (search) params.set('search', search);
            const time = document.getElementById('log-filter-time')?.value;
            if (time) params.set('from_ts', (Date.now() / 1000 - parseInt(time) * 60).toString());
            params.set('limit', '500');

            try {
                const res = await fetch(`/api/logs/?${params}`);
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                this._logCache = data.entries || [];
                this._renderLogs();
            } catch (err) { console.warn('loadLogs failed', err); }
        },

        _renderLogs() {
            const tbody = document.getElementById('log-table-body');
            if (!tbody) return;
            if (!this._logCache.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Keine Log-Einträge gefunden.</td></tr>';
                return;
            }
            const levelColors = { INFO: 'log-info', WARN: 'log-warn', ERROR: 'log-error', CRIT: 'log-crit' };
            // Älteste zuerst anzeigen (neueste am Ende, Auto-Scroll zeigt aktuellste)
            const displayEntries = [...this._logCache].reverse();
            tbody.innerHTML = displayEntries.map((entry, idx) => `
                <tr class="log-row log-row-${(entry.level || 'INFO').toLowerCase()}" data-action="_showLogDetail" data-args="${JSON.stringify([this._logCache.length - 1 - idx]).replace(/\"/g, '&quot;')}">
                    <td class="log-ts">${entry.timestamp || ''}</td>
                    <td><span class="log-level-badge ${levelColors[entry.level] || 'log-info'}">${entry.level || 'INFO'}</span></td>
                    <td class="log-cat">${entry.category || ''}</td>
                    <td class="log-msg">${this._escapeHtml(entry.message || '')}</td>
                </tr>
            `).join('');
            if (this._logAutoScroll) {
                const wrapper = document.getElementById('log-table-wrapper');
                if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
            }
        },

        hideLogDetailPanel() {
            const p = document.getElementById('log-detail-panel');
            if (p) p.classList.add('hidden');
        },

        _showLogDetail(idx) {
            const entry = this._logCache[idx];
            if (!entry) return;
            const panel = document.getElementById('log-detail-panel');
            const content = document.getElementById('log-detail-content');
            panel.classList.remove('hidden');
            content.innerHTML = `
                <p><strong>Timestamp:</strong> ${entry.timestamp}</p>
                <p><strong>Level:</strong> ${entry.level}</p>
                <p><strong>Logger:</strong> ${entry.logger}</p>
                <p><strong>Kategorie:</strong> ${entry.category}</p>
                <p><strong>Message:</strong><br><code>${this._escapeHtml(entry.message || '')}</code></p>
                ${entry.traceback ? `<p><strong>Traceback:</strong></p><pre class="log-traceback">${this._escapeHtml(entry.traceback)}</pre>` : ''}
            `;
        },

        toggleLogAutoScroll(enabled) { this._logAutoScroll = enabled; },

        exportLogs(format) {
            const data = this._logCache;
            if (!data.length) { showNotification('Keine Daten zum Exportieren', 'info'); return; }
            let content, type, ext;
            if (format === 'json') {
                content = JSON.stringify(data, null, 2);
                type = 'application/json'; ext = 'json';
            } else {
                const header = 'Timestamp,Level,Kategorie,Message\n';
                content = header + data.map(e => `"${e.timestamp}","${e.level}","${e.category}","${(e.message || '').replace(/"/g, "'")}"`).join('\n');
                type = 'text/csv'; ext = 'csv';
            }
            const blob = new Blob([content], { type });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a'); a.href = url; a.download = `ninko-logs.${ext}`;
            a.click(); URL.revokeObjectURL(url);
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, LogsFeature);
    } else {
        window.LogsFeature = LogsFeature;
    }
})();
