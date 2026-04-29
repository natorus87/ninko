/**
 * Docker Dashboard Tab – JavaScript
 * Nutzt IIFE-Pattern (keine ES-Module).
 */
const DockerTab = {
    API_PREFIX: '/api/docker',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
            this.startPolling();
        }

        document.getElementById('docker-connection-select')
            ?.addEventListener('change', async (e) => {
                this.currentConnectionId = e.target.value;
                this.refresh();
            });
    },

    startPolling() {
        this.stopPolling();
        this.pollInterval = setInterval(() => this.refresh(), 30000);
    },

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
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
            const res = await fetch('/api/connections/docker');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('docker-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">' + I18n.t('modules.docker.noConnections') + '</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
        } catch (err) {
            console.error('Docker Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadSystemInfo(),
            this.loadContainers(),
            this.loadImages(),
            this.loadVolumes(),
        ]);
    },

    async loadSystemInfo() {
        try {
            const res = await fetch(`${this.API_PREFIX}/info${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Info API error");
            const info = await res.json();
            const container = document.getElementById('docker-system-info');
            if (!container) return;

            container.innerHTML = `
                <div class="info-card">
                    <div class="info-label">Docker</div>
                    <div class="info-value">${info.docker_version || '?'}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">CPUs</div>
                    <div class="info-value">${info.cpus || 0}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">RAM</div>
                    <div class="info-value">${info.total_memory || '?'}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Container</div>
                    <div class="info-value">${info.containers_running || 0} ${I18n.t('modules.docker.runningOf')}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Images</div>
                    <div class="info-value">${info.images_count || 0}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Storage</div>
                    <div class="info-value">${info.storage_driver || '?'}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">OS</div>
                    <div class="info-value">${info.os || '?'}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Kernel</div>
                    <div class="info-value">${info.kernel || '?'}</div>
                </div>
            `;
        } catch (err) {
            console.error('Docker Info Fehler:', err);
            const container = document.getElementById('docker-system-info');
            if (container) container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.docker.sysInfoError') + '</p>';
        }
    },

    async loadContainers() {
        try {
            const res = await fetch(`${this.API_PREFIX}/containers${this.getQueryParams({ all: true })}`);
            if (!res.ok) throw new Error("Containers API error");
            const containers = await res.json();
            const tbody = document.getElementById('docker-containers-tbody');
            if (!tbody) return;

            if (containers.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">' + I18n.t('modules.docker.noContainers') + '</td></tr>';
                return;
            }

            tbody.innerHTML = containers.map(c => {
                const stateClass = c.state === 'running' ? 'status-ok' : c.state === 'exited' ? 'status-error' : 'status-warning';
                const ports = (c.ports || []).map(p => {
                    if (p.PublicPort) return `${p.PublicPort}:${p.PrivatePort}/${p.Type}`;
                    return `${p.PrivatePort}/${p.Type}`;
                }).join(', ') || '-';

                return `<tr>
                    <td>${this.escapeHtml(c.name)}</td>
                    <td><code>${this.escapeHtml(c.image)}</code></td>
                    <td><span class="status-badge ${stateClass}">${c.state}</span></td>
                    <td style="font-size:0.85em">${this.escapeHtml(c.status)}</td>
                    <td style="font-size:0.85em">${this.escapeHtml(ports)}</td>
                    <td class="action-buttons">
                        ${c.state !== 'running' ?
                            `<button class="btn btn-sm btn-success" onclick="DockerTab.startContainer('${c.id}')">▶ Start</button>` :
                            `<button class="btn btn-sm btn-warning" onclick="DockerTab.restartContainer('${c.id}')">🔄 Restart</button>
                             <button class="btn btn-sm btn-danger" onclick="DockerTab.stopContainer('${c.id}')">⏹ Stop</button>`
                        }
                        <button class="btn btn-sm" onclick="DockerTab.showLogs('${c.id}', '${this.escapeHtml(c.name)}')">📋 Logs</button>
                    </td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('Docker Containers Fehler:', err);
            const tbody = document.getElementById('docker-containers-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-state text-error">' + I18n.t('modules.docker.loadContainersError') + '</td></tr>';
        }
    },

    async loadImages() {
        try {
            const res = await fetch(`${this.API_PREFIX}/images${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Images API error");
            const images = await res.json();
            const tbody = document.getElementById('docker-images-tbody');
            if (!tbody) return;

            if (images.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="empty-state">' + I18n.t('modules.docker.noImages') + '</td></tr>';
                return;
            }

            tbody.innerHTML = images.map(img => `
                <tr>
                    <td><code>${img.id}</code></td>
                    <td>${(img.tags || []).map(t => `<code>${this.escapeHtml(t)}</code>`).join('<br>') || '-'}</td>
                    <td>${img.size}</td>
                </tr>
            `).join('');
        } catch (err) {
            console.error('Docker Images Fehler:', err);
            const tbody = document.getElementById('docker-images-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="empty-state text-error">' + I18n.t('modules.docker.loadImagesError') + '</td></tr>';
        }
    },

    async loadVolumes() {
        try {
            const res = await fetch(`${this.API_PREFIX}/volumes${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Volumes API error");
            const volumes = await res.json();
            const tbody = document.getElementById('docker-volumes-tbody');
            if (!tbody) return;

            if (volumes.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="empty-state">' + I18n.t('modules.docker.noVolumes') + '</td></tr>';
                return;
            }

            tbody.innerHTML = volumes.map(v => `
                <tr>
                    <td><code>${this.escapeHtml(v.name)}</code></td>
                    <td>${v.driver}</td>
                    <td style="font-size:0.85em;word-break:break-all">${this.escapeHtml(v.mountpoint)}</td>
                </tr>
            `).join('');
        } catch (err) {
            console.error('Docker Volumes Fehler:', err);
            const tbody = document.getElementById('docker-volumes-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="empty-state text-error">' + I18n.t('modules.docker.loadVolumesError') + '</td></tr>';
        }
    },

    async startContainer(id) {
        try {
            const res = await fetch(`${this.API_PREFIX}/containers/${id}/start${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'error');
            setTimeout(() => this.refresh(), 3000);
        } catch (err) {
            showNotification(I18n.t('modules.docker.connectionError'), 'error');
        }
    },

    async stopContainer(id) {
        if (!confirm(I18n.t('modules.docker.confirmStop').replace('...', this.escapeHtml(id)))) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/containers/${id}/stop${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'warning');
            setTimeout(() => this.refresh(), 3000);
        } catch (err) {
            showNotification(I18n.t('modules.docker.connectionError'), 'error');
        }
    },

    async restartContainer(id) {
        if (!confirm(I18n.t('modules.docker.confirmRestart').replace('...', this.escapeHtml(id)))) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/containers/${id}/restart${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'error');
            setTimeout(() => this.refresh(), 5000);
        } catch (err) {
            showNotification(I18n.t('modules.docker.connectionError'), 'error');
        }
    },

    async showLogs(id, name) {
        try {
            const res = await fetch(`${this.API_PREFIX}/containers/${id}/logs${this.getQueryParams({ tail: 200 })}`);
            const text = await res.text();
            const logWindow = window.open('', `Logs: ${name}`, 'width=800,height=600,scrollbars=yes');
            if (logWindow) {
                logWindow.document.write(`
                    <html><head><title>Logs: ${this.escapeHtml(name)}</title>
                    <style>
                        body { background: #1e1e1e; color: #d4d4d4; font-family: monospace; padding: 1rem; white-space: pre-wrap; font-size: 0.65rem; }
                        a { color: #569cd6; }
                    </style></head><body>${this.escapeHtml(text)}</body></html>
                `);
            }
        } catch (err) {
            showNotification(I18n.t('modules.docker.loadLogsError'), 'error');
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    },

    destroy() {
        this.stopPolling();
    }
};

if (typeof Ninko !== 'undefined') Ninko._pluginTabs['docker'] = DockerTab;
