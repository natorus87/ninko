/**
 * Telegram Module Frontend Logik
 */
(function () {
    window.TelegramModule = {
        statusInterval: null,
        _allowedIds: [],

        async init() {
            await this.checkStatus();
            await this.loadAllowedIds();
            await this.loadVoiceReplyConfig();
            if (!this.statusInterval) {
                this.statusInterval = setInterval(() => this.checkStatus(), 10000);
            }
        },

        async checkStatus() {
            try {
                const res = await fetch('/api/telegram/status');
                if (res.ok) {
                    const data = await res.json();
                    this.updateStatusUI(data);
                }
            } catch (e) {
                console.error('Telegram Status check failed', e);
            }
        },

        updateStatusUI(data) {
            const card = document.getElementById('tg-status-card');
            const icon = document.getElementById('tg-status-icon');
            const text = document.getElementById('tg-status-text');
            const usernameEl = document.getElementById('tg-username');
            const chatIdEl = document.getElementById('tg-chatid');

            if (card && icon && text) {
                if (data.running) {
                    card.className = 'status-card running';
                    icon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--accent-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="9 12 11 14 15 10"></polyline></svg>';
                    text.textContent = 'Aktiv';
                } else {
                    card.className = 'status-card failing';
                    icon.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="var(--text-muted)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect></svg>';
                    text.textContent = 'Gestoppt';
                }
            }

            if (usernameEl) {
                usernameEl.textContent = data.username ? '@' + data.username : '—';
            }

            if (chatIdEl) {
                chatIdEl.textContent = data.default_chat_id || '—';
            }

            // Eingabefeld mit aktueller default_chat_id vorausfüllen
            const inputEl = document.getElementById('tg-default-chatid-input');
            if (inputEl && data.default_chat_id) {
                inputEl.value = data.default_chat_id;
            }
        },

        async saveDefaultChatId() {
            const input = document.getElementById('tg-default-chatid-input');
            const statusEl = document.getElementById('tg-default-chatid-status');
            const val = input?.value?.trim();

            if (!val) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-warn">Bitte Chat-ID eingeben.</span>';
                return;
            }
            if (!/^-?\d+$/.test(val)) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-warn">Nur numerische Chat-IDs erlaubt.</span>';
                return;
            }

            if (statusEl) statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';

            try {
                const res = await fetch('/api/telegram/default-chat-id', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ default_chat_id: val }),
                });
                const data = await res.json();
                if (res.ok && data.ok) {
                    if (statusEl) statusEl.innerHTML = '<span class="sf sf-ok">Standard Chat-ID gespeichert.</span>';
                    await this.checkStatus();
                    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
                } else {
                    if (statusEl) statusEl.innerHTML = `<span class="sf sf-error">${data.detail || 'Speichern fehlgeschlagen'}</span>`;
                }
            } catch (e) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-error">Verbindungsfehler</span>';
            }
        },

        async startBot() {
            try {
                const res = await fetch('/api/telegram/start', { method: 'POST' });
                if (res.ok) {
                    showNotification('Telegram Bot gestartet.', 'success');
                    await this.checkStatus();
                } else {
                    const data = await res.json();
                    showNotification(`Fehler: ${data.detail || 'Unbekannt'}`, 'error');
                }
            } catch (e) {
                showNotification('Fehler beim Starten des Bots.', 'error');
            }
        },

        async stopBot() {
            try {
                const res = await fetch('/api/telegram/stop', { method: 'POST' });
                if (res.ok) {
                    showNotification('Telegram Bot gestoppt.', 'info');
                    await this.checkStatus();
                } else {
                    showNotification('Fehler beim Stoppen.', 'error');
                }
            } catch (e) {
                showNotification('Fehler beim Stoppen des Bots.', 'error');
            }
        },

        async sendTestMessage() {
            const textarea = document.getElementById('tg-test-msg');
            const statusEl = document.getElementById('tg-send-status');
            const msg = textarea?.value?.trim();

            if (!msg) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-warn">Bitte Nachricht eingeben.</span>';
                return;
            }

            if (statusEl) statusEl.textContent = '⏳ Sende…';

            try {
                const res = await fetch('/api/telegram/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg }),
                });
                const data = await res.json();
                if (res.ok && data.ok) {
                    if (statusEl) statusEl.innerHTML = '<span class="sf sf-ok">Gesendet!</span>';
                    if (textarea) textarea.value = '';
                    setTimeout(() => { if (statusEl) statusEl.innerHTML = ''; }, 3000);
                } else {
                    if (statusEl) statusEl.innerHTML = `<span class="sf sf-error">${data.detail || 'Fehler beim Senden'}</span>`;
                }
            } catch (e) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-error">Verbindungsfehler</span>';
            }
        },

        // ── Erlaubte Nutzer-IDs ──────────────────────────────────────────────

        async loadAllowedIds() {
            try {
                const res = await fetch('/api/telegram/allowed-ids');
                if (res.ok) {
                    const data = await res.json();
                    this._allowedIds = data.allowed_ids || [];
                    this._renderAllowedIds();
                }
            } catch (e) {
                console.error('Telegram: Allowlist laden fehlgeschlagen', e);
            }
        },

        _renderAllowedIds() {
            const container = document.getElementById('tg-allowed-ids-list');
            if (!container) return;

            if (this._allowedIds.length === 0) {
                container.innerHTML = '<span style="color:var(--text-muted);font-size:0.82rem;line-height:2rem;">Keine Einschränkung – alle Chat-IDs erlaubt</span>';
                return;
            }

            container.innerHTML = this._allowedIds.map(id => `
                <span style="display:inline-flex;align-items:center;gap:0.35rem;padding:0.25rem 0.6rem;border-radius:4px;background:var(--bg-hover);border:1px solid var(--border-color);font-size:0.82rem;font-family:monospace;">
                    ${id}
                    <button
                        onclick="TelegramModule.removeAllowedId('${id}')"
                        title="Entfernen"
                        style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:0;line-height:1;font-size:0.9rem;"
                    >✕</button>
                </span>
            `).join('');
        },

        async addAllowedId() {
            const input = document.getElementById('tg-new-id-input');
            const statusEl = document.getElementById('tg-allowed-ids-status');
            const val = input?.value?.trim();

            if (!val) return;
            if (!/^\d+$/.test(val)) {
                if (statusEl) statusEl.innerHTML = '<span class="sf sf-warn">Nur numerische Chat-IDs erlaubt.</span>';
                return;
            }
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
            const statusEl = document.getElementById('tg-allowed-ids-status');
            if (statusEl) statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';

            try {
                const res = await fetch('/api/telegram/allowed-ids', {
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
                const res = await fetch('/api/telegram/voice-reply');
                if (!res.ok) return;
                const data = await res.json();
                const cbReply = document.getElementById('tg-voice-reply');
                const cbText = document.getElementById('tg-voice-reply-text-too');
                if (cbReply) cbReply.checked = !!data.voice_reply;
                if (cbText) cbText.checked = !!data.voice_reply_text_too;
                const langEl = document.getElementById('tg-voice-lang');
                const nameEl = document.getElementById('tg-voice-name');
                if (langEl) langEl.value = data.voice_lang || '';
                if (nameEl) nameEl.value = data.voice_name || '';
            } catch (e) {
                console.error('Telegram: Voice-Reply laden fehlgeschlagen', e);
            }
        },

        async saveVoiceReplyConfig() {
            const btn = document.getElementById('tg-voice-reply-save-btn');
            const statusEl = document.getElementById('tg-voice-reply-status');
            if (btn) btn.disabled = true;
            if (statusEl) statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
            try {
                const body = {
                    voice_reply: document.getElementById('tg-voice-reply')?.checked ?? false,
                    voice_reply_text_too: document.getElementById('tg-voice-reply-text-too')?.checked ?? false,
                    voice_lang: document.getElementById('tg-voice-lang')?.value.trim() ?? '',
                    voice_name: document.getElementById('tg-voice-name')?.value.trim() ?? '',
                };
                const res = await fetch('/api/telegram/voice-reply', {
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
            if (this.statusInterval) {
                clearInterval(this.statusInterval);
                this.statusInterval = null;
            }
        },
    };
})();
