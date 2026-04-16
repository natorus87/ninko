/**
 * Ninko Agents Feature Module
 * 
 * Enthält alle Agenten-bezogenen Funktionen:
 * - Agenten-Liste und CRUD
 * - Templates
 * - KI-Generierung
 * - Skills
 * - Agent Editor
 */

(function() {
    'use strict';

    const AgentsFeature = {
        // -------------------------------------------------------
        //  AGENTEN
        // -------------------------------------------------------

        _agentSteps: [],
        _agentEditId: null,

        async loadAgents() {
            const container = document.getElementById('agents-list');
            try {
                const res = await fetch('/api/agents/');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const agents = data.agents || [];

                this._customAgentsCache = agents.filter(a => a.enabled);
                this._buildModulePicker();

                if (!agents.length) {
                    container.innerHTML = `<p class="empty-state">Noch keine Agenten konfiguriert.<br>
                        <span style="font-size:0.85rem;opacity:0.7">Klicke auf „⚡ Vorlagen" für einen schnellen Einstieg oder „+ Neuer Agent" für einen leeren Editor.</span></p>`;
                    return;
                }
                container.innerHTML = agents.map(a => {
                    const isDynamic = !!a.dynamic;
                    const typeBadge = isDynamic
                        ? `<span class="agent-type-badge agent-type-dynamic" title="Via KI erstellt">✨ KI</span>`
                        : `<span class="agent-type-badge agent-type-manual" title="Manuell erstellt">Manuell</span>`;
                    return `
                    <div class="agent-card ${a.enabled ? '' : 'agent-card-disabled'}" data-agent-id="${this._escapeHtml(a.id)}">
                        <div class="agent-card-header">
                            <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;">
                                <span class="agent-card-name">${this._escapeHtml(a.name)}</span>
                                ${typeBadge}
                                <span class="agent-card-badge ${a.enabled ? 'badge-active' : 'badge-inactive'}">${a.enabled ? 'Aktiv' : 'Inaktiv'}</span>
                            </div>
                            <div class="agent-card-actions">
                                <button class="btn-icon btn-icon-sm" data-action="edit" title="Bearbeiten">${this._ic.edit}</button>
                                <button class="btn-icon btn-icon-sm" data-action="duplicate" title="Duplizieren">${this._ic.copy}</button>
                                <button class="btn-icon btn-icon-sm" data-action="delete" title="Löschen" style="color:var(--error-color)">${this._ic.trash}</button>
                            </div>
                        </div>
                        <p class="agent-card-desc">${a.description ? this._escapeHtml(a.description) : '<em style="color:var(--text-muted)">Keine Beschreibung</em>'}</p>
                        <div class="agent-card-footer">
                            <span>${this._ic.cpu} ${a.llm_provider_id ? this._escapeHtml(a.llm_provider_id) : 'Standard LLM'}</span>
                            <span>${this._ic.layers} ${(a.module_names || []).length} Module</span>
                            <span>${this._ic.steps} ${(a.steps || []).length} Schritte</span>
                            ${a.updated_at ? `<span title="Zuletzt geändert">${this._ic.clock} ${new Date(a.updated_at).toLocaleDateString('de')}</span>` : ''}
                        </div>
                    </div>`;
                }).join('');
                container.querySelectorAll('.agent-card').forEach(card => {
                    const id = card.dataset.agentId;
                    const name = card.querySelector('.agent-card-name')?.textContent || '';
                    card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.openAgentEditor(id));
                    card.querySelector('[data-action="duplicate"]')?.addEventListener('click', () => this.duplicateAgent(id));
                    card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteAgent(id, name));
                });
            } catch (e) {
                container.innerHTML = '<p class="empty-state">Fehler beim Laden der Agenten.</p>';
            }
        },

        // -------------------------------------------------------
        //  AGENT BUILDER: TEMPLATES
        // -------------------------------------------------------

        _allPanels() {
            return ['agenten-overview', 'agenten-templates', 'agenten-skills', 'agenten-skill-editor', 'agenten-editor'];
        },

        _showOnlyPanel(panelId) {
            this._allPanels().forEach(id => {
                document.getElementById(id)?.classList.toggle('hidden', id !== panelId);
            });
        },

        async openTemplatesPanel() {
            this._showOnlyPanel('agenten-templates');
            await this.loadTemplates();
        },

        closeTemplatesPanel() {
            this._showOnlyPanel('agenten-overview');
            this.loadAgents();
        },

        async loadTemplates() {
            const container = document.getElementById('templates-grid');
            if (!container) return;
            container.innerHTML = '<p class="empty-state">Lade Vorlagen…</p>';
            try {
                const res = await fetch('/api/agents/templates');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const templates = data.templates || [];
                if (!templates.length) {
                    container.innerHTML = '<p class="empty-state">Keine Vorlagen verfügbar.</p>';
                    return;
                }
                container.innerHTML = templates.map(tpl => `
                    <div class="template-card" data-tpl-id="${this._escapeHtml(tpl.id)}" tabindex="0" role="button" aria-label="Vorlage ${this._escapeHtml(tpl.label || tpl.name)} verwenden">
                        <div class="template-card-header">
                            <span class="template-card-icon">${tpl.icon || '🤖'}</span>
                            <span class="template-card-name">${this._escapeHtml(tpl.label || tpl.name)}</span>
                        </div>
                        <p class="template-card-desc">${this._escapeHtml(tpl.description || '')}</p>
                        <div class="template-card-tags">
                            ${(tpl.tags || []).slice(0, 4).map(tag => `<span class="template-tag">${this._escapeHtml(tag)}</span>`).join('')}
                        </div>
                    </div>
                `).join('');
                container.querySelectorAll('.template-card').forEach(card => {
                    const tplId = card.dataset.tplId;
                    const tpl = templates.find(t => t.id === tplId);
                    const activate = () => { if (tpl) this.useTemplate(tpl); };
                    card.addEventListener('click', activate);
                    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } });
                });
            } catch (e) {
                container.innerHTML = '<p class="empty-state">Fehler beim Laden der Vorlagen.</p>';
            }
        },

        useTemplate(tpl) {
            this._showOnlyPanel('agenten-editor');
            this._agentEditId = null;
            this._agentSteps = [];
            document.getElementById('agent-editor-title').textContent = 'Neuer Agent';
            document.getElementById('agent-name').value = tpl.label || tpl.name || '';
            document.getElementById('agent-desc').value = tpl.description || '';
            document.getElementById('agent-system-prompt').value = tpl.system_prompt || '';
            document.getElementById('agent-enabled').checked = true;
            document.getElementById('agent-usecase').value = '';
            this._renderAgentSteps();
            this._populateAgentSafeguardSelect(null);
            this._populateModulesAndPreselect(tpl.suggested_modules || []);
            this._populateAgentSkills();
        },

        async _populateModulesAndPreselect(suggestedModules) {
            const container = document.getElementById('agent-modules-list');
            if (!container) return;
            try {
                const res = await fetch('/api/modules/');
                if (!res.ok) return;
                const modules = await res.json();
                const enabled = modules.filter(m => m.enabled);
                if (!enabled.length) { container.innerHTML = '<p class="text-muted">Keine aktiven Module.</p>'; return; }
                container.innerHTML = enabled.map(m => {
                    const checked = suggestedModules.includes(m.name) ? 'checked' : '';
                    return `<label class="module-checkbox-item"><input type="checkbox" id="agent-mod-${this._escapeHtml(m.name)}" value="${this._escapeHtml(m.name)}" ${checked}><span>${this._escapeHtml(m.display_name || m.name)}</span></label>`;
                }).join('');
            } catch { container.innerHTML = '<p class="text-muted">Fehler beim Laden.</p>'; }
        },

        // -------------------------------------------------------
        //  AGENT BUILDER: KI-GENERIERUNG
        // -------------------------------------------------------

        async generateAgentWithAI() {
            const usecase = document.getElementById('agent-usecase')?.value?.trim();
            if (!usecase) {
                showNotification('Bitte zuerst einen Use-Case beschreiben.', 'warning');
                return;
            }
            const btn = document.getElementById('agent-generate-btn');
            if (btn) { btn.disabled = true; btn.textContent = '✨ Generiere…'; }
            try {
                const checkedModules = Array.from(
                    document.querySelectorAll('#agent-modules-list input[type="checkbox"]:checked')
                ).map(el => el.value);

                const res = await fetch('/api/agents/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ use_case: usecase, allowed_modules: checkedModules }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || res.statusText);
                }
                const spec = await res.json();
                if (spec.name) document.getElementById('agent-name').value = spec.name;
                if (spec.description) document.getElementById('agent-desc').value = spec.description;
                if (spec.system_prompt) document.getElementById('agent-system-prompt').value = spec.system_prompt;
                if (spec.suggested_modules?.length) {
                    document.querySelectorAll('#agent-modules-list input[type="checkbox"]').forEach(cb => {
                        cb.checked = spec.suggested_modules.includes(cb.value);
                    });
                }

                const genInfo = spec._generation_info || {};
                if (genInfo.fallback_used) {
                    const errorDetail = genInfo.original_error ? ` (${genInfo.original_error})` : '';
                    showNotification(
                        `Agent mit Fallback generiert ⚠️${errorDetail}. Bitte System-Prompt prüfen.`,
                        'warning'
                    );
                } else if (genInfo.used_inferred_modules) {
                    showNotification(
                        `Agent-Spezifikation generiert ✨ (Module: ${spec.suggested_modules?.join(', ') || 'keine'})`,
                        'success'
                    );
                } else {
                    showNotification('Agent-Spezifikation erfolgreich generiert ✨', 'success');
                }
            } catch (e) {
                showNotification(`Generierung fehlgeschlagen: ${e.message}`, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = '✨ Generieren'; }
            }
        },

        // -------------------------------------------------------
        //  SKILLS
        // -------------------------------------------------------

        _agentEditorContext: null,

        async openSkillsPanel() {
            this._showOnlyPanel('agenten-skills');
            await this.loadSkillsList();
        },

        closeSkillsPanel() {
            this._showOnlyPanel('agenten-overview');
            this.loadAgents();
        },

        async loadSkillsList() {
            const container = document.getElementById('skills-list');
            if (!container) return;
            container.innerHTML = '<p class="empty-state">Lade…</p>';
            try {
                const res = await fetch('/api/skills/');
                const skills = await res.json();
                if (!skills.length) {
                    container.innerHTML = '<p class="empty-state">Keine Skills vorhanden.</p>';
                    return;
                }
                container.innerHTML = skills.map(s => `
                    <div class="agent-card" style="position:relative;">
                        <div class="agent-card-header">
                            <div style="display:flex;align-items:center;gap:0.5rem;flex:1;min-width:0;">
                                <span style="font-size:1.1rem;">${s.builtin ? '🔒' : '📝'}</span>
                                <div style="min-width:0;">
                                    <div class="agent-card-name">${s.name}</div>
                                    <div class="agent-card-desc">${s.description}</div>
                                </div>
                            </div>
                            <div class="agent-card-actions">
                                ${!s.builtin ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditor('${s.name}')" title="Bearbeiten">${this._ic.edit}</button>` : `<button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditor('${s.name}')" title="Ansehen/Override">${this._ic.edit}</button>`}
                                ${!s.builtin ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.deleteSkill('${s.name}')" title="Löschen" style="color:var(--error-color);">${this._ic.trash}</button>` : ''}
                            </div>
                        </div>
                        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-top:0.5rem;">
                            ${s.builtin ? '<span class="status-badge status-unknown" style="font-size:0.7rem;">built-in</span>' : '<span class="status-badge status-ok" style="font-size:0.7rem;">custom</span>'}
                            ${s.modules.length ? s.modules.map(m => `<span class="status-badge" style="font-size:0.7rem;background:rgba(92,158,235,0.15);color:var(--accent-blue);border:1px solid var(--accent-blue);">${m}</span>`).join('') : '<span class="status-badge status-unknown" style="font-size:0.7rem;">alle Agenten</span>'}
                        </div>
                    </div>
                `).join('');
            } catch {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
            }
        },

        // -------------------------------------------------------------------
        // Skills aus Settings
        // -------------------------------------------------------------------

        openSkillsPanelFromSettings() {
            this.switchTab('automatisierung');
            this._showOnlyPanel('agenten-skills');
            this.switchSkillTab('installed');
            this.loadSkillsList();
        },

        openSkillMarketplaceFromSettings() {
            this.switchTab('automatisierung');
            this._showOnlyPanel('agenten-skills');
            this.switchSkillTab('marketplace');
            this.loadSkillMarketplace();
        },

        async loadSettingsSkillsList() {
            const container = document.getElementById('settings-skills-list');
            if (!container) return;
            container.innerHTML = '<p class="empty-state">Lade…</p>';
            try {
                const res = await fetch('/api/skills/');
                const skills = await res.json();
                if (!skills.length) {
                    container.innerHTML = '<p class="empty-state">Keine Skills vorhanden.</p>';
                    return;
                }
                container.innerHTML = skills.map(s => `
                    <div class="agent-card" style="position:relative;">
                        <div class="agent-card-header">
                            <div style="display:flex;align-items:center;gap:0.5rem;flex:1;min-width:0;">
                                <span style="font-size:1.1rem;">${s.builtin ? '🔒' : '📝'}</span>
                                <div style="min-width:0;">
                                    <div class="agent-card-name">${s.name}</div>
                                    <div class="agent-card-desc">${s.description}</div>
                                </div>
                            </div>
                        </div>
                        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-top:0.5rem;">
                            ${s.builtin ? '<span class="status-badge status-unknown" style="font-size:0.7rem;">built-in</span>' : '<span class="status-badge status-ok" style="font-size:0.7rem;">custom</span>'}
                            ${s.modules.length ? s.modules.map(m => `<span class="status-badge" style="font-size:0.7rem;background:rgba(92,158,235,0.15);color:var(--accent-blue);border:1px solid var(--accent-blue);">${m}</span>`).join('') : '<span class="status-badge status-unknown" style="font-size:0.7rem;">alle Agenten</span>'}
                        </div>
                    </div>
                `).join('');
            } catch {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
            }
        },

        switchSkillTab(tab) {
            document.querySelectorAll('.skill-subtab').forEach(b => b.classList.remove('active'));
            const btn = document.getElementById(`skill-tab-${tab}`);
            if (btn) btn.classList.add('active');

            const panels = { installed: 'skills-list', marketplace: 'skills-marketplace', repos: 'skills-repos' };
            Object.values(panels).forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.add('hidden');
            });
            const active = document.getElementById(panels[tab]);
            if (active) active.classList.remove('hidden');

            if (tab === 'marketplace') this.loadSkillMarketplace();
            else if (tab === 'repos') this.loadSkillRepos();
        },

        async loadSkillMarketplace() {
            const container = document.getElementById('skills-marketplace');
            if (!container) return;
            container.innerHTML = '<p class="empty-state">Lade Marketplace…</p>';
            try {
                const res = await fetch('/api/skills/marketplace');
                const skills = await res.json();
                if (!skills.length) {
                    container.innerHTML = '<p class="empty-state">Keine Skills im Marketplace verfügbar.</p>';
                    return;
                }
                container.innerHTML = skills.map(s => `
                    <div class="agent-card" style="position:relative;">
                        <div class="agent-card-header">
                            <div style="display:flex;align-items:center;gap:0.5rem;flex:1;min-width:0;">
                                <span style="font-size:1.1rem;">${s.installed ? '✅' : '📦'}</span>
                                <div style="min-width:0;">
                                    <div class="agent-card-name">${this._esc(s.name)}</div>
                                    <div class="agent-card-desc">${this._esc(s.description || '')}</div>
                                </div>
                            </div>
                            <div class="agent-card-actions">
                                ${s.installed
                                    ? '<span class="status-badge status-ok" style="font-size:0.7rem;">installiert</span>'
                                    : `<button class="btn btn-primary" style="font-size:0.8rem;padding:0.3rem 0.7rem;" onclick="Ninko.installMarketplaceSkill('${this._esc(s.name)}', '${this._esc(s.skill_url)}', ${JSON.stringify(s.modules || []).replace(/"/g, '&quot;')})">Installieren</button>`
                                }
                            </div>
                        </div>
                        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-top:0.5rem;">
                            ${(s.tags || []).map(t => `<span class="status-badge" style="font-size:0.65rem;background:rgba(92,158,235,0.1);color:var(--accent-blue);border:1px solid rgba(92,158,235,0.3);">${this._esc(t)}</span>`).join('')}
                            ${(s.modules || []).map(m => `<span class="status-badge" style="font-size:0.65rem;background:rgba(168,85,247,0.1);color:var(--purple,#a855f7);border:1px solid rgba(168,85,247,0.3);">${this._esc(m)}</span>`).join('')}
                            <span class="status-badge status-unknown" style="font-size:0.65rem;">${this._esc(s.repo_name || 'unknown')}</span>
                        </div>
                    </div>
                `).join('');
            } catch {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden des Marketplace.</p>';
            }
        },

        async installMarketplaceSkill(name, skillUrl, modules) {
            try {
                showNotification('Installiere Skill…', 'info');
                const res = await fetch('/api/skills/marketplace/install', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, skill_url: skillUrl, modules: modules || [] }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
                showNotification(`Skill "${name}" installiert!`, 'success');
                this.loadSkillMarketplace();
                this.loadSkillsList();
            } catch (e) {
                showNotification(`Installation fehlgeschlagen: ${e.message}`, 'error');
            }
        },

        async loadSkillRepos() {
            const container = document.getElementById('skills-repos');
            if (!container) return;
            container.innerHTML = '<p class="empty-state">Lade Repos…</p>';
            try {
                const res = await fetch('/api/skills/repos');
                const repos = await res.json();
                let html = repos.map(r => `
                    <div class="agent-card" style="margin-bottom:0.5rem;">
                        <div class="agent-card-header">
                            <div style="flex:1;min-width:0;">
                                <div class="agent-card-name">${this._esc(r.name || r.id)} ${r.builtin ? '🔒' : ''}</div>
                                <div class="agent-card-desc" style="word-break:break-all;">${this._esc(r.catalog_url || '')}</div>
                            </div>
                            ${!r.builtin ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.removeSkillRepo('${this._esc(r.id)}')" title="Entfernen" style="color:var(--error-color);">${this._ic.trash}</button>` : ''}
                        </div>
                    </div>
                `).join('');
                html += `
                    <div style="margin-top:1rem;display:flex;flex-direction:column;gap:0.5rem;">
                        <h4>Neues Repo hinzufügen</h4>
                        <input type="text" id="new-repo-id" placeholder="ID (z.B. community)" class="form-control" style="max-width:300px;">
                        <input type="text" id="new-repo-name" placeholder="Name (optional)" class="form-control" style="max-width:300px;">
                        <input type="text" id="new-repo-url" placeholder="catalog.json URL" class="form-control" style="max-width:500px;">
                        <button class="btn btn-primary" style="max-width:200px;" onclick="Ninko.addSkillRepo()">Repo hinzufügen</button>
                    </div>
                `;
                container.innerHTML = html;
            } catch {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
            }
        },

        async addSkillRepo() {
            const id = document.getElementById('new-repo-id')?.value?.trim();
            const name = document.getElementById('new-repo-name')?.value?.trim();
            const url = document.getElementById('new-repo-url')?.value?.trim();
            if (!id || !url) { showNotification('ID und URL sind erforderlich.', 'error'); return; }
            try {
                const res = await fetch('/api/skills/repos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id, name: name || id, catalog_url: url }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
                showNotification(`Repo "${id}" hinzugefügt!`, 'success');
                this.loadSkillRepos();
            } catch (e) {
                showNotification(`Fehler: ${e.message}`, 'error');
            }
        },

        async removeSkillRepo(repoId) {
            if (!confirm(`Repo "${repoId}" wirklich entfernen?`)) return;
            try {
                const res = await fetch(`/api/skills/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
                showNotification(`Repo "${repoId}" entfernt.`, 'success');
                this.loadSkillRepos();
            } catch (e) {
                showNotification(`Fehler: ${e.message}`, 'error');
            }
        },

        async openSkillEditor(name) {
            this._agentEditorContext = null;
            await this._showSkillEditorPanel(name);
        },

        openSkillEditorFromAgent() {
            const agentName = document.getElementById('agent-name')?.value?.trim() || '';
            this._agentEditorContext = agentName;
            this._showOnlyPanel('agenten-skill-editor');
            this._clearSkillEditor();
            if (agentName) document.getElementById('skill-modules').value = agentName;
            this._updateSkillFrontmatterPreview();
        },

        async _showSkillEditorPanel(name) {
            this._showOnlyPanel('agenten-skill-editor');

            if (name) {
                document.getElementById('skill-editor-title').textContent = 'Skill bearbeiten';
                document.getElementById('skill-edit-name').value = name;
                try {
                    const res = await fetch(`/api/skills/${encodeURIComponent(name)}`);
                    const s = await res.json();
                    document.getElementById('skill-name').value = s.name;
                    document.getElementById('skill-name').disabled = true;
                    document.getElementById('skill-description').value = s.description;
                    document.getElementById('skill-modules').value = (s.modules || []).join(', ');
                    document.getElementById('skill-content').value = s.content;
                    const saveBtn = document.getElementById('skill-save-btn');
                    if (saveBtn) saveBtn.textContent = s.builtin ? '💾 Als Override speichern' : '💾 Speichern';
                } catch { showNotification('Fehler beim Laden des Skills', 'error'); }
            } else {
                document.getElementById('skill-editor-title').textContent = 'Neuer Skill';
                this._clearSkillEditor();
            }
            this._updateSkillFrontmatterPreview();
            ['skill-name', 'skill-description', 'skill-modules'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.oninput = () => this._updateSkillFrontmatterPreview();
            });
        },

        _clearSkillEditor() {
            document.getElementById('skill-edit-name').value = '';
            document.getElementById('skill-name').value = '';
            document.getElementById('skill-name').disabled = false;
            document.getElementById('skill-description').value = '';
            document.getElementById('skill-modules').value = '';
            document.getElementById('skill-content').value = '';
            const saveBtn = document.getElementById('skill-save-btn');
            if (saveBtn) saveBtn.textContent = '💾 Speichern';
        },

        _updateSkillFrontmatterPreview() {
            const name = document.getElementById('skill-name')?.value?.trim() || 'mein-skill';
            const desc = document.getElementById('skill-description')?.value?.trim() || '...';
            const mods = document.getElementById('skill-modules')?.value?.trim();
            const modsLine = mods ? `\nmodules: [${mods}]` : '';
            const pre = document.getElementById('skill-frontmatter-preview');
            if (pre) pre.textContent = `---\nname: ${name}\ndescription: ${desc}${modsLine}\n---`;
        },

        closeSkillEditor() {
            if (this._agentEditorContext !== null) {
                this._showOnlyPanel('agenten-editor');
                this._populateAgentSkills();
                this._agentEditorContext = null;
            } else {
                this._showOnlyPanel('agenten-skills');
                this.loadSkillsList();
            }
        },

        async saveSkill() {
            const editName = document.getElementById('skill-edit-name').value;
            const name = document.getElementById('skill-name').value.trim();
            const description = document.getElementById('skill-description').value.trim();
            const content = document.getElementById('skill-content').value.trim();
            const modulesRaw = document.getElementById('skill-modules').value.trim();
            const modules = modulesRaw ? modulesRaw.split(',').map(m => m.trim()).filter(Boolean) : [];

            if (!name || !description || !content) {
                showNotification('Name, Beschreibung und Inhalt sind Pflichtfelder.', 'error');
                return;
            }
            if (!/^[a-z0-9\-]+$/.test(name)) {
                showNotification('Name darf nur Kleinbuchstaben, Zahlen und Bindestriche enthalten.', 'error');
                return;
            }

            const btn = document.getElementById('skill-save-btn');
            if (btn) btn.disabled = true;
            try {
                const isEdit = !!editName;
                const url = isEdit ? `/api/skills/${encodeURIComponent(editName)}` : '/api/skills/';
                const method = isEdit ? 'PUT' : 'POST';
                const body = { name, description, content, modules };
                const bodyToSend = isEdit ? { description, content, modules } : body;

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bodyToSend),
                });
                if (res.ok) {
                    showNotification(`Skill "${name}" gespeichert.`, 'success');
                    this.closeSkillEditor();
                } else {
                    const err = await res.json();
                    showNotification('Fehler: ' + (err.detail || res.statusText), 'error');
                }
            } catch { showNotification('Verbindungsfehler', 'error'); }
            finally { if (btn) btn.disabled = false; }
        },

        async deleteSkill(name) {
            if (!await this.confirm(`Skill "${name}" löschen?`)) return;
            try {
                const res = await fetch(`/api/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
                if (res.ok || res.status === 204) {
                    showNotification(`Skill "${name}" gelöscht.`, 'info');
                    this.loadSkillsList();
                } else {
                    const err = await res.json().catch(() => ({}));
                    showNotification('Fehler: ' + (err.detail || 'Unbekannt'), 'error');
                }
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async _populateAgentSkills() {
            const container = document.getElementById('agent-skills-list');
            if (!container) return;
            const agentName = document.getElementById('agent-name')?.value?.trim() || '';
            try {
                const res = await fetch('/api/skills/');
                const skills = await res.json();
                const relevant = skills.filter(s => !s.modules.length || s.modules.includes(agentName));
                if (!relevant.length) {
                    container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Keine Skills vorhanden.</p>';
                    return;
                }
                container.innerHTML = relevant.map(s => `
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;padding:0.3rem 0.5rem;border-radius:4px;background:var(--bg-body);border:1px solid var(--border-color);">
                        <div style="min-width:0;">
                            <span style="font-size:0.82rem;color:var(--text-color);font-weight:500;">${s.name}</span>
                            ${s.builtin ? '<span class="status-badge status-unknown" style="font-size:0.68rem;margin-left:4px;">built-in</span>' : ''}
                            <div style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s.description}</div>
                        </div>
                        <button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditorFromAgentWithName('${s.name}')" title="Bearbeiten" style="flex-shrink:0;">${this._ic.edit}</button>
                    </div>
                `).join('');
            } catch {
                container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Fehler beim Laden.</p>';
            }
        },

        async openSkillEditorFromAgentWithName(skillName) {
            this._agentEditorContext = document.getElementById('agent-name')?.value?.trim() || '';
            this._showOnlyPanel('agenten-skill-editor');
            await this._showSkillEditorPanel(skillName);
        },

        // -------------------------------------------------------
        //  AGENTEN EDITOR
        // -------------------------------------------------------

        async openAgentEditor(agentId) {
            this._agentEditId = agentId;
            this._agentSteps = [];
            document.getElementById('agent-usecase').value = '';
            this._showOnlyPanel('agenten-editor');

            await this._populateLlmDropdown('agent-llm');
            await this._populateModuleChecklist();

            if (agentId) {
                document.getElementById('agent-editor-title').textContent = 'Agent bearbeiten';
                try {
                    const res = await fetch(`/api/agents/${agentId}`);
                    const a = await res.json();
                    document.getElementById('agent-name').value = a.name || '';
                    document.getElementById('agent-desc').value = a.description || '';
                    document.getElementById('agent-system-prompt').value = a.system_prompt || '';
                    document.getElementById('agent-llm').value = a.llm_provider_id || '';
                    document.getElementById('agent-enabled').checked = a.enabled !== false;
                    this._agentSteps = a.steps || [];
                    (a.module_names || []).forEach(name => {
                        const cb = document.getElementById(`agent-mod-${name}`);
                        if (cb) cb.checked = true;
                    });
                    await this._populateAgentSafeguardSelect(agentId);
                } catch { }
            } else {
                document.getElementById('agent-editor-title').textContent = 'Neuer Agent';
                document.getElementById('agent-name').value = '';
                document.getElementById('agent-desc').value = '';
                document.getElementById('agent-system-prompt').value = '';
                document.getElementById('agent-enabled').checked = true;
                await this._populateAgentSafeguardSelect(null);
            }
            this._renderAgentSteps();
            await this._populateAgentSkills();
        },

        closeAgentEditor() {
            this._showOnlyPanel('agenten-overview');
            this.loadAgents();
        },

        async _populateLlmDropdown(selectId) {
            const sel = document.getElementById(selectId);
            if (!sel) return;
            try {
                const res = await fetch('/api/settings/llm/providers');
                if (!res.ok) throw new Error(res.statusText);
                const providers = await res.json();
                const extra = providers.map(p => `<option value="${p.id}">${this._escapeHtml(p.name)}${p.is_default ? ' (Standard)' : ''}</option>`).join('');
                sel.innerHTML = '<option value="">Standard verwenden</option>' + extra;
            } catch { }
        },

        async _populateModuleChecklist() {
            const container = document.getElementById('agent-modules-list');
            if (!container) return;
            try {
                const res = await fetch('/api/modules/');
                const modules = await res.json();
                if (!modules.length) { container.innerHTML = '<p class="text-muted">Keine Module verfügbar.</p>'; return; }
                container.innerHTML = modules.filter(m => m.enabled).map(m => `
                    <label class="module-checkbox-item">
                        <input type="checkbox" id="agent-mod-${m.name}" value="${m.name}">
                        <span>${m.display_name || m.name}</span>
                    </label>
                `).join('');
            } catch { container.innerHTML = '<p class="text-muted">Fehler beim Laden.</p>'; }
        },

        _renderAgentSteps() {
            const container = document.getElementById('agent-steps-list');
            if (!container) return;
            if (!this._agentSteps.length) { container.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Noch keine Schritte definiert.</p>'; return; }
            const typeOptions = [
                { value: 'llm_call',       label: 'LLM-Call' },
                { value: 'module_action',  label: 'Modul' },
                { value: 'condition',      label: 'Bedingung' },
                { value: 'set_variable',   label: 'Variable' },
            ];
            container.innerHTML = this._agentSteps.map((step, idx) => `
                <div class="sequence-step" draggable="true" data-step-idx="${idx}">
                    <span class="step-drag-handle">⠿</span>
                    <select class="form-select form-select-sm step-type-sel" data-idx="${idx}" style="min-width:130px;">
                        ${typeOptions.map(t => `<option value="${t.value}" ${step.type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                    </select>
                    <input type="text" class="form-input form-input-sm step-label-inp" data-idx="${idx}"
                        value="${this._escapeHtml(step.label || '')}" placeholder="Beschreibung…">
                    <select class="form-select form-select-sm step-err-sel" data-idx="${idx}" style="min-width:80px;">
                        ${['retry', 'skip', 'abort'].map(e => `<option value="${e}" ${step.error_handling === e ? 'selected' : ''}>${e}</option>`).join('')}
                    </select>
                    <button class="btn-icon btn-icon-sm step-remove-btn" data-idx="${idx}" style="color:var(--error-color)">✕</button>
                </div>
            `).join('');
            container.querySelectorAll('.step-type-sel').forEach(sel => {
                sel.addEventListener('change', () => { this._agentSteps[+sel.dataset.idx].type = sel.value; });
            });
            container.querySelectorAll('.step-label-inp').forEach(inp => {
                inp.addEventListener('input', () => { this._agentSteps[+inp.dataset.idx].label = inp.value; });
            });
            container.querySelectorAll('.step-err-sel').forEach(sel => {
                sel.addEventListener('change', () => { this._agentSteps[+sel.dataset.idx].error_handling = sel.value; });
            });
            container.querySelectorAll('.step-remove-btn').forEach(btn => {
                btn.addEventListener('click', () => { this._removeAgentStep(+btn.dataset.idx); });
            });
            this._setupStepDragDrop(container);
        },

        _setupStepDragDrop(container) {
            let dragIdx = null;
            container.querySelectorAll('.sequence-step').forEach(el => {
                el.addEventListener('dragstart', () => {
                    dragIdx = +el.dataset.stepIdx;
                    el.classList.add('dragging');
                });
                el.addEventListener('dragend', () => {
                    el.classList.remove('dragging');
                    container.querySelectorAll('.sequence-step').forEach(s => s.classList.remove('drag-over'));
                    dragIdx = null;
                });
                el.addEventListener('dragover', e => {
                    e.preventDefault();
                    el.classList.add('drag-over');
                });
                el.addEventListener('dragleave', () => {
                    el.classList.remove('drag-over');
                });
                el.addEventListener('drop', e => {
                    e.preventDefault();
                    el.classList.remove('drag-over');
                    const dropIdx = +el.dataset.stepIdx;
                    if (dragIdx === null || dragIdx === dropIdx) return;
                    const [moved] = this._agentSteps.splice(dragIdx, 1);
                    this._agentSteps.splice(dropIdx, 0, moved);
                    this._renderAgentSteps();
                });
            });
        },

        addAgentStep() {
            this._agentSteps.push({ id: Date.now().toString(36), order: this._agentSteps.length, type: 'llm_call', label: '', config: {}, error_handling: 'abort' });
            this._renderAgentSteps();
        },

        _removeAgentStep(idx) {
            this._agentSteps.splice(idx, 1);
            this._renderAgentSteps();
        },

        async saveAgent() {
            const name = document.getElementById('agent-name').value.trim();
            if (!name) { showNotification('Name ist Pflichtfeld', 'error'); return; }
            const saveBtn = document.querySelector('#agenten-editor .btn-primary');
            if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Speichern…'; }
            const selectedModules = [...document.querySelectorAll('#agent-modules-list input[type=checkbox]:checked')].map(cb => cb.value);
            const body = {
                name,
                description: document.getElementById('agent-desc').value,
                system_prompt: document.getElementById('agent-system-prompt').value,
                llm_provider_id: document.getElementById('agent-llm').value || null,
                enabled: document.getElementById('agent-enabled').checked,
                module_names: selectedModules,
                steps: this._agentSteps,
            };
            try {
                const url = this._agentEditId ? `/api/agents/${this._agentEditId}` : '/api/agents/';
                const method = this._agentEditId ? 'PUT' : 'POST';
                const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
                if (res.ok) {
                    const saved = await res.json();
                    const savedId = saved.id || this._agentEditId;
                    if (savedId) {
                        const sgProfileSel = document.getElementById('agent-safeguard-profile');
                        const sgProfileId = sgProfileSel ? sgProfileSel.value : '';
                        try {
                            if (sgProfileId) {
                                await fetch(`/api/safeguard/agents/${savedId}/profile`, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ profile_id: sgProfileId }),
                                });
                            } else {
                                await fetch(`/api/safeguard/agents/${savedId}/profile`, { method: 'DELETE' });
                            }
                        } catch { }
                    }
                    showNotification(`Agent "${name}" gespeichert`, 'success');
                    this.closeAgentEditor();
                } else {
                    showNotification('Fehler beim Speichern', 'error');
                }
            } catch { showNotification('Verbindungsfehler', 'error'); }
            finally {
                if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '💾 Speichern'; }
            }
        },

        async deleteAgent(id, name) {
            if (!await this.confirm(`Agent "${name}" löschen?`)) return;
            try {
                const res = await fetch(`/api/agents/${id}`, { method: 'DELETE' });
                if (res.ok) { showNotification(`Agent "${name}" gelöscht`, 'info'); this.loadAgents(); }
                else showNotification('Fehler beim Löschen', 'error');
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async duplicateAgent(id) {
            try {
                const res = await fetch(`/api/agents/${id}/duplicate`, { method: 'POST' });
                if (res.ok) { showNotification('Agent dupliziert', 'success'); this.loadAgents(); }
                else showNotification('Fehler beim Duplizieren', 'error');
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },
    };

    // Feature in Ninko-Objekt integrieren
    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, AgentsFeature);
    } else {
        window.AgentsFeature = AgentsFeature;
    }
})();
