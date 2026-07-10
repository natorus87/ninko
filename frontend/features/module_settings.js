/**
 * Ninko Module Settings & Connections Feature Module
 *
 * Modul-Aktivierung sowie Verbindungs-/Umgebungs-Verwaltung pro Modul
 * (ACTION_FIELDS-Formulardefinitionen, Connection-CRUD). Aus app.js
 * extrahiert; via Object.assign auf Ninko gemergt.
 */

(function() {
    'use strict';

    const ModuleSettingsFeature = {
        ACTION_FIELDS: {
            proxmox: [
                { key: 'host', label: 'Host / URL', placeholder: '192.168.1.100:8006' },
                { key: 'user', label: 'Benutzer', placeholder: 'root@pam' },
                { key: 'token_id', label: 'Token-ID', placeholder: 'sophy' },
                { key: 'token_secret', label: 'Token-Secret', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren (Nein anklicken bei invalidem SSL Cert)', type: 'checkbox' },
            ],
            glpi: [
                { key: 'base_url', label: 'Base URL', placeholder: 'https://glpi.example.com' },
                { key: 'app_token', label: 'App-Token', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'user_token', label: 'User-Token', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren', type: 'checkbox' },
                { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
            ],
            kubernetes: [
                { key: 'context', label: 'Context (optional)', placeholder: 'kubernetes-admin@prod' },
                { key: 'kubeconfig', label: 'Kubeconfig-Datei', type: 'file', isSecret: true },
            ],
            licium: [
                { key: 'base_url', label: 'Licium URL', placeholder: 'https://licium.example.com' },
                { key: 'username', label: 'Benutzername', placeholder: 'admin' },
                { key: 'LICIUM_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
            ],
            pihole: [
                { key: 'url', label: 'Pi-hole URL', placeholder: 'http://192.168.1.2' },
                { key: 'password', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            ionos: [
                { key: 'api_key', label: 'API-Key', placeholder: 'prefix.secret', type: 'password', isSecret: true },
            ],
            jira: [
                { key: 'url', label: 'Jira URL', placeholder: 'https://company.atlassian.net' },
                { key: 'email', label: 'E-Mail', placeholder: 'user@company.com' },
                { key: 'JIRA_API_KEY', label: 'API-Token', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
            ],
            fritzbox: [
                { key: 'host', label: 'FritzBox Host/IP', placeholder: '192.168.178.1' },
                { key: 'user', label: 'Benutzername (optional)', placeholder: 'admin' },
                { key: 'password', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            telegram: [
                { key: 'TELEGRAM_BOT_TOKEN', label: 'Bot-Token (Von @BotFather auf Telegram)', placeholder: '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ', type: 'password', isSecret: true },
            ],
            email: [
                { key: 'imap_server', label: 'IMAP Server', placeholder: 'imap.gmx.net' },
                { key: 'imap_port', label: 'IMAP Port', placeholder: '993', type: 'number' },
                { key: 'smtp_server', label: 'SMTP Server', placeholder: 'mail.gmx.net' },
                { key: 'smtp_port', label: 'SMTP Port', placeholder: '587', type: 'number' },
                { key: 'email_address', label: 'E-Mail Adresse', placeholder: 'bot@domain.de' },
                { key: 'auth_type', label: 'Auth-Typ (basic oder oauth2)', placeholder: 'basic' },
                { key: 'EMAIL_SECRET', label: 'Passwort / Client Secret', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'client_id', label: 'OAuth2 Client ID (nur M365)', placeholder: '...' },
                { key: 'tenant_id', label: 'OAuth2 Tenant ID (nur M365)', placeholder: 'common' },
            ],
            homeassistant: [
                { key: 'url', label: 'Home Assistant URL', placeholder: 'http://homeassistant.local:8123' },
                { key: 'HOMEASSISTANT_API_TOKEN', label: 'Long-Lived Access Token', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            synology: [
                { key: 'url', label: 'DSM URL', placeholder: 'https://192.168.1.100:5001' },
                { key: 'username', label: 'Benutzername', placeholder: 'admin' },
                { key: 'SYNOLOGY_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'SYNOLOGY_API_KEY', label: 'API Key (optional)', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            redmine: [
                { key: 'url', label: 'Redmine URL', placeholder: 'https://redmine.example.com' },
                { key: 'REDMINE_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
            ],
            openproject: [
                { key: 'url', label: 'OpenProject URL', placeholder: 'https://openproject.example.com' },
                { key: 'OPENPROJECT_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
            ],
            teams: [
                { key: 'MICROSOFT_APP_ID', label: 'Microsoft App ID', placeholder: 'e.g. 1234abcd-1234-abcd-1234-abcd1234abcd' },
                { key: 'MICROSOFT_APP_PASSWORD', label: 'Microsoft App Password / Client Secret', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            confluence: [
                { key: 'url', label: 'Confluence URL', placeholder: 'https://company.atlassian.net' },
                { key: 'email', label: 'E-Mail', placeholder: 'user@company.com' },
                { key: 'CONFLUENCE_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
            ],
            docker: [
                { key: 'host', label: 'Docker Host', placeholder: '192.168.1.100' },
                { key: 'port', label: 'Docker API Port', placeholder: '2375', type: 'number' },
                { key: 'tls', label: 'TLS aktivieren', type: 'checkbox' },
                { key: 'api_version', label: 'API Version (optional)', placeholder: '1.43' },
            ],
            linux_server: [
                { key: 'host', label: 'Server Host / IP', placeholder: '192.168.1.100' },
                { key: 'port', label: 'SSH Port', placeholder: '22', type: 'number' },
                { key: 'user', label: 'Benutzer', placeholder: 'root' },
                { key: 'LINUX_SERVER_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'LINUX_SERVER_SSH_KEY', label: 'RSA/Ed25519 Private Key (optional)', placeholder: '-----BEGIN OPENSSH PRIVATE KEY-----', type: 'password', isSecret: true },
            ],
            wordpress: [
                { key: 'url', label: 'WordPress URL', placeholder: 'https://meine-seite.de' },
                { key: 'username', label: 'Benutzername', placeholder: 'admin' },
                { key: 'WORDPRESS_APP_PASSWORD', label: 'Application Password', placeholder: 'xxxx xxxx xxxx xxxx', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
                { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
            ],
            opnsense: [
                { key: 'host', label: 'Host / IP (ohne https://)', placeholder: '192.168.1.1:4443' },
                { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'OPNSENSE_API_SECRET', label: 'API Secret', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'verify_ssl', label: 'SSL verifizieren', type: 'checkbox' },
                { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
            ],
            qdrant: [
                { key: 'url', label: 'Qdrant URL', placeholder: 'http://qdrant:6333' },
                { key: 'QDRANT_API_KEY', label: 'API Key (optional)', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'default_collection', label: 'Default Collection (optional)', placeholder: 'ninko_knowledge' },
            ],
            tasmota: [
                { key: 'host', label: 'Host / IP', placeholder: '192.168.1.50' },
            ],
            checkmk: [
                { key: 'url', label: 'Checkmk URL', placeholder: 'https://monitoring.example.com' },
                { key: 'site', label: 'Site', placeholder: 'mysite' },
                { key: 'username', label: 'Username', placeholder: 'automation' },
                { key: 'password', label: 'Password', placeholder: '••••••', type: 'password', isSecret: true },
                { key: 'api_token', label: 'API Token', placeholder: '••••••', type: 'password', isSecret: true },
            ],
            mcp_server: [
                {
                    key: 'transport',
                    label: 'Transport',
                    type: 'select',
                    defaultValue: 'stdio',
                    options: [
                        { value: 'stdio', label: 'stdio' },
                        { value: 'http', label: 'http' },
                        { value: 'sse', label: 'sse' },
                    ],
                },
                {
                    key: 'command',
                    label: 'Command',
                    placeholder: 'npx -y @modelcontextprotocol/server-filesystem /srv/data',
                    showWhen: { key: 'transport', values: ['stdio'] },
                },
                {
                    key: 'args_json',
                    label: 'Command Args (JSON Array)',
                    type: 'textarea',
                    rows: 4,
                    placeholder: '["/srv/data"]',
                    showWhen: { key: 'transport', values: ['stdio'] },
                },
                {
                    key: 'cwd',
                    label: 'Working Directory (optional)',
                    placeholder: '/srv/mcp',
                    showWhen: { key: 'transport', values: ['stdio'] },
                },
                {
                    key: 'env_json',
                    label: 'Environment (JSON Object)',
                    type: 'textarea',
                    rows: 5,
                    placeholder: '{"NODE_ENV":"production"}',
                    showWhen: { key: 'transport', values: ['stdio'] },
                },
                {
                    key: 'url',
                    label: 'Server URL',
                    placeholder: 'https://mcp.example.com/mcp',
                    showWhen: { key: 'transport', values: ['http', 'sse'] },
                },
                {
                    key: 'message_url',
                    label: 'SSE Message URL (optional)',
                    placeholder: 'https://mcp.example.com/messages',
                    showWhen: { key: 'transport', values: ['sse'] },
                },
                {
                    key: 'headers_json',
                    label: 'Headers (JSON Object)',
                    type: 'textarea',
                    rows: 5,
                    placeholder: '{"X-API-Key":"value"}',
                    showWhen: { key: 'transport', values: ['http', 'sse'] },
                },
                {
                    key: 'protocol_version',
                    label: 'Protocol Version',
                    placeholder: '2025-03-26',
                    defaultValue: '2025-03-26',
                },
                {
                    key: 'timeout_seconds',
                    label: 'Timeout (seconds)',
                    type: 'number',
                    placeholder: '20',
                    defaultValue: '20',
                },
                {
                    key: 'MCP_AUTH_TOKEN',
                    label: 'Bearer Token (optional)',
                    placeholder: '••••••',
                    type: 'password',
                    isSecret: true,
                },
            ],
        },

        async loadModulesSettings() {
            // Don't repaint the module list while a bulk update is iterating over
            // the same DOM nodes — it would clobber per-card highlighting and the
            // pending-updates cache.
            if (this._bulkUpdating) return;

            const container = document.getElementById('settings-modules-list');
            try {
                const res = await fetch('/api/settings/modules');
                if (!res.ok) throw new Error(res.statusText);
                const modules = await res.json();

                const updatesRes = await fetch('/api/plugins/check-updates');
                const updatesData = await updatesRes.json();
                const updatesMap = {};
                for (const p of (updatesData.plugins || [])) {
                    updatesMap[p.name] = p;
                }

                // Cache names with available updates for the bulk-update button
                this._pendingPluginUpdates = (updatesData.plugins || [])
                    .filter(p => p.update_available)
                    .map(p => p.name);
                this._updateBulkUpdateButton();

                if (!modules.length) {
                    container.innerHTML = `<p class="empty-state">${t('module.noneFound')}</p>`;
                    return;
                }

                container.innerHTML = modules.map(mod => {
                    const updateInfo = updatesMap[mod.name] || {};
                    const hasUpdate = updateInfo.update_available;
                    const safeName = this._escapeHtml(mod.name);
                    const safeDisplayName = this._escapeHtml(mod.display_name);
                    const safeDesc = this._escapeHtml(mod.description || '');
                    const safeVersion = this._escapeHtml(mod.version || '');
                    const safeRepoVersion = this._escapeHtml(updateInfo.repo_version || '');
                    return `
                    <div class="module-config-card" id="module-card-${safeName}">
                        <div class="module-config-header">
                            <div class="module-config-info">
                                <span class="module-config-name">${safeDisplayName}</span>
                                <span class="module-config-version">v${safeVersion}${hasUpdate ? ' <span class="version-update-indicator">→ ' + safeRepoVersion + '</span>' : ''}</span>
                            </div>
                            <div style="display: flex; gap: 0.5rem; align-items: center; flex-shrink: 0;">
                                ${hasUpdate ? `<button class="btn-primary btn-sm btn-update" data-action="updatePlugin" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" data-self="true" title="Auf Version ${safeRepoVersion} aktualisieren"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px; vertical-align: middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>Update</button>` : ''}
                                <label class="toggle-switch" title="Aktivieren/Deaktivieren">
                                    <input type="checkbox" ${mod.enabled ? 'checked' : ''}
                                        id="mod-toggle-${safeName}"
                                        onchange="Ninko.toggleModule('${safeName}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                                <button class="btn-icon btn-icon-sm" data-action="toggleModuleSettings" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" title="Einstellungen">
                                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                                </button>
                                <button class="btn-icon btn-icon-sm" data-action="deletePlugin" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" title="Plugin unwiderruflich deinstallieren" style="color: var(--error-color);">
                                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                        <p class="module-config-desc">${safeDesc}</p>
                        <div id="mod-connections-container-${safeName}" class="module-connections-container">
                            <h5 style="margin-top:0; margin-bottom: 0.5rem; color: var(--text-color);">Verbindungen / Umgebungen</h5>
                            <div id="connections-list-${safeName}">Lade Verbindungen...</div>
                            ${this._renderModuleConnectionForm(mod.name)}
                        </div>
                    </div>
                `}).join('');

                // Load connections for enabled modules
                for (const mod of modules) {
                    if (mod.enabled && this.ACTION_FIELDS[mod.name]) {
                        await this.loadModuleConnections(mod.name);
                    } else if (mod.enabled) {
                        const lc = document.getElementById(`connections-list-${mod.name}`);
                        if (lc) lc.innerHTML = '<p class="text-muted" style="margin:0; font-size: 0.85rem">Keine konfigurationspflichtigen Verbindungen.</p>';
                    }
                    if (this.ACTION_FIELDS[mod.name]) {
                        this.updateConnectionFieldVisibility(mod.name);
                    }
                }

            } catch (e) {
                console.error(e);
                container.innerHTML = '<p class="empty-state">Fehler beim Laden der Module.</p>';
            }
        },

        toggleModuleSettings(name) {
            const connContainer = document.getElementById(`mod-connections-container-${name}`);
            if (connContainer) {
                const opening = connContainer.style.display === 'none';
                connContainer.style.display = opening ? 'block' : 'none';
                if (opening && this.ACTION_FIELDS[name]) {
                    this.loadModuleConnections(name);
                    this.updateConnectionFieldVisibility(name);
                }
            }
        },

        _getConnectionFieldValue(moduleName, key) {
            const el = document.getElementById(`conn-new-${moduleName}-${key}`);
            if (!el) return '';
            if (el.type === 'checkbox') return el.checked ? 'true' : 'false';
            return (el.value || '').trim();
        },

        updateConnectionFieldVisibility(moduleName) {
            const container = document.getElementById(`mod-connections-container-${moduleName}`);
            if (!container) return;
            const rows = container.querySelectorAll('[data-show-when-key]');
            rows.forEach((row) => {
                const key = row.getAttribute('data-show-when-key');
                const values = (row.getAttribute('data-show-when-values') || '')
                    .split(',')
                    .map(v => v.trim())
                    .filter(Boolean);
                const current = this._getConnectionFieldValue(moduleName, key);
                row.style.display = values.includes(current) ? '' : 'none';
            });
        },

        applyMcpPreset(moduleName, presetId) {
            if (moduleName !== 'mcp_server') return;
            const presets = {
                filesystem_stdio: {
                    name: 'Filesystem MCP',
                    environment: 'lab',
                    description: 'Lokaler stdio-MCP-Server fuer Dateisystemzugriff',
                    transport: 'stdio',
                    command: 'npx',
                    args_json: '["-y","@modelcontextprotocol/server-filesystem","/srv/data"]',
                    cwd: '',
                    env_json: '{}',
                    url: '',
                    message_url: '',
                    headers_json: '{}',
                    protocol_version: '2025-03-26',
                    timeout_seconds: '20',
                },
                remote_http: {
                    name: 'Remote MCP HTTP',
                    environment: 'staging',
                    description: 'HTTP-basierter MCP-Server',
                    transport: 'http',
                    command: '',
                    args_json: '[]',
                    cwd: '',
                    env_json: '{}',
                    url: 'https://mcp.example.com/mcp',
                    message_url: '',
                    headers_json: '{"X-API-Key":"replace-me"}',
                    protocol_version: '2025-03-26',
                    timeout_seconds: '20',
                },
                remote_sse: {
                    name: 'Remote MCP SSE',
                    environment: 'staging',
                    description: 'SSE-basierter MCP-Server',
                    transport: 'sse',
                    command: '',
                    args_json: '[]',
                    cwd: '',
                    env_json: '{}',
                    url: 'https://mcp.example.com/sse',
                    message_url: 'https://mcp.example.com/messages',
                    headers_json: '{"Authorization":"Bearer replace-me"}',
                    protocol_version: '2025-03-26',
                    timeout_seconds: '20',
                },
            };
            const preset = presets[presetId];
            if (!preset) return;

            const setValue = (key, value) => {
                const el = document.getElementById(`conn-new-${moduleName}-${key}`);
                if (!el) return;
                if (el.type === 'checkbox') {
                    el.checked = value === true || value === 'true';
                } else {
                    el.value = value ?? '';
                }
            };

            document.getElementById(`conn-new-${moduleName}-name`).value = preset.name;
            document.getElementById(`conn-new-${moduleName}-environment`).value = preset.environment;
            document.getElementById(`conn-new-${moduleName}-desc`).value = preset.description;

            Object.entries(preset).forEach(([key, value]) => {
                if (['name', 'environment', 'description'].includes(key)) return;
                setValue(key, value);
            });

            this.updateConnectionFieldVisibility(moduleName);
            showNotification(`MCP-Beispielprofil "${preset.name}" eingefuellt`, 'info');
        },

        async toggleModule(name, enabled) {
            const connContainer = document.getElementById(`mod-connections-container-${name}`);
            if (connContainer && !enabled) {
                connContainer.style.display = 'none';
            }

            try {
                // connection legacy property is left Empty: {}
                await fetch(`/api/settings/modules/${name}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled, connection: {} }),
                });

                showNotification(`${name} ${enabled ? 'aktiviert' : 'deaktiviert'}. Neustart empfohlen.`, 'info');
                if (enabled && this.ACTION_FIELDS[name]) {
                    await this.loadModuleConnections(name);
                }
            } catch {
                showNotification(`Fehler beim ${enabled ? 'Aktivieren' : 'Deaktivieren'} von ${name}`, 'error');
            }
        },

        _renderModuleConnectionForm(moduleName) {
            const moduleFields = this.ACTION_FIELDS[moduleName] || [];
            if (!moduleFields.length) return '';
            const presetSection = moduleName === 'mcp_server'
                ? `
                    <div class="form-row form-row-sm">
                        <label class="form-label">Beispielprofile</label>
                        <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                            <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'filesystem_stdio']).replace(/\"/g, '&quot;')}">Filesystem stdio</button>
                            <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'remote_http']).replace(/\"/g, '&quot;')}">Remote HTTP</button>
                            <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'remote_sse']).replace(/\"/g, '&quot;')}">Remote SSE</button>
                        </div>
                        <small class="text-muted">Füllt typische MCP-Server-Konfigurationen vor. Werte danach bei Bedarf anpassen.</small>
                    </div>
                `
                : '';

            return `
                <div class="add-connection-section">
                    <h6 id="conn-form-title-${moduleName}" class="add-connection-title">Neue Verbindung hinzufügen</h6>
                    <input type="hidden" id="conn-edit-id-${moduleName}" value="">
                    <div class="form-row form-row-sm">
                        <label class="form-label" for="conn-new-${moduleName}-name">Name</label>
                        <input type="text" id="conn-new-${moduleName}-name" class="form-input" placeholder="z.B. Prod Cluster">
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label" for="conn-new-${moduleName}-environment">Umgebung</label>
                        <select id="conn-new-${moduleName}-environment" class="form-select">
                            <option value="prod">Production</option>
                            <option value="staging">Staging</option>
                            <option value="dev">Development</option>
                            <option value="lab">Lab</option>
                        </select>
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label" for="conn-new-${moduleName}-desc">Beschreibung (optional)</label>
                        <input type="text" id="conn-new-${moduleName}-desc" class="form-input" placeholder="...">
                    </div>
                    ${presetSection}
                    ${moduleFields.map(f => {
                const wrapperAttrs = f.showWhen
                    ? ` data-show-when-key="${f.showWhen.key}" data-show-when-values="${f.showWhen.values.join(',')}"`
                    : '';
                if (f.type === 'checkbox') {
                    return `
                            <div class="form-row form-row-sm"${wrapperAttrs}>
                                <label class="form-label">
                                    <input type="checkbox" id="conn-new-${moduleName}-${f.key}" checked>
                                    ${f.label}
                                </label>
                            </div>`;
                }
                if (f.type === 'select') {
                    const options = (f.options || []).map(opt => `
                                    <option value="${this._escapeHtml(opt.value)}" ${opt.value === (f.defaultValue || '') ? 'selected' : ''}>${this._escapeHtml(opt.label)}</option>
                                `).join('');
                    const handler = moduleName === 'mcp_server' && f.key === 'transport'
                        ? ` onchange="Ninko.updateConnectionFieldVisibility('${moduleName}')"`
                        : '';
                    return `
                            <div class="form-row form-row-sm"${wrapperAttrs}>
                                <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                                <select id="conn-new-${moduleName}-${f.key}" class="form-select"${handler}>
                                    ${options}
                                </select>
                            </div>`;
                }
                if (f.type === 'file') {
                    return `
                            <div class="form-row form-row-sm"${wrapperAttrs}>
                                <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                                <input type="file" id="conn-new-${moduleName}-${f.key}" class="form-input form-file">
                                ${f.isSecret ? '<small class="text-muted">Leer lassen, um das vorhandene Zertifikat beizubehalten.</small>' : ''}
                            </div>`;
                }
                if (f.type === 'textarea') {
                    return `
                            <div class="form-row form-row-sm"${wrapperAttrs}>
                                <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                                <textarea id="conn-new-${moduleName}-${f.key}"
                                    class="form-input form-textarea"
                                    rows="${f.rows || 4}"
                                    placeholder="${f.placeholder || ''}">${f.defaultValue || ''}</textarea>
                            </div>`;
                }
                return `
                            <div class="form-row form-row-sm"${wrapperAttrs}>
                                <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                                <input type="${f.type || 'text'}" id="conn-new-${moduleName}-${f.key}"
                                    class="form-input" placeholder="${f.placeholder || ''}" value="${f.defaultValue || ''}">
                            </div>`;
            }).join('')}
                    <div class="form-row form-row-sm">
                        <label class="form-label">
                            <input type="checkbox" id="conn-new-${moduleName}-default">
                            Als Standard-Verbindung für dieses Modul setzen
                        </label>
                    </div>
                    <div class="form-actions add-connection-actions">
                        <span id="mod-save-status-${moduleName}" class="save-status"></span>
                        <button class="btn btn-sm btn-primary" id="conn-save-btn-${moduleName}"
                            data-action="saveConnection" data-args="${JSON.stringify([moduleName]).replace(/\"/g, '&quot;')}">
                            ➕ Speichern
                        </button>
                        <button class="btn btn-sm btn-outline hidden" id="conn-cancel-btn-${moduleName}"
                            data-action="cancelEditConnection" data-args="${JSON.stringify([moduleName]).replace(/\"/g, '&quot;')}">
                            Abbrechen
                        </button>
                    </div>
                </div>`;
        },

        async loadModuleConnections(moduleName) {
            const container = document.getElementById(`connections-list-${moduleName}`);
            if (!container) return;

            try {
                const res = await fetch(`/api/connections/${moduleName}?_t=${Date.now()}`, { cache: 'no-store' });
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const connections = data.connections || [];

                if (!connections.length) {
                    container.innerHTML = '<p class="text-sm text-muted" style="margin-bottom: 1rem;">Noch keine Verbindungen angelegt.</p>';
                    return;
                }

                container.innerHTML = connections.map(c => `
                    <div class="cluster-card ${c.is_default ? 'cluster-default' : ''}">
                        <div class="cluster-info">
                            <span class="cluster-name">
                                ${this._escapeHtml(c.name)}
                                <span class="status-badge status-unknown cluster-env-badge">${this._escapeHtml(c.environment || '')}</span>
                            </span>
                            ${c.description ? `<span class="cluster-desc">${this._escapeHtml(c.description)}</span>` : ''}
                            ${c.is_default ? '<span class="status-badge status-ok cluster-default-badge">Standard</span>' : ''}
                        </div>
                        <div class="cluster-actions">
                            ${!c.is_default ? `<button class="btn btn-sm btn-outline" data-action="setDefaultConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">⭐ Standard</button>` : ''}
                            <button class="btn btn-sm btn-outline" data-action="editConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">✎</button>
                            <button class="btn btn-sm btn-danger" data-action="deleteConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">${this._ic.trash}</button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error(`Fehler beim Laden der Connections für ${moduleName}:`, e);
                container.innerHTML = '<p class="text-sm save-error">Fehler beim Laden.</p>';
            }
        },

        async editConnection(moduleName, connectionId) {
            try {
                const res = await fetch(`/api/connections/${moduleName}`, { cache: 'no-store' });
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const conn = (data.connections || []).find(c => c.id === connectionId);
                if (!conn) return;

                // Fill form
                document.getElementById(`conn-edit-id-${moduleName}`).value = conn.id;
                document.getElementById(`conn-new-${moduleName}-name`).value = conn.name;
                document.getElementById(`conn-new-${moduleName}-environment`).value = conn.environment;
                document.getElementById(`conn-new-${moduleName}-desc`).value = conn.description || '';
                document.getElementById(`conn-new-${moduleName}-default`).checked = conn.is_default;

                const fields = this.ACTION_FIELDS[moduleName] || [];
                for (const f of fields) {
                    const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
                    const val = conn.config ? conn.config[f.key] : '';
                    if (f.type === 'checkbox') {
                        // Default to true (checked) unless explicitly set to false
                        el.checked = val === undefined ? true : val === true || val === 'true';
                    } else if (f.type !== 'file' && !f.isSecret) {
                        el.value = val || '';
                    } else if (f.isSecret) {
                        el.placeholder = '•••••• (Leer lassen, um beizubehalten)';
                        el.value = '';
                    }
                }
                this.updateConnectionFieldVisibility(moduleName);

                // Update UI state
                document.getElementById(`conn-form-title-${moduleName}`).textContent = 'Verbindung bearbeiten';
                const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
                saveBtn.innerHTML = '💾 Aktualisieren';
                document.getElementById(`conn-cancel-btn-${moduleName}`).classList.remove('hidden');

                document.getElementById(`conn-form-title-${moduleName}`).scrollIntoView({ behavior: 'smooth' });
            } catch (e) {
                console.error('Fehler beim Laden für Bearbeitung', e);
            }
        },

        cancelEditConnection(moduleName) {
            document.getElementById(`conn-edit-id-${moduleName}`).value = '';
            document.getElementById(`conn-new-${moduleName}-name`).value = '';
            document.getElementById(`conn-form-title-${moduleName}`).textContent = 'Neue Verbindung hinzufügen';

            const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
            saveBtn.innerHTML = '➕ Speichern';
            document.getElementById(`conn-cancel-btn-${moduleName}`).classList.add('hidden');

            const fields = this.ACTION_FIELDS[moduleName] || [];
            for (const f of fields) {
                const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
                if (f.type === 'checkbox') el.checked = true;
                else if (f.type === 'file') el.value = '';
                else el.value = f.defaultValue || '';

                if (f.isSecret) el.placeholder = f.placeholder || '';
            }
            this.updateConnectionFieldVisibility(moduleName);
        },

        async saveConnection(moduleName) {
            const statusEl = document.getElementById(`mod-save-status-${moduleName}`);
            const editId = document.getElementById(`conn-edit-id-${moduleName}`).value;
            const name = document.getElementById(`conn-new-${moduleName}-name`).value.trim();
            const env = document.getElementById(`conn-new-${moduleName}-environment`).value;
            const desc = document.getElementById(`conn-new-${moduleName}-desc`).value.trim();
            const isDefault = document.getElementById(`conn-new-${moduleName}-default`).checked;

            if (!name) {
                statusEl.textContent = 'Name erforderlich';
                statusEl.className = 'save-status save-error';
                return;
            }

            const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
            if (saveBtn) saveBtn.disabled = true;

            statusEl.textContent = 'Speichere…';
            statusEl.className = 'save-status save-pending';

            const config = {};
            const vault_keys = {};
            const fields = this.ACTION_FIELDS[moduleName] || [];

            try {
                for (const f of fields) {
                    const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
                    let val = '';
                    if (f.type === 'checkbox') {
                        val = el.checked ? "true" : "false"; // bools are usually cast strings or handle natively
                    } else if (f.type === 'file') {
                        if (el.files && el.files.length > 0) {
                            const file = el.files[0];
                            const text = await file.text();
                            val = btoa(text);
                        }
                    } else {
                        val = el.value.trim();
                    }

                    if (val) {
                        if (f.isSecret) vault_keys[f.key] = val;
                        else config[f.key] = val;
                    }
                }

                if (moduleName === 'mcp_server') {
                    const transport = config.transport || 'stdio';
                    const jsonChecks = [
                        { key: 'args_json', type: 'array', enabled: transport === 'stdio' },
                        { key: 'env_json', type: 'object', enabled: transport === 'stdio' },
                        { key: 'headers_json', type: 'object', enabled: transport === 'http' || transport === 'sse' },
                    ];
                    for (const check of jsonChecks) {
                        if (!check.enabled || !config[check.key]) continue;
                        const parsed = JSON.parse(config[check.key]);
                        const isValid =
                            (check.type === 'array' && Array.isArray(parsed)) ||
                            (check.type === 'object' && parsed && typeof parsed === 'object' && !Array.isArray(parsed));
                        if (!isValid) {
                            throw new Error(`${check.key} muss gültiges JSON vom Typ ${check.type} sein.`);
                        }
                    }
                    if (transport === 'stdio' && !config.command) {
                        throw new Error('Für stdio ist ein Command erforderlich.');
                    }
                    if ((transport === 'http' || transport === 'sse') && !config.url) {
                        throw new Error(`Für ${transport} ist eine URL erforderlich.`);
                    }
                }

                const payload = {
                    name: name,
                    environment: env,
                    description: desc,
                    config: config,
                    secrets: vault_keys,
                    is_default: isDefault
                };

                const url = editId ? `/api/connections/${moduleName}/${editId}` : `/api/connections/${moduleName}`;
                const method = editId ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (res.ok) {
                    statusEl.textContent = 'Gespeichert';
                    statusEl.className = 'save-status save-ok';
                    showNotification(`Verbindung "${name}" ${editId ? 'aktualisiert' : 'hinzugefügt'}`, 'info');

                    this.cancelEditConnection(moduleName);
                    await this.loadModuleConnections(moduleName);
                } else {
                    const err = await res.json();
                    statusEl.textContent = err.detail || 'Fehler';
                    statusEl.className = 'save-status save-error';
                }
            } catch (e) {
                console.error(e);
                statusEl.textContent = 'Verbindungsfehler';
                statusEl.className = 'save-status save-error';
            } finally {
                const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
                if (saveBtn) saveBtn.disabled = false;
            }
        },

        async deleteConnection(moduleName, connectionId) {
            // HINWEIS: Native confirm() Dialoge brechen in manchen Browsern (Chrome) sofort ab, 
            // wenn im Hintergrund DOM-Updates (durch Websockets/Traefik) getriggert werden.
            // Um ein "Flackern" des Popups zu verhindern, löschen wir direkt.
            if (!await this.confirm('Verbindung wirklich löschen?')) return;
            try {
                const res = await fetch(`/api/connections/${moduleName}/${connectionId}?_t=${Date.now()}`, { method: 'DELETE', cache: 'no-store' });
                if (res.ok) {
                    showNotification('Verbindung gelöscht', 'info');
                    await this.loadModuleConnections(moduleName);
                } else {
                    showNotification('Fehler beim Löschen', 'error');
                }
            } catch {
                showNotification('Verbindungsfehler', 'error');
            }
        },

        async setDefaultConnection(moduleName, connectionId) {
            try {
                const res = await fetch(`/api/connections/${moduleName}/${connectionId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_default: true }),
                });
                if (res.ok) {
                    showNotification('Standard-Verbindung aktualisiert', 'info');
                    await this.loadModuleConnections(moduleName);
                } else {
                    showNotification('Fehler beim Aktualisieren des Defaults', 'error');
                }
            } catch {
                showNotification('Verbindungsfehler', 'error');
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, ModuleSettingsFeature);
    } else {
        window.ModuleSettingsFeature = ModuleSettingsFeature;
    }
})();
