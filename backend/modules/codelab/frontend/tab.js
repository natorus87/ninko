/**
 * CodeLab Tab – Code-Sandbox & Text-Verbesserung
 */
(function () {
    let _clickOutsideRegistered = false;

    const CodelabTab = {
        API_PREFIX: '/api/codelab',

        init() {
            this._setupTabKeyInEditor();
            this._setupSelectListeners();
            this._setupClickOutside();
            this._loadLanguages();
        },

        // ── Custom Select ──────────────────────────────────────────

        toggleSelect(selectId) {
            const el = document.getElementById(selectId);
            if (!el) return;
            const isOpen = el.classList.contains('open');
            // Alle anderen schließen
            document.querySelectorAll('.cl-select.open').forEach(s => s.classList.remove('open'));
            if (!isOpen) el.classList.add('open');
        },

        _setupSelectListeners() {
            document.querySelectorAll('#codelab-tab-content .cl-select').forEach(sel => {
                sel.querySelectorAll('.cl-select-option').forEach(opt => {
                    opt.addEventListener('click', () => {
                        if (opt.classList.contains('disabled')) return;
                        sel.querySelectorAll('.cl-select-option').forEach(o => o.classList.remove('selected'));
                        opt.classList.add('selected');
                        const label = sel.querySelector('.cl-select-label');
                        if (label) label.textContent = opt.textContent;
                        sel.classList.remove('open');
                    });
                });
            });
        },

        _setupClickOutside() {
            if (_clickOutsideRegistered) return;
            _clickOutsideRegistered = true;
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.cl-select')) {
                    document.querySelectorAll('.cl-select.open').forEach(s => s.classList.remove('open'));
                }
            });
        },

        _getSelectValue(selectId) {
            const sel = document.getElementById(selectId);
            const opt = sel?.querySelector('.cl-select-option.selected');
            return opt?.dataset.value || '';
        },

        // ── Languages ──────────────────────────────────────────────

        async _loadLanguages() {
            try {
                const res = await fetch(`${this.API_PREFIX}/languages`);
                const langs = await res.json();
                const sel = document.getElementById('codelab-lang-select');
                if (!sel) return;
                sel.querySelectorAll('.cl-select-option').forEach(opt => {
                    const info = langs[opt.dataset.value];
                    if (info && !info.available) {
                        opt.classList.add('disabled');
                        opt.textContent += ' (nicht verfügbar)';
                        // Falls die aktuell gewählte Option nicht verfügbar ist,
                        // erste verfügbare Option aktivieren
                        if (opt.classList.contains('selected')) {
                            opt.classList.remove('selected');
                            const first = sel.querySelector('.cl-select-option:not(.disabled)');
                            if (first) {
                                first.classList.add('selected');
                                const label = sel.querySelector('.cl-select-label');
                                if (label) label.textContent = first.textContent;
                            }
                        }
                    }
                });
            } catch (_) { /* ignore */ }
        },

        // ── Editor ─────────────────────────────────────────────────

        _setupTabKeyInEditor() {
            const editor = document.getElementById('codelab-editor');
            if (!editor) return;
            editor.addEventListener('keydown', (e) => {
                if (e.key === 'Tab') {
                    e.preventDefault();
                    const s = editor.selectionStart;
                    editor.value = editor.value.slice(0, s) + '    ' + editor.value.slice(editor.selectionEnd);
                    editor.selectionStart = editor.selectionEnd = s + 4;
                }
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    this.runCode();
                }
            });
        },

        // ── Code ausführen ─────────────────────────────────────────

        async runCode() {
            const editor = document.getElementById('codelab-editor');
            const lang = this._getSelectValue('codelab-lang-select') || 'python';
            const code = editor?.value?.trim();

            if (!code) { this._setStatus('Kein Code eingegeben.'); return; }

            const btn = document.getElementById('codelab-run-btn');
            if (btn) { btn.disabled = true; btn.textContent = 'Läuft…'; }
            this._setStatus('Ausführen…');
            this._clearOutput();

            try {
                const res = await fetch(`${this.API_PREFIX}/execute`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, language: lang, timeout: 15 }),
                });
                this._showOutput(await res.json());
            } catch (err) {
                this._showOutput({ stdout: '', stderr: String(err), exit_code: -1, duration_ms: 0 });
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = '▶ Ausführen'; }
                this._setStatus('');
            }
        },

        _showOutput(data) {
            const stdout = document.getElementById('codelab-stdout');
            const stderr = document.getElementById('codelab-stderr');
            const badge  = document.getElementById('codelab-exit-badge');
            const dur    = document.getElementById('codelab-duration');

            if (stdout) stdout.textContent = data.stdout || '(keine Ausgabe)';
            if (stderr && data.stderr) { stderr.textContent = data.stderr; stderr.style.display = 'block'; }
            else if (stderr)           { stderr.style.display = 'none'; }

            if (badge) {
                const ok = data.exit_code === 0;
                badge.textContent = ok ? '✓ Exit 0' : `✗ Exit ${data.exit_code}`;
                badge.style.cssText = `display:inline; font-size:0.75rem; font-weight:normal; padding:0.15rem 0.5rem; border-radius:99px; background:${ok ? 'rgba(76,175,80,0.15)' : 'rgba(224,82,82,0.15)'}; color:${ok ? '#4caf50' : '#e05252'};`;
            }
            if (dur && data.duration_ms !== undefined) dur.textContent = `${data.duration_ms.toFixed(0)} ms`;
        },

        _clearOutput() {
            const stdout = document.getElementById('codelab-stdout');
            const stderr = document.getElementById('codelab-stderr');
            const badge  = document.getElementById('codelab-exit-badge');
            const dur    = document.getElementById('codelab-duration');
            if (stdout) stdout.textContent = '';
            if (stderr) { stderr.textContent = ''; stderr.style.display = 'none'; }
            if (badge)  badge.style.display = 'none';
            if (dur)    dur.textContent = '';
        },

        _setStatus(msg) {
            const el = document.getElementById('codelab-status');
            if (el) el.textContent = msg;
        },

        // ── Clipboard ──────────────────────────────────────────────

        copyText(elementId) {
            const el = document.getElementById(elementId);
            const text = (el?.tagName === 'TEXTAREA' || el?.tagName === 'INPUT')
                ? el.value
                : el?.textContent;
            if (!text || !text.trim()) return;
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(() => {
                    if (typeof showNotification === 'function') showNotification('Kopiert!', 'success');
                }).catch(() => this._copyFallback(text));
            } else {
                this._copyFallback(text);
            }
        },

        _copyFallback(text) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;opacity:0;';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        },

        // ── Chat-Integration ───────────────────────────────────────

        sendToChat(action) {
            const editor = document.getElementById('codelab-editor');
            const code = editor?.value?.trim();
            const lang = this._getSelectValue('codelab-lang-select') || 'python';

            if (!code) {
                if (typeof showNotification === 'function') showNotification('Kein Code im Editor.', 'warning');
                return;
            }

            const msgs = {
                improve: `Bitte verbessere den folgenden ${lang}-Code hinsichtlich Lesbarkeit, Performance und Best Practices:\n\n\`\`\`${lang}\n${code}\n\`\`\``,
                explain: `Erkläre mir bitte Schritt für Schritt, was dieser ${lang}-Code macht:\n\n\`\`\`${lang}\n${code}\n\`\`\``,
                review:  `Führe bitte ein Code-Review für den folgenden ${lang}-Code durch und gib strukturiertes Feedback:\n\n\`\`\`${lang}\n${code}\n\`\`\``,
            };

            const chatInput = document.getElementById('chat-input');
            if (chatInput && msgs[action]) {
                chatInput.value = msgs[action];
                if (typeof app !== 'undefined' && typeof app.sendMessage === 'function') app.sendMessage();
            }
        },

        // ── Text-Verbesserung ──────────────────────────────────────

        async improveText() {
            const input  = document.getElementById('codelab-text-input');
            const output = document.getElementById('codelab-text-output');
            const style  = this._getSelectValue('codelab-style-select') || 'klar';
            const btn    = document.getElementById('codelab-text-btn');
            const text   = input?.value?.trim();

            if (!text) {
                if (typeof showNotification === 'function') showNotification('Bitte Text eingeben.', 'warning');
                return;
            }

            if (btn) { btn.disabled = true; btn.textContent = 'Läuft…'; }
            if (output) output.value = 'Warte auf Antwort…';

            try {
                const res = await fetch(`${this.API_PREFIX}/improve-text`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, style }),
                });
                const data = await res.json();
                if (output) output.value = data.result || data.error || 'Keine Antwort erhalten.';
            } catch (err) {
                if (output) output.value = `Fehler: ${err}`;
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = 'Verbessern'; }
            }
        },

        // ── Leeren ─────────────────────────────────────────────────

        clearAll() {
            const editor = document.getElementById('codelab-editor');
            if (editor) editor.value = '';
            this._clearOutput();
            this._setStatus('');
            const textIn  = document.getElementById('codelab-text-input');
            const textOut = document.getElementById('codelab-text-output');
            if (textIn)  textIn.value  = '';
            if (textOut) textOut.value = '';
        },

        destroy() { },
    };

    window.CodelabTab = CodelabTab;
})();
