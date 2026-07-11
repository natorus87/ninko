/**
 * Ninko Background Settings Feature Module
 *
 * Hintergrundfarben (Settings → Themes → Hintergrundfarben): Presets,
 * Farb-Picker, Ableitung der Verlaufs-Stops, Persistenz via
 * /api/settings/background mit localStorage-Fastpath. Aus app.js
 * extrahiert; via Object.assign gemergt. loadBackgroundSettings wird
 * beim App-Init (nach Feature-Merge) gerufen, initBackgroundSettingsUI
 * aus themes.js. Der State (_background, _bgSaveTimer, _bgUiBound)
 * wandert mit ins Feature.
 */

(function() {
    'use strict';

    const BackgroundSettingsFeature = {
        _background: null,
        _bgSaveTimer: null,
        _bgUiBound: false,

        _bgDefaults() {
            return { preset: 'default', tint: '#070b24', accent1: '#6d28d9', accent2: '#007aff' };
        },

        _bgPresets() {
            return [
                { id: 'default', tint: '#070b24', accent1: '#6d28d9', accent2: '#007aff' },
                { id: 'ocean', tint: '#041526', accent1: '#0891b2', accent2: '#38bdf8' },
                { id: 'emerald', tint: '#04160f', accent1: '#059669', accent2: '#34d399' },
                { id: 'sunset', tint: '#1c0b05', accent1: '#ea580c', accent2: '#f59e0b' },
                { id: 'crimson', tint: '#1b0511', accent1: '#be123c', accent2: '#ec4899' },
                { id: 'graphite', tint: '#0b0d12', accent1: '#475569', accent2: '#64748b' },
            ];
        },

        _isHexColor(v) {
            return typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v);
        },

        /** Leitet Mittel- und Tiefton des Basis-Verlaufs aus dem Grundton ab.
         *  Für den Default (#070b24) ergeben sich exakt die bisherigen Stops. */
        _deriveTintStops(hex) {
            const n = parseInt(hex.slice(1), 16);
            const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
            const clamp = (x) => Math.max(0, Math.min(255, Math.round(x)));
            const toHex = (rr, gg, bb) =>
                '#' + [rr, gg, bb].map((x) => x.toString(16).padStart(2, '0')).join('');
            return {
                mid: toHex(clamp(r + 2), clamp(g + 2), clamp(b + 10)),
                deep: toHex(clamp(r * 0.3), clamp(g * 0.55), clamp(b * 0.65)),
            };
        },

        _applyBackgroundColors(cfg) {
            const c = { ...this._bgDefaults(), ...(cfg || {}) };
            if (!this._isHexColor(c.tint) || !this._isHexColor(c.accent1) || !this._isHexColor(c.accent2)) return;
            const stops = this._deriveTintStops(c.tint);
            const root = document.documentElement.style;
            root.setProperty('--bg-tint', c.tint);
            root.setProperty('--bg-tint-mid', stops.mid);
            root.setProperty('--bg-tint-deep', stops.deep);
            root.setProperty('--bg-accent-1', c.accent1);
            root.setProperty('--bg-accent-2', c.accent2);
            this._background = c;
        },

        async loadBackgroundSettings() {
            // Schneller Pfad: zuletzt angewendete Farben aus localStorage (kein Flash)
            try {
                const cached = JSON.parse(localStorage.getItem('ninko_background') || 'null');
                if (cached) this._applyBackgroundColors(cached);
            } catch { /* ignore */ }
            try {
                const res = await fetch('/api/settings/background', { cache: 'no-store' });
                if (!res.ok) return;
                const data = await res.json();
                this._applyBackgroundColors(data);
                localStorage.setItem('ninko_background', JSON.stringify(this._background));
            } catch { /* Netzwerkfehler: Cache/Defaults bleiben aktiv */ }
        },

        _persistBackgroundSettings() {
            clearTimeout(this._bgSaveTimer);
            this._bgSaveTimer = setTimeout(async () => {
                const status = document.getElementById('bg-settings-status');
                try {
                    const res = await fetch('/api/settings/background', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this._background),
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    localStorage.setItem('ninko_background', JSON.stringify(this._background));
                    if (status) {
                        status.textContent = t('settings.background.saved');
                        setTimeout(() => { if (status.textContent === t('settings.background.saved')) status.textContent = ''; }, 2000);
                    }
                } catch (e) {
                    if (status) status.textContent = t('common.error');
                    console.warn('Hintergrund-Settings konnten nicht gespeichert werden:', e);
                }
            }, 400);
        },

        _setBackground(cfg) {
            this._applyBackgroundColors(cfg);
            this._syncBackgroundForm();
            this._renderBackgroundPresets();
            this._persistBackgroundSettings();
        },

        async resetBackgroundSettings() {
            this._setBackground(this._bgDefaults());
        },

        _syncBackgroundForm() {
            const c = this._background || this._bgDefaults();
            for (const key of ['tint', 'accent1', 'accent2']) {
                const picker = document.getElementById(`bg-picker-${key}`);
                const hexInput = document.getElementById(`bg-hex-${key}`);
                if (picker) picker.value = c[key];
                if (hexInput) {
                    hexInput.value = c[key];
                    hexInput.classList.remove('invalid');
                }
            }
        },

        _renderBackgroundPresets() {
            const list = document.getElementById('bg-preset-list');
            if (!list) return;
            const active = this._background?.preset || 'default';
            list.innerHTML = this._bgPresets().map((p) => `
                <button type="button" class="bg-preset-chip${p.id === active ? ' active' : ''}" data-bg-preset="${p.id}"
                        title="${this._escapeHtml(t('settings.background.preset.' + p.id))}">
                    <span class="bg-preset-swatch" style="background:
                        radial-gradient(circle at 30% 25%, ${p.accent1} 0%, transparent 55%),
                        radial-gradient(circle at 72% 70%, ${p.accent2} 0%, transparent 55%),
                        ${p.tint};"></span>
                    <span class="bg-preset-name">${this._escapeHtml(t('settings.background.preset.' + p.id))}</span>
                </button>
            `).join('');
            list.querySelectorAll('[data-bg-preset]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const preset = this._bgPresets().find((p) => p.id === btn.dataset.bgPreset);
                    if (preset) {
                        const { id, ...colors } = preset;
                        this._setBackground({ preset: id, ...colors });
                    }
                });
            });
        },

        initBackgroundSettingsUI() {
            this._renderBackgroundPresets();
            this._syncBackgroundForm();
            if (this._bgUiBound) return;
            this._bgUiBound = true;
            for (const key of ['tint', 'accent1', 'accent2']) {
                const picker = document.getElementById(`bg-picker-${key}`);
                const hexInput = document.getElementById(`bg-hex-${key}`);
                picker?.addEventListener('input', () => {
                    this._setBackground({ ...(this._background || this._bgDefaults()), preset: 'custom', [key]: picker.value });
                });
                hexInput?.addEventListener('input', () => {
                    const val = hexInput.value.trim().toLowerCase();
                    if (!this._isHexColor(val)) {
                        hexInput.classList.add('invalid');
                        return;
                    }
                    hexInput.classList.remove('invalid');
                    this._setBackground({ ...(this._background || this._bgDefaults()), preset: 'custom', [key]: val });
                });
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, BackgroundSettingsFeature);
    } else {
        window.BackgroundSettingsFeature = BackgroundSettingsFeature;
    }
})();
