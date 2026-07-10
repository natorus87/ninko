/**
 * Ninko Speech Settings Feature Module
 *
 * Spracheingabe (STT/Whisper), Bilderkennung (OCR/Vision) und Sprachausgabe
 * (TTS/Piper) — das Settings-Panel 'Sprache & Audio'. Aus app.js extrahiert;
 * via Object.assign gemergt.
 */

(function() {
    'use strict';

    const SpeechSettingsFeature = {
        onSttProviderChange() {
            const provider = document.getElementById('stt-provider')?.value;
            document.getElementById('stt-whisper-fields')?.classList.toggle('hidden', provider !== 'whisper');
            document.getElementById('stt-api-fields')?.classList.toggle('hidden', provider !== 'openai_compatible');
        },

        async loadSttSettings() {
            try {
                const res = await fetch('/api/settings/stt');
                if (!res.ok) throw new Error(res.statusText);
                const d = await res.json();

                const provSel = document.getElementById('stt-provider');
                if (provSel) {
                    provSel.value = d.STT_PROVIDER || 'whisper';
                    this.onSttProviderChange();
                }
                const langEl = document.getElementById('stt-language');
                if (langEl) langEl.value = d.WHISPER_LANGUAGE || 'de';

                const sizeSel = document.getElementById('stt-model-size');
                if (sizeSel) sizeSel.value = d.WHISPER_MODEL_SIZE || 'base';

                const devSel = document.getElementById('stt-device');
                if (devSel) devSel.value = d.WHISPER_DEVICE || 'cpu';

                const compSel = document.getElementById('stt-compute-type');
                if (compSel) compSel.value = d.WHISPER_COMPUTE_TYPE || 'int8';

                const urlEl = document.getElementById('stt-api-url');
                if (urlEl) urlEl.value = d.STT_API_URL || '';

                const keyEl = document.getElementById('stt-api-key');
                const sttHasKey = !!(d.STT_API_KEY_SET || d.STT_API_KEY);
                if (keyEl) keyEl.value = sttHasKey ? '••••••••' : '';
                if (keyEl) keyEl.dataset.hasKey = sttHasKey ? '1' : '';

                const modelEl = document.getElementById('stt-api-model');
                if (modelEl) modelEl.value = d.STT_MODEL || 'whisper-large-v3';

                const spellEl = document.getElementById('stt-spellcheck');
                if (spellEl) spellEl.checked = !!d.STT_SPELLCHECK;

                const st = document.getElementById('stt-save-status');
                if (st) st.innerHTML = d.source === 'redis'
                    ? '<span class="sf sf-ok">Gespeichert</span>'
                    : '<span class="sf sf-loading">Standard</span>';
            } catch {
                const st = document.getElementById('stt-save-status');
                if (st) st.innerHTML = '<span class="sf sf-error">Fehler beim Laden</span>';
            }
        },

        async saveSttSettings() {
            const btn = document.getElementById('stt-save-btn');
            const st = document.getElementById('stt-save-status');
            btn.disabled = true;
            st.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
            try {
                const keyEl = document.getElementById('stt-api-key');
                const keyVal = keyEl?.value || '';
                // Nur senden wenn nicht Platzhalter-Dots
                const apiKey = keyVal && keyVal !== '••••••••' ? keyVal : (keyEl?.dataset.hasKey ? undefined : '');

                const body = {
                    STT_PROVIDER: document.getElementById('stt-provider')?.value || 'whisper',
                    WHISPER_LANGUAGE: document.getElementById('stt-language')?.value.trim() || 'de',
                    WHISPER_MODEL_SIZE: document.getElementById('stt-model-size')?.value || 'base',
                    WHISPER_DEVICE: document.getElementById('stt-device')?.value || 'cpu',
                    WHISPER_COMPUTE_TYPE: document.getElementById('stt-compute-type')?.value || 'int8',
                    STT_API_URL: document.getElementById('stt-api-url')?.value.trim() || '',
                    STT_MODEL: document.getElementById('stt-api-model')?.value.trim() || 'whisper-large-v3',
                    STT_SPELLCHECK: document.getElementById('stt-spellcheck')?.checked || false,
                };
                if (apiKey !== undefined) body.STT_API_KEY = apiKey;

                const res = await fetch('/api/settings/stt', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
                st.innerHTML = '<span class="sf sf-ok">Gespeichert</span>';
                // Key-Feld maskieren
                if (keyEl && body.STT_API_KEY) {
                    keyEl.value = '••••••••';
                    keyEl.dataset.hasKey = '1';
                }
            } catch (err) {
                st.innerHTML = `<span class="sf sf-error">${this._escapeHtml(err.message)}</span>`;
            } finally {
                btn.disabled = false;
            }
        },

        // --- OCR Settings ---
        onOcrProviderChange() {
            const provider = document.getElementById('ocr-provider')?.value;
            document.getElementById('ocr-python-fields')?.classList.toggle('hidden', provider !== 'python');
            document.getElementById('ocr-vision-fields')?.classList.toggle('hidden', provider !== 'llm_vision');
        },

        async loadOcrSettings() {
            try {
                const res = await fetch('/api/settings/ocr');
                if (!res.ok) throw new Error(res.statusText);
                const d = await res.json();

                const providerEl = document.getElementById('ocr-provider');
                if (providerEl) {
                    providerEl.value = d.OCR_PROVIDER || 'python';
                    this.onOcrProviderChange();
                }

                const engineEl = document.getElementById('ocr-python-engine');
                if (engineEl) engineEl.value = d.OCR_PYTHON_ENGINE || 'pytesseract';

                const langEl = document.getElementById('ocr-language');
                if (langEl) langEl.value = d.OCR_LANGUAGE || 'deu+eng';

                const urlEl = document.getElementById('ocr-vision-api-url');
                if (urlEl) urlEl.value = d.OCR_VISION_API_URL || '';

                const keyEl = document.getElementById('ocr-vision-api-key');
                const hasKey = !!(d.OCR_VISION_API_KEY_SET || d.OCR_VISION_API_KEY);
                if (keyEl) keyEl.value = hasKey ? '••••••••' : '';
                if (keyEl) keyEl.dataset.hasKey = hasKey ? '1' : '';

                const modelEl = document.getElementById('ocr-vision-model');
                if (modelEl) modelEl.value = d.OCR_VISION_MODEL || '';

                const promptEl = document.getElementById('ocr-vision-prompt');
                if (promptEl) {
                    promptEl.value = d.OCR_VISION_PROMPT || 'Extract all readable text from this image. Return plain text only.';
                }

                const st = document.getElementById('ocr-save-status');
                if (st) {
                    st.innerHTML = d.source === 'redis'
                        ? '<span class="sf sf-ok">Gespeichert</span>'
                        : '<span class="sf sf-loading">Standard</span>';
                }
            } catch {
                const st = document.getElementById('ocr-save-status');
                if (st) st.innerHTML = '<span class="sf sf-error">Fehler beim Laden</span>';
            }
        },

        async saveOcrSettings() {
            const btn = document.getElementById('ocr-save-btn');
            const st = document.getElementById('ocr-save-status');
            btn.disabled = true;
            st.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
            try {
                const keyEl = document.getElementById('ocr-vision-api-key');
                const keyVal = keyEl?.value || '';
                const apiKey = keyVal && keyVal !== '••••••••'
                    ? keyVal
                    : (keyEl?.dataset.hasKey ? undefined : '');

                const body = {
                    OCR_PROVIDER: document.getElementById('ocr-provider')?.value || 'python',
                    OCR_PYTHON_ENGINE: document.getElementById('ocr-python-engine')?.value || 'pytesseract',
                    OCR_LANGUAGE: document.getElementById('ocr-language')?.value.trim() || 'deu+eng',
                    OCR_VISION_API_URL: document.getElementById('ocr-vision-api-url')?.value.trim() || '',
                    OCR_VISION_MODEL: document.getElementById('ocr-vision-model')?.value.trim() || '',
                    OCR_VISION_PROMPT: document.getElementById('ocr-vision-prompt')?.value.trim()
                        || 'Extract all readable text from this image. Return plain text only.',
                };
                if (apiKey !== undefined) body.OCR_VISION_API_KEY = apiKey;

                const res = await fetch('/api/settings/ocr', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error((await res.json()).detail || res.statusText);

                st.innerHTML = '<span class="sf sf-ok">Gespeichert</span>';
                if (keyEl && body.OCR_VISION_API_KEY) {
                    keyEl.value = '••••••••';
                    keyEl.dataset.hasKey = '1';
                }
            } catch (err) {
                st.innerHTML = `<span class="sf sf-error">${this._escapeHtml(err.message)}</span>`;
            } finally {
                btn.disabled = false;
            }
        },

        // --- TTS Settings ---
        async loadTtsSettings() {
            // Stimmen laden und Select befüllen
            let voices = [];
            try {
                const vRes = await fetch('/api/tts/voices');
                if (vRes.ok) voices = await vRes.json();
            } catch { /* ignore */ }
            const sel = document.getElementById('tts-default-voice');
            if (sel) {
                const placeholder = document.createElement('option');
                placeholder.value = '';
                placeholder.textContent = '-- Stimme wählen --';
                const voiceOpts = voices.map(v => {
                    const opt = document.createElement('option');
                    opt.value = `${v.lang}/${v.name}`;
                    opt.textContent = `${v.lang}/${v.name} (${v.quality})`;
                    return opt;
                });
                sel.replaceChildren(placeholder, ...voiceOpts);
            }

            try {
                const res = await fetch('/api/settings/tts');
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                document.getElementById('tts-enabled').checked = !!data.TTS_ENABLED;
                document.getElementById('tts-piper-binary').value = data.PIPER_BINARY || 'piper';
                document.getElementById('tts-voices-dir').value = data.VOICES_DIR || '/app/data/voices';
                document.getElementById('tts-default-lang').value = data.TTS_DEFAULT_LANG || 'de';
                document.getElementById('tts-sample-rate').value = data.TTS_SAMPLE_RATE || 22050;
                // Dropdown: "de/thorsten-medium" aus gespeicherten Werten zusammensetzen
                if (sel && data.TTS_DEFAULT_VOICE) {
                    const combined = `${data.TTS_DEFAULT_LANG || 'de'}/${data.TTS_DEFAULT_VOICE}`;
                    // Ggf. fehlende Option ergänzen (z.B. nach manueller Config-Änderung)
                    if (!Array.from(sel.options).some(o => o.value === combined)) {
                        const opt = document.createElement('option');
                        opt.value = combined;
                        opt.textContent = `${combined} (konfiguriert)`;
                        sel.appendChild(opt);
                    }
                    sel.value = combined;
                }
                const st = document.getElementById('tts-save-status');
                st.innerHTML = data.source === 'redis' ? '<span class="sf sf-ok">Gespeichert</span>' : '<span class="sf sf-loading">Standard</span>';
                st.className = 'save-status';
            } catch {
                const st = document.getElementById('tts-save-status');
                st.innerHTML = '<span class="sf sf-error">Fehler beim Laden</span>';
                st.className = 'save-status';
            }
        },

        async saveTtsSettings() {
            const btn = document.getElementById('tts-save-btn');
            const st = document.getElementById('tts-save-status');
            btn.disabled = true;
            st.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
            st.className = 'save-status';
            try {
                // Stimmen-Dropdown: "de/thorsten-medium" → TTS_DEFAULT_LANG + TTS_DEFAULT_VOICE
                const voiceSel = document.getElementById('tts-default-voice');
                const voiceVal = voiceSel ? voiceSel.value : '';
                const slashIdx = voiceVal.indexOf('/');
                const voiceLang = slashIdx >= 0 ? voiceVal.slice(0, slashIdx) : '';
                const voiceName = slashIdx >= 0 ? voiceVal.slice(slashIdx + 1) : '';
                const langFallback = document.getElementById('tts-default-lang').value.trim();
                const body = {
                    TTS_ENABLED: document.getElementById('tts-enabled').checked,
                    PIPER_BINARY: document.getElementById('tts-piper-binary').value.trim(),
                    VOICES_DIR: document.getElementById('tts-voices-dir').value.trim(),
                    TTS_DEFAULT_LANG: voiceLang || langFallback,
                    TTS_DEFAULT_VOICE: voiceName || langFallback,
                    TTS_SAMPLE_RATE: parseInt(document.getElementById('tts-sample-rate').value) || 22050,
                };
                const res = await fetch('/api/settings/tts', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
                st.innerHTML = '<span class="sf sf-ok">Gespeichert</span>';
                st.className = 'save-status';
            } catch (err) {
                st.innerHTML = `<span class="sf sf-error">${this._escapeHtml(err.message)}</span>`;
                st.className = 'save-status';
            } finally {
                btn.disabled = false;
            }
        },

        fillTtsPreset(lang, voice) {
            document.getElementById('tts-dl-lang').value = lang;
            document.getElementById('tts-dl-voice').value = voice;
            document.getElementById('tts-dl-status').textContent = '';
        },

        async loadTtsVoices() {
            const container = document.getElementById('tts-voices-list');
            if (!container) return;
            container.innerHTML = '<p class="text-muted">Lade…</p>';
            try {
                const res = await fetch('/api/tts/voices');
                if (!res.ok) throw new Error(res.statusText);
                const voices = await res.json();
                // Dropdown aktualisieren
                const sel = document.getElementById('tts-default-voice');
                if (sel) {
                    const current = sel.value;
                    const placeholder = document.createElement('option');
                    placeholder.value = '';
                    placeholder.textContent = '-- Stimme wählen --';
                    const voiceOpts = voices.map(v => {
                        const opt = document.createElement('option');
                        opt.value = `${v.lang}/${v.name}`;
                        opt.textContent = `${v.lang}/${v.name} (${v.quality})`;
                        return opt;
                    });
                    sel.replaceChildren(placeholder, ...voiceOpts);
                    if (current) sel.value = current;
                }
                if (voices.length === 0) {
                    container.innerHTML = '<p class="text-muted">Keine Stimmen installiert. Stimme unten herunterladen.</p>';
                    return;
                }
                const table = document.createElement('table');
                table.className = 'data-table';
                const thead = document.createElement('thead');
                const headRow = document.createElement('tr');
                ['Sprache', 'Name', 'Qualität', ''].forEach(label => {
                    const th = document.createElement('th');
                    th.textContent = label;
                    headRow.appendChild(th);
                });
                thead.appendChild(headRow);
                table.appendChild(thead);
                const tbody = document.createElement('tbody');
                voices.forEach(v => {
                    const tr = document.createElement('tr');
                    [v.lang, v.name, v.quality].forEach(val => {
                        const td = document.createElement('td');
                        td.textContent = val || '';
                        tr.appendChild(td);
                    });
                    const actionTd = document.createElement('td');
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-outline btn-sm';
                    btn.style.color = 'var(--error-color)';
                    btn.style.borderColor = 'var(--error-color)';
                    btn.dataset.action = 'deleteTtsVoice';
                    btn.dataset.args = JSON.stringify([v.lang, v.name]);
                    btn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>';
                    actionTd.appendChild(btn);
                    tr.appendChild(actionTd);
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody);
                container.replaceChildren(table);
            } catch (err) {
                container.innerHTML = `<p class="text-muted">Fehler: ${this._escapeHtml(err.message)}</p>`;
            }
        },

        async testTtsPreview() {
            const text = document.getElementById('tts-preview-text').value.trim() || 'Hallo, ich bin Ninko.';
            const audioEl = document.getElementById('tts-preview-audio');
            audioEl.style.display = 'none';
            try {
                const res = await fetch('/api/tts/synthesize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text }),
                });
                if (!res.ok) {
                    const err = await res.json();
                    showNotification(err.detail || 'TTS-Fehler', 'error');
                    return;
                }
                const blob = await res.blob();
                audioEl.src = URL.createObjectURL(blob);
                audioEl.style.display = 'block';
                audioEl.play();
            } catch (err) {
                showNotification(`TTS-Fehler: ${err.message}`, 'error');
            }
        },

        async downloadTtsVoice() {
            const btn = document.getElementById('tts-dl-btn');
            const st = document.getElementById('tts-dl-status');
            const lang = document.getElementById('tts-dl-lang').value.trim();
            const voice = document.getElementById('tts-dl-voice').value.trim();
            if (!lang || !voice) {
                st.innerHTML = '<span class="sf sf-error">Sprache und Stimmenname sind Pflichtfelder.</span>';
                st.className = 'save-status';
                return;
            }
            btn.disabled = true;
            st.innerHTML = '<span class="sf sf-loading">Lade herunter… (kann einige Minuten dauern)</span>';
            st.className = 'save-status';
            try {
                const res = await fetch('/api/tts/voices/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lang, voice }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || res.statusText);
                if (data.status === 'already_installed') {
                    st.innerHTML = '<span class="sf sf-ok">Bereits installiert</span>';
                    st.className = 'save-status';
                } else {
                    const okSpan = document.createElement('span');
                    okSpan.className = 'sf sf-ok';
                    okSpan.textContent = `${lang}/${voice} installiert`;
                    st.replaceChildren(okSpan);
                    st.className = 'save-status';
                    this.loadTtsVoices();
                }
            } catch (err) {
                st.innerHTML = `<span class="sf sf-error">${this._escapeHtml(err.message)}</span>`;
                st.className = 'save-status';
            } finally {
                btn.disabled = false;
            }
        },

        async deleteTtsVoice(lang, voice) {
            if (!confirm(`Stimme "${lang}/${voice}" wirklich löschen?`)) return;
            try {
                const res = await fetch(`/api/tts/voices/${lang}/${voice}`, { method: 'DELETE' });
                if (!res.ok) {
                    const data = await res.json();
                    showNotification(data.detail || 'Fehler', 'error');
                    return;
                }
                showNotification(`Stimme ${lang}/${voice} gelöscht`, 'success');
                this.loadTtsVoices();
            } catch (err) {
                showNotification(`Fehler: ${err.message}`, 'error');
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, SpeechSettingsFeature);
    } else {
        window.SpeechSettingsFeature = SpeechSettingsFeature;
    }
})();
