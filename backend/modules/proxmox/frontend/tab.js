/**
 * Proxmox Dashboard Tab – JavaScript
 */
const ProxmoxTab = {
    API_PREFIX: '/api/proxmox',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
            this.startPolling();
        }

        document.getElementById('proxmox-connection-select')
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
            const res = await fetch('/api/connections/proxmox');
            const data = await res.json();
            const conns = data.connections || [];
            const select = document.getElementById('proxmox-connection-select');
            if (!select) return;

            if (conns.length === 0) {
                select.innerHTML = '<option value="">Keine Proxmox Verbindungen</option>';
                this.currentConnectionId = '';
                return;
            }

            select.innerHTML = conns.map(c =>
                `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
            ).join('');

            // Set initial connection
            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
        } catch (err) {
            console.error('Proxmox Connections Fehler:', err);
        }
    },

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadNodes(),
            this.loadVMs(),
        ]);
    },

    async loadNodes() {
        try {
            const res = await fetch(`${this.API_PREFIX}/nodes${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Nodes API error");
            const nodes = await res.json();
            const container = document.getElementById('proxmox-nodes');
            if (!container) return;

            if (nodes.length === 0) {
                container.innerHTML = '<p class="empty-state">Keine Nodes gefunden.</p>';
                return;
            }

            container.innerHTML = nodes.map(node => `
                <div class="node-card ${node.status === 'online' ? 'node-online' : 'node-offline'}">
                    <div class="node-header">
                        <span class="node-name">${node.node}</span>
                        <span class="node-status-badge ${node.status}">${node.status}</span>
                    </div>
                    <div class="node-metrics">
                        <div class="metric">
                            <label>CPU</label>
                            <div class="progress-bar">
                                <div class="progress-fill ${this.getUsageColor(node.cpu_usage)}" style="width: ${node.cpu_usage}%"></div>
                            </div>
                            <span class="metric-value">${node.cpu_usage}%</span>
                        </div>
                        <div class="metric">
                            <label>RAM</label>
                            <div class="progress-bar">
                                <div class="progress-fill ${this.getUsageColor(node.mem_usage)}" style="width: ${node.mem_usage}%"></div>
                            </div>
                            <span class="metric-value">${node.mem_usage}% (${node.mem_used_human} / ${node.mem_total_human})</span>
                        </div>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            console.error('Proxmox Nodes Fehler:', err);
            const container = document.getElementById('proxmox-nodes');
            if (container) container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden der Nodes.</p>';
        }
    },

    async loadVMs() {
        try {
            const res = await fetch(`${this.API_PREFIX}/vms${this.getQueryParams()}`);
            if (!res.ok) throw new Error("VMs API error");
            const vms = await res.json();
            const tbody = document.getElementById('proxmox-vms-tbody');
            if (!tbody) return;

            if (vms.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Keine VMs gefunden.</td></tr>';
                return;
            }

            tbody.innerHTML = vms.map(vm => {
                const statusClass = vm.status === 'running' ? 'status-ok' : vm.status === 'stopped' ? 'status-error' : 'status-warning';
                const memMB = Math.round(vm.mem_used / 1024 / 1024);
                const memTotalMB = Math.round(vm.mem_total / 1024 / 1024);
                const typeBadge = vm.type === 'lxc' ? 'LXC' : 'VM';

                return `<tr>
                    <td>${vm.vmid}</td>
                    <td>${vm.name}</td>
                    <td><span class="status-badge status-unknown">${typeBadge}</span></td>
                    <td>${vm.node}</td>
                    <td><span class="status-badge ${statusClass}">${vm.status}</span></td>
                    <td>${vm.cpu_usage}%</td>
                    <td>${memMB}/${memTotalMB} MB</td>
                    <td class="action-buttons">
                        ${vm.status !== 'running' ?
                        `<button class="btn btn-sm btn-success" onclick="ProxmoxTab.startVM('${vm.node}', ${vm.vmid})">Start</button>` :
                        `<button class="btn btn-sm btn-warning" onclick="ProxmoxTab.rebootVM('${vm.node}', ${vm.vmid})">Reboot</button>
                             <button class="btn btn-sm btn-danger" onclick="ProxmoxTab.stopVM('${vm.node}', ${vm.vmid})">Stop</button>`
                    }
                    </td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('Proxmox VMs Fehler:', err);
            const tbody = document.getElementById('proxmox-vms-tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="empty-state text-error">Fehler beim Laden der VMs.</td></tr>';
        }
    },

    async startVM(node, vmid) {
        try {
            const res = await fetch(`${this.API_PREFIX}/vm/${node}/${vmid}/start${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'error');
            setTimeout(() => this.refresh(), 3000);
        } catch (err) {
            showNotification('Verbindungsfehler', 'error');
        }
    },

    async stopVM(node, vmid) {
        if (!confirm(`VM ${vmid} auf Node "${node}" wirklich stoppen?`)) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/vm/${node}/${vmid}/stop${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'warning');
            setTimeout(() => this.refresh(), 3000);
        } catch (err) {
            showNotification('Verbindungsfehler', 'error');
        }
    },

    async rebootVM(node, vmid) {
        if (!confirm(`VM ${vmid} auf Node "${node}" neu starten?`)) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/vm/${node}/${vmid}/reboot${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            showNotification(data.detail, data.status === 'success' ? 'success' : 'error');
            setTimeout(() => this.refresh(), 5000);
        } catch (err) {
            showNotification('Verbindungsfehler', 'error');
        }
    },

    getUsageColor(percent) {
        if (percent > 80) return 'usage-critical';
        if (percent > 60) return 'usage-warning';
        return 'usage-ok';
    },

    destroy() {
        this.stopPolling();
    }
};
