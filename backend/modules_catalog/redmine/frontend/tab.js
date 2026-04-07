(function() {
    'use strict';

    const RedmineTab = {
        connId: '',
        refresh: async function() {
            const container = document.getElementById('redmine-issues');
            if (!this.connId) {
                container.innerHTML = '<p class="empty-state">' + I18n.t('modules.redmine.selectConnection') + '</p>';
                return;
            }

            container.innerHTML = '<p class="empty-state">' + I18n.t('modules.redmine.loading') + '</p>';

            try {
                const [projResp, issuesResp] = await Promise.all([
                    fetch(`/api/redmine/projects?connection_id=${this.connId}`),
                    fetch(`/api/redmine/issues?connection_id=${this.connId}&status=open`),
                ]);

                const projData = await projResp.json();
                const issuesData = await issuesResp.json();

                if (projData.status === 'ok' && projData.data && projData.data.projects) {
                    document.getElementById('redmine-projects-count').textContent = projData.data.total || 0;
                }

                if (issuesData.status === 'ok' && issuesData.data && issuesData.data.issues) {
                    const issues = issuesData.data.issues;
                    const open = issues.filter(i => !i.status.is_closed).length;
                    const closed = issues.filter(i => i.status.is_closed).length;
                    document.getElementById('redmine-open-count').textContent = open;
                    document.getElementById('redmine-closed-count').textContent = closed;

                    if (issues.length === 0) {
                        container.innerHTML = '<p class="empty-state">' + I18n.t('modules.redmine.noTickets') + '</p>';
                    } else {
                        container.innerHTML = '<table class="data-table"><thead><tr><th>#</th><th>Subject</th><th>Status</th><th>Priority</th></tr></thead><tbody>' +
                            issues.slice(0, 10).map(i => {
                                const statusClass = i.status.is_closed ? 'status-ok' : 'status-warning';
                                return '<tr>' +
                                    '<td>' + i.id + '</td>' +
                                    '<td>' + (i.subject || '-') + '</td>' +
                                    '<td><span class="status-badge ' + statusClass + '">' + (i.status.name || '-') + '</span></td>' +
                                    '<td>' + (i.priority ? i.priority.name : '-') + '</td>' +
                                    '</tr>';
                            }).join('') + '</tbody></table>';
                    }
                } else {
                    container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.redmine.loadError') + '</p>';
                }
            } catch (e) {
                container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.redmine.error') + e.message + '</p>';
            }
        },

        init: async function() {
            await this.loadConnections();
            document.querySelector('[data-action="redmine-refresh"]')?.addEventListener('click', () => this.refresh());
            await this.refresh();
        },

        loadConnections: async function() {
            try {
                const resp = await fetch('/api/connections/redmine');
                const data = await resp.json();
                const dropdown = document.getElementById('redmine-conn-options');
                const label = document.querySelector('#redmine-conn-select .cl-select-label');

                if (data.connections && data.connections.length > 0) {
                    dropdown.innerHTML = data.connections.map(c =>
                        '<div class="cl-select-option" data-id="' + c.id + '">' + c.name + '</div>'
                    ).join('');
                    dropdown.querySelectorAll('.cl-select-option').forEach(opt => {
                        opt.addEventListener('click', (e) => {
                            this.connId = e.target.dataset.id;
                            label.textContent = e.target.textContent;
                            this.refresh();
                            document.getElementById('redmine-conn-select').classList.remove('open');
                        });
                    });
                    this.connId = data.connections[0].id;
                    label.textContent = data.connections[0].name;
                } else {
                    dropdown.innerHTML = '<div class="cl-select-option">' + I18n.t('modules.redmine.noConnections') + '</div>';
                    label.textContent = I18n.t('modules.redmine.noConnection');
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
        Ninko._pluginTabs['redmine'] = RedmineTab;
    }
    
    // Global expose for inline onclick handlers
    window.RedmineTab = RedmineTab;
})();
