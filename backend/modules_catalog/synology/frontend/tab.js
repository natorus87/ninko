(function() {
    'use strict';

    const SynologyTab = {
        connId: '',
        refresh: async function() {
            const container = document.getElementById('synology-storage');
            const pkgContainer = document.getElementById('synology-packages');
            const statusCard = document.getElementById('synology-status-card');

            if (!this.connId) {
                container.innerHTML = '<p class="empty-state">Bitte Verbindung auswählen.</p>';
                return;
            }

            container.innerHTML = '<p class="empty-state">Lade…</p>';
            pkgContainer.innerHTML = '<p class="empty-state">Lade…</p>';

            try {
                const [sysResp, storageResp, pkgResp] = await Promise.all([
                    fetch(`/api/synology/status?connection_id=${this.connId}`),
                    fetch(`/api/synology/storage?connection_id=${this.connId}`),
                    fetch(`/api/synology/packages?connection_id=${this.connId}`)
                ]);

                const sysData = await sysResp.json();
                const storageData = await storageResp.json();
                const pkgData = await pkgResp.json();

                if (sysData.status === 'ok' && sysData.data && !sysData.data.error) {
                    const info = sysData.data;
                    document.getElementById('synology-model').textContent = info.model || '-';
                    document.getElementById('synology-version').textContent = info.version_string || '-';
                    document.getElementById('synology-status').textContent = 'Online';
                    statusCard.classList.remove('failing');
                    statusCard.classList.add('running');
                } else {
                    document.getElementById('synology-status').textContent = 'Error';
                    statusCard.classList.remove('running');
                    statusCard.classList.add('failing');
                    container.innerHTML = '<p class="empty-state text-error">Fehler: ' + (sysData.data?.error || 'Verbindung fehlgeschlagen') + '</p>';
                }

                if (storageData.status === 'ok' && storageData.data && storageData.data.disks) {
                    const disks = storageData.data.disks;
                    if (disks.length === 0) {
                        container.innerHTML = '<p class="empty-state">Keine Laufwerke gefunden.</p>';
                    } else {
                        container.innerHTML = disks.map(d => {
                            const statusClass = d.status === 'normal' ? 'running' : 'failing';
                            return '<div class="status-card ' + statusClass + '">' +
                                '<span class="status-value" style="font-variant-numeric:tabular-nums">' + d.id + '</span>' +
                                '<span class="status-label">' + (d.model || 'Disk') + '</span>' +
                                '</div>';
                        }).join('');
                    }
                }

                if (pkgData.status === 'ok' && pkgData.data && pkgData.data.packages) {
                    const pkgs = pkgData.data.packages;
                    if (pkgs.length === 0) {
                        pkgContainer.innerHTML = '<p class="empty-state">Keine Pakete gefunden.</p>';
                    } else {
                        const rows = pkgs.slice(0, 10).map(p => {
                            const statusClass = p.status === 'installed' ? 'status-ok' : 'status-warning';
                            return '<tr>' +
                                '<td>' + (p.display_name || p.name) + '</td>' +
                                '<td>' + (p.version || '-') + '</td>' +
                                '<td><span class="status-badge ' + statusClass + '">' + p.status + '</span></td>' +
                                '</tr>';
                        }).join('');
                        pkgContainer.innerHTML = '<table class="data-table"><thead><tr><th>Package</th><th>Version</th><th>Status</th></tr></thead><tbody>' + rows + '</tbody></table>';
                    }
                }
            } catch (e) {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden: ' + e.message + '</p>';
            }
        },

        init: async function() {
            await this.loadConnections();
            document.querySelector('[data-action="synology-refresh"]')?.addEventListener('click', () => this.refresh());
            await this.refresh();
        },

        loadConnections: async function() {
            try {
                const resp = await fetch('/api/connections/synology');
                const data = await resp.json();
                const dropdown = document.getElementById('synology-conn-options');
                const label = document.querySelector('#synology-conn-select .cl-select-label');

                if (data.connections && data.connections.length > 0) {
                    dropdown.innerHTML = data.connections.map(c =>
                        '<div class="cl-select-option" data-id="' + c.id + '">' + c.name + '</div>'
                    ).join('');
                    dropdown.querySelectorAll('.cl-select-option').forEach(opt => {
                        opt.addEventListener('click', (e) => {
                            this.connId = e.target.dataset.id;
                            label.textContent = e.target.textContent;
                            this.refresh();
                            document.getElementById('synology-conn-select').classList.remove('open');
                        });
                    });
                    this.connId = data.connections[0].id;
                    label.textContent = data.connections[0].name;
                } else {
                    dropdown.innerHTML = '<div class="cl-select-option">Keine Verbindungen</div>';
                    label.textContent = 'Keine Verbindung';
                }
            } catch (e) {
                console.error('Failed to load connections:', e);
            }
        },

        toggleSelect: function(id) {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('open');
        },

        destroy: function() {}
    };

    if (typeof Ninko !== 'undefined') {
        Ninko._pluginTabs['synology'] = SynologyTab;
    }
})();
