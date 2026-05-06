(function() {
    'use strict';

    function esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    const JiraTab = {
        connId: '',
        refresh: async function() {
            const container = document.getElementById('jira-issues');
            if (!this.connId) {
                container.innerHTML = '<p class="empty-state">' + I18n.t('modules.jira.selectConnection') + '</p>';
                return;
            }

            container.innerHTML = '<p class="empty-state">' + I18n.t('modules.jira.loading') + '</p>';

            try {
                const [projResp, issuesResp] = await Promise.all([
                    fetch(`/api/jira/projects?connection_id=${this.connId}`),
                    fetch(`/api/jira/issues?connection_id=${this.connId}&status=open`),
                ]);

                const projData = await projResp.json();
                const issuesData = await issuesResp.json();

                if (projData.status === 'ok' && projData.data && projData.data.projects) {
                    document.getElementById('jira-projects-count').textContent = projData.data.projects.length || 0;
                }

                if (issuesData.status === 'ok' && issuesData.data && issuesData.data.issues) {
                    const issues = issuesData.data.issues;
                    document.getElementById('jira-issues-count').textContent = issuesData.data.total || 0;

                    if (issues.length === 0) {
                        container.innerHTML = '<p class="empty-state">' + I18n.t('modules.jira.noIssues') + '</p>';
                    } else {
                        container.innerHTML = '<table class="data-table"><thead><tr><th>Key</th><th>Summary</th><th>Type</th><th>Status</th></tr></thead><tbody>' +
                            issues.slice(0, 10).map(i => {
                                const statusClass = i.fields.status.name === 'Done' || i.fields.status.name === 'Closed' ? 'status-ok' : 'status-warning';
                                return '<tr>' +
                                    '<td>' + esc(i.key) + '</td>' +
                                    '<td>' + esc(i.fields.summary) || '-' + '</td>' +
                                    '<td>' + esc(i.fields.issuetype ? i.fields.issuetype.name : '-') + '</td>' +
                                    '<td><span class="status-badge ' + statusClass + '">' + esc(i.fields.status ? i.fields.status.name : '-') + '</span></td>' +
                                    '</tr>';
                            }).join('') + '</tbody></table>';
                    }
                } else {
                    container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.jira.loadError') + '</p>';
                }
            } catch (e) {
                container.innerHTML = '<p class="empty-state text-error">' + I18n.t('modules.jira.error') + esc(e.message) + '</p>';
            }
        },

        init: async function() {
            await this.loadConnections();
            document.querySelector('[data-action="jira-refresh"]')?.addEventListener('click', () => this.refresh());
            await this.refresh();
        },

        loadConnections: async function() {
            try {
                const resp = await fetch('/api/connections/jira');
                const data = await resp.json();
                const dropdown = document.getElementById('jira-conn-options');
                const label = document.querySelector('#jira-conn-select .cl-select-label');

                if (data.connections && data.connections.length > 0) {
                    dropdown.innerHTML = data.connections.map(c =>
                        '<div class="cl-select-option" data-id="' + c.id + '">' + c.name + '</div>'
                    ).join('');
                    dropdown.querySelectorAll('.cl-select-option').forEach(opt => {
                        opt.addEventListener('click', (e) => {
                            this.connId = e.target.dataset.id;
                            label.textContent = e.target.textContent;
                            this.refresh();
                            document.getElementById('jira-conn-select').classList.remove('open');
                        });
                    });
                    this.connId = data.connections[0].id;
                    label.textContent = data.connections[0].name;
                } else {
                    dropdown.innerHTML = '<div class="cl-select-option">' + I18n.t('modules.jira.noConnections') + '</div>';
                    label.textContent = I18n.t('modules.jira.noConnection');
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
        Ninko._pluginTabs['jira'] = JiraTab;
    }
})();
