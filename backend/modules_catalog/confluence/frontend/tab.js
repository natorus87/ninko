(function() {
    'use strict';

    function esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    const ConfluenceTab = {
        connId: '',
        refresh: async function() {
            const container = document.getElementById('confluence-pages');
            if (!this.connId) {
                container.innerHTML = '<p class="empty-state">' + I18n.t('modules.confluence.selectConnection') + '</p>';
                return;
            }

            container.innerHTML = '<p class="empty-state">' + I18n.t('modules.confluence.loading') + '</p>';

            try {
                const [spacesResp, pagesResp] = await Promise.all([
                    fetch(`/api/confluence/spaces?connection_id=${this.connId}`),
                    fetch(`/api/confluence/pages?connection_id=${this.connId}`),
                ]);

                const spacesData = await spacesResp.json();
                const pagesData = await pagesResp.json();

                if (spacesData.status === 'ok' && spacesData.data && spacesData.data.spaces) {
                    document.getElementById('confluence-spaces-count').textContent = spacesData.data.total || 0;
                }

                if (pagesData.status === 'ok' && pagesData.data && pagesData.data.pages) {
                    const pages = pagesData.data.pages;
                    document.getElementById('confluence-pages-count').textContent = pagesData.data.total || 0;

                    if (pages.length === 0) {
                        container.innerHTML = '<p class="empty-state">' + I18n.t('modules.confluence.noPages') + '</p>';
                    } else {
                        container.innerHTML = '<table class="data-table"><thead><tr><th>Title</th><th>Space</th><th>Status</th></tr></thead><tbody>' +
                            pages.slice(0, 10).map(p => {
                                const statusClass = p.status === 'current' ? 'status-ok' : 'status-warning';
                                return '<tr>' +
                                    '<td>' + esc(p.title) || '-' + '</td>' +
                                    '<td>' + esc(p.spaceId) || '-' + '</td>' +
                                    '<td><span class="status-badge ' + statusClass + '">' + esc(p.status) || '-' + '</span></td>' +
                                    '</tr>';
                            }).join('') + '</tbody></table>';
                    }
                } else {
                    container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.confluence.loadError') + '</p>';
                }
            } catch (e) {
                container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.confluence.error') + esc(e.message) + '</p>';
            }
        },

        init: async function() {
            await this.loadConnections();
            document.querySelector('[data-action="confluence-refresh"]')?.addEventListener('click', () => this.refresh());
            await this.refresh();
        },

        loadConnections: async function() {
            try {
                const resp = await fetch('/api/connections/confluence');
                const data = await resp.json();
                const dropdown = document.getElementById('confluence-conn-options');
                const label = document.querySelector('#confluence-conn-select .cl-select-label');

                if (data.connections && data.connections.length > 0) {
                    dropdown.innerHTML = data.connections.map(c =>
                        '<div class="cl-select-option" data-id="' + c.id + '">' + c.name + '</div>'
                    ).join('');
                    dropdown.querySelectorAll('.cl-select-option').forEach(opt => {
                        opt.addEventListener('click', (e) => {
                            this.connId = e.target.dataset.id;
                            label.textContent = e.target.textContent;
                            this.refresh();
                            document.getElementById('confluence-conn-select').classList.remove('open');
                        });
                    });
                    this.connId = data.connections[0].id;
                    label.textContent = data.connections[0].name;
                } else {
                    dropdown.innerHTML = '<div class="cl-select-option">' + I18n.t('modules.confluence.noConnections') + '</div>';
                    label.textContent = I18n.t('modules.confluence.noConnection');
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
        Ninko._pluginTabs['confluence'] = ConfluenceTab;
    }
})();
