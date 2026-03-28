/**
 * Kubernetes Dashboard Tab – JavaScript
 */
const K8sTab = {
    API_PREFIX: '/api/k8s',
    pollInterval: null,
    currentNamespace: 'default',
    currentConnectionId: '',

    async init() {
        this._setupClickOutside();
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.loadNamespaces();
            await this.refresh();
            this.startPolling();
        }
    },

    // ── Custom Select ──────────────────────────────────────────

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#k8s-tab-content .cl-select.open').forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#k8s-tab-content .cl-select')) {
                document.querySelectorAll('#k8s-tab-content .cl-select.open').forEach(s => s.classList.remove('open'));
            }
        });
    },

    _getSelectValue(selectId) {
        const sel = document.getElementById(selectId);
        return sel?.querySelector('.cl-select-option.selected')?.dataset.value || '';
    },

    _setSelectOptions(optionsContainerId, options, onSelect) {
        const container = document.getElementById(optionsContainerId);
        if (!container) return;
        container.innerHTML = options.map(o =>
            `<div class="cl-select-option${o.selected ? ' selected' : ''}" data-value="${o.value}">${o.label}</div>`
        ).join('');
        container.querySelectorAll('.cl-select-option').forEach(opt => {
            opt.addEventListener('click', () => {
                container.querySelectorAll('.cl-select-option').forEach(o => o.classList.remove('selected'));
                opt.classList.add('selected');
                const wrapper = container.closest('.cl-select');
                if (wrapper) {
                    const lbl = wrapper.querySelector('.cl-select-label');
                    if (lbl) lbl.textContent = opt.textContent;
                    wrapper.classList.remove('open');
                }
                onSelect(opt.dataset.value);
            });
        });
    },

    _setSelectLabel(wrapperId, label) {
        const el = document.getElementById(wrapperId);
        if (el) {
            const lbl = el.querySelector('.cl-select-label');
            if (lbl) lbl.textContent = label;
        }
    },

    // ── Polling ────────────────────────────────────────────────

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
        if (this.currentConnectionId) params.append('connection_id', this.currentConnectionId);
        for (const [k, v] of Object.entries(additional)) params.append(k, String(v));
        const str = params.toString();
        return str ? `?${str}` : '';
    },

    // ── Connections ────────────────────────────────────────────

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/kubernetes');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('k8s-conn-select', 'Keine K8s Verbindungen');
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;
            this._setSelectLabel('k8s-conn-select', `${defaultConn.name} (${defaultConn.environment})`);

            this._setSelectOptions('k8s-conn-options', conns.map(c => ({
                value: c.id,
                label: `${c.name} (${c.environment})`,
                selected: c.id === defaultConn.id,
            })), async (id) => {
                this.currentConnectionId = id;
                this.currentNamespace = 'default';
                await this.loadNamespaces();
                this.refresh();
            });
        } catch (err) {
            console.error('K8s Connections Fehler:', err);
        }
    },

    // ── Namespaces ─────────────────────────────────────────────

    async loadNamespaces() {
        try {
            const res = await fetch(`${this.API_PREFIX}/namespaces${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Namespaces API error");
            const namespaces = await res.json();

            this._setSelectOptions('k8s-ns-options', namespaces.map(ns => ({
                value: ns.name,
                label: ns.name,
                selected: ns.name === this.currentNamespace,
            })), (ns) => {
                this.currentNamespace = ns;
                this.refresh();
            });

            // Label des aktuell gewählten Namespace setzen
            const current = namespaces.find(n => n.name === this.currentNamespace) || namespaces[0];
            if (current) {
                this.currentNamespace = current.name;
                this._setSelectLabel('k8s-ns-select', current.name);
            }
        } catch (err) {
            console.error('K8s Namespaces Fehler:', err);
        }
    },

    // ── Refresh ────────────────────────────────────────────────

    async refresh() {
        if (!this.currentConnectionId) return;
        await Promise.all([
            this.loadClusterStatus(),
            this.loadPods(),
            this.loadFailingPods(),
        ]);
    },

    async loadClusterStatus() {
        try {
            const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Status API error");
            const data = await res.json();
            document.getElementById('k8s-nodes').textContent = data.nodes ?? '-';
            document.getElementById('k8s-total-pods').textContent = data.total_pods ?? '-';
            document.getElementById('k8s-running-pods').textContent = data.running_pods ?? '-';
            document.getElementById('k8s-deployments').textContent = data.deployments ?? '-';

            const failing = data.failing_pods ?? 0;
            document.getElementById('k8s-failing-pods').textContent = failing;

            // Failing-Card nur rot wenn wirklich Pods failing sind
            const card = document.getElementById('k8s-failing-card');
            if (card) {
                card.classList.toggle('failing', failing > 0);
            }
        } catch (err) {
            console.error('K8s Cluster Status Fehler:', err);
            this._resetStatusCounters();
        }
    },

    _resetStatusCounters() {
        ['k8s-nodes', 'k8s-total-pods', 'k8s-running-pods', 'k8s-failing-pods', 'k8s-deployments']
            .forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '-'; });
        const card = document.getElementById('k8s-failing-card');
        if (card) card.classList.remove('failing');
    },

    async loadPods() {
        const tbody = document.getElementById('k8s-pods-tbody');
        if (!tbody) return;

        try {
            const res = await fetch(`${this.API_PREFIX}/pods/${this.currentNamespace}${this.getQueryParams()}`);
            if (!res.ok) throw new Error("Pods API error");
            const pods = await res.json();

            if (pods.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Keine Pods in diesem Namespace.</td></tr>';
                return;
            }

            tbody.innerHTML = pods.map(pod => {
                const statusClass = this.getStatusClass(pod.status);
                return `<tr>
                    <td class="pod-name">${pod.name}</td>
                    <td><span class="status-badge ${statusClass}">${pod.status}</span></td>
                    <td>${pod.ready}</td>
                    <td>${pod.restarts}</td>
                    <td>${pod.age}</td>
                    <td>
                        <button class="btn btn-sm btn-action" onclick="K8sTab.restartPod('${pod.namespace}', '${pod.name}')">
                            🔄 Neustart
                        </button>
                    </td>
                </tr>`;
            }).join('');
        } catch (err) {
            console.error('K8s Pods Fehler:', err);
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state text-error">Fehler beim Laden der Pods.</td></tr>';
        }
    },

    async loadFailingPods() {
        const container = document.getElementById('k8s-failing-list');
        if (!container) return;

        try {
            const res = await fetch(`${this.API_PREFIX}/failing${this.getQueryParams({ namespace: this.currentNamespace })}`);
            if (!res.ok) throw new Error("Failing Pods API error");
            const failing = await res.json();

            if (failing.length === 0) {
                container.innerHTML = '<p class="empty-state">Keine fehlerhaften Pods gefunden.</p>';
                return;
            }

            container.innerHTML = failing.map(pod => `
                <div class="failing-pod-card">
                    <div class="failing-pod-header">
                        <span class="pod-name">${pod.name}</span>
                        <span class="pod-ns">${pod.namespace}</span>
                    </div>
                    <div class="failing-pod-issues">
                        ${pod.issues.map(i => `<span class="issue-badge">${i}</span>`).join('')}
                    </div>
                    <div class="failing-pod-actions">
                        <span class="restarts-count">${pod.restarts} Neustarts</span>
                        <button class="btn btn-sm btn-danger" onclick="K8sTab.restartPod('${pod.namespace}', '${pod.name}')">
                            🔄 Neu starten
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (err) {
            console.error('K8s Failing Pods Fehler:', err);
            container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden der fehlerhaften Pods.</p>';
        }
    },

    async restartPod(namespace, podName) {
        if (!confirm(`Pod "${podName}" im Namespace "${namespace}" wirklich neu starten?`)) return;
        try {
            const res = await fetch(`${this.API_PREFIX}/restart/${namespace}/${podName}${this.getQueryParams()}`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.status === 'success') {
                showNotification('Pod wird neu gestartet: ' + podName, 'success');
                setTimeout(() => this.refresh(), 3000);
            } else {
                showNotification('Fehler: ' + (data.detail || 'Unbekannt'), 'error');
            }
        } catch (err) {
            showNotification('Verbindungsfehler beim Pod-Neustart', 'error');
        }
    },

    getStatusClass(status) {
        switch (status) {
            case 'Running':          return 'status-ok';
            case 'Succeeded':        return 'status-ok';
            case 'Pending':          return 'status-warning';
            case 'Failed':           return 'status-error';
            case 'CrashLoopBackOff': return 'status-error';
            case 'Terminating':      return 'status-warning';
            default:                 return 'status-unknown';
        }
    },

    destroy() {
        this.stopPolling();
    }
};
