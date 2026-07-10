/**
 * Ninko RBAC / Access Feature Module
 *
 * Benutzer-, Gruppen- und Rollenverwaltung inkl. Modulrechte, API-Tokens
 * und benutzerdefinierten Settings. Aus app.js extrahiert; via Object.assign
 * auf Ninko gemergt. Der _rbac*-State bleibt in app.js (Init-Bereich).
 */

(function() {
    'use strict';

    const RbacFeature = {
        async loadRbacSettings() {
            const root = document.getElementById('rbac-root');
            if (!root) return;
            root.innerHTML = '<p class="text-muted">Lade Benutzerverwaltung…</p>';

            try {
                const [modsRes, rolesRes, groupsRes, usersRes] = await Promise.all([
                    fetch('/api/auth/modules/available'),
                    fetch('/api/auth/roles'),
                    fetch('/api/auth/groups'),
                    fetch('/api/auth/users'),
                ]);
                if (!modsRes.ok || !rolesRes.ok || !groupsRes.ok || !usersRes.ok) {
                    throw new Error('RBAC-Endpunkte nicht verfügbar oder keine Berechtigung.');
                }

                const mods = await modsRes.json();
                const roles = await rolesRes.json();
                const groups = await groupsRes.json();
                const users = await usersRes.json();

                this._rbacModules = mods.modules || [];
                this._rbacRoles = roles.roles || [];
                this._rbacGroups = groups.groups || [];
                this._rbacUsers = users.users || [];
                if (!this._rbacSelectedUser && this._rbacUsers.length) {
                    this._rbacSelectedUser = this._rbacUsers[0].username;
                }
                if (!this._rbacTokenSelectedUser && this._rbacUsers.length) {
                    this._rbacTokenSelectedUser = this._rbacUsers[0].username;
                }

                this.renderRbacSettings();
            } catch (e) {
                root.innerHTML = `<p class="empty-state">${this._escapeHtml(e.message || 'Fehler beim Laden der Benutzerverwaltung.')}</p>`;
            }
        },

        _rbacUserOptions(selectedUsername = '') {
            return this._rbacUsers
                .map(u => `<option value="${this._escapeHtml(u.username)}" ${u.username === selectedUsername ? 'selected' : ''}>${this._escapeHtml(u.username)}</option>`)
                .join('');
        },

        renderRbacSettings() {
            const root = document.getElementById('rbac-root');
            if (!root) return;

            const roleOptions = this._rbacRoles
                .map(r => `<option value="${this._escapeHtml(r.id)}">${this._escapeHtml(r.name || r.id)}</option>`)
                .join('');
            const groupOptions = this._rbacGroups
                .map(g => `<option value="${this._escapeHtml(g.id)}">${this._escapeHtml(g.name || g.id)}</option>`)
                .join('');

            root.innerHTML = `
                <div class="setting-group">
                    <h4>Benutzerverwaltung (RBAC)</h4>
                    <p class="setting-desc">Verwalte Benutzer, Gruppen und Rollen. Rechte können pro Modul konfiguriert werden.</p>
                    <div class="form-actions">
                        <span id="rbac-save-status" class="save-status"></span>
                        <button class="btn btn-outline btn-sm" data-action="loadRbacSettings">Neu laden</button>
                    </div>
                </div>

                <div class="setting-group">
                    <h4>Benutzer</h4>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                        <input id="rbac-user-username" type="text" class="form-input" placeholder="username" style="max-width:180px;">
                        <input id="rbac-user-password" type="password" class="form-input" placeholder="Passwort (>=8)" style="max-width:220px;">
                        <select id="rbac-user-role" class="form-select" style="max-width:200px;">
                            <option value="">Rolle (optional)</option>
                            ${roleOptions}
                        </select>
                        <select id="rbac-user-group" class="form-select" style="max-width:200px;">
                            <option value="">Gruppe (optional)</option>
                            ${groupOptions}
                        </select>
                        <button class="btn btn-primary btn-sm" data-action="createRbacUser">Benutzer anlegen</button>
                    </div>
                    <div id="rbac-users-list">${this._renderRbacUsersTable()}</div>
                </div>

                <div class="setting-group">
                    <h4>API-Tokens</h4>
                    <p class="setting-desc">API-Tokens werden nur von Admins erstellt und einmalig angezeigt. Zugriff erfolgt via <code>X-API-Key</code> oder <code>Authorization: Bearer ...</code>.</p>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                        <select id="rbac-token-user" class="form-select" style="max-width:220px;" onchange="Ninko.onRbacTokenUserChange(this.value)">
                            ${this._rbacUserOptions(this._rbacTokenSelectedUser || '')}
                        </select>
                        <input id="rbac-token-name" type="text" class="form-input" placeholder="Token-Name" style="max-width:220px;">
                        <input id="rbac-token-exp-hours" type="number" min="1" max="8760" class="form-input" placeholder="Ablauf in Stunden" value="720" style="max-width:180px;">
                        <button class="btn btn-primary btn-sm" data-action="createRbacUserApiToken">Token erstellen</button>
                    </div>
                    <div id="rbac-token-created" class="save-status" style="margin-bottom:0.6rem;"></div>
                    <div id="rbac-token-list"><p class="text-muted">Bitte Benutzer auswählen.</p></div>
                </div>

                <div class="setting-group">
                    <h4>Benutzerdefinierte Settings</h4>
                    <p class="setting-desc">Freies JSON-Feld je Benutzer (z.B. individuelle Präferenzen oder Modulvorgaben).</p>
                    <div class="form-row">
                        <label class="form-label" for="rbac-user-settings-user">Benutzer</label>
                        <select id="rbac-user-settings-user" class="form-select" style="max-width:220px;" onchange="Ninko.onRbacSettingsUserChange(this.value)">
                            ${this._rbacUserOptions(this._rbacSelectedUser || '')}
                        </select>
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="rbac-user-custom-settings-json">Settings (JSON)</label>
                        <textarea id="rbac-user-custom-settings-json" class="form-input" rows="8" placeholder='{"dashboard":{"default_module":"kubernetes"}}'></textarea>
                    </div>
                    <div class="form-actions">
                        <button class="btn btn-outline btn-sm" data-action="loadRbacUserCustomSettings">Laden</button>
                        <button class="btn btn-primary btn-sm" data-action="saveRbacUserCustomSettings">Speichern</button>
                    </div>
                </div>

                <div class="setting-group">
                    <h4>Gruppen</h4>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                        <input id="rbac-group-id" type="text" class="form-input" placeholder="group_id" style="max-width:180px;">
                        <input id="rbac-group-name" type="text" class="form-input" placeholder="Anzeigename" style="max-width:220px;">
                        <select id="rbac-group-role" class="form-select" style="max-width:220px;">
                            <option value="">Rolle zuweisen (optional)</option>
                            ${roleOptions}
                        </select>
                        <button class="btn btn-primary btn-sm" data-action="createRbacGroup">Gruppe anlegen</button>
                    </div>
                    <div id="rbac-groups-list">${this._renderRbacGroupsTable()}</div>
                </div>

                <div class="setting-group">
                    <h4>Rollen</h4>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                        <input id="rbac-role-id" type="text" class="form-input" placeholder="role_id" style="max-width:180px;">
                        <input id="rbac-role-name" type="text" class="form-input" placeholder="Anzeigename" style="max-width:220px;">
                        <select id="rbac-role-base" class="form-select" style="max-width:140px;">
                            <option value="read">read</option>
                            <option value="write">write</option>
                            <option value="admin">admin</option>
                        </select>
                        <button class="btn btn-primary btn-sm" data-action="createRbacRole">Rolle anlegen</button>
                    </div>
                    <div class="form-row">
                        <label class="form-label" for="rbac-role-edit-select">Rolle für Modulrechte bearbeiten</label>
                        <select id="rbac-role-edit-select" class="form-select" onchange="Ninko.renderRbacRolePermissions()">
                            <option value="">Bitte Rolle wählen…</option>
                            ${roleOptions}
                        </select>
                    </div>
                    <div id="rbac-role-permissions"></div>
                    <div id="rbac-roles-list" style="margin-top:0.75rem;">${this._renderRbacRolesTable()}</div>
                </div>
            `;
            this.loadRbacUserApiTokens();
            this.loadRbacUserCustomSettings();
        },

        _setRbacStatus(message, ok = true) {
            const el = document.getElementById('rbac-save-status');
            if (!el) return;
            el.innerHTML = ok
                ? `<span class="sf sf-ok">${this._escapeHtml(message)}</span>`
                : `<span class="sf sf-error">${this._escapeHtml(message)}</span>`;
            clearTimeout(this._rbacStatusTimer);
            if (ok) this._rbacStatusTimer = setTimeout(() => { el.innerHTML = ''; }, 4000);
        },

        _renderRbacUsersTable() {
            if (!this._rbacUsers.length) return '<p class="text-muted">Keine Benutzer vorhanden.</p>';
            const rows = this._rbacUsers.map(u => `
                <tr>
                    <td><code>${this._escapeHtml(u.username)}</code></td>
                    <td>${u.active ? 'aktiv' : 'inaktiv'}</td>
                    <td>${this._escapeHtml((u.roles || []).join(', ') || '-')}</td>
                    <td>${this._escapeHtml((u.groups || []).join(', ') || '-')}</td>
                    <td style="white-space:nowrap;">
                        <div style="display:inline-flex; gap:0.35rem;">
                            <button class="btn btn-outline btn-sm" data-action="toggleRbacUserActive" data-args="${JSON.stringify([u.username, !u.active]).replace(/\"/g, '&quot;')}">${u.active ? 'Deaktivieren' : 'Aktivieren'}</button>
                            <button class="btn btn-outline btn-sm" data-action="setRbacUserPassword" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Passwort</button>
                            <button class="btn btn-outline btn-sm" data-action="openRbacUserSettings" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Settings</button>
                            <button class="btn btn-outline btn-sm" data-action="openRbacUserTokens" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">API-Token</button>
                            <button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacUser" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Löschen</button>
                        </div>
                    </td>
                </tr>
            `).join('');
            return `
                <div style="overflow:auto;">
                    <table class="log-table log-table-auto">
                        <thead><tr><th>User</th><th>Status</th><th>Rollen</th><th>Gruppen</th><th>Aktionen</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        },

        _renderRbacGroupsTable() {
            if (!this._rbacGroups.length) return '<p class="text-muted">Keine Gruppen vorhanden.</p>';
            const rows = this._rbacGroups.map(g => `
                <tr>
                    <td><code>${this._escapeHtml(g.id)}</code></td>
                    <td>${this._escapeHtml(g.name || '')}</td>
                    <td>${this._escapeHtml((g.roles || []).join(', ') || '-')}</td>
                    <td>${this._escapeHtml(((g.users || []).length).toString())}</td>
                    <td>
                        ${g.id === 'group_admins' ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacGroup" data-args="${JSON.stringify([g.id]).replace(/\"/g, '&quot;')}">Löschen</button>`}
                    </td>
                </tr>
            `).join('');
            return `
                <div style="overflow:auto;">
                    <table class="log-table">
                        <thead><tr><th>ID</th><th>Name</th><th>Rollen</th><th>Mitglieder</th><th>Aktion</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        },

        _renderRbacRolesTable() {
            if (!this._rbacRoles.length) return '<p class="text-muted">Keine Rollen vorhanden.</p>';
            const rows = this._rbacRoles.map(r => `
                <tr>
                    <td><code>${this._escapeHtml(r.id)}</code></td>
                    <td>${this._escapeHtml(r.name || '')}</td>
                    <td>${this._escapeHtml(r.base_role || 'read')}</td>
                    <td>${this._escapeHtml(Object.keys(r.module_permissions || {}).join(', ') || '-')}</td>
                    <td>
                        ${r.id === 'role_admin' ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacRole" data-args="${JSON.stringify([r.id]).replace(/\"/g, '&quot;')}">Löschen</button>`}
                    </td>
                </tr>
            `).join('');
            return `
                <div style="overflow:auto;">
                    <table class="log-table">
                        <thead><tr><th>ID</th><th>Name</th><th>Base Role</th><th>Module</th><th>Aktion</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        },

        renderRbacRolePermissions() {
            const roleId = document.getElementById('rbac-role-edit-select')?.value || '';
            const container = document.getElementById('rbac-role-permissions');
            if (!container) return;
            if (!roleId) {
                container.innerHTML = '';
                return;
            }
            const role = this._rbacRoles.find(r => r.id === roleId);
            if (!role) {
                container.innerHTML = '<p class="text-muted">Rolle nicht gefunden.</p>';
                return;
            }

            const currentPerms = role.module_permissions || {};
            const rows = this._rbacModules.map(m => {
                const key = (m.id || '').toLowerCase().replace(/-/g, '_');
                const wildcard = currentPerms['*'] || {};
                const specific = currentPerms[key] || {};
                const readChecked = (specific.read === true) || (specific.read !== false && wildcard.read === true);
                const writeChecked = (specific.write === true) || (specific.write !== false && wildcard.write === true);
                return `
                    <tr>
                        <td>${this._escapeHtml(m.display_name || m.id)}</td>
                        <td><input type="checkbox" data-rbac-perm="read" data-module-id="${this._escapeHtml(key)}" ${readChecked ? 'checked' : ''}></td>
                        <td><input type="checkbox" data-rbac-perm="write" data-module-id="${this._escapeHtml(key)}" ${writeChecked ? 'checked' : ''}></td>
                    </tr>
                `;
            }).join('');

            container.innerHTML = `
                <div style="margin-top:0.6rem;">
                    <div class="text-muted" style="font-size:0.82rem; margin-bottom:0.4rem;">Rolle: <code>${this._escapeHtml(roleId)}</code></div>
                    <div style="overflow:auto; max-height:280px;">
                        <table class="log-table">
                            <thead><tr><th>Modul</th><th>Read</th><th>Write</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                    <div class="form-actions" style="margin-top:0.5rem;">
                        <button class="btn btn-primary btn-sm" data-action="saveRbacRolePermissions" data-args="${JSON.stringify([roleId]).replace(/\"/g, '&quot;')}">Modulrechte speichern</button>
                    </div>
                </div>
            `;
        },

        async createRbacUser() {
            const username = document.getElementById('rbac-user-username')?.value?.trim() || '';
            const password = document.getElementById('rbac-user-password')?.value || '';
            const role = document.getElementById('rbac-user-role')?.value || '';
            const group = document.getElementById('rbac-user-group')?.value || '';
            if (!username || !password) return this._setRbacStatus('Username und Passwort sind Pflicht.', false);
            try {
                const res = await fetch('/api/auth/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username,
                        password,
                        active: true,
                        roles: role ? [role] : [],
                        groups: group ? [group] : [],
                    }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
                this._setRbacStatus(`Benutzer ${username} angelegt.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async toggleRbacUserActive(username, active) {
            try {
                const user = this._rbacUsers.find(u => u.username === username);
                if (!user) throw new Error('Benutzer nicht gefunden');
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        active,
                        roles: user.roles || [],
                        groups: user.groups || [],
                    }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Aktualisieren');
                this._setRbacStatus(`Benutzer ${username} aktualisiert.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async setRbacUserPassword(username) {
            const pw = prompt(`Neues Passwort für ${username} (mind. 8 Zeichen):`);
            if (!pw) return;
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/password`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: pw }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Passwort-Update');
                this._setRbacStatus(`Passwort für ${username} gesetzt.`);
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async deleteRbacUser(username) {
            if (!confirm(`Benutzer ${username} wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
                this._setRbacStatus(`Benutzer ${username} gelöscht.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        openRbacUserSettings(username) {
            this._rbacSelectedUser = username;
            const sel = document.getElementById('rbac-user-settings-user');
            if (sel) sel.value = username;
            this.loadRbacUserCustomSettings();
        },

        openRbacUserTokens(username) {
            this._rbacTokenSelectedUser = username;
            const sel = document.getElementById('rbac-token-user');
            if (sel) sel.value = username;
            this.loadRbacUserApiTokens();
        },

        onRbacSettingsUserChange(username) {
            this._rbacSelectedUser = username || '';
            this.loadRbacUserCustomSettings();
        },

        onRbacTokenUserChange(username) {
            this._rbacTokenSelectedUser = username || '';
            this.loadRbacUserApiTokens();
        },

        async loadRbacUserCustomSettings() {
            const username = this._rbacSelectedUser || document.getElementById('rbac-user-settings-user')?.value || '';
            const ta = document.getElementById('rbac-user-custom-settings-json');
            if (!username || !ta) return;
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/settings`);
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Laden der Settings');
                const data = await res.json();
                ta.value = JSON.stringify(data.settings || {}, null, 2);
                this._setRbacStatus(`Settings für ${username} geladen.`);
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async saveRbacUserCustomSettings() {
            const username = this._rbacSelectedUser || document.getElementById('rbac-user-settings-user')?.value || '';
            const ta = document.getElementById('rbac-user-custom-settings-json');
            if (!username || !ta) return this._setRbacStatus('Bitte Benutzer wählen.', false);
            let settings = {};
            try {
                settings = ta.value.trim() ? JSON.parse(ta.value) : {};
            } catch {
                return this._setRbacStatus('Ungültiges JSON in benutzerdefinierten Settings.', false);
            }
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/settings`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ settings }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Speichern der Settings');
                this._setRbacStatus(`Settings für ${username} gespeichert.`);
                await this.loadRbacSettings();
                this._rbacSelectedUser = username;
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async loadRbacUserApiTokens() {
            const username = this._rbacTokenSelectedUser || document.getElementById('rbac-token-user')?.value || '';
            const listEl = document.getElementById('rbac-token-list');
            if (!listEl || !username) return;
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens`);
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Laden der API-Tokens');
                const data = await res.json();
                const tokens = data.tokens || [];
                if (!tokens.length) {
                    listEl.innerHTML = '<p class="text-muted">Keine API-Tokens vorhanden.</p>';
                    return;
                }
                const rows = tokens.map(t => `
                    <tr>
                        <td><code>${this._escapeHtml(t.id || '')}</code></td>
                        <td>${this._escapeHtml(t.name || '')}</td>
                        <td>${this._escapeHtml(t.created_at || '-')}</td>
                        <td>${this._escapeHtml(t.expires_at || '-')}</td>
                        <td>${t.revoked ? 'revoked' : 'active'}</td>
                        <td>${t.revoked ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="revokeRbacUserApiToken" data-args="${JSON.stringify([username, t.id || '']).replace(/\"/g, '&quot;')}">Revoke</button>`}</td>
                    </tr>
                `).join('');
                listEl.innerHTML = `
                    <div style="overflow:auto;">
                        <table class="log-table">
                            <thead><tr><th>ID</th><th>Name</th><th>Created</th><th>Expires</th><th>Status</th><th>Aktion</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                `;
            } catch (e) {
                listEl.innerHTML = `<p class="empty-state">${this._escapeHtml(e.message || 'Fehler')}</p>`;
            }
        },

        async createRbacUserApiToken() {
            const username = this._rbacTokenSelectedUser || document.getElementById('rbac-token-user')?.value || '';
            const name = document.getElementById('rbac-token-name')?.value?.trim() || 'api-token';
            const expiresHours = parseInt(document.getElementById('rbac-token-exp-hours')?.value || '720', 10);
            const out = document.getElementById('rbac-token-created');
            if (!username) return this._setRbacStatus('Bitte Benutzer für API-Token wählen.', false);
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, expires_hours: Number.isFinite(expiresHours) ? expiresHours : 720 }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Fehler beim Erstellen des API-Tokens');
                if (out) {
                    out.innerHTML = `
                        <span class="sf sf-ok">Token erstellt (wird nur einmal angezeigt):</span>
                        <code style="display:block; margin-top:0.35rem; word-break:break-all;">${this._escapeHtml(data.token || '')}</code>
                    `;
                }
                this._setRbacStatus(`API-Token für ${username} erstellt.`);
                await this.loadRbacUserApiTokens();
            } catch (e) {
                if (out) out.innerHTML = '';
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async revokeRbacUserApiToken(username, tokenId) {
            try {
                const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens/${encodeURIComponent(tokenId)}`, {
                    method: 'DELETE',
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Widerruf');
                this._setRbacStatus(`Token ${tokenId} widerrufen.`);
                await this.loadRbacUserApiTokens();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async createRbacGroup() {
            const group_id = document.getElementById('rbac-group-id')?.value?.trim() || '';
            const name = document.getElementById('rbac-group-name')?.value?.trim() || '';
            const role = document.getElementById('rbac-group-role')?.value || '';
            if (!group_id || !name) return this._setRbacStatus('group_id und Name sind Pflicht.', false);
            try {
                const res = await fetch('/api/auth/groups', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ group_id, name, description: '', roles: role ? [role] : [] }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
                this._setRbacStatus(`Gruppe ${group_id} angelegt.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async deleteRbacGroup(groupId) {
            if (!confirm(`Gruppe ${groupId} wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/auth/groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
                this._setRbacStatus(`Gruppe ${groupId} gelöscht.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async createRbacRole() {
            const role_id = document.getElementById('rbac-role-id')?.value?.trim() || '';
            const name = document.getElementById('rbac-role-name')?.value?.trim() || '';
            const base_role = document.getElementById('rbac-role-base')?.value || 'read';
            if (!role_id || !name) return this._setRbacStatus('role_id und Name sind Pflicht.', false);
            try {
                const res = await fetch('/api/auth/roles', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role_id,
                        name,
                        description: '',
                        base_role,
                        module_permissions: { '*': { read: true, write: base_role !== 'read' } },
                    }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
                this._setRbacStatus(`Rolle ${role_id} angelegt.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async saveRbacRolePermissions(roleId) {
            const rows = Array.from(document.querySelectorAll('#rbac-role-permissions input[data-module-id]'));
            const module_permissions = {};
            const byModule = new Map();
            for (const input of rows) {
                const moduleId = input.dataset.moduleId;
                const perm = input.dataset.rbacPerm;
                if (!byModule.has(moduleId)) byModule.set(moduleId, { read: false, write: false });
                byModule.get(moduleId)[perm] = !!input.checked;
            }
            for (const [moduleId, perms] of byModule.entries()) module_permissions[moduleId] = perms;

            try {
                const res = await fetch(`/api/auth/roles/${encodeURIComponent(roleId)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ module_permissions }),
                });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Speichern');
                this._setRbacStatus(`Modulrechte für ${roleId} gespeichert.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },

        async deleteRbacRole(roleId) {
            if (!confirm(`Rolle ${roleId} wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/auth/roles/${encodeURIComponent(roleId)}`, { method: 'DELETE' });
                if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
                this._setRbacStatus(`Rolle ${roleId} gelöscht.`);
                await this.loadRbacSettings();
            } catch (e) {
                this._setRbacStatus(e.message || 'Fehler', false);
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, RbacFeature);
    } else {
        window.RbacFeature = RbacFeature;
    }
})();
