/**
 * Ninko Plugins Feature Module
 *
 * Plugin-Verwaltung (Settings → Module): ZIP-Upload, Deinstallation,
 * Einzel- und Bulk-Update via /api/plugins/*. Aus app.js extrahiert;
 * via Object.assign gemergt. Der Update-State (_pendingPluginUpdates,
 * _bulkUpdating) wird von features/module_settings.js befüllt und
 * bleibt dort/in app.js — Zugriff via this.* zur Laufzeit.
 */

(function() {
    'use strict';

    const PluginsFeature = {
        async uploadPlugin() {
            const fileInput = document.getElementById('plugin-upload-file');
            const statusEl = document.getElementById('plugin-upload-status');
            const btn = document.getElementById('plugin-upload-btn');

            if (!fileInput.files || fileInput.files.length === 0) {
                statusEl.textContent = 'Bitte wähle eine ZIP-Datei aus.';
                statusEl.className = 'save-status save-error';
                return;
            }

            const file = fileInput.files[0];
            if (!file.name.endsWith('.zip')) {
                statusEl.textContent = 'Nur .zip Dateien sind erlaubt.';
                statusEl.className = 'save-status save-error';
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            statusEl.textContent = 'Lade hoch und installiere…';
            statusEl.className = 'save-status save-pending';
            btn.disabled = true;

            try {
                const res = await fetch('/api/plugins/upload', {
                    method: 'POST',
                    body: formData
                });

                if (res.ok) {
                    const data = await res.json();
                    statusEl.textContent = data.message;
                    statusEl.className = 'save-status save-ok';
                    showNotification('Plugin erfolgreich installiert!', 'info');
                    fileInput.value = ''; // Reset

                    // Hard-Reload the UI to fetch the new scripts from the backend
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    const err = await res.json();
                    statusEl.textContent = err.detail || 'Upload fehlgeschlagen';
                    statusEl.className = 'save-status save-error';
                }
            } catch (e) {
                console.error('Plugin Upload Fehler:', e);
                statusEl.textContent = 'Netzwerkfehler beim Upload.';
                statusEl.className = 'save-status save-error';
            } finally {
                btn.disabled = false;
            }
        },

        async deletePlugin(name) {
            if (!await this.confirm(`Möchtest du das Plugin '${name}' wirklich unwiderruflich deinstallieren und löschen?\n\nHinweis: Core-Module können nicht deinstalliert werden (gibt einen 404 Fehler).`)) {
                return;
            }

            try {
                const res = await fetch(`/api/plugins/${name}`, { method: 'DELETE' });
                if (res.ok) {
                    showNotification(`Plugin '${name}' wurde deinstalliert.`, 'info');
                    const card = document.getElementById(`module-card-${name}`);
                    if (card) card.style.display = 'none';
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    const err = await res.json();
                    showNotification(`Fehler: ${err.detail || 'Konnte nicht gelöscht werden.'}`, 'error');
                }
            } catch (e) {
                console.error('Plugin Delete Error:', e);
                showNotification('Netzwerkfehler beim Deinstallieren.', 'error');
            }
        },

        async updatePlugin(name, btnEl) {
            if (this._bulkUpdating) {
                showNotification(t('marketplace.bulkRunning'), 'info');
                return;
            }
            // btnEl is provided by the dispatcher (data-self="true"); fall back to
            // a DOM lookup for legacy/keyboard activation paths.
            const btn = btnEl || document.querySelector(`.btn-update[data-args*="${name}"]`);
            const originalText = btn?.textContent;
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Update...';
            }

            try {
                const res = await fetch(`/api/plugins/reinstall/${encodeURIComponent(name)}`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (res.ok) {
                    const data = await res.json();
                    showNotification(data.message || `Plugin '${name}' wurde aktualisiert.`, 'success');
                    // Keep the pending-updates cache consistent for the moment
                    // before reload — relevant if the reload is ever cancelled.
                    if (Array.isArray(this._pendingPluginUpdates)) {
                        this._pendingPluginUpdates = this._pendingPluginUpdates.filter(n => n !== name);
                        this._updateBulkUpdateButton();
                    }
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
                    showNotification(`Update-Fehler: ${err.detail || 'HTTP ' + res.status}`, 'error');
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = originalText;
                    }
                }
            } catch (e) {
                console.error('Plugin Update Error:', e);
                showNotification('Netzwerkfehler beim Aktualisieren: ' + e.message, 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            }
        },

        _updateBulkUpdateButton() {
            const btn = document.getElementById('btn-update-all-modules');
            if (!btn) return;
            const count = (this._pendingPluginUpdates || []).length;
            btn.style.display = count > 0 ? '' : 'none';
            const label = document.getElementById('btn-update-all-modules-label');
            if (label) {
                label.textContent = count > 1
                    ? t('marketplace.updateAllWithCount', count)
                    : t('marketplace.updateAll');
            }
        },

        async updateAllPlugins() {
            if (this._bulkUpdating) {
                showNotification(t('marketplace.bulkAlreadyRunning'), 'info');
                return;
            }
            const names = [...(this._pendingPluginUpdates || [])];
            if (!names.length) {
                showNotification(t('marketplace.noUpdates'), 'info');
                return;
            }

            if (!await this.confirm(t('marketplace.bulkConfirm', names.length), undefined, {
                okLabel: t('marketplace.update'),
                okVariant: 'primary',
            })) {
                return;
            }

            const btn = document.getElementById('btn-update-all-modules');
            const label = document.getElementById('btn-update-all-modules-label');
            const originalLabel = label?.textContent || t('marketplace.updateAll');
            if (btn) btn.disabled = true;

            // Disable individual update buttons to prevent concurrent reinstalls.
            document.querySelectorAll('.btn-update').forEach(b => { b.disabled = true; });

            this._bulkUpdating = true;
            const results = { ok: [], failed: [] };

            try {
                for (let i = 0; i < names.length; i++) {
                    const name = names[i];
                    if (label) label.textContent = t('marketplace.bulkProgress', i + 1, names.length, name);

                    const card = document.getElementById(`module-card-${name}`);
                    card?.classList.add('module-card-updating');

                    try {
                        const res = await fetch(`/api/plugins/reinstall/${encodeURIComponent(name)}`, {
                            method: 'POST',
                            credentials: 'include',
                            headers: { 'Content-Type': 'application/json' },
                        });
                        if (res.ok) {
                            results.ok.push(name);
                        } else {
                            const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
                            results.failed.push({ name, error: err.detail || `HTTP ${res.status}` });
                        }
                    } catch (e) {
                        console.error(`Bulk update failed for ${name}:`, e);
                        results.failed.push({ name, error: e.message || 'Netzwerkfehler' });
                    } finally {
                        card?.classList.remove('module-card-updating');
                    }
                }
            } finally {
                this._bulkUpdating = false;
            }

            // Summary
            if (results.failed.length === 0) {
                showNotification(t('marketplace.bulkSuccess', results.ok.length), 'success');
            } else if (results.ok.length === 0) {
                showNotification(t('marketplace.bulkAllFailed', results.failed.length), 'error');
                console.warn('Bulk update failures:', results.failed);
            } else {
                showNotification(
                    t('marketplace.bulkPartial', results.ok.length, results.failed.length),
                    'warning',
                );
                console.warn('Bulk update failures:', results.failed);
            }

            if (label) label.textContent = originalLabel;
            if (btn) btn.disabled = false;

            // Only reload if at least one update succeeded — otherwise nothing
            // changed on disk and a reload would just be noise. The route is
            // persisted in sessionStorage, so the user lands back on this tab.
            if (results.ok.length > 0) {
                // Keep update buttons disabled until the reload kicks in to avoid
                // a brief window where the user could trigger another reinstall.
                setTimeout(() => window.location.reload(), 1500);
            } else {
                // Re-query buttons fresh — the DOM may have been re-rendered.
                document.querySelectorAll('.btn-update').forEach(b => { b.disabled = false; });
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, PluginsFeature);
    } else {
        window.PluginsFeature = PluginsFeature;
    }
})();
