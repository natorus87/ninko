/**
 * Ninko Branding Feature Module
 *
 * Dashboard- und Login-Branding: Formular laden/speichern/zurücksetzen,
 * Asset-Upload/-Löschung, Login-Bild-Generierung und Live-Vorschau. Aus
 * app.js extrahiert; via Object.assign gemergt. loadBrandingSettings/
 * applyBranding werden beim App-Init (nach Feature-Merge) gerufen. Der
 * _branding-State bleibt in app.js.
 */

(function() {
    'use strict';

    const BrandingFeature = {
        async loadBrandingSettings() {
            try {
                const res = await fetch('/api/settings/branding', { cache: 'no-store' });
                if (!res.ok) return;
                const data = await res.json();
                this._branding = { ...this._branding, ...(data || {}) };
            } catch { /* ignore */ }
        },

        applyBranding() {
            const b = this._branding || {};
            const pageTitle = (b.page_title || b.brand_name || 'Ninko').trim() || 'Ninko';
            document.title = pageTitle;
            const desc = document.querySelector('meta[name="description"]');
            if (desc) {
                desc.setAttribute('content', `${b.brand_name || 'Ninko'} – IT-Operations-AI-Agent Dashboard`);
            }

            const chatTitle = document.querySelector('.welcome-message h2');
            if (chatTitle) {
                this.renderWelcomeState();
            }
        },

        async loadBrandingForm() {
            await this.loadBrandingSettings();
            const b = this._branding || {};
            const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
            setVal('branding-brand-name', b.brand_name || '');
            setVal('branding-page-title', b.page_title || '');
            setVal('branding-welcome-mode', b.welcome_mode === 'off' ? 'off' : 'text');
            setVal('branding-welcome-title', b.welcome_title || '');
            setVal('branding-welcome-text', b.welcome_text || '');
            setVal('branding-login-title', b.login_title || 'Ninko Login');
            setVal('branding-login-subtitle', b.login_subtitle || 'Please sign in with your admin account.');
            setVal('branding-login-help-url', b.login_help_url || 'https://github.com/natorus87/ninko/blob/main/DOCS.md');
            setVal('branding-login-head-mode', b.login_head_mode || 'image');
            setVal('branding-login-image-url', b.login_image_url || '/static/images/logo_dashboard_new.png?v=3');
            setVal('branding-login-background-style', b.login_background_style || 'aurora');
            setVal('branding-login-card-style', b.login_card_style || 'glass');
            setVal('branding-login-gen-prompt', 'Futuristic AI guardian head, glowing cyan eyes, dark navy background, clean composition, high detail');
            const loginInput = document.getElementById('branding-login-image-url');
            if (loginInput && !loginInput.dataset.boundPreview) {
                loginInput.addEventListener('input', () => this.refreshBrandingPreviews());
                loginInput.dataset.boundPreview = '1';
            }
            const loginEyes = document.getElementById('branding-login-show-eyes');
            if (loginEyes) loginEyes.checked = b.login_show_eyes !== false;
            this._bindBrandingLivePreviewInputs();
            this.onLoginHeadModeChange();
            this.refreshBrandingPreviews();
            this.renderLoginLivePreview();
        },

        onLoginHeadModeChange() {
            const mode = document.getElementById('branding-login-head-mode')?.value || 'image';
            const imgRow = document.getElementById('branding-login-image-row');
            const eyeRow = document.getElementById('branding-login-eyes-row');
            if (imgRow) imgRow.style.display = mode === 'image' ? '' : 'none';
            if (eyeRow) eyeRow.style.display = mode === 'image' ? '' : 'none';
            this.refreshBrandingPreviews();
            this.renderLoginLivePreview();
        },

        refreshBrandingPreviews() {
            const loginUrl = document.getElementById('branding-login-image-url')?.value?.trim() || '/static/images/logo_dashboard_new.png?v=3';
            const loginPreview = document.getElementById('branding-login-preview');
            if (loginPreview) loginPreview.src = loginUrl;
            this.renderLoginLivePreview();
        },

        _bindBrandingLivePreviewInputs() {
            const ids = [
                'branding-login-title',
                'branding-login-subtitle',
                'branding-login-help-url',
                'branding-login-head-mode',
                'branding-login-image-url',
                'branding-login-show-eyes',
                'branding-login-background-style',
                'branding-login-card-style',
                'branding-brand-name',
            ];
            for (const id of ids) {
                const el = document.getElementById(id);
                if (!el || el.dataset.liveBound === '1') continue;
                const eventName = el.type === 'checkbox' || el.tagName === 'SELECT' ? 'change' : 'input';
                el.addEventListener(eventName, () => this.renderLoginLivePreview());
                el.dataset.liveBound = '1';
            }
        },

        renderLoginLivePreview() {
            const shell = document.getElementById('branding-login-live-preview');
            if (!shell) return;

            const title = document.getElementById('branding-login-title')?.value?.trim() || 'Ninko Login';
            const subtitle = document.getElementById('branding-login-subtitle')?.value || 'Please sign in with your admin account.';
            const helpUrl = document.getElementById('branding-login-help-url')?.value?.trim() || 'https://github.com/natorus87/ninko/blob/main/DOCS.md';
            const headMode = document.getElementById('branding-login-head-mode')?.value || 'image';
            const imageUrl = document.getElementById('branding-login-image-url')?.value?.trim() || '/static/images/logo_dashboard_new.png?v=3';
            const showEyes = !!document.getElementById('branding-login-show-eyes')?.checked;
            const bgStyle = document.getElementById('branding-login-background-style')?.value || 'aurora';
            const cardStyle = document.getElementById('branding-login-card-style')?.value || 'glass';
            const brandName = document.getElementById('branding-brand-name')?.value?.trim() || 'Ninko';

            const previewShell = document.getElementById('branding-login-preview-shell');
            const headWrap = document.getElementById('branding-login-preview-head-wrap');
            const imageWrap = document.getElementById('branding-login-preview-image-wrap');
            const imageEl = document.getElementById('branding-login-preview-image');
            const textEl = document.getElementById('branding-login-preview-text');
            const eyeL = document.getElementById('branding-login-preview-eye-left');
            const eyeR = document.getElementById('branding-login-preview-eye-right');
            const titleEl = document.getElementById('branding-login-preview-title');
            const subtitleEl = document.getElementById('branding-login-preview-subtitle');
            const helpWrap = document.getElementById('branding-login-preview-help-wrap');
            const helpEl = document.getElementById('branding-login-preview-help');

            if (titleEl) titleEl.textContent = title;
            if (subtitleEl) subtitleEl.textContent = subtitle;
            if (helpEl) {
                helpEl.href = helpUrl || '#';
                helpEl.style.display = helpUrl ? '' : 'none';
            }
            if (helpWrap) helpWrap.style.display = helpUrl ? '' : 'none';
            if (imageEl) imageEl.src = imageUrl;

            shell.style.background = bgStyle === 'minimal'
                ? 'var(--bg-primary)'
                : (bgStyle === 'gradient'
                    ? 'linear-gradient(135deg, color-mix(in srgb, var(--primary-color) 18%, var(--bg-primary) 82%) 0%, var(--bg-primary) 68%)'
                    : 'radial-gradient(900px 520px at 18% 10%, color-mix(in srgb, var(--primary-color) 22%, transparent), transparent 66%), var(--bg-primary)');

            if (previewShell) {
                previewShell.style.backdropFilter = cardStyle === 'solid' ? 'none' : 'blur(10px)';
                previewShell.style.background = cardStyle === 'solid'
                    ? 'var(--bg-secondary)'
                    : 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 92%, white 8%) 0%, var(--bg-secondary) 100%)';
            }

            if (headMode === 'off') {
                if (headWrap) headWrap.style.display = 'none';
            } else if (headMode === 'text') {
                if (headWrap) headWrap.style.display = '';
                if (imageWrap) imageWrap.style.display = 'none';
                if (textEl) {
                    textEl.style.display = 'inline-flex';
                    textEl.textContent = brandName.toUpperCase();
                }
            } else {
                if (headWrap) headWrap.style.display = '';
                if (imageWrap) imageWrap.style.display = '';
                if (textEl) textEl.style.display = 'none';
                if (eyeL) eyeL.style.display = showEyes ? '' : 'none';
                if (eyeR) eyeR.style.display = showEyes ? '' : 'none';
            }
        },

        _brandingAssetFilenameFromUrl(url) {
            if (!url) return '';
            const m = url.match(/\/api\/settings\/branding\/assets\/([^?#]+)/);
            return m ? decodeURIComponent(m[1]) : '';
        },

        async saveBrandingSettings() {
            const status = document.getElementById('branding-save-status');
            if (status) status.textContent = 'Speichere…';
            try {
                const payload = {
                    brand_name: document.getElementById('branding-brand-name')?.value.trim() || 'Ninko',
                    page_title: document.getElementById('branding-page-title')?.value.trim() || 'Ninko',
                    logo_url: this._branding?.logo_url || '/static/images/logo_icon.png',
                    welcome_mode: document.getElementById('branding-welcome-mode')?.value || 'text',
                    welcome_title: document.getElementById('branding-welcome-title')?.value.trim() || 'Ninko',
                    welcome_text: document.getElementById('branding-welcome-text')?.value || '',
                    welcome_image_url: this._branding?.welcome_image_url || '/static/images/logo_dashboard_new.png?v=3',
                    welcome_show_eyes: this._branding?.welcome_show_eyes !== false,
                    show_quick_actions: false,
                    login_title: document.getElementById('branding-login-title')?.value.trim() || 'Ninko Login',
                    login_subtitle: document.getElementById('branding-login-subtitle')?.value.trim() || 'Please sign in with your admin account.',
                    login_help_url: document.getElementById('branding-login-help-url')?.value.trim() || 'https://github.com/natorus87/ninko/blob/main/DOCS.md',
                    login_head_mode: document.getElementById('branding-login-head-mode')?.value || 'image',
                    login_image_url: document.getElementById('branding-login-image-url')?.value.trim() || '/static/images/logo_dashboard_new.png?v=3',
                    login_show_eyes: !!document.getElementById('branding-login-show-eyes')?.checked,
                    login_background_style: document.getElementById('branding-login-background-style')?.value || 'aurora',
                    login_card_style: document.getElementById('branding-login-card-style')?.value || 'glass',
                };
                const res = await fetch('/api/settings/branding', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Fehler beim Speichern');
                }
                const data = await res.json();
                this._branding = { ...this._branding, ...(data || {}) };
                this.applyBranding();
                this.refreshBrandingPreviews();
                this.renderLoginLivePreview();
                if (status) status.textContent = 'Gespeichert';
                showNotification('Branding gespeichert', 'success');
            } catch (e) {
                if (status) status.textContent = 'Fehler';
                showNotification(e.message || 'Fehler beim Speichern', 'error');
            }
        },

        async resetBrandingSettings() {
            const status = document.getElementById('branding-save-status');
            if (status) status.textContent = 'Lade Defaults…';
            try {
                const res = await fetch('/api/settings/branding/reset', { method: 'POST' });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Reset fehlgeschlagen');
                }
                const data = await res.json();
                this._branding = { ...this._branding, ...(data || {}) };
                await this.loadBrandingForm();
                this.applyBranding();
                this.renderLoginLivePreview();
                if (status) status.textContent = 'Defaults geladen';
                showNotification('Branding auf Defaults gesetzt', 'info');
            } catch (e) {
                if (status) status.textContent = 'Fehler';
                showNotification(e.message || 'Reset fehlgeschlagen', 'error');
            }
        },

        async uploadBrandingAsset(kind) {
            const isLogo = kind === 'logo';
            const isLogin = kind === 'login';
            const fileInput = document.getElementById(
                isLogo ? 'branding-logo-file' : (isLogin ? 'branding-login-file' : 'branding-welcome-file')
            );
            const targetInput = document.getElementById(
                isLogo ? 'branding-logo-url' : (isLogin ? 'branding-login-image-url' : 'branding-welcome-image-url')
            );
            const status = document.getElementById('branding-save-status');
            if (!fileInput || !targetInput || !fileInput.files || fileInput.files.length === 0) {
                showNotification('Bitte zuerst eine Datei auswählen.', 'error');
                return;
            }
            const file = fileInput.files[0];
            const form = new FormData();
            form.append('file', file);
            if (status) status.textContent = 'Upload läuft…';
            try {
                const res = await fetch('/api/settings/branding/upload', {
                    method: 'POST',
                    body: form,
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || 'Upload fehlgeschlagen');
                }
                targetInput.value = data.url || '';
                this.refreshBrandingPreviews();
                this.renderLoginLivePreview();
                if (status) status.textContent = 'Upload OK';
                showNotification('Bild hochgeladen', 'success');
            } catch (e) {
                if (status) status.textContent = 'Upload-Fehler';
                showNotification(e.message || 'Upload fehlgeschlagen', 'error');
            }
        },

        async deleteBrandingAsset(kind) {
            const isLogo = kind === 'logo';
            const isLogin = kind === 'login';
            const targetInput = document.getElementById(
                isLogo ? 'branding-logo-url' : (isLogin ? 'branding-login-image-url' : 'branding-welcome-image-url')
            );
            const status = document.getElementById('branding-save-status');
            if (!targetInput) return;
            const url = targetInput.value.trim();
            const filename = this._brandingAssetFilenameFromUrl(url);
            if (!filename) {
                showNotification('Kein hochgeladenes Branding-Asset hinterlegt.', 'info');
                return;
            }

            if (status) status.textContent = 'Lösche Asset…';
            try {
                const res = await fetch(`/api/settings/branding/assets/${encodeURIComponent(filename)}`, { method: 'DELETE' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(data.detail || 'Löschen fehlgeschlagen');
                }
                targetInput.value = isLogo
                    ? '/static/images/logo_icon.png'
                    : (isLogin ? '/static/images/logo_dashboard_new.png?v=3' : '/static/images/logo_dashboard_new.png?v=3');
                this.refreshBrandingPreviews();
                this.renderLoginLivePreview();
                if (status) status.textContent = 'Asset gelöscht';
                showNotification('Branding-Asset gelöscht', 'success');
            } catch (e) {
                if (status) status.textContent = 'Fehler';
                showNotification(e.message || 'Löschen fehlgeschlagen', 'error');
            }
        },

        async generateBrandingLoginImage() {
            const prompt = document.getElementById('branding-login-gen-prompt')?.value?.trim() || '';
            const status = document.getElementById('branding-login-gen-status');
            const targetInput = document.getElementById('branding-login-image-url');
            if (!prompt) {
                if (status) status.textContent = 'Bitte Prompt eingeben';
                return;
            }
            if (status) status.textContent = 'Generiere…';
            try {
                const res = await fetch('/api/images/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt, size: '1024x1024' }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || 'Bildgenerierung fehlgeschlagen');
                if (targetInput && data.url) targetInput.value = data.url;
                this.refreshBrandingPreviews();
                this.renderLoginLivePreview();
                if (status) status.textContent = 'Bild generiert';
                showNotification('Login-Bild generiert', 'success');
            } catch (e) {
                if (status) status.textContent = 'Fehler';
                showNotification(e.message || 'Bildgenerierung fehlgeschlagen', 'error');
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, BrandingFeature);
    } else {
        window.BrandingFeature = BrandingFeature;
    }
})();
