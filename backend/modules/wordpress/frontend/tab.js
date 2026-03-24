/**
 * WordPress Dashboard Tab – JavaScript
 * Globales Objekt: WordPressTab (für app.js:getTabObject())
 */
const WordPressTab = {
    API_PREFIX: '/api/wordpress',
    currentConnectionId: '',
    pollInterval: null,

    async init() {
        await this.loadConnections();
        if (this.currentConnectionId) {
            await this.refresh();
        }
        document.getElementById('wordpress-connection-select')
            ?.addEventListener('change', async (e) => {
                this.currentConnectionId = e.target.value;
                this.refresh();
            });
    },

    getQueryParams(additional = {}) {
        const params = new URLSearchParams();
        if (this.currentConnectionId) {
            params.append('connection_id', this.currentConnectionId);
        }
        for (const [k, v] of Object.entries(additional)) {
            params.append(k, String(v));
        }
        const str = params.toString();
        return str ? `?${str}` : '';
    },

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/wordpress');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('wordpress-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine WordPress Verbindungen</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${this.escapeHtml(c.name)} (${c.environment})</option>`
            ).join('');

            const def = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = def.id;
        } catch (err) {
            console.error('WP Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadSiteInfo(),
            this.loadPages('publish'),
            this.loadPosts('publish'),
            this.loadPlugins('all'),
            this.loadUsers(),
        ]);
    },

    showSection(name) {
        document.querySelectorAll('.wordpress-section').forEach(s => s.style.display = 'none');
        document.querySelectorAll('.wordpress-nav-btn').forEach(b => b.classList.remove('active'));
        const section = document.getElementById(`wordpress-section-${name}`);
        if (section) section.style.display = 'block';
        event.target.classList.add('active');
    },

    async loadSiteInfo() {
        try {
            const res = await fetch(`${this.API_PREFIX}/info${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Info API error");
            const info = await res.json();
            const container = document.getElementById('wordpress-info');
            if (!container) return;

            if (info.error) {
                container.innerHTML = `<p class="empty-state text-error">${this.escapeHtml(info.error)}</p>`;
                return;
            }

            container.innerHTML = `
                <div class="info-card">
                    <div class="info-label">Site</div>
                    <div class="info-value">${this.escapeHtml(info.name || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">WordPress</div>
                    <div class="info-value">${this.escapeHtml(info.wp_version || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">URL</div>
                    <div class="info-value"><a href="${this.escapeHtml(info.url || '#')}" target="_blank" style="color: var(--accent-blue);">${this.escapeHtml(info.url || '?')}</a></div>
                </div>
                <div class="info-card">
                    <div class="info-label">Sprache</div>
                    <div class="info-value">${this.escapeHtml(info.language || '?')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Zeitzone</div>
                    <div class="info-value">${this.escapeHtml(info.timezone || '?')}</div>
                </div>
            `;
        } catch (err) {
            console.error('WP Info Fehler:', err);
            const container = document.getElementById('wordpress-info');
            if (container) container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
        }
    },

    async loadPages(status) {
        try {
            const res = await fetch(`${this.API_PREFIX}/pages${this.getQueryParams({ status, per_page: 50 })}`);
            if (!res.ok) throw new Error("Pages API error");
            const pages = await res.json();
            const tbody = document.getElementById('wordpress-pages-tbody');
            if (!tbody) return;

            if (!pages.length || pages[0]?.error) {
                tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${pages[0]?.error ? this.escapeHtml(pages[0].error) : 'Keine Seiten gefunden.'}</td></tr>`;
                return;
            }

            tbody.innerHTML = pages.map(p => {
                const statusClass = p.status === 'publish' ? 'status-ok' : p.status === 'draft' ? 'status-warning' : p.status === 'trash' ? 'status-error' : '';
                return `<tr>
                    <td>${p.id}</td>
                    <td><strong>${this.escapeHtml(p.title || '(Ohne Titel)')}</strong></td>
                    <td><span class="status-badge ${statusClass}">${p.status}</span></td>
                    <td style="font-size:0.85em">${this.escapeHtml(p.modified?.split('T')[0] || '')}</td>
                    <td>${p.link ? `<a href="${this.escapeHtml(p.link)}" target="_blank" style="color: var(--primary-color);">↗</a>` : '-'}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('WP Pages Fehler:', err);
            const tbody = document.getElementById('wordpress-pages-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-state text-error">Fehler.</td></tr>';
        }
    },

    async loadPosts(status) {
        try {
            const res = await fetch(`${this.API_PREFIX}/posts${this.getQueryParams({ status, per_page: 50 })}`);
            if (!res.ok) throw new Error("Posts API error");
            const posts = await res.json();
            const tbody = document.getElementById('wordpress-posts-tbody');
            if (!tbody) return;

            if (!posts.length || posts[0]?.error) {
                tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${posts[0]?.error ? this.escapeHtml(posts[0].error) : 'Keine Beiträge gefunden.'}</td></tr>`;
                return;
            }

            tbody.innerHTML = posts.map(p => {
                const statusClass = p.status === 'publish' ? 'status-ok' : p.status === 'draft' ? 'status-warning' : '';
                return `<tr>
                    <td>${p.id}</td>
                    <td><strong>${this.escapeHtml(p.title || '(Ohne Titel)')}</strong></td>
                    <td><span class="status-badge ${statusClass}">${p.status}</span></td>
                    <td style="font-size:0.85em">${this.escapeHtml(p.modified?.split('T')[0] || '')}</td>
                    <td>${p.link ? `<a href="${this.escapeHtml(p.link)}" target="_blank" style="color: var(--primary-color);">↗</a>` : '-'}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('WP Posts Fehler:', err);
            const tbody = document.getElementById('wordpress-posts-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-state text-error">Fehler.</td></tr>';
        }
    },

    async loadPlugins(status) {
        try {
            const res = await fetch(`${this.API_PREFIX}/plugins${this.getQueryParams({ status })}`);
            if (!res.ok) throw new Error("Plugins API error");
            const plugins = await res.json();
            const tbody = document.getElementById('wordpress-plugins-tbody');
            if (!tbody) return;

            if (!plugins.length || plugins[0]?.error) {
                tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${plugins[0]?.error ? this.escapeHtml(plugins[0].error) : 'Keine Plugins gefunden.'}</td></tr>`;
                return;
            }

            tbody.innerHTML = plugins.map(p => {
                const statusClass = p.status === 'active' ? 'status-ok' : 'status-warning';
                const updateBadge = p.update_available ? '<span class="status-badge status-warning">Update</span>' : '<span class="status-badge status-ok">Aktuell</span>';
                return `<tr>
                    <td><strong>${this.escapeHtml(p.name)}</strong><br><code style="font-size:0.8em">${this.escapeHtml(p.slug)}</code></td>
                    <td>${this.escapeHtml(p.version)}</td>
                    <td><span class="status-badge ${statusClass}">${p.status === 'active' ? 'Aktiv' : 'Inaktiv'}</span></td>
                    <td>${updateBadge}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('WP Plugins Fehler:', err);
            const tbody = document.getElementById('wordpress-plugins-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-state text-error">Fehler.</td></tr>';
        }
    },

    async loadUsers() {
        try {
            const res = await fetch(`${this.API_PREFIX}/users${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Users API error");
            const users = await res.json();
            const tbody = document.getElementById('wordpress-users-tbody');
            if (!tbody) return;

            if (!users.length || users[0]?.error) {
                tbody.innerHTML = `<tr><td colspan="4" class="empty-state">${users[0]?.error ? this.escapeHtml(users[0].error) : 'Keine Benutzer.'}</td></tr>`;
                return;
            }

            tbody.innerHTML = users.map(u => `<tr>
                <td>${u.id}</td>
                <td><strong>${this.escapeHtml(u.name)}</strong><br><code style="font-size:0.8em">${this.escapeHtml(u.username)}</code></td>
                <td>${this.escapeHtml(u.email || '-')}</td>
                <td>${(u.roles || []).join(', ')}</td>
            </tr>`).join('');
        } catch (err) {
            console.error('WP Users Fehler:', err);
            const tbody = document.getElementById('wordpress-users-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-state text-error">Fehler.</td></tr>';
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    },

    destroy() {
        if (this.pollInterval) clearInterval(this.pollInterval);
    }
};
