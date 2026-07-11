/**
 * Ninko SafeGuard Feature Module
 *
 * Profil-System (Picker, Auswahl, Bestätigungs-Flow) und Settings-Panel
 * (Profil-CRUD, globale Auswahl, Agent-Zuweisung). Aus app.js extrahiert;
 * via Object.assign gemergt. initSafeguard() wird beim App-Init (DOMContent-
 * Loaded, nach allen Feature-Merges) aufgerufen. _safeguard*-State in app.js.
 */

(function() {
    'use strict';

    const SafeguardFeature = {
        async initSafeguard() {
            try {
                const [statusRes, profilesRes] = await Promise.all([
                    fetch('/api/safeguard/status'),
                    fetch('/api/safeguard/profiles'),
                ]);
                if (statusRes.ok) {
                    const data = await statusRes.json();
                    this._safeguardEnabled = !!data.enabled;
                    this._safeguardActiveId = data.profile_id || 'moderate';
                }
                if (profilesRes.ok) {
                    this._safeguardProfiles = await profilesRes.json();
                }
                this._updateSafeguardBtn();
            } catch (err) { console.warn('loadSafeguardActive failed', err); }
        },

        // Öffnet/schließt den Profil-Picker im Chat-Toolbar
        toggleSafeguardPicker(event) {
            event.stopPropagation();
            const picker = document.getElementById('safeguard-picker');
            const anchor = document.getElementById('btn-safeguard');
            if (!picker) return;
            if (this._safeguardPickerOpen) {
                this._closeSafeguardPicker();
                return;
            }
            this._renderSafeguardPicker(picker);
            this._positionFloatingPopover(picker, anchor, { align: 'right' });
            this._safeguardPickerOpen = true;
            // Außerhalb klicken → schließen
            setTimeout(() => {
                document.addEventListener('click', this._onPickerOutsideClick, { once: true });
            }, 0);
        },

        _onPickerOutsideClick(e) {
            const picker = document.getElementById('safeguard-picker');
            if (picker && !picker.contains(e.target)) {
                Ninko._closeSafeguardPicker();
            } else if (Ninko._safeguardPickerOpen) {
                // Klick innerhalb des Pickers hat den once-Listener konsumiert,
                // ohne zu schließen — neu registrieren, damit der nächste
                // Außenklick den Picker weiterhin schließt.
                document.addEventListener('click', Ninko._onPickerOutsideClick, { once: true });
            }
        },

        _closeSafeguardPicker() {
            const picker = document.getElementById('safeguard-picker');
            if (picker) picker.style.display = 'none';
            this._safeguardPickerOpen = false;
        },

        _renderSafeguardPicker(picker) {
            const profiles = this._safeguardProfiles || [];
            const activeId = this._safeguardActiveId || 'moderate';
            const header = document.createElement('div');
            header.className = 'sg-picker-header';
            header.textContent = t('safeguard.pickProfile');
            const buttons = profiles.map(p => {
                const isActive = p.id === activeId;
                const scopeBadge = this._sgScopeBadge(p);
                const btn = document.createElement('button');
                btn.className = 'sg-picker-item' + (isActive ? ' active' : '');
                btn.dataset.action = '_selectSafeguardProfile';
                btn.dataset.args = JSON.stringify([p.id]);
                const nameSpan = document.createElement('span');
                nameSpan.className = 'sg-picker-name';
                nameSpan.textContent = p.name;
                const scopeSpan = document.createElement('span');
                scopeSpan.className = 'sg-picker-scope';
                scopeSpan.textContent = scopeBadge;
                btn.append(nameSpan, scopeSpan);
                return btn;
            });
            const footer = document.createElement('div');
            footer.className = 'sg-picker-footer';
            const settingsBtn = document.createElement('button');
            settingsBtn.className = 'sg-picker-settings';
            settingsBtn.dataset.actions = '[["_closeSafeguardPicker"],["switchTab","settings"],["switchSettingsTab","safeguard"]]';
            settingsBtn.textContent = t('safeguard.manageProfiles');
            footer.appendChild(settingsBtn);
            picker.replaceChildren(header, ...buttons, footer);
        },

        _sgScopeBadge(p) {
            if (p.auto_mode) return '⚡';
            if (!p.check_user_messages && !p.check_tool_calls) return '⊘';
            if (p.check_user_messages && p.check_tool_calls) return '●●';
            if (p.check_user_messages) return '👤';
            return '🤖';
        },

        _sgToggleAutoPolicy() {
            const on = document.getElementById('sg-editor-auto-mode')?.checked;
            const row = document.getElementById('sg-editor-policy-row');
            if (row) row.style.display = on ? 'flex' : 'none';
        },

        async _selectSafeguardProfile(profileId) {
            this._closeSafeguardPicker();
            try {
                const res = await fetch('/api/safeguard/active', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile_id: profileId }),
                });
                if (res.ok) {
                    this._safeguardActiveId = profileId;
                    const profile = (this._safeguardProfiles || []).find(p => p.id === profileId);
                    this._safeguardEnabled = profile ? (profile.check_user_messages || profile.check_tool_calls) : true;
                    this._updateSafeguardBtn();
                }
            } catch (err) { console.warn('selectSafeguardProfile failed', err); }
        },

        // Backward-compat: einfacher Toggle (Moderate ↔ Disabled)
        async toggleSafeguard() {
            const targetId = this._safeguardEnabled ? 'disabled' : 'moderate';
            await this._selectSafeguardProfile(targetId);
        },

        _updateSafeguardBtn() {
            const btn = document.getElementById('btn-safeguard');
            if (!btn) return;
            const profile = (this._safeguardProfiles || []).find(p => p.id === this._safeguardActiveId);
            const name = profile ? profile.name : (this._safeguardEnabled ? 'Moderate' : 'Disabled');
            if (this._safeguardEnabled) {
                btn.classList.add('safeguard-on');
                btn.classList.remove('safeguard-off');
            } else {
                btn.classList.remove('safeguard-on');
                btn.classList.add('safeguard-off');
            }
            btn.title = `SafeGuard: ${name}`;
        },

        _showSafeguardConfirmPrompt(sg) {
            document.getElementById('safeguard-confirm-prompt')?.remove();
            const container = document.getElementById('chat-messages');
            const catClass = `sg-${(sg.category || 'unknown').toLowerCase().replace('_', '-')}`;
            const isInjection = sg.category === 'PROMPT_INJECTION';
            const div = document.createElement('div');
            div.className = 'safeguard-confirm-prompt';
            div.id = 'safeguard-confirm-prompt';
            div.innerHTML = `
                <div class="safeguard-confirm-content">
                    <span class="safeguard-confirm-category ${catClass}">${sg.category}</span>
                    ${isInjection ? `<p class="sg-injection-warning">${t('safeguard.injectionWarning')}</p>` : ''}
                    <p class="sg-rationale">${this._escapeHtml(sg.rationale || '')}</p>
                    <div class="safeguard-confirm-actions">
                        <button class="btn-confirm-action btn-confirm-run" data-action="confirmSafeguardAction">${t('safeguard.confirmRun')}</button>
                        <button class="btn-confirm-action btn-confirm-cancel" data-action="cancelSafeguardAction">${t('safeguard.confirmCancel')}</button>
                    </div>
                </div>
            `;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        },

        async confirmSafeguardAction() {
            if (!this._safeguardPendingMessage) return;
            document.getElementById('safeguard-confirm-prompt')?.remove();
            const msg = this._safeguardPendingMessage;
            this._safeguardPendingMessage = null;
            const input = document.getElementById('chat-input');
            input.value = msg;
            this._confirmedPending = true;
            await this.sendMessage();
        },

        cancelSafeguardAction() {
            this._safeguardPendingMessage = null;
            document.getElementById('safeguard-confirm-prompt')?.remove();
        },

        // --- SafeGuard Settings Panel -------------------------------------------

        async renderSafeguardSettingsPanel() {
            try {
                const [profilesRes, activeRes] = await Promise.all([
                    fetch('/api/safeguard/profiles'),
                    fetch('/api/safeguard/active'),
                ]);
                if (!profilesRes.ok || !activeRes.ok) return;
                this._safeguardProfiles = await profilesRes.json();
                const activeData = await activeRes.json();
                this._safeguardActiveId = activeData.profile_id;
                this._safeguardEnabled = this._safeguardActiveId !== 'disabled';
                this._updateSafeguardBtn();
            } catch { return; }

            this._renderSgGlobalSelect();
            this._renderSgProfileLists();
        },

        _renderSgGlobalSelect() {
            const sel = document.getElementById('sg-global-profile');
            if (!sel) return;
            sel.innerHTML = (this._safeguardProfiles || []).map(p =>
                `<option value="${this._escapeHtml(p.id)}" ${p.id === this._safeguardActiveId ? 'selected' : ''}>${this._escapeHtml(p.name)}</option>`
            ).join('');
            this._updateSgProfileDetails(this._safeguardActiveId);
        },

        _updateSgProfileDetails(profileId) {
            const profile = (this._safeguardProfiles || []).find(p => p.id === profileId);
            const box = document.getElementById('sg-profile-details');
            const badges = document.getElementById('sg-profile-badges');
            if (!profile || !box || !badges) return;
            box.style.display = 'block';
            const scopeLabel = profile.auto_mode ? t('safeguard.scopeAuto')
                : profile.check_user_messages && profile.check_tool_calls ? t('safeguard.scopeBoth')
                : profile.check_user_messages ? t('safeguard.scopeUser')
                : profile.check_tool_calls ? t('safeguard.scopeLLM')
                : t('safeguard.scopeNone');
            badges.innerHTML = `
                <span class="sg-detail-badge${profile.auto_mode ? ' sg-cat-auto' : ''}">${scopeLabel}</span>
                ${profile.confirm_categories.map(c => `<span class="sg-cat-badge sg-cat-${this._escapeHtml(c.toLowerCase().replace('_','-'))}">${this._escapeHtml(c)}</span>`).join('')}
                ${profile.detect_prompt_injection ? `<span class="sg-detail-badge sg-injection-badge">${t('safeguard.injectionDetect')}</span>` : ''}
                ${profile.fail_open ? `<span class="sg-detail-badge sg-failopen-badge">${t('safeguard.failOpen')}</span>` : ''}
                ${profile.auto_mode ? `<span class="sg-cat-badge sg-cat-auto">⚡ ${t('safeguard.autoMode')}</span>` : ''}
            `;
        },

        async setSafeguardGlobalProfile(profileId) {
            try {
                const res = await fetch('/api/safeguard/active', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile_id: profileId }),
                });
                if (res.ok) {
                    this._safeguardActiveId = profileId;
                    this._safeguardEnabled = profileId !== 'disabled';
                    this._updateSafeguardBtn();
                    this._updateSgProfileDetails(profileId);
                }
            } catch (err) { console.warn('selectSafeguardProfile failed', err); }
        },

        _renderSgProfileLists() {
            const profiles = this._safeguardProfiles || [];
            const custom = profiles.filter(p => !p.builtin);
            const builtin = profiles.filter(p => p.builtin);

            const customList = document.getElementById('sg-custom-profiles-list');
            if (customList) {
                if (custom.length === 0) {
                    customList.innerHTML = `<p class="text-muted" style="font-size:0.85rem;" data-i18n="safeguard.noCustomProfiles">${t('safeguard.noCustomProfiles')}</p>`;
                } else {
                    customList.innerHTML = custom.map(p => this._renderSgProfileCard(p, false)).join('');
                }
            }

            const builtinList = document.getElementById('sg-builtin-profiles-list');
            if (builtinList) {
                builtinList.innerHTML = builtin.map(p => this._renderSgProfileCard(p, true)).join('');
            }
        },

        _renderSgProfileCard(p, readonly) {
            const cats = p.confirm_categories.map(c =>
                `<span class="sg-cat-badge sg-cat-${this._escapeHtml(c.toLowerCase().replace('_','-'))}">${this._escapeHtml(c)}</span>`
            ).join('');
            const scopeIco = this._sgScopeBadge(p);
            const injIco = p.detect_prompt_injection ? ' 🔍' : '';
            const autoIco = p.auto_mode ? ` <span class="sg-cat-badge sg-cat-auto" title="${this._escapeHtml(t('safeguard.autoModeDesc'))}">⚡ ${this._escapeHtml(t('safeguard.autoMode'))}</span>` : '';
            const escapedId = this._escapeHtml(p.id);
            const escapedName = this._escapeHtml(p.name);
            return `<div class="sg-profile-card">
                <div class="sg-profile-card-header">
                    <span class="sg-profile-card-name">${escapedName}</span>
                    <span class="sg-profile-card-id text-muted">${escapedId}</span>
                    ${!readonly ? `
                        <div class="sg-profile-card-actions">
                            <button class="btn btn-xs btn-outline" data-action="openSafeguardProfileEditor" data-args="${JSON.stringify([escapedId]).replace(/\"/g, '&quot;')}">${t('safeguard.edit')}</button>
                            <button class="btn btn-xs btn-danger" data-action="deleteSafeguardProfile" data-args="${JSON.stringify([escapedId]).replace(/\"/g, '&quot;')}">${t('safeguard.delete')}</button>
                        </div>` : ''}
                </div>
                <div class="sg-profile-card-meta">
                    <span class="sg-detail-badge">${scopeIco}</span>${cats}${injIco}${autoIco}
                </div>
            </div>`;
        },

        openSafeguardProfileEditor(profileId) {
            const editor = document.getElementById('sg-profile-editor');
            if (!editor) return;
            const title = document.getElementById('sg-editor-title');
            editor._editingId = profileId || null;

            if (profileId) {
                const p = (this._safeguardProfiles || []).find(x => x.id === profileId);
                if (!p) return;
                document.getElementById('sg-editor-id').value = p.id;
                document.getElementById('sg-editor-id').disabled = true; // ID nicht änderbar
                document.getElementById('sg-editor-name').value = p.name;
                document.getElementById('sg-editor-check-user').checked = p.check_user_messages;
                document.getElementById('sg-editor-check-tools').checked = p.check_tool_calls;
                document.getElementById('sg-editor-cat-destructive').checked = p.confirm_categories.includes('DESTRUCTIVE');
                document.getElementById('sg-editor-cat-state').checked = p.confirm_categories.includes('STATE_CHANGING');
                document.getElementById('sg-editor-cat-injection').checked = p.confirm_categories.includes('PROMPT_INJECTION');
                document.getElementById('sg-editor-injection').checked = p.detect_prompt_injection;
                document.getElementById('sg-editor-fail-open').checked = p.fail_open;
                document.getElementById('sg-editor-auto-mode').checked = !!p.auto_mode;
                document.getElementById('sg-editor-auto-policy').value = p.auto_mode_policy || '';
                if (title) title.textContent = t('safeguard.editProfile');
            } else {
                document.getElementById('sg-editor-id').value = '';
                document.getElementById('sg-editor-id').disabled = false;
                document.getElementById('sg-editor-name').value = '';
                document.getElementById('sg-editor-check-user').checked = true;
                document.getElementById('sg-editor-check-tools').checked = true;
                document.getElementById('sg-editor-cat-destructive').checked = true;
                document.getElementById('sg-editor-cat-state').checked = true;
                document.getElementById('sg-editor-cat-injection').checked = false;
                document.getElementById('sg-editor-injection').checked = false;
                document.getElementById('sg-editor-fail-open').checked = false;
                document.getElementById('sg-editor-auto-mode').checked = false;
                document.getElementById('sg-editor-auto-policy').value = '';
                if (title) title.textContent = t('safeguard.addProfile');
            }
            this._sgToggleAutoPolicy();
            document.getElementById('sg-editor-status').textContent = '';
            editor.style.display = 'block';
            editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        },

        closeSafeguardProfileEditor() {
            const editor = document.getElementById('sg-profile-editor');
            if (editor) editor.style.display = 'none';
        },

        async saveSafeguardProfile() {
            const editor = document.getElementById('sg-profile-editor');
            const status = document.getElementById('sg-editor-status');
            const editingId = editor?._editingId;
            const id = document.getElementById('sg-editor-id').value.trim();
            const name = document.getElementById('sg-editor-name').value.trim();
            if (!name || (!editingId && !id)) {
                if (status) { status.textContent = t('safeguard.errorMissingFields'); status.style.color = 'var(--error-color)'; }
                return;
            }
            const cats = ['DESTRUCTIVE', 'STATE_CHANGING', 'PROMPT_INJECTION']
                .filter(c => document.getElementById(`sg-editor-cat-${c === 'DESTRUCTIVE' ? 'destructive' : c === 'STATE_CHANGING' ? 'state' : 'injection'}`).checked);
            const body = {
                name,
                check_user_messages: document.getElementById('sg-editor-check-user').checked,
                check_tool_calls: document.getElementById('sg-editor-check-tools').checked,
                confirm_categories: cats,
                detect_prompt_injection: document.getElementById('sg-editor-injection').checked,
                fail_open: document.getElementById('sg-editor-fail-open').checked,
                auto_mode: document.getElementById('sg-editor-auto-mode').checked,
                auto_mode_policy: document.getElementById('sg-editor-auto-policy').value.trim(),
            };
            try {
                let res;
                if (editingId) {
                    res = await fetch(`/api/safeguard/profiles/${editingId}`, {
                        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
                    });
                } else {
                    res = await fetch('/api/safeguard/profiles', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id, ...body }),
                    });
                }
                if (res.ok) {
                    this.closeSafeguardProfileEditor();
                    await this.renderSafeguardSettingsPanel();
                } else {
                    const err = await res.json().catch(() => ({}));
                    if (status) { status.textContent = err.detail || t('safeguard.errorSave'); status.style.color = 'var(--error-color)'; }
                }
            } catch {
                if (status) { status.textContent = t('safeguard.errorSave'); status.style.color = 'var(--error-color)'; }
            }
        },

        async deleteSafeguardProfile(profileId) {
            const ok = await this.showConfirmDialog(
                t('safeguard.deleteConfirmTitle'),
                t('safeguard.deleteConfirmMsg').replace('{id}', profileId),
            );
            if (!ok) return;
            try {
                const res = await fetch(`/api/safeguard/profiles/${profileId}`, { method: 'DELETE' });
                if (res.ok || res.status === 204) {
                    await this.renderSafeguardSettingsPanel();
                }
            } catch (err) { console.warn('deleteSafeguardProfile failed', err); }
        },

        // Füllt den Profile-Select im Agent-Editor
        async _populateAgentSafeguardSelect(agentId) {
            const sel = document.getElementById('agent-safeguard-profile');
            if (!sel) return;
            const profiles = this._safeguardProfiles || [];
            // Option "globales Profil" als erster Eintrag
            const globalOpt = document.createElement('option');
            globalOpt.value = '';
            globalOpt.textContent = t('safeguard.useGlobal');
            const profileOpts = profiles.map(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                return opt;
            });
            sel.replaceChildren(globalOpt, ...profileOpts);
            if (agentId) {
                try {
                    const res = await fetch(`/api/safeguard/agents/${agentId}/profile`);
                    if (res.ok) {
                        const data = await res.json();
                        sel.value = data.source === 'agent' ? data.profile_id : '';
                    }
                } catch (err) { console.warn('loadAgentSafeguardProfile failed', err); }
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, SafeguardFeature);
    } else {
        window.SafeguardFeature = SafeguardFeature;
    }
})();
