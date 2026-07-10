/**
 * Ninko Marketplace Feature Module
 *
 * Multi-Repo Modul-Marketplace: GitHub-Repos verwalten, Module auflisten
 * und installieren. Aus app.js extrahiert; via Object.assign auf Ninko
 * gemergt, daher bleiben alle this.*-Aufrufe (Helfer/State) gültig.
 */

(function() {
    'use strict';

    const MarketplaceFeature = {
        async loadMarketplaceConfig() {
            await this._loadMarketplaceRepos();
        },

        async _loadMarketplaceRepos() {
            const container = document.getElementById('marketplace-repos-list');
            if (!container) return;
            try {
                const res = await fetch('/api/plugins/marketplace/repos');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                this._renderRepoList(data.repos || []);
            } catch (e) {
                if (container) container.innerHTML = `<p class="text-muted" style="font-size:0.85rem;">${t('marketplace.networkError')}</p>`;
                console.error('loadMarketplaceRepos:', e);
            }
        },

        _renderRepoList(repos) {
            const container = document.getElementById('marketplace-repos-list');
            if (!container) return;
            if (!repos.length) {
                container.innerHTML = `<p class="text-muted" style="font-size:0.85rem;">${t('marketplace.noRepos')}</p>`;
                return;
            }
            container.innerHTML = repos.map(repo => this._renderRepoCard(repo)).join('');
        },

        _renderRepoCard(repo) {
            const isOfficial = repo.id === 'official';
            const e = (v) => v == null ? '' : String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
            return `
            <div class="module-config-card" id="repo-card-${e(repo.id)}" style="margin-bottom:0.75rem;">
                <div class="module-config-header">
                    <div class="module-config-info" style="min-width:0;">
                        <span class="module-config-name">${e(repo.name)}</span>
                        ${isOfficial ? `<span class="module-config-version" style="background:rgba(var(--primary-color-rgb),0.15);">${t('marketplace.official')}</span>` : ''}
                        <span class="text-muted" style="font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; margin-top:0.1rem;">${e(repo.repo_url)} · ${e(repo.branch)}</span>
                    </div>
                    <div style="display:flex; gap:0.35rem; align-items:center; flex-shrink:0;">
                        <button class="btn btn-outline" data-action="loadRepoModules" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}"
                            id="repo-load-btn-${e(repo.id)}"
                            style="font-size:0.78rem; padding:0.2rem 0.6rem;">
                            ${t('marketplace.loadModules')}
                        </button>
                        <button class="btn-icon btn-icon-sm" data-action="toggleRepoEdit" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}" title="${e(t('marketplace.editRepo'))}">
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                        </button>
                        ${!isOfficial ? `<button class="btn-icon btn-icon-sm" data-action="deleteRepo" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}" title="${e(t('marketplace.deleteRepo'))}" style="color:var(--error-color);">
                            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>` : ''}
                    </div>
                </div>

                <!-- Edit-Form (hidden) -->
                <div id="repo-edit-${e(repo.id)}" style="display:none; border-top:1px dashed var(--border-color); padding-top:0.75rem; margin-top:0.75rem;">
                    <div class="form-row form-row-sm">
                        <label class="form-label">${e(t('marketplace.repoName'))}</label>
                        <input id="edit-repo-name-${e(repo.id)}" type="text" class="form-input" value="${e(repo.name)}">
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label">${e(t('marketplace.repoUrl'))}</label>
                        <input id="edit-repo-url-${e(repo.id)}" type="text" class="form-input" value="${e(repo.repo_url)}" ${isOfficial ? 'readonly style="opacity:0.6;"' : ''}>
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label">${e(t('marketplace.repoBranch'))}</label>
                        <input id="edit-repo-branch-${e(repo.id)}" type="text" class="form-input" value="${e(repo.branch)}" style="max-width:130px;">
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label">${e(t('marketplace.repoPath'))}</label>
                        <input id="edit-repo-path-${e(repo.id)}" type="text" class="form-input" value="${e(repo.modules_path||'')}">
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label">${e(t('marketplace.repoToken'))} ${repo.github_token_set ? `<span class="text-muted">${e(t('marketplace.repoTokenSet'))}</span>` : ''}</label>
                        <input id="edit-repo-token-${e(repo.id)}" type="password" class="form-input" placeholder="${e(t('marketplace.repoTokenPlaceholder'))}">
                    </div>
                    <div class="form-row form-row-sm">
                        <label class="form-label"></label>
                        <label style="font-size:0.82rem; cursor:pointer; display:flex; align-items:center; gap:0.35rem;">
                            <input type="checkbox" id="edit-repo-token-clear-${e(repo.id)}"> ${e(t('marketplace.repoTokenClear'))}
                        </label>
                    </div>
                    <div style="display:flex; gap:0.5rem; margin-top:0.5rem;">
                        <button class="btn btn-primary" data-action="saveRepoEdit" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}" style="font-size:0.82rem;">${e(t('marketplace.save'))}</button>
                        <button class="btn btn-outline" data-action="toggleRepoEdit" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}" style="font-size:0.82rem;">${e(t('marketplace.cancel'))}</button>
                        <span id="edit-repo-status-${e(repo.id)}" class="save-status" style="display:inline; align-self:center;"></span>
                    </div>
                </div>

                <!-- Modul-Liste -->
                <div id="repo-modules-${e(repo.id)}" style="margin-top:0.5rem;"></div>
            </div>`;
        },

        toggleRepoEdit(repoId) {
            const el = document.getElementById(`repo-edit-${repoId}`);
            if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
        },

        async saveRepoEdit(repoId) {
            const g = id => document.getElementById(id);
            const statusEl = g(`edit-repo-status-${repoId}`);
            const body = {
                name: g(`edit-repo-name-${repoId}`)?.value.trim(),
                repo_url: g(`edit-repo-url-${repoId}`)?.value.trim(),
                branch: g(`edit-repo-branch-${repoId}`)?.value.trim(),
                modules_path: g(`edit-repo-path-${repoId}`)?.value.trim(),
                github_token: g(`edit-repo-token-${repoId}`)?.value || '',
                github_token_clear: g(`edit-repo-token-clear-${repoId}`)?.checked || false,
            };
            statusEl.textContent = t('marketplace.saving'); statusEl.className = 'save-status save-pending';
            try {
                const res = await fetch(`/api/plugins/marketplace/repos/${repoId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (res.ok) {
                    statusEl.textContent = t('marketplace.saved'); statusEl.className = 'save-status save-ok';
                    await this._loadMarketplaceRepos();
                } else {
                    const err = await res.json();
                    statusEl.textContent = err.detail || t('common.error'); statusEl.className = 'save-status save-error';
                }
            } catch (e) { statusEl.textContent = t('marketplace.networkError'); statusEl.className = 'save-status save-error'; }
        },

        showAddRepoForm() {
            const form = document.getElementById('marketplace-add-form');
            if (form) form.style.display = 'block';
            document.getElementById('add-repo-name')?.focus();
        },

        hideAddRepoForm() {
            const form = document.getElementById('marketplace-add-form');
            if (form) form.style.display = 'none';
            ['add-repo-name','add-repo-url','add-repo-branch','add-repo-path','add-repo-token'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            const s = document.getElementById('add-repo-status');
            if (s) { s.textContent = ''; s.className = 'save-status'; }
        },

        async addRepo() {
            const g = id => document.getElementById(id);
            const statusEl = g('add-repo-status');
            const body = {
                name: g('add-repo-name')?.value.trim() || '',
                repo_url: g('add-repo-url')?.value.trim() || '',
                branch: g('add-repo-branch')?.value.trim() || 'main',
                modules_path: g('add-repo-path')?.value.trim() || 'backend/modules_catalog',
                github_token: g('add-repo-token')?.value || '',
            };
            if (!body.repo_url) {
                statusEl.textContent = t('marketplace.urlRequired'); statusEl.className = 'save-status save-error'; return;
            }
            statusEl.textContent = t('marketplace.adding'); statusEl.className = 'save-status save-pending';
            try {
                const res = await fetch('/api/plugins/marketplace/repos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (res.ok) {
                    this.hideAddRepoForm();
                    await this._loadMarketplaceRepos();
                    showNotification(t('marketplace.repoAdded'), 'info');
                } else {
                    const err = await res.json();
                    statusEl.textContent = err.detail || t('common.error'); statusEl.className = 'save-status save-error';
                }
            } catch (e) { statusEl.textContent = t('marketplace.networkError'); statusEl.className = 'save-status save-error'; }
        },

        async deleteRepo(repoId) {
            if (!await this.confirm(t('marketplace.deleteConfirm'))) return;
            try {
                const res = await fetch(`/api/plugins/marketplace/repos/${repoId}`, { method: 'DELETE' });
                if (res.ok) {
                    const card = document.getElementById(`repo-card-${repoId}`);
                    if (card) card.remove();
                    showNotification(t('marketplace.repoRemoved'), 'info');
                } else {
                    const err = await res.json();
                    showNotification(`${t('common.error')}: ${err.detail}`, 'error');
                }
            } catch (e) { showNotification(t('marketplace.networkError'), 'error'); }
        },

        async loadRepoModules(repoId) {
            const container = document.getElementById(`repo-modules-${repoId}`);
            const btn = document.getElementById(`repo-load-btn-${repoId}`);
            if (!container) return;

            container.innerHTML = `<p class="text-muted" style="font-size:0.82rem; padding:0.5rem 0;">${t('marketplace.loadingModules')}</p>`;
            if (btn) btn.disabled = true;

            const renderCard = (mod, isUpdate, repoId) => {
                const btnLabel = isUpdate ? t('marketplace.update') : t('marketplace.install');
                const btnClass = isUpdate ? 'btn btn-outline' : 'btn btn-primary';
                const versionInfo = isUpdate
                    ? `<span class="module-config-version">v${mod.installed_version}</span><span class="text-muted" style="font-size:0.76rem;"> → v${mod.version}</span>`
                    : (mod.version ? `<span class="module-config-version">v${mod.version}</span>` : '');
                const sourceInfo = isUpdate && mod.installed_source
                    ? `<span class="text-muted" style="font-size:0.72rem;">source: ${this._escapeHtml(mod.installed_source)}</span>`
                    : '';
                return `
                <div class="module-config-card" id="mkt-card-${repoId}-${mod.name}" style="transition:opacity 0.3s;">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${mod.display_name || mod.name}</span>
                            ${versionInfo}
                            ${sourceInfo}
                        </div>
                        <button class="${btnClass}" data-action="installFromRepo" data-args="${JSON.stringify([mod.name, repoId]).replace(/\"/g, '&quot;')}"
                            id="mkt-btn-${repoId}-${mod.name}"
                            style="font-size:0.78rem; padding:0.2rem 0.6rem; flex-shrink:0;">
                            ${btnLabel}
                        </button>
                    </div>
                    ${mod.description ? `<p class="module-config-desc">${mod.description}</p>` : ''}
                </div>`;
            };

            try {
                const res = await fetch(`/api/plugins/marketplace/repos/${repoId}/modules`);
                const data = await res.json();

                if (data.error) {
                    container.innerHTML = `<p style="font-size:0.82rem; color:var(--error-color); padding:0.25rem 0;">${this._escapeHtml(data.error)}</p>`;
                    return;
                }

                const modules = data.modules || [];
                const updates = (data.updates || []).filter(u => u.update_available);
                let html = '';

                if (updates.length) {
                    html += `<p style="font-size:0.78rem; color:var(--warning-color,#f59e0b); margin:0.5rem 0 0.25rem; font-weight:600;">${t('marketplace.updates', updates.length)}</p>
                    <div class="modules-grid" style="margin-bottom:0.5rem;">${updates.map(m => renderCard(m, true, repoId)).join('')}</div>`;
                }
                if (modules.length) {
                    html += `<p style="font-size:0.78rem; color:var(--text-muted); margin:0.5rem 0 0.25rem; font-weight:600;">${t('marketplace.available', modules.length)}</p>
                    <div class="modules-grid">${modules.map(m => renderCard(m, false, repoId)).join('')}</div>`;
                }
                if (!html) {
                    html = `<p class="text-muted" style="font-size:0.82rem; padding:0.25rem 0;">${t('marketplace.allUpToDate')}</p>`;
                }

                container.innerHTML = html;
            } catch (e) {
                container.innerHTML = `<p style="font-size:0.82rem; color:var(--error-color);">${t('marketplace.networkError')}</p>`;
                console.error('loadRepoModules:', e);
            } finally {
                if (btn) btn.disabled = false;
            }
        },

        async installFromRepo(moduleName, repoId = 'official') {
            const btn = document.getElementById(`mkt-btn-${repoId}-${moduleName}`);
            const card = document.getElementById(`mkt-card-${repoId}-${moduleName}`);

            if (btn) { btn.disabled = true; btn.textContent = t('marketplace.installing'); }

            try {
                const res = await fetch(`/api/plugins/install-from-repo/${moduleName}?repo_id=${encodeURIComponent(repoId)}`, { 
                    method: 'POST',
                    credentials: 'include'
                });
                const data = await res.json();

                if (res.ok) {
                    showNotification(data.message || t('marketplace.installed'), 'info');
                    if (card) { card.style.opacity = '0'; setTimeout(() => card.remove(), 300); }
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    showNotification(`${t('common.error')}: ${data.detail || t('marketplace.installFailed')}`, 'error');
                    if (btn) { btn.disabled = false; btn.textContent = btn._isUpdate ? t('marketplace.update') : t('marketplace.install'); }
                }
            } catch (e) {
                showNotification(t('marketplace.networkError'), 'error');
                if (btn) { btn.disabled = false; btn.textContent = t('marketplace.install'); }
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, MarketplaceFeature);
    } else {
        window.MarketplaceFeature = MarketplaceFeature;
    }
})();
