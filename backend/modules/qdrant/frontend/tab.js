/**
 * Qdrant Knowledge Bank – Dashboard Tab
 * IIFE-Pattern (kein ES-Modul import/export)
 */
(async function initQdrantTab() {

    const API = '/api/qdrant';

    const QdrantTab = {
        currentConnectionId: '',
        currentCollection: '',
        entryOffset: 0,
        entryLimit: 20,

        // ── Init ────────────────────────────────────────────────────────────

        async init() {
            await this.loadConnections();
            await this.loadCollections();
            await this.loadEntries(0);

            document.getElementById('qdrant-connection-select')
                ?.addEventListener('change', async (e) => {
                    this.currentConnectionId = e.target.value;
                    await this.loadCollections();
                    await this.loadEntries(0);
                });

            document.getElementById('qdrant-collection-select')
                ?.addEventListener('change', async (e) => {
                    this.currentCollection = e.target.value;
                    const label = document.getElementById('qdrant-active-collection');
                    if (label) label.textContent = this.currentCollection || '-';
                    await this.loadEntries(0);
                });
        },

        async refresh() {
            await Promise.all([this.loadCollections(), this.loadEntries(0)]);
        },

        // ── Verbindungen ────────────────────────────────────────────────────

        async loadConnections() {
            try {
                const res = await fetch('/api/connections/qdrant');
                const data = await res.json();
                const conns = data.connections || [];
                const select = document.getElementById('qdrant-connection-select');
                if (!select) return;

                if (conns.length === 0) {
                    select.innerHTML = '<option value="">Keine Qdrant-Verbindungen</option>';
                    this.currentConnectionId = '';
                    return;
                }

                select.innerHTML = conns.map(c =>
                    `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})${c.is_default ? ' ★' : ''}</option>`
                ).join('');

                const def = conns.find(c => c.is_default) || conns[0];
                this.currentConnectionId = def.id;
                this._connections = conns;

                // Edit-Button neben Select anzeigen
                const editBtn = document.getElementById('qdrant-conn-edit-btn');
                if (editBtn) editBtn.style.display = 'inline-flex';
            } catch (err) {
                console.error('Qdrant Connections Fehler:', err);
            }
        },

        _qs(extra = {}) {
            const p = new URLSearchParams();
            if (this.currentConnectionId) p.append('connection_id', this.currentConnectionId);
            for (const [k, v] of Object.entries(extra)) p.append(k, String(v));
            const s = p.toString();
            return s ? `?${s}` : '';
        },

        // ── Collections ─────────────────────────────────────────────────────

        async loadCollections() {
            const grid = document.getElementById('qdrant-collections-grid');
            const collSelect = document.getElementById('qdrant-collection-select');
            if (!grid) return;

            try {
                const res = await fetch(`${API}/collections${this._qs()}`);
                if (!res.ok) throw new Error('API Fehler ' + res.status);
                const cols = await res.json();

                // Stats
                const totalCols = cols.filter(c => !c.info && !c.error).length;
                const totalVecs = cols.reduce((s, c) => s + (c.vectors_count || 0), 0);
                const el = document.getElementById('qdrant-total-collections');
                const ev = document.getElementById('qdrant-total-vectors');
                if (el) el.textContent = totalCols;
                if (ev) ev.textContent = totalVecs.toLocaleString('de-DE');

                // Collection-Select befüllen
                if (collSelect) {
                    const validCols = cols.filter(c => c.name);
                    collSelect.innerHTML = '<option value="">Alle Collections</option>' +
                        validCols.map(c =>
                            `<option value="${c.name}" ${c.name === this.currentCollection ? 'selected' : ''}>${c.name} (${(c.vectors_count || 0).toLocaleString('de-DE')} Vektoren)</option>`
                        ).join('');
                }

                if (!cols.length || (cols.length === 1 && cols[0].info)) {
                    grid.innerHTML = '<p class="empty-state">Keine Collections vorhanden. Erstelle eine mit "+ Neue Collection".</p>';
                    return;
                }

                grid.innerHTML = cols
                    .filter(c => c.name)
                    .map(c => `
                        <div class="status-card" style="cursor:pointer;text-align:left;"
                             onclick="QdrantTab.selectCollection('${c.name}')">
                            <div style="display:flex;justify-content:space-between;align-items:flex-start;width:100%;">
                                <strong style="color:var(--text-color);font-size:0.95rem;">${c.name}</strong>
                                <span class="status-badge ${c.status === 'green' || c.status === 'ok' ? 'status-ok' : 'status-unknown'}"
                                      style="font-size:0.7rem;">${c.status}</span>
                            </div>
                            <div style="margin-top:0.5rem;color:var(--text-muted);font-size:0.8rem;">
                                📊 ${(c.vectors_count || 0).toLocaleString('de-DE')} Vektoren<br>
                                📐 Dimension: ${c.vector_size || '-'}
                            </div>
                        </div>
                    `).join('');

            } catch (err) {
                console.error('Qdrant Collections Fehler:', err);
                grid.innerHTML = '<p class="empty-state text-error">Fehler beim Laden der Collections.</p>';
            }
        },

        selectCollection(name) {
            this.currentCollection = name;
            const sel = document.getElementById('qdrant-collection-select');
            if (sel) sel.value = name;
            const label = document.getElementById('qdrant-active-collection');
            if (label) label.textContent = name;
            this.loadEntries(0);
        },

        // ── Suche ───────────────────────────────────────────────────────────

        async doSearch() {
            const query = document.getElementById('qdrant-search-query')?.value?.trim();
            if (!query) return;

            const category = document.getElementById('qdrant-search-category')?.value?.trim() || '';
            const topK = parseInt(document.getElementById('qdrant-search-topk')?.value || '5', 10);
            const resultsDiv = document.getElementById('qdrant-search-results');
            if (resultsDiv) resultsDiv.innerHTML = '<p class="empty-state">Suche…</p>';

            try {
                const qs = this.currentConnectionId ? `?connection_id=${this.currentConnectionId}` : '';
                const res = await fetch(`${API}/search${qs}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query,
                        collection: this.currentCollection,
                        top_k: topK,
                        category: category || null,
                    }),
                });
                const results = await res.json();

                if (!resultsDiv) return;
                if (!results.length || results[0]?.info || results[0]?.error) {
                    resultsDiv.innerHTML = `<p class="empty-state">${results[0]?.info || results[0]?.error || 'Keine Treffer.'}</p>`;
                    return;
                }

                resultsDiv.innerHTML = results.map((r, i) => `
                    <div class="k8s-section" style="margin-bottom:0.75rem;padding:1rem;">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;">
                            <div style="flex:1;">
                                <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;">
                                    <strong style="color:var(--text-color);">${i + 1}. ${r.title || '(kein Titel)'}</strong>
                                    <span class="status-badge status-ok" style="font-size:0.7rem;">
                                        Score: ${(r.score * 100).toFixed(1)}%
                                    </span>
                                    ${r.category ? `<span class="status-badge status-unknown" style="font-size:0.7rem;">${r.category}</span>` : ''}
                                </div>
                                <p style="color:var(--text-secondary);font-size:0.875rem;margin:0 0 0.4rem 0;line-height:1.5;">${r.content}</p>
                                <div style="font-size:0.75rem;color:var(--text-muted);">
                                    ${r.tags?.length ? '🏷️ ' + r.tags.join(', ') + ' · ' : ''}
                                    ${r.source ? '🔗 ' + r.source + ' · ' : ''}
                                    ${r.chunk_total > 1 ? `Chunk ${r.chunk_index + 1}/${r.chunk_total}` : ''}
                                </div>
                            </div>
                            <button class="btn btn-sm" style="color:var(--accent-red);border-color:var(--accent-red);"
                                    onclick="QdrantTab.confirmDelete('${r.id}', '${(r.title || '').replace(/'/g, "\\'")}')">
                                🗑
                            </button>
                        </div>
                    </div>
                `).join('');

            } catch (err) {
                console.error('Qdrant Suche Fehler:', err);
                if (resultsDiv) resultsDiv.innerHTML = '<p class="empty-state text-error">Fehler bei der Suche.</p>';
            }
        },

        // ── Einträge ────────────────────────────────────────────────────────

        async loadEntries(offset) {
            this.entryOffset = offset;
            const tbody = document.getElementById('qdrant-entries-tbody');
            const pager = document.getElementById('qdrant-pagination');
            if (!tbody) return;

            tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Lade…</td></tr>';

            try {
                const category = document.getElementById('qdrant-filter-category')?.value?.trim() || '';
                const params = {
                    collection: this.currentCollection,
                    limit: this.entryLimit,
                    offset,
                };
                if (category) params.category = category;

                const res = await fetch(`${API}/entries${this._qs(params)}`);
                if (!res.ok) throw new Error('API Fehler ' + res.status);
                const data = await res.json();
                const entries = data.entries || [];

                if (!entries.length) {
                    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Keine Einträge gefunden.</td></tr>';
                    if (pager) pager.innerHTML = '';
                    return;
                }

                tbody.innerHTML = entries.map(e => `
                    <tr>
                        <td class="pod-name" title="${e.title}">${e.title || '—'}</td>
                        <td><span class="status-badge status-unknown">${e.category || '—'}</span></td>
                        <td style="font-size:0.8rem;color:var(--text-muted);">${(e.tags || []).join(', ') || '—'}</td>
                        <td style="font-size:0.8rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${e.source}">${e.source || '—'}</td>
                        <td style="font-size:0.8rem;color:var(--text-muted);">${e.created_at ? e.created_at.slice(0, 10) : '—'}</td>
                        <td style="font-size:0.8rem;color:var(--text-muted);">${e.chunk_total > 1 ? e.chunk_index + 1 + '/' + e.chunk_total : '—'}</td>
                        <td>
                            <button class="btn btn-sm" style="color:var(--accent-red);border-color:var(--accent-red);"
                                    onclick="QdrantTab.confirmDelete('${e.id}', '${(e.title || '').replace(/'/g, "\\'")}')">🗑</button>
                        </td>
                    </tr>
                `).join('');

                // Pagination
                if (pager) {
                    const prevDisabled = offset === 0 ? 'disabled' : '';
                    const nextDisabled = entries.length < this.entryLimit ? 'disabled' : '';
                    pager.innerHTML = `
                        <button class="btn btn-sm" onclick="QdrantTab.loadEntries(${Math.max(0, offset - this.entryLimit)})" ${prevDisabled}>← Zurück</button>
                        <span style="color:var(--text-muted);font-size:0.85rem;">Einträge ${offset + 1}–${offset + entries.length}</span>
                        <button class="btn btn-sm" onclick="QdrantTab.loadEntries(${offset + this.entryLimit})" ${nextDisabled}>Weiter →</button>
                    `;
                }

            } catch (err) {
                console.error('Qdrant Entries Fehler:', err);
                tbody.innerHTML = '<tr><td colspan="7" class="empty-state text-error">Fehler beim Laden.</td></tr>';
            }
        },

        // ── Eintrag speichern ───────────────────────────────────────────────

        async saveEntry() {
            const btn = document.getElementById('qdrant-save-btn');
            const content = document.getElementById('qdrant-add-content')?.value?.trim();
            if (!content) { showNotification('Inhalt ist erforderlich.', 'error'); return; }

            if (btn) btn.disabled = true;
            try {
                const qs = this.currentConnectionId ? `?connection_id=${this.currentConnectionId}` : '';
                const res = await fetch(`${API}/entries${qs}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        content,
                        title: document.getElementById('qdrant-add-title')?.value?.trim() || '',
                        category: document.getElementById('qdrant-add-category')?.value?.trim() || 'general',
                        tags: (document.getElementById('qdrant-add-tags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
                        source: document.getElementById('qdrant-add-source')?.value?.trim() || '',
                        collection: document.getElementById('qdrant-add-collection')?.value?.trim() || this.currentCollection,
                    }),
                });
                const data = await res.json();
                if (res.ok) {
                    showNotification(data.message || 'Gespeichert', 'success');
                    this.showPanel(null);
                    this._clearAddForm();
                    await this.refresh();
                } else {
                    showNotification('Fehler: ' + (data.error || 'Unbekannt'), 'error');
                }
            } catch (err) {
                showNotification('Fehler beim Speichern', 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        },

        _clearAddForm() {
            ['qdrant-add-title', 'qdrant-add-content', 'qdrant-add-tags',
             'qdrant-add-source', 'qdrant-add-collection'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = id === 'qdrant-add-category' ? 'general' : '';
            });
        },

        // ── Collection erstellen ─────────────────────────────────────────────

        async createCollection() {
            const name = document.getElementById('qdrant-new-collection-name')?.value?.trim();
            if (!name) { showNotification('Name ist erforderlich.', 'error'); return; }
            if (!/^[a-zA-Z0-9_\-]+$/.test(name)) {
                showNotification('Nur a-z, 0-9, _ und - erlaubt.', 'error'); return;
            }

            try {
                const qs = this.currentConnectionId ? `?connection_id=${this.currentConnectionId}` : '';
                const res = await fetch(`${API}/collections${qs}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name }),
                });
                const data = await res.json();
                if (res.ok) {
                    showNotification(data.message || `Collection '${name}' erstellt.`, 'success');
                    this.showPanel(null);
                    document.getElementById('qdrant-new-collection-name').value = '';
                    await this.loadCollections();
                } else {
                    showNotification('Fehler: ' + (data.error || 'Unbekannt'), 'error');
                }
            } catch (err) {
                showNotification('Fehler beim Erstellen', 'error');
            }
        },

        // ── Löschen ──────────────────────────────────────────────────────────

        async confirmDelete(pointId, title) {
            if (!confirm(`Eintrag "${title}" wirklich löschen?`)) return;
            try {
                const qs = this._qs({ collection: this.currentCollection });
                const res = await fetch(`${API}/entries/${pointId}${qs}`, { method: 'DELETE' });
                const data = await res.json();
                if (res.ok) {
                    showNotification(data.message || 'Gelöscht', 'success');
                    await this.refresh();
                    // Suchergebnisse leeren falls der Eintrag dort angezeigt war
                    const sr = document.getElementById('qdrant-search-results');
                    if (sr) sr.innerHTML = '';
                } else {
                    showNotification('Fehler: ' + (data.error || 'Unbekannt'), 'error');
                }
            } catch (err) {
                showNotification('Fehler beim Löschen', 'error');
            }
        },

        // ── Verbindungen verwalten ───────────────────────────────────────────

        editCurrentConnection() {
            const conn = (this._connections || []).find(c => c.id === this.currentConnectionId);
            this.showConnForm(conn || null);
        },

        showConnForm(conn = null) {
            document.getElementById('qdrant-conn-edit-id').value = conn ? conn.id : '';
            document.getElementById('qdrant-conn-form-title').textContent = conn ? 'Verbindung bearbeiten' : 'Verbindung hinzufügen';
            document.getElementById('qdrant-conn-name').value = conn?.name || '';
            document.getElementById('qdrant-conn-env').value = conn?.environment || 'local';
            document.getElementById('qdrant-conn-url').value = conn?.config?.url || '';
            document.getElementById('qdrant-conn-collection').value = conn?.config?.default_collection || '';
            document.getElementById('qdrant-conn-apikey').value = '';
            document.getElementById('qdrant-conn-desc').value = conn?.description || '';
            document.getElementById('qdrant-conn-default').checked = conn?.is_default || false;
            const delBtn = document.getElementById('qdrant-conn-delete-btn');
            if (delBtn) delBtn.style.display = conn ? 'inline-flex' : 'none';
            this.showPanel('conn-form');
        },

        async saveConnection() {
            const btn = document.getElementById('qdrant-conn-save-btn');
            const url = document.getElementById('qdrant-conn-url').value.trim();
            const name = document.getElementById('qdrant-conn-name').value.trim();
            if (!name || !url) { showNotification('Name und URL sind erforderlich.', 'error'); return; }

            btn.disabled = true;
            try {
                const editId = document.getElementById('qdrant-conn-edit-id').value;
                const apiKey = document.getElementById('qdrant-conn-apikey').value;
                const body = {
                    name,
                    environment: document.getElementById('qdrant-conn-env').value,
                    description: document.getElementById('qdrant-conn-desc').value.trim() || null,
                    is_default: document.getElementById('qdrant-conn-default').checked,
                    config: {
                        url,
                        default_collection: document.getElementById('qdrant-conn-collection').value.trim() || 'ninko_knowledge',
                    },
                    secrets: apiKey ? { api_key: apiKey } : {},
                };
                const method = editId ? 'PUT' : 'POST';
                const endpoint = editId ? `/api/connections/qdrant/${editId}` : '/api/connections/qdrant';
                const res = await fetch(endpoint, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
                showNotification(`Verbindung "${name}" gespeichert.`, 'success');
                this.showPanel(null);
                await this.loadConnections();
                await this.loadCollections();
            } catch (err) {
                showNotification('Fehler: ' + err.message, 'error');
            } finally {
                btn.disabled = false;
            }
        },

        async deleteConnection() {
            const editId = document.getElementById('qdrant-conn-edit-id').value;
            const name = document.getElementById('qdrant-conn-name').value;
            if (!editId || !confirm(`Verbindung "${name}" wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/connections/qdrant/${editId}`, { method: 'DELETE' });
                if (res.ok || res.status === 204) {
                    showNotification(`Verbindung "${name}" gelöscht.`, 'info');
                    this.showPanel(null);
                    await this.loadConnections();
                } else {
                    showNotification('Fehler beim Löschen.', 'error');
                }
            } catch (err) {
                showNotification('Fehler: ' + err.message, 'error');
            }
        },

        // ── UI-Hilfsfunktionen ───────────────────────────────────────────────

        showPanel(name) {
            ['add', 'collection', 'conn-form'].forEach(p => {
                const el = document.getElementById(`qdrant-${p}-panel`);
                if (el) el.style.display = name === p ? 'block' : 'none';
            });
        },

        destroy() {},
    };

    window.QdrantTab = QdrantTab;

})();
