/**
 * Microsoft Teams Modul – Frontend Tab
 */
(function () {
    window.TeamsTab = {
        _allowedIds: [],

        async init() {
            await this.checkStatus();
            await this.loadAllowedIds();
            await this.loadVoiceReplyConfig();
        },

        async checkStatus() {
            try {
                const res = await fetch('/api/teams/status');
                if (!res.ok) return;
                const data = await res.json();

                const configIcon = document.getElementById('teams-config-icon');
                const configText = document.getElementById('teams-config-text');
                const configCard = document.getElementById('teams-config-card');
                if (configCard && configIcon && configText) {
                    if (data.configured) {
                        configCard.className = 'status-card running';
                        configIcon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="9 12 11 14 15 10"></polyline></svg>';
                        configText.textContent = 'Konfiguriert';
                    } else {
                        configCard.className = 'status-card failing';
                        configIcon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-yellow)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
                        configText.textContent = 'Nicht konfiguriert';
                    }
                }

                const convEl = document.getElementById('teams-conv-text');
                if (convEl) {
                    convEl.textContent = data.last_conversation_id
                        ? data.last_conversation_id.slice(0, 40) + '…'
                        : '—';
                }

                const countEl = document.getElementById('teams-allowed-count');
                if (countEl) {
                    countEl.textContent = (data.allowed_ids || []).length === 0
                        ? 'Alle'
                        : (data.allowed_ids || []).length;
                }
            } catch (e) {
                console.error('Teams Status check failed', e);
            }
        },

        // ── Erlaubte Nutzer-IDs ──────────────────────────────────────────────

        async loadAllowedIds() {
            try {
                const res = await fetch('/api/teams/allowed-ids');
                if (res.ok) {
                    const data = await res.json();
                    this._allowedIds = data.allowed_ids || [];
                    this._renderAllowedIds();
                }
            } catch (e) {
                console.error('Teams: Allowlist laden fehlgeschlagen', e);
            }
        },

        _renderAllowedIds() {
            const container = document.getElementById('teams-allowed-ids-list');
            if (!container) return;

            if (this._allowedIds.length === 0) {
                container.innerHTML = '<span style="color:var(--text-muted);font-size:0.82rem;line-height:2rem;">Keine Einschränkung – alle Nutzer erlaubt</span>';
                return;
            }

            container.innerHTML = this._allowedIds.map(id => `
                <span style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.25rem 0.6rem;border-radius:4px;background:var(--bg-hover);border:1px solid var(--border-color);font-size:0.82rem;font-family:monospace;">
                    ${id}
                    <button
                        onclick="TeamsTab.removeAllowedId('${id}')"
                        title="Entfernen"
                        style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:0;line-height:1;font-size:0.9rem;"
                    >✕</button>
                </span>
            `).join('');
        },

        async addAllowedId() {
            const input = document.getElementById('teams-new-id-input');
            const statusEl = document.getElementById('teams-allowed-ids-status');
            const val = input?.value?.trim();

            if (!val) return;
            if (this._allowedIds.includes(val)) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-warn">Diese ID ist bereits in der Liste.</span>';
                return;
            }

            const newIds = [...this._allowedIds, val];
            await this._saveAllowedIds(newIds);
            if (input) input.value = '';
        },

        async removeAllowedId(id) {
            const newIds = this._allowedIds.filter(x => x !== id);
            await this._saveAllowedIds(newIds);
        },

        async _saveAllowedIds(ids) {
            const statusEl = document.getElementById('teams-allowed-ids-status');
            if (statusEl) statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';

            try {
                const res = await fetch('/api/teams/allowed-ids', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids }),
                });
                const data = await res.json();
                if (res.ok && data.ok) {
                    this._allowedIds = data.allowed_ids;
                    this._renderAllowedIds();
                    if (statusEl) statusEl.innerHTML = '<span class="sf sf-ok">Gespeichert.</span>';
                    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
                    await this.checkStatus();
                } else {
                    if (statusEl) statusEl.innerHTML = `<span class="sf sf-error">${data.detail || 'Speichern fehlgeschlagen'}</span>`;
                }
            } catch (e) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-error">Verbindungsfehler</span>';
            }
        },

        // ── Voice-Reply ──────────────────────────────────────────────────────
        async loadVoiceReplyConfig() {
            try {
                const res = await fetch('/api/teams/voice-reply');
                if (!res.ok) return;
                const data = await res.json();
                const cbReply = document.getElementById('teams-voice-reply');
                const cbText = document.getElementById('teams-voice-reply-text-too');
                if (cbReply) cbReply.checked = !!data.voice_reply;
                if (cbText) cbText.checked = data.voice_reply_text_too !== false;
                const langEl = document.getElementById('teams-voice-lang');
                const nameEl = document.getElementById('teams-voice-name');
                if (langEl) langEl.value = data.voice_lang || '';
                if (nameEl) nameEl.value = data.voice_name || '';
            } catch (e) {
                console.error('Teams: Voice-Reply laden fehlgeschlagen', e);
            }
        },

        async saveVoiceReplyConfig() {
            const btn = document.getElementById('teams-voice-reply-save-btn');
            const statusEl = document.getElementById('teams-voice-reply-status');
            if (btn) btn.disabled = true;
            if (statusEl) statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
            try {
                const body = {
                    voice_reply: document.getElementById('teams-voice-reply')?.checked ?? false,
                    voice_reply_text_too: document.getElementById('teams-voice-reply-text-too')?.checked ?? true,
                    voice_lang: document.getElementById('teams-voice-lang')?.value.trim() ?? '',
                    voice_name: document.getElementById('teams-voice-name')?.value.trim() ?? '',
                };
                const res = await fetch('/api/teams/voice-reply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (res.ok && data.ok) {
                    if (statusEl) statusEl.innerHTML = '<span class="sf sf-ok">Gespeichert.</span>';
                    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
                } else {
                    if (statusEl) statusEl.innerHTML = `<span class="sf sf-error">${data.detail || 'Fehler'}</span>`;
                }
            } catch (e) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-error">Verbindungsfehler</span>';
            } finally {
                if (btn) btn.disabled = false;
            }
        },

        destroy() {
            // kein Polling-Interval notwendig
        },
    };
})();
