/**
 * Ninko – Main Application JavaScript
 */

// --- i18n ---------------------------------------------
const I18n = {
    _translations: {},
    _lang: 'de',

    /**
     * Gibt den übersetzten String für `key` zurück.
     * Parameterersetzung: t('key', arg0, arg1) ersetzt {0}, {1} usw.
     */
    t(key, ...args) {
        let str = this._translations[key] ?? key;
        args.forEach((a, i) => { str = str.replaceAll(`{${i}}`, a); });
        return str;
    },

    /** Lädt die Sprachdatei und setzt alle data-i18n Attribute. */
    async load(lang) {
        try {
            const res = await fetch(`/static/i18n/${lang}.json?v=${Date.now()}`);
            if (!res.ok) throw new Error(`i18n ${lang} not found`);
            this._translations = await res.json();
            this._lang = lang;
        } catch {
            // Fallback auf Deutsch
            if (lang !== 'de') await this.load('de');
        }
        this._apply();
    },

    /** Setzt textContent aller [data-i18n] Elemente. */
    _apply() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.dataset.i18n;
            const val = this._translations[key];
            if (val !== undefined) el.textContent = val;
        });
        // Quick-Action-Nachrichten (data-i18n-msg → data-msg)
        document.querySelectorAll('[data-i18n-msg]').forEach(el => {
            const key = el.getAttribute('data-i18n-msg');
            const val = this._translations[key];
            if (val !== undefined) el.dataset.msg = val;
        });
        // Attribute (placeholder, title)
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const val = this._translations[el.dataset.i18nPlaceholder];
            if (val !== undefined) el.placeholder = val;
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const val = this._translations[el.dataset.i18nTitle];
            if (val !== undefined) el.title = val;
        });
        // HTML-Lang-Attribut
        document.documentElement.lang = this._lang;
        // Safeguard-Button-Titel nach Sprachwechsel aktualisieren
        if (typeof Ninko !== 'undefined') {
            Ninko._updateSafeguardBtn?.();
            // Re-render the bulk-update button so the count placeholder
            // ({0}) survives a live language switch.
            Ninko._updateBulkUpdateButton?.();
        }
    },
};

/** Globale Shorthand-Funktion */
function t(key, ...args) { return I18n.t(key, ...args); }
function tf(key, fallback, ...args) {
    const translated = I18n.t(key, ...args);
    return translated === key ? fallback : translated;
}

// ------------------------------------------------------

const Ninko = {
    ws: null,
    sessionId: null,
    modules: [],
    _moduleNavItems: [],
    _moduleFavorites: [],
    _moduleRecent: [],
    _moduleFilterQuery: '',
    activeTab: 'chat',
    moduleScripts: {},
    chatHistory: [],
    currentHistoryId: null,
    _abortController: null,
    _chatMessages: [], // [{id, role, text}] — spiegelt Redis-History wider
    _pluginTabs: {}, // Dynamisch registrierte Plugin-Tabs: { tabId: TabObject }
    _ttsAvailable: false,
    _ttsAudio: null,
    _ttsSpeakingMsgId: null,
    _safeguardEnabled: true,
    _safeguardPendingMessage: null,
    _confirmedPending: false,
    _forcedModule: null,
    _branding: {
        brand_name: 'Ninko',
        page_title: 'Ninko',
        logo_url: '/static/images/logo_icon.png',
        welcome_mode: 'text',
        welcome_title: 'Ninko',
        welcome_text: '',
        welcome_image_url: '/static/images/logo_dashboard_new.png?v=3',
        welcome_show_eyes: true,
        show_quick_actions: true,
        login_title: 'Ninko Login',
        login_subtitle: 'Please sign in with your admin account.',
        login_help_url: 'https://github.com/natorus87/ninko/blob/main/DOCS.md',
        login_head_mode: 'image',
        login_image_url: '/static/images/logo_dashboard_new.png?v=3',
        login_show_eyes: true,
        login_background_style: 'aurora',
        login_card_style: 'glass',
    },
    _themes: [],
    _activeThemeId: 'default',
    _activeThemeDefinition: null,
    _appliedThemeVars: [],
    _themeRepos: [],
    _rbacModules: [],
    _rbacRoles: [],
    _rbacGroups: [],
    _rbacUsers: [],
    _me: null,
    _sidebarAccountMenuOpen: false,
    t: tf,

    // --- SVG Icon Library (Lucide-style, currentColor) ---
    _ic: {
        // 14×14 – Action-Button Icons
        edit:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
        trash:   `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`,
        copy:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
        play:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
        pause:   `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
        list:    `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
        // 12×12 – Meta/Footer Icons
        cpu:     `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;opacity:.55"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`,
        layers:  `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;opacity:.55"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
        steps:   `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;opacity:.55"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
        clock:   `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;opacity:.55"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
        cron:    `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;opacity:.55"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
        // 15×15 – Workflow Canvas Node Icons
        zap:     `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
        bot:     `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>`,
        branch:  `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>`,
        loop:    `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
        box:     `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>`,
        stopci:  `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><rect x="9" y="9" width="6" height="6"/></svg>`,
        script:  `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
        // 18×18 – Run-Step Status Icons
        hourglass:`<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/></svg>`,
        loader:  `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:ic-spin .9s linear infinite"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`,
        check:   `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
        xcircle: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        skip:    `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`,
    },

    // --- Init ---
    async init() {
        console.log('Ninko: Initializing v1.0.1...');

        try {
            // Sprache laden (aus localStorage oder API)
            const savedLang = localStorage.getItem('ninko_lang') || 'de';
            await I18n.load(savedLang);

            // Sprache aus Backend übernehmen wenn noch keine lokale gespeichert
            if (!localStorage.getItem('ninko_lang')) {
                try {
                    const r = await fetch('/api/settings/language');
                    if (r.ok) {
                        const d = await r.json();
                        if (d.language && d.language !== savedLang) {
                            await I18n.load(d.language);
                            localStorage.setItem('ninko_lang', d.language);
                        }
                    }
                } catch (err) { console.warn('loadBranding failed, using defaults', err); }
            }

            // Auth-Guard: verhindert unautorisierte App-Initialisierung (auch bei /index.html Direktaufruf)
            const isAuthed = await this.ensureAuthenticated();
            if (!isAuthed) return;

            await this.loadBrandingSettings();
            this.applyBranding();

            this.switchTab('chat');

            document.addEventListener('change', (e) => {
                if (e.target.name === 'sched-type') {
                    this.toggleSchedType();
                }
            });
            this.sessionId = this.getSessionId();
            this.restoreTheme();
            this.loadBackgroundSettings();
            await this.loadActiveTheme();
            this.applyActiveThemeTokens();
            await this.loadHistory();

            // Initial chat state: centered (welcome message visible)
            this._setChatState('centered');

            // Modal Event-Handler (Cancel)
            document.getElementById('ninko-confirm-cancel')?.addEventListener('click', () => {
                this._confirmResolver?.(false);
                this._hideConfirm();
            });
            document.getElementById('ninko-confirm-ok')?.addEventListener('click', () => {
                this._confirmResolver?.(true);
                this._hideConfirm();
            });
            await this.loadModules();
            // After modules are loaded, try to restore the last route the user
            // was on before a reload (e.g. after a plugin update). Falls back
            // silently to the chat tab if nothing is stored.
            try { this._restoreRoute(); } catch (e) { console.warn('Route restore failed:', e); }
            this.connectWebSocket();
            this.autoResizeTextarea();
            this.initResizers();
            this.initSidebarTransitions();
            this.initScrollbarVisibility();
            this._checkTtsAvailable();
            this.initSafeguard();
            this._initCtxIndicator();
            this._bindCtxIndicatorAction();
            this.initSidebarAccountMenu();
            this.initMobileMenu();
            this.initChatPlusMenu();
            if (window.NinkoCommandPalette?.create) {
                this._commandPalette = window.NinkoCommandPalette.create(this);
                this._commandPalette.init();
            }
        } catch (err) {
            console.error('Ninko init failed:', err);
            this._showInitError(err);
        } finally {
            document.body.style.opacity = '1';
        }
    },

    _showInitError(err) {
        const message = (err && err.message) ? err.message : 'Unbekannter Initialisierungsfehler';
        const target = document.getElementById('main-content') || document.body;
        if (!target || document.getElementById('ninko-init-error')) return;
        const box = document.createElement('div');
        box.id = 'ninko-init-error';
        box.style.cssText = [
            'margin:16px',
            'padding:14px 16px',
            'border-radius:12px',
            'border:1px solid rgba(239,68,68,.35)',
            'background:rgba(127,29,29,.18)',
            'color:var(--text-primary, #fff)',
            'font-size:.95rem',
            'line-height:1.45'
        ].join(';');
        box.innerHTML = `
            <strong style="display:block;margin-bottom:6px;">Dashboard konnte nicht vollständig initialisiert werden.</strong>
            <div style="opacity:.92">Fehler: ${this._escapeHtml(String(message))}</div>
            <div style="margin-top:6px;opacity:.75">Browser-Konsole öffnen und Seite neu laden. Der Rest der Oberfläche bleibt sichtbar.</div>
        `;
        target.prepend(box);
    },

    async ensureAuthenticated() {
        try {
            const res = await fetch('/api/auth/me', { credentials: 'include' });
            if (!res.ok) return true; // API nicht erreichbar: App normal laden, damit Fehler sichtbar bleibt
            const me = await res.json();
            if (me.auth_enabled === false) {
                this._me = me;
                this._updateAuthUi(false);
                return true;
            }
            if (me.authenticated) {
                if (me.password_change_required) {
                    window.location.replace('/login');
                    return false;
                }
                this._me = me;
                this._updateAuthUi(true);
                return true;
            }
            this._me = null;
            this._updateAuthUi(false);
            window.location.replace('/login');
            return false;
        } catch {
            return true;
        }
    },

    _updateAuthUi(authenticated) {
        const btn = document.getElementById('btn-logout');
        if (btn) btn.style.display = authenticated ? 'inline-flex' : 'none';
        this._renderSidebarAccountInfo();
    },

    async logout() {
        this.closeSidebarUserMenu();
        try {
            await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
        } catch {
            // ignore network errors and force redirect anyway
        }
        window.location.replace('/login');
    },

    initSidebarAccountMenu() {
        if (this._sidebarAccountMenuInitialized) return;
        this._sidebarAccountMenuInitialized = true;
        document.addEventListener('click', (e) => {
            const wrap = document.getElementById('sidebar-account-wrap');
            if (!wrap) return;
            if (!this._sidebarAccountMenuOpen) return;
            if (!wrap.contains(e.target)) {
                this.closeSidebarUserMenu();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeSidebarUserMenu();
        });
        this._renderSidebarAccountInfo();
    },

    _renderSidebarAccountInfo() {
        const me = this._me || {};
        const usernameRaw = (me.username || 'admin').toString().trim();
        const username = usernameRaw || 'admin';
        const role = (me.role || 'admin').toString().trim().toLowerCase();
        const roleLabel = role === 'admin' ? 'Administrator' : (role === 'write' ? 'Operator' : 'Viewer');

        const avatar = document.getElementById('sidebar-account-avatar');
        const nameEl = document.getElementById('sidebar-account-name');
        const roleEl = document.getElementById('sidebar-account-plan');
        if (avatar) avatar.textContent = username.charAt(0).toUpperCase();
        if (nameEl) nameEl.textContent = username;
        if (roleEl) roleEl.textContent = roleLabel;
    },

    toggleSidebarUserMenu(event) {
        event?.stopPropagation();
        if (this._sidebarAccountMenuOpen) {
            this.closeSidebarUserMenu();
            return;
        }
        this._sidebarAccountMenuOpen = true;
        const wrap = document.getElementById('sidebar-account-wrap');
        const menu = document.getElementById('sidebar-account-menu');
        if (wrap) wrap.classList.add('menu-open');
        if (menu) menu.style.display = '';
    },

    closeSidebarUserMenu() {
        this._sidebarAccountMenuOpen = false;
        const wrap = document.getElementById('sidebar-account-wrap');
        const menu = document.getElementById('sidebar-account-menu');
        if (wrap) wrap.classList.remove('menu-open');
        if (menu) menu.style.display = 'none';
    },

    /**
     * Initialize mobile hamburger menu and sidebar toggle.
     * Handles sidebar open/close on screens <= 768px.
     */
    initMobileMenu() {
        const hamburgerBtn = document.getElementById('hamburger-btn');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');

        if (!hamburgerBtn || !sidebar || !overlay) return;

        // Toggle sidebar on hamburger button click
        hamburgerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('mobile-open');
            overlay.classList.toggle('mobile-open');
        });

        // Close sidebar when clicking on overlay
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('mobile-open');
        });

        // Close sidebar when clicking on any sidebar navigation item
        const navTabs = sidebar.querySelectorAll('.nav-tab');
        navTabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                if (window.innerWidth <= 768) {
                    sidebar.classList.remove('mobile-open');
                    overlay.classList.remove('mobile-open');
                }
            });
        });

        // Close sidebar when clicking outside of it on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 768 &&
                !sidebar.contains(e.target) &&
                !hamburgerBtn.contains(e.target)) {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('mobile-open');
            }
        });

        // Close sidebar on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                sidebar.classList.remove('mobile-open');
                overlay.classList.remove('mobile-open');
            }
        });
    },

    _updateMobileNav() {
        if (!this._mobileNavFrame) {
            this._mobileNavFrame = requestAnimationFrame(() => {
                const active = this.activeTab || 'chat';
                document.querySelectorAll('#mobile-nav .mobile-nav-item').forEach((btn) => {
                    btn.classList.toggle('active', btn.dataset.mobileTab === active);
                });
                this._mobileNavFrame = null;
            });
        }
    },

    _updateBreadcrumb() {
        const root = document.getElementById('app-breadcrumb');
        if (!root) return;
        const parts = ['Dashboard'];
        const tab = this.activeTab || 'chat';

        if (tab === 'chat') {
            parts.push('Chat');
        } else if (['automatisierung', 'scripting', 'modules'].includes(tab)) {
            parts.push('Automatisierung');
            const auto = document.querySelector('#subnav-automatisierung .settings-tab.active span')?.textContent?.trim();
            if (auto) parts.push(auto);
        } else if (tab === 'settings') {
            parts.push(t('nav.settings'));
            const set = document.querySelector('#subnav-settings .settings-tab.active span')?.textContent?.trim()
                || document.querySelector('#subnav-settings .settings-tab.active')?.textContent?.trim();
            if (set) parts.push(set.replace(/\s+/g, ' '));
        } else {
            parts.push(tab.charAt(0).toUpperCase() + tab.slice(1));
        }

        root.innerHTML = parts.map((label, idx) => {
            const cls = idx === parts.length - 1 ? 'crumb current' : 'crumb';
            return `<span class="${cls}">${this._escapeHtml(label)}</span>`;
        }).join('<span class="crumb-sep">/</span>');
    },

    openSettingsFromMenu() {
        this.closeSidebarUserMenu();
        this.switchTab('settings');
    },

    openLanguageFromMenu() {
        this.closeSidebarUserMenu();
        this.switchTab('settings');
        this.switchSettingsTab('language');
    },

    /**
     * Custom Confirm Promise.
     * @param {object} [opts] - Optional {okLabel, okVariant: 'danger'|'primary'}.
     *                          Defaults preserve the historical delete dialog.
     */
    confirm(message, title = 'Bestätigung', opts = {}) {
        return new Promise((resolve) => {
            const modal = document.getElementById('ninko-confirm-modal');
            const msgEl = document.getElementById('ninko-confirm-message');
            const titleEl = document.getElementById('ninko-confirm-title');
            const okBtn = document.getElementById('ninko-confirm-ok');

            if (msgEl) msgEl.innerText = message;
            if (titleEl) titleEl.innerText = title;
            if (okBtn) {
                okBtn.textContent = opts.okLabel || 'Löschen';
                const variant = opts.okVariant === 'primary' ? 'btn-primary' : 'btn-danger';
                okBtn.classList.remove('btn-primary', 'btn-danger');
                okBtn.classList.add(variant);
            }
            if (modal) {
                modal.style.display = 'flex';
                // Trigger animation
                requestAnimationFrame(() => {
                    modal.classList.add('active');
                });
            }

            this._confirmResolver = resolve;
        });
    },

    /** Hide Modal with animation */
    _hideConfirm() {
        const modal = document.getElementById('ninko-confirm-modal');
        if (modal) {
            modal.classList.remove('active');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 300);
        }
    },

    generateUUID() {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
            return crypto.randomUUID();
        }
        return 'sess-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9);
    },

    // SECURITY: Session ID wird in Memory gehalten, NICHT in sessionStorage (XSS-Protection)
    _sessionId: null,

    getSessionId() {
        if (!this._sessionId) {
            this._sessionId = this.generateUUID();
        }
        return this._sessionId;
    },

    // --- Modules ---
    async loadModules() {
        // Register click handlers for all primary nav tabs
        document.querySelectorAll('#nav-tabs-top .nav-tab[data-tab], #nav-tabs-bottom .nav-tab[data-tab]').forEach(tab => {
            const tabId = tab.dataset.tab;
            if (tabId) {
                tab.addEventListener('click', () => this.switchTab(tabId));
            }
        });

        try {
            const res = await fetch('/api/modules');
            if (!res.ok) throw new Error(res.statusText);
            this.modules = await res.json();

            const mainContent = document.getElementById('main-content');
            this._moduleNavItems = [];
            const modulesWithoutDashboardFiles = new Set(['image_gen', 'scripting']);

            for (const mod of this.modules) {
                if (!mod.enabled) continue;

                const tab = mod.dashboard_tab || {};
                const tabId = tab.id || mod.name;
                this._moduleNavItems.push({
                    moduleName: mod.name,
                    tabId,
                    label: tab.label || mod.display_name || mod.name,
                    icon: tab.icon || '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>',
                    category: this._moduleCategoryFor(mod.name),
                });

                // Tab Panel
                const panel = document.createElement('div');
                panel.id = `tab-${tabId}`;
                panel.className = 'tab-panel';

                const skipFrontendFetch = modulesWithoutDashboardFiles.has(mod.name);
                let hasFrontend = false;
                const setNoDashboard = () => {
                    const wrap = document.createElement('div');
                    wrap.className = 'module-tab-content';
                    const p = document.createElement('p');
                    p.className = 'empty-state';
                    p.textContent = t('module.noDashboard', mod.display_name);
                    wrap.appendChild(p);
                    panel.replaceChildren(wrap);
                };
                if (skipFrontendFetch) {
                    setNoDashboard();
                } else {
                    try {
                        const htmlRes = await fetch(`/api/modules/${mod.name}/frontend/tab.html`);
                        if (htmlRes.ok) {
                            const html = await htmlRes.text();
                            // Backend-Marker für "kein Dashboard": lokalisierten Empty-State
                            // rendern statt des sprachneutralen Fallback-HTMLs
                            if (html.includes('ninko:no-dashboard')) {
                                setNoDashboard();
                                mainContent.appendChild(panel);
                                continue;
                            }
                            panel.innerHTML = (typeof DOMPurify !== 'undefined')
                                ? DOMPurify.sanitize(html, {
                                    ADD_ATTR: ['target', 'rel'],
                                    FORBID_TAGS: ['script', 'iframe', 'style'],
                                    FORBID_ATTR: [
                                        'onclick',
                                        'onerror',
                                        'onload',
                                        'onmouseover',
                                        'onfocus',
                                        'onblur',
                                        'onchange',
                                        'onsubmit',
                                        'formaction',
                                    ],
                                    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/api\/)/i,
                                })
                                : '';
                            hasFrontend = true;
                        } else {
                            setNoDashboard();
                        }
                    } catch {
                        const wrap = document.createElement('div');
                        wrap.className = 'module-tab-content';
                        const p = document.createElement('p');
                        p.className = 'empty-state';
                        p.textContent = t('module.dashboardError');
                        wrap.appendChild(p);
                        panel.replaceChildren(wrap);
                    }
                }

                mainContent.appendChild(panel);

                // Load JS
                if (hasFrontend) {
                    try {
                        const script = document.createElement('script');
                        script.src = `/api/modules/${mod.name}/frontend/tab.js?v=${Date.now()}`;
                        script.type = 'text/javascript';
                        script.async = true;
                        document.body.appendChild(script);
                    } catch {
                        // JS optional
                    }
                }
            }
            this._loadModuleNavPrefs();
            this._renderModuleSidebar();
            this._buildModulePicker();
        } catch (err) {
            console.error('Module konnten nicht geladen werden:', err);
        }
    },

    _moduleCategoryFor(moduleName) {
        const name = String(moduleName || '').toLowerCase();
        const inSet = (items) => items.includes(name);

        if (inSet(['kubernetes', 'proxmox', 'docker', 'linux_server', 'hpe_ilo', 'lenovo_xclarity'])) return 'infrastructure';
        if (inSet(['pihole', 'opnsense', 'fritzbox', 'ubiquiti', 'mikrotik', 'cisco', 'netgear'])) return 'network';
        if (inSet(['checkmk', 'zabbix', 'dataviz'])) return 'monitoring';
        if (inSet(['glpi', 'jira', 'confluence', 'nextcloud', 'openproject', 'redmine'])) return 'productivity';
        if (inSet(['telegram', 'slack', 'discord', 'teams', 'email', 'message_hub'])) return 'communication';
        if (inSet(['github', 'gitlab', 'ionos', 'wordpress', 'netbox'])) return 'cloud';
        if (inSet(['homeassistant', 'tasmota', 'synology'])) return 'iot';
        return 'other';
    },

    _moduleCategoryLabel(category) {
        const known = ['infrastructure', 'network', 'monitoring', 'productivity', 'communication', 'cloud', 'iot', 'other'];
        const key = known.includes(category) ? category : 'other';
        return t('module.category.' + key);
    },

    _loadModuleNavPrefs() {
        try {
            const favRaw = localStorage.getItem('ninko_module_favorites');
            const recentRaw = localStorage.getItem('ninko_module_recent');
            const favParsed = JSON.parse(favRaw || '[]');
            const recentParsed = JSON.parse(recentRaw || '[]');
            const fav = Array.isArray(favParsed) ? favParsed : [];
            const recent = Array.isArray(recentParsed) ? recentParsed : [];
            const validIds = new Set(this._moduleNavItems.map((i) => i.tabId));
            this._moduleFavorites = fav.filter((id) => validIds.has(id));
            this._moduleRecent = recent.filter((id) => validIds.has(id)).slice(0, 5);
        } catch {
            this._moduleFavorites = [];
            this._moduleRecent = [];
        }
    },

    _saveModuleNavPrefs() {
        try {
            localStorage.setItem('ninko_module_favorites', JSON.stringify(this._moduleFavorites));
            localStorage.setItem('ninko_module_recent', JSON.stringify(this._moduleRecent.slice(0, 5)));
        } catch {
            // ignore localStorage errors
        }
    },

    /** Zentrierte Empty-State-Karte für Listen-Ansichten.
     *  actions: [{label, action, args?, primary?}] — nutzt das data-action-Dispatching. */
    _renderEmptyStateCard({ icon = '', title = '', hint = '', actions = [] }) {
        const buttons = actions.map((a) => `
            <button class="btn btn-sm ${a.primary ? 'btn-primary' : 'btn-outline'}"
                data-action="${this._escapeHtml(a.action)}"
                ${a.args !== undefined ? `data-args='${JSON.stringify(a.args)}'` : ''}>${this._escapeHtml(a.label)}</button>
        `).join('');
        return `
            <div class="empty-state-card">
                ${icon}
                <div class="empty-state-title">${this._escapeHtml(title)}</div>
                ${hint ? `<div class="empty-state-hint">${this._escapeHtml(hint)}</div>` : ''}
                ${buttons ? `<div class="empty-state-actions">${buttons}</div>` : ''}
            </div>
        `;
    },

    filterModuleSidebar(query) {
        this._moduleFilterQuery = String(query || '');
        this._renderModuleSidebar();
    },

    _toggleFavoriteModule(tabId) {
        const idx = this._moduleFavorites.indexOf(tabId);
        if (idx >= 0) this._moduleFavorites.splice(idx, 1);
        else this._moduleFavorites.push(tabId);
        this._saveModuleNavPrefs();
        this._renderModuleSidebar();
    },

    _recordRecentModule(tabId) {
        this._moduleRecent = [tabId, ...this._moduleRecent.filter((id) => id !== tabId)].slice(0, 5);
        this._saveModuleNavPrefs();
    },

    _renderModuleSidebar() {
        const list = document.getElementById('module-subnav-list');
        if (!list) return;

        const query = (this._moduleFilterQuery || '').trim().toLowerCase();
        const byId = new Map(this._moduleNavItems.map((it) => [it.tabId, it]));
        const matches = (item) => {
            if (!query) return true;
            const haystack = `${item.label} ${item.moduleName} ${item.category}`.toLowerCase();
            return haystack.includes(query);
        };

        const filtered = this._moduleNavItems.filter(matches);
        const filteredIds = new Set(filtered.map((i) => i.tabId));
        const favorites = this._moduleFavorites.map((id) => byId.get(id)).filter((i) => i && filteredIds.has(i.tabId));
        const recent = this._moduleRecent.map((id) => byId.get(id)).filter((i) => i && filteredIds.has(i.tabId));

        const groups = new Map();
        filtered.forEach((item) => {
            if (!groups.has(item.category)) groups.set(item.category, []);
            groups.get(item.category).push(item);
        });

        const order = ['infrastructure', 'network', 'monitoring', 'productivity', 'communication', 'cloud', 'iot', 'other'];

        const renderRow = (item) => {
            const isFavorite = this._moduleFavorites.includes(item.tabId);
            const active = this._activeModuleTab === item.tabId ? ' active' : '';
            return `
                <div class="module-nav-row">
                    <button class="settings-tab settings-tab-sub module-nav-btn${active}"${active ? ' aria-current="page"' : ''} data-module-tab="${this._escapeHtml(item.tabId)}">
                        ${item.icon}<span>${this._escapeHtml(item.label)}</span>
                    </button>
                    <button class="module-fav-btn${isFavorite ? ' is-favorite' : ''}" data-fav-tab="${this._escapeHtml(item.tabId)}" title="Favorit">
                        ★
                    </button>
                </div>
            `;
        };

        const parts = [];
        const renderedIds = new Set();
        const renderUniqueRows = (items) => items
            .filter((item) => item && !renderedIds.has(item.tabId))
            .map((item) => {
                renderedIds.add(item.tabId);
                return renderRow(item);
            });

        if (favorites.length) {
            parts.push(`<div class="module-nav-group-label">${t('module.group.favorites')}</div>`);
            parts.push(...renderUniqueRows(favorites));
        }
        if (recent.length) {
            parts.push(`<div class="module-nav-group-label">${t('module.group.recent')}</div>`);
            parts.push(...renderUniqueRows(recent));
        }
        order.forEach((category) => {
            const items = groups.get(category) || [];
            if (!items.length) return;
            const uniqueItems = items.filter((item) => !renderedIds.has(item.tabId));
            if (!uniqueItems.length) return;
            parts.push(`<div class="module-nav-group-label">${this._moduleCategoryLabel(category)}</div>`);
            parts.push(...renderUniqueRows(uniqueItems));
        });

        if (!parts.length) {
            parts.push(`<div class="module-subnav-empty">${t('module.noneFound')}</div>`);
        }

        list.innerHTML = parts.join('');

        list.querySelectorAll('.module-nav-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.moduleTab;
                if (id) this.switchModuleTab(id);
            });
        });

        list.querySelectorAll('.module-fav-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.dataset.favTab;
                if (id) this._toggleFavoriteModule(id);
            });
        });
    },

    _customAgentsCache: [],

    async _refreshCustomAgentsCache() {
        try {
            const res = await fetch('/api/agents/');
            if (!res.ok) return;
            const data = await res.json();
            this._customAgentsCache = (data.agents || []).filter(a => a.enabled);
        } catch (err) { console.warn('loadCustomAgents failed', err); }
    },

    _buildModulePicker() {
        const dropdown = document.getElementById('module-picker-dropdown');
        if (!dropdown) return;
        const enabledMods = this.modules.filter(m => m.enabled);
        const autoLabel = t('chat.moduleAuto');
        const items = [
            `<button class="module-picker-item${this._forcedModule === null ? ' selected' : ''}" data-action="setForcedModule" data-args='[null]'>
                ${autoLabel}
            </button>`,
            enabledMods.length ? '<div class="module-picker-divider"></div>' : '',
            ...enabledMods.map(m => {
                const icon = m.dashboard_tab?.icon || '';
                const label = m.display_name || m.name;
                return `<button class="module-picker-item${this._forcedModule === m.name ? ' selected' : ''}" data-action="setForcedModule" data-args="${JSON.stringify([m.name]).replace(/\"/g, '&quot;')}">
                    ${icon ? icon + ' ' : ''}${label}
                </button>`;
            }),
        ];
        // Custom Agents Sektion
        if (this._customAgentsCache.length) {
            items.push('<div class="module-picker-divider"></div>');
            items.push('<div style="padding:0.25rem 0.75rem;font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;">Meine Agenten</div>');
            this._customAgentsCache.forEach(a => {
                items.push(`<button class="module-picker-item${this._forcedModule === a.id ? ' selected' : ''}" data-action="setForcedModule" data-args="${JSON.stringify([a.id, a.name]).replace(/\"/g, '&quot;')}">
                    🤖 ${this._escapeHtml(a.name)}
                </button>`);
            });
        }
        dropdown.innerHTML = items.join('');
    },

    toggleModulePicker(event) {
        event.stopPropagation();
        const picker = document.getElementById('module-picker');
        const dropdown = document.getElementById('module-picker-dropdown');
        if (!dropdown) return;
        const isOpen = dropdown.style.display !== 'none';
        if (isOpen) {
            dropdown.style.display = 'none';
            picker.classList.remove('open');
        } else {
            dropdown.style.display = 'block';
            picker.classList.add('open');
            const close = (e) => {
                if (!picker.contains(e.target)) {
                    dropdown.style.display = 'none';
                    picker.classList.remove('open');
                    document.removeEventListener('click', close);
                }
            };
            setTimeout(() => document.addEventListener('click', close), 0);
        }
    },

    setForcedModule(name, customLabel) {
        this._forcedModule = name;
        const btn = document.getElementById('module-picker-btn');
        const label = document.getElementById('module-picker-label');
        if (name === null) {
            label.textContent = t('chat.moduleAuto');
            btn.classList.remove('active');
        } else {
            const mod = this.modules.find(m => m.name === name);
            // Modul-Agent → display_name; Custom Agent → customLabel übergeben
            label.textContent = mod ? (mod.display_name || name) : (customLabel || name);
            btn.classList.add('active');
        }
        this._buildModulePicker();
        const dropdown = document.getElementById('module-picker-dropdown');
        const picker = document.getElementById('module-picker');
        if (dropdown) dropdown.style.display = 'none';
        if (picker) picker.classList.remove('open');
    },

    initSidebarTransitions() {
        // Slide panels removed — Automatisierung and Modules are now full tab panels
    },


    // --- Route Persistence ---
    // Saves the current view (main tab + sub-tab) to sessionStorage so a
    // page reload (e.g. after a plugin update) can restore it instead of
    // dropping the user back on the dashboard.
    _ROUTE_STORAGE_KEY: 'ninko_last_route',

    _persistRoute() {
        try {
            const route = {
                tab: this.activeTab || null,
                settingsTab: document.querySelector('#subnav-settings .settings-tab.active[data-settings-tab]')?.dataset.settingsTab || null,
                moduleTab: this._activeModuleTab || null,
                autoTab: this._activeAutoTab || null,
            };
            sessionStorage.setItem(this._ROUTE_STORAGE_KEY, JSON.stringify(route));
        } catch (_) {
            // sessionStorage may be unavailable (private mode, etc.) — ignore.
        }
    },

    _readPersistedRoute() {
        try {
            const raw = sessionStorage.getItem(this._ROUTE_STORAGE_KEY);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (_) {
            return null;
        }
    },

    _isValidRouteId(value) {
        // Tab IDs are simple slugs (a-z, 0-9, dash, underscore). Reject anything
        // else to prevent tampered sessionStorage values from breaking CSS
        // selectors downstream (`[data-tab="..."]`).
        return typeof value === 'string' && value.length > 0 && value.length <= 64 && /^[a-zA-Z0-9_-]+$/.test(value);
    },

    _domHasTab(tabId) {
        return !!document.getElementById(`tab-${tabId}`);
    },

    _domHasSettingsTab(tabId) {
        return !!document.querySelector(`#subnav-settings .settings-tab[data-settings-tab="${tabId}"]`);
    },

    _domHasAutoTab(tabId) {
        if (tabId === 'skills') return !!document.getElementById('tab-agents');
        return this._domHasTab(tabId);
    },

    _restoreRoute() {
        const route = this._readPersistedRoute();
        if (!route || !this._isValidRouteId(route.tab) || route.tab === 'chat') return false;

        if (!this._domHasTab(route.tab)) {
            sessionStorage.removeItem(this._ROUTE_STORAGE_KEY);
            return false;
        }

        this.switchTab(route.tab);

        if (route.tab === 'settings' && this._isValidRouteId(route.settingsTab) && this._domHasSettingsTab(route.settingsTab)) {
            this.switchSettingsTab(route.settingsTab);
        }
        if (route.tab === 'modules' && this._isValidRouteId(route.moduleTab) && this._domHasTab(route.moduleTab)) {
            this.switchModuleTab(route.moduleTab);
        }
        if (route.tab === 'automatisierung' && this._isValidRouteId(route.autoTab) && this._domHasAutoTab(route.autoTab)) {
            this.switchAutoTab(route.autoTab);
        }
        return true;
    },

    // --- Tab Switching ---
    switchTab(tabId) {
        // Redirect tasks/agents/workflows through the automatisierung tab
        if (['tasks', 'agents', 'skills', 'workflows'].includes(tabId)) {
            if (this.activeTab !== 'automatisierung') {
                this._doSwitchTab('automatisierung');
            }
            this.switchAutoTab(tabId);
            return;
        }
        this._doSwitchTab(tabId);
    },

    openSidebarPanel(panelId) {
        const panels = document.getElementById('sidebar-panels');
        if (!panels) return;
        panels.classList.remove('show-automatisierung', 'show-secondary');
        if (panelId === 'automatisierung') panels.classList.add('show-automatisierung');
        if (panelId === 'secondary') panels.classList.add('show-secondary');
    },

    _doSwitchTab(tabId) {
        const automationTabs = ['automatisierung', 'scripting', 'modules'];

        // Deactivate all nav tabs and tab panels
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

        // Stop log polling when leaving settings
        if (this.activeTab === 'settings' && tabId !== 'settings') {
            this.stopLogPolling();
        }
        // Stop workflows run-refresh timer when leaving automatisierung while on workflows
        if (this.activeTab === 'automatisierung' && this._activeAutoTab === 'workflows') {
            clearInterval(this._wfRunRefreshTimer);
        }

        // Activate new nav tab and panel
        const activeNavTabId = automationTabs.includes(tabId) ? 'automatisierung' : tabId;
        document.querySelector(`.nav-tab[data-tab="${activeNavTabId}"]`)?.classList.add('active');
        const panel = document.getElementById(`tab-${tabId}`);
        if (panel) panel.classList.add('active');

        this.activeTab = tabId;

        // Show/hide sidebar history section (only in chat tab)
        const historySection = document.getElementById('sidebar-history-section');
        if (historySection) {
            historySection.style.display = tabId === 'chat' ? '' : 'none';
        }

        // Show/hide sidebar sub-navigation for automatisierung / modules / settings
        const settingsSubnav = document.getElementById('sidebar-settings-subnav');
        const settingsSection = document.getElementById('subnav-settings');
        if (settingsSubnav) {
            settingsSubnav.style.display = tabId === 'settings' ? '' : 'none';
        }
        if (settingsSection) {
            settingsSection.style.display = tabId === 'settings' ? '' : 'none';
        }

        if (tabId === 'modules') this.openSidebarPanel('secondary');
        else if (automationTabs.includes(tabId)) this.openSidebarPanel('automatisierung');
        else this.openSidebarPanel('primary');

        const navTop = document.getElementById('nav-tabs-top');
        const navBottom = document.getElementById('nav-tabs-bottom');
        const navBack = document.getElementById('nav-tabs-back');
        if (navTop && navBottom && navBack) {
            if (tabId === 'settings') {
                navTop.style.display = 'none';
                navBottom.style.display = 'none';
                navBack.style.display = '';
            } else {
                navTop.style.display = '';
                navBottom.style.display = '';
                navBack.style.display = 'none';
            }
        }

        // Tab-specific init
        if (tabId === 'automatisierung') {
            // Show last active sub-tab, default to tasks
            this.switchAutoTab(this._activeAutoTab || 'tasks');
        }
        if (['scripting', 'modules'].includes(tabId)) {
            this._setAutomationSubnavActive(tabId);
        }
        if (tabId === 'modules') {
            // Re-show active module panel, or select first module
            if (this._activeModuleTab) {
                this.switchModuleTab(this._activeModuleTab);
            } else if (this.modules?.length) {
                const first = this.modules.find(m => m.enabled);
                if (first) this.switchModuleTab((first.dashboard_tab?.id) || first.name);
            }
        }
        if (tabId === 'scripting' && typeof this.loadScripts === 'function') {
            this.loadScripts();
        }
        if (tabId === 'logs') this.startLogPolling();
        if (tabId === 'settings') this.loadSettingsContent();

        // Init module tab if navigated directly (e.g. from chat toolbar)
        const tabObj = this.getTabObject(tabId);
        if (tabObj && typeof tabObj.init === 'function' && !tabObj._initialized) {
            tabObj.init();
            tabObj._initialized = true;
        }
        this._updateMobileNav();
        this._updateBreadcrumb();
        this._persistRoute();
    },

    // --- Automatisierung Sub-Tab Switching ---
    switchAutoTab(tabId) {
        this.openSidebarPanel('automatisierung');
        const panelTabId = tabId === 'skills' ? 'agents' : tabId;

        // Ensure the automatisierung parent panel is active (e.g. when coming from scripting/modules)
        const autoPanel = document.getElementById('tab-automatisierung');
        if (autoPanel && !autoPanel.classList.contains('active')) {
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            autoPanel.classList.add('active');
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelector('.nav-tab[data-tab="automatisierung"]')?.classList.add('active');
            this.activeTab = 'automatisierung';
        }

        // Stop workflows timer when leaving workflows sub-tab
        if (this._activeAutoTab === 'workflows' && tabId !== 'workflows') {
            clearInterval(this._wfRunRefreshTimer);
        }

        // Restore previous panel back to main-content (hidden)
        if (this._activeAutoTab && this._activeAutoTab !== tabId) {
            const prevTabId = this._activeAutoTab === 'skills' ? 'agents' : this._activeAutoTab;
            const prev = document.getElementById(`tab-${prevTabId}`);
            if (prev) {
                document.getElementById('main-content')?.appendChild(prev);
                prev.classList.remove('active');
            }
        }

        // Update sidebar active state
        this._setAutomationSubnavActive(tabId);

        // Move panel into auto-content and activate
        const autoContent = document.getElementById('auto-content');
        const panel = document.getElementById(`tab-${panelTabId}`);
        if (autoContent && panel) {
            autoContent.appendChild(panel);
            panel.classList.add('active');
        }

        this._activeAutoTab = tabId;

        // Load content
        if (tabId === 'tasks') this.loadScheduledTasks();
        if (tabId === 'agents') {
            if (typeof this._showOnlyPanel === 'function') this._showOnlyPanel('agenten-overview');
            this.loadAgents();
        }
        if (tabId === 'skills') {
            if (typeof this._showOnlyPanel === 'function') this._showOnlyPanel('agenten-skills');
            if (typeof this.switchSkillTab === 'function') this.switchSkillTab('installed');
            if (typeof this.loadSkillsList === 'function') this.loadSkillsList();
        }
        if (tabId === 'workflows') this.loadWorkflows();
        this._updateBreadcrumb();
        this._persistRoute();
    },

    _setAutomationSubnavActive(tabId) {
        document.querySelectorAll('#subnav-automatisierung .settings-tab').forEach(t => {
            t.classList.remove('active');
            t.removeAttribute('aria-current');
        });
        const btn = document.querySelector(
            `#subnav-automatisierung .settings-tab[data-auto-tab="${tabId}"], ` +
            `#subnav-automatisierung .settings-tab[data-auto-link="${tabId}"]`
        );
        btn?.classList.add('active');
        btn?.setAttribute('aria-current', 'page');
    },

    // --- Module Sub-Tab Switching ---
    switchModuleTab(tabId) {
        this.openSidebarPanel('secondary');

        // Restore previous module panel back to main-content
        if (this._activeModuleTab && this._activeModuleTab !== tabId) {
            const prev = document.getElementById(`tab-${this._activeModuleTab}`);
            if (prev) {
                document.getElementById('main-content')?.appendChild(prev);
                prev.classList.remove('active');
            }
        }

        // Update sidebar active state
        document.querySelectorAll('#subnav-modules .module-nav-btn').forEach(t => t.classList.remove('active'));
        document.querySelector(`#subnav-modules .module-nav-btn[data-module-tab="${tabId}"]`)?.classList.add('active');

        // Move panel into modules-content and activate
        const modContent = document.getElementById('modules-content');
        const panel = document.getElementById(`tab-${tabId}`);
        if (modContent && panel) {
            modContent.appendChild(panel);
            panel.classList.add('active');
        }

        this._activeModuleTab = tabId;
        this._recordRecentModule(tabId);
        this._renderModuleSidebar();

        // Legacy compatibility: some module tabs read #connection-selector.
        // Ensure it is populated before module init runs.
        this._syncLegacyConnectionSelector(tabId).finally(() => {
            const tabObj = this.getTabObject(tabId);
            if (tabObj && typeof tabObj.init === 'function' && !tabObj._initialized) {
                tabObj.init();
                tabObj._initialized = true;
            }
        });
        this._updateBreadcrumb();
        this._persistRoute();
    },

    _normalizeConnectionModuleName(tabId) {
        if (tabId === 'k8s') return 'kubernetes';
        return tabId;
    },

    _usesLegacyConnectionSelector(tabId) {
        const moduleName = this._normalizeConnectionModuleName(tabId);
        const coreModulesWithoutConnections = new Set([
            'agent_browser',
            'codelab',
            'dataviz',
            'image_gen',
            'knowledge_graph',
            'message_hub',
            'network_analysis',
            'scripting',
            'web_search',
        ]);
        return !coreModulesWithoutConnections.has(moduleName);
    },

    async _syncLegacyConnectionSelector(tabId) {
        const wrap = document.getElementById('legacy-connection-bar');
        const select = document.getElementById('connection-selector');
        if (!select) return;

        const moduleName = this._normalizeConnectionModuleName(tabId);
        if (!this._usesLegacyConnectionSelector(moduleName)) {
            select.innerHTML = '';
            select.value = '';
            select.disabled = true;
            wrap?.classList.add('hidden');
            return;
        }

        try {
            const res = await fetch(`/api/connections/${moduleName}?_t=${Date.now()}`, { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const connections = data.connections || [];

            if (!connections.length) {
                select.innerHTML = '<option value="">Keine Verbindung</option>';
                select.value = '';
                select.disabled = true;
                wrap?.classList.remove('hidden');
                return;
            }

            select.innerHTML = connections
                .map((c) => `<option value="${this._escapeHtml(c.id)}">${this._escapeHtml(c.name)} (${this._escapeHtml(c.environment || '')})</option>`)
                .join('');
            const defaultConn = connections.find((c) => c.is_default) || connections[0];
            select.value = defaultConn?.id || '';
            select.disabled = false;
            wrap?.classList.remove('hidden');

            // Notify tabs that subscribe to connection selector changes.
            select.dispatchEvent(new Event('change', { bubbles: true }));
        } catch (e) {
            console.warn(`Legacy connection selector sync failed for ${moduleName}:`, e);
            select.innerHTML = '<option value="">Verbindung nicht ladbar</option>';
            select.value = '';
            select.disabled = true;
            wrap?.classList.remove('hidden');
        }
    },

    getTabObject(tabId) {
        const map = {
            'k8s': typeof K8sTab !== 'undefined' ? K8sTab : null,
            'kubernetes': typeof K8sTab !== 'undefined' ? K8sTab : null,
            'proxmox': typeof ProxmoxTab !== 'undefined' ? ProxmoxTab : null,
            'glpi': typeof GlpiTab !== 'undefined' ? GlpiTab : null,
            'pihole': typeof PiholeTab !== 'undefined' ? PiholeTab : null,
            'ionos': typeof IonosTab !== 'undefined' ? IonosTab : null,
            'fritzbox': typeof fritzboxApp !== 'undefined' ? fritzboxApp : null,
            'homeassistant': null,  // Homeassistant script is an IIFE block
            'telegram': typeof TelegramModule !== 'undefined' ? TelegramModule : null,
            'teams': typeof TeamsTab !== 'undefined' ? TeamsTab : null,
            'web_search': typeof WebSearchTab !== 'undefined' ? WebSearchTab : null,
            'codelab': typeof CodelabTab !== 'undefined' ? CodelabTab : null,
            'docker': typeof DockerTab !== 'undefined' ? DockerTab : null,
            'linux_server': typeof LinuxServerTab !== 'undefined' ? LinuxServerTab : null,
            'wordpress': typeof WordPressTab !== 'undefined' ? WordPressTab : null,
            'qdrant': typeof QdrantTab !== 'undefined' ? QdrantTab : null,
            'tasmota': typeof TasmotaTab !== 'undefined' ? TasmotaTab : null,
            'opnsense': typeof OPNsenseTab !== 'undefined' ? OPNsenseTab : null,
            'checkmk': typeof CheckmkTab !== 'undefined' ? CheckmkTab : null,
            'dataviz': typeof DataVizTab !== 'undefined' ? DataVizTab : null,
            'message_hub': typeof MessageHubTab !== 'undefined' ? MessageHubTab : null,
        };
        // Fallback: dynamisch registrierte Plugin-Tabs (via Ninko._pluginTabs)
        return map[tabId] || this._pluginTabs[tabId] || null;
    },

    // --- Chat ---
    _setChatBusy(busy) {
        const btnSend = document.getElementById('btn-send');
        const input = document.getElementById('chat-input');
        if (btnSend) {
            btnSend.classList.toggle('is-stop', busy);
            const iconSend = btnSend.querySelector('.icon-send');
            const iconStop = btnSend.querySelector('.icon-stop');
            if (iconSend) iconSend.style.display = busy ? 'none' : '';
            if (iconStop) iconStop.style.display = busy ? '' : 'none';
            btnSend.title = busy ? 'Antwort abbrechen' : 'Senden';
        }
        if (input) input.disabled = busy;
    },

    _setChatState(state) {
        const cc = document.querySelector('.chat-container');
        if (!cc) return;
        cc.classList.remove('chat-centered', 'chat-active');
        cc.classList.add(state === 'centered' ? 'chat-centered' : 'chat-active');
    },

    handleSendOrStop() {
        if (this._abortController) {
            this.stopMessage();
        } else {
            this.sendMessage();
        }
    },

    stopMessage() {
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
    },

    initChatPlusMenu() {
        if (this._chatPlusMenuInitialized) return;
        this._chatPlusMenuInitialized = true;
        document.addEventListener('click', (e) => {
            const wrap = document.getElementById('chat-plus-menu');
            if (!wrap || !wrap.contains(e.target)) this.closeChatPlusMenu();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeChatPlusMenu();
        });
    },

    toggleChatPlusMenu(event) {
        event?.stopPropagation();
        const wrap = document.getElementById('chat-plus-menu');
        const menu = document.getElementById('chat-plus-dropdown');
        if (!wrap || !menu) return;
        const isOpen = menu.style.display !== 'none';
        if (isOpen) {
            this.closeChatPlusMenu();
            return;
        }
        menu.style.display = 'block';
        wrap.classList.add('open');
        // Aufklapprichtung dynamisch: nach oben, wenn unter dem Trigger nicht genug Platz ist
        // (z.B. wenn die Chatbox bei laufendem Chat am unteren Viewport-Rand sitzt).
        const trigger = document.getElementById('chat-plus-trigger') || wrap;
        const rect = trigger.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        const needed = menu.offsetHeight + 16;
        wrap.classList.toggle('drop-up', spaceBelow < needed && rect.top > spaceBelow);
    },

    closeChatPlusMenu() {
        const wrap = document.getElementById('chat-plus-menu');
        const menu = document.getElementById('chat-plus-dropdown');
        if (menu) menu.style.display = 'none';
        if (wrap) wrap.classList.remove('open', 'drop-up');
    },

    // --- Spracheingabe ---
    _mediaRecorder: null,
    _audioChunks: [],
    _isRecording: false,
    _MIC_SVG: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>',
    _STOP_SVG: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>',

    async toggleRecording() {
        if (this._isRecording) {
            this._stopRecording();
        } else {
            await this._startRecording();
        }
    },

    async _startRecording() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            const isInsecure = location.protocol !== 'https:' && location.hostname !== 'localhost';
            if (isInsecure) {
                alert('Mikrofon-Zugriff erfordert HTTPS.\n\nQuick-Fix in Chrome:\nchrome://flags/#unsafely-treat-insecure-origin-as-secure\n→ ' + location.origin + ' eintragen → Relaunch');
            } else {
                alert('Mikrofon-Zugriff wird von diesem Browser nicht unterstützt.');
            }
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this._audioChunks = [];

            // WebM bevorzugen, OGG als Fallback
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
                    ? 'audio/ogg;codecs=opus'
                    : '';

            this._mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
            this._mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) this._audioChunks.push(e.data);
            };
            this._mediaRecorder.onstop = () => this._transcribeRecording();
            this._mediaRecorder.start();
            this._isRecording = true;

            const btn = document.getElementById('btn-mic');
            if (btn) {
                btn.classList.add('recording');
                btn.title = 'Aufnahme beenden';
                btn.querySelector('.mic-icon').innerHTML = this._STOP_SVG;
            }
        } catch (err) {
            alert('Mikrofon-Zugriff verweigert: ' + err.message);
        }
    },

    _stopRecording() {
        if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
            this._mediaRecorder.stop();
            this._mediaRecorder.stream.getTracks().forEach((t) => t.stop());
        }
        this._isRecording = false;

        const btn = document.getElementById('btn-mic');
        if (btn) {
            btn.classList.remove('recording');
            btn.classList.add('processing');
            btn.title = 'Transkribiere…';
            btn.querySelector('.mic-icon').innerHTML = '<span class="mic-spinner"></span>';
        }
    },

    async _transcribeRecording() {
        const mimeType = (this._mediaRecorder && this._mediaRecorder.mimeType) || 'audio/webm';
        const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
        const blob = new Blob(this._audioChunks, { type: mimeType });
        this._audioChunks = [];

        const btn = document.getElementById('btn-mic');
        try {
            const formData = new FormData();
            formData.append('file', blob, `recording.${ext}`);

            const res = await fetch('/api/transcription/', { method: 'POST', body: formData });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || res.statusText);
            }
            const data = await res.json();
            const input = document.getElementById('chat-input');
            if (input) {
                input.value = data.text;
                input.focus();
                // Höhe automatisch anpassen
                input.style.height = 'auto';
                input.style.height = input.scrollHeight + 'px';
            }
        } catch (err) {
            this.addChatMessage('ai', 'Transkription fehlgeschlagen: ' + err.message);
        } finally {
            if (btn) {
                btn.classList.remove('processing');
                btn.title = 'Spracheingabe';
                btn.querySelector('.mic-icon').innerHTML = this._MIC_SVG;
            }
        }
    },

    async sendMessage() {
        const input = document.getElementById('chat-input');
        const text = input.value.trim();
        if (!text) return;

        const isConfirmation = this._confirmedPending;

        input.value = '';
        if (!isConfirmation) {
            this.addChatMessage('user', text);
        }
        this.showTyping();
        this._setChatBusy(true);

        // Snapshot der Identifiers ZUM START des Requests. Wenn der User
        // während des laufenden Requests auf einen anderen Chat wechselt,
        // nutzen wir diese gemerkten Werte, damit _saveToHistory nicht in
        // den falschen Chat speichert (Race-Condition-Bug).
        const _reqHistoryId = this.currentHistoryId;
        const _reqSessionId = this.sessionId;

        // AbortController für Stop-Funktion
        this._abortController = new AbortController();

        // History-Eintrag sofort anlegen (vor API-Call)
        if (!this.currentHistoryId) {
            this.currentHistoryId = Date.now().toString();
        }
        this._ensureHistoryEntry(text);

        const useStreaming = localStorage.getItem('ninko_streaming') === 'true';

        // SSE-Stream für Live-Status öffnen (vor dem POST)
        let evtSource = null;
        try {
            evtSource = new EventSource(`/api/chat/stream?session_id=${encodeURIComponent(this.sessionId)}`);
            evtSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === 'status') {
                        this.updateTypingStatus(data.text);
                    } else if (data.type === 'tool_start' || data.type === 'tool_end') {
                        this.handleToolEvent(data);
                    } else if (data.type === 'trace_event') {
                        this._handleTraceEvent(data);
                    } else if (data.type === 'thinking_content') {
                        this._handleThinkingContent(data.text);
                    } else if (data.type === 'subagent_step') {
                        this._handleSubagentStepSSE(data);
                    } else if (data.type === 'done') {
                        evtSource.close();
                        evtSource = null;
                    }
                } catch (_) { /* ignore parse errors */ }
            };
            evtSource.onerror = () => { evtSource?.close(); evtSource = null; };
        } catch (_) { /* SSE nicht verfügbar – trotzdem fortfahren */ }

        try {
            const confirmedNow = this._confirmedPending;
            this._confirmedPending = false;

            const res = await fetch('/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: useStreaming ? 'text/event-stream' : 'application/json' },
                body: JSON.stringify({ message: text, session_id: this.sessionId, confirmed: confirmedNow, ...(this._forcedModule ? { force_module: this._forcedModule } : {}) }),
                signal: this._abortController.signal,
            });

            if (useStreaming && res.ok && res.headers.get('content-type')?.includes('text/event-stream')) {
                // Status-SSE und Typing-Bubble bleiben absichtlich offen — der
                // Streaming-Pfad schliesst sie via finalizeBubble() am Ende.
                await this._streamResponse(text, res, _reqHistoryId);
                evtSource?.close();
                this._abortController = null;
                this._setChatBusy(false);
                return;
            }

            evtSource?.close();
            this.hideTyping();

            if (res.ok) {
                const data = await res.json();
                this.addChatMessage('ai', data.response);

                if (
                    data.routing_confidence !== null &&
                    data.routing_confidence !== undefined &&
                    data.routing_confidence < 0.7
                ) {
                    const pct = Math.round(data.routing_confidence * 100);
                    this.addChatMeta(`⚠️ Unsicheres Routing (${pct} % Konfidenz) – Modul-Zuweisung könnte ungenau sein.`);
                }

                if (data.confirmation_required && data.safeguard) {
                    this._safeguardPendingMessage = text;
                    this._showSafeguardConfirmPrompt(data.safeguard);
                }

                // Auto-mode: show inline badge when autonomously allowed
                if (data.safeguard?.auto_decided && data.safeguard?.auto_decision === 'allow') {
                    this.addChatMeta(`⚡ ${t('safeguard.autoAllowed')}`);
                }

                if (data.compacted) {
                    this.addCompactionNotice();
                    // Context-Ring kurz aufblitzen lassen (zeigt Reset an)
                    const ctxEl = document.getElementById('ctx-indicator');
                    if (ctxEl) {
                        ctxEl.classList.remove('ctx-flash');
                        void ctxEl.offsetWidth; // reflow für CSS-Animation-Neustart
                        ctxEl.classList.add('ctx-flash');
                        setTimeout(() => ctxEl.classList.remove('ctx-flash'), 1000);
                    }
                }

                if (data.context_budget) {
                    this._updateCtxIndicator(data.context_budget);
                }

                // Save conversation to localStorage history.
                // _reqHistoryId ist der Snapshot zum Zeitpunkt des Requests,
                // um Race-Conditions bei schnellem Chat-Switching zu vermeiden.
                this._saveToHistory(text, data.response, _reqHistoryId);
            } else {
                this.addChatMessage('ai', t('chat.errorProcessing'));
            }
        } catch (err) {
            evtSource?.close();
            this.hideTyping();
            if (err.name !== 'AbortError') {
                this.addChatMessage('ai', t('chat.errorConnection'));
            }
        } finally {
            this._abortController = null;
            this._setChatBusy(false);
        }
    },

    _emojiForTitle(text) {
        const t = text.toLowerCase();
        const map = [
            [/kubernetes|k8s|pod|cluster|deploy|namespace/i, '☸️'],
            [/vm|proxmox|virtuelle maschine/i, '🖥️'],
            [/dns|pihole|pi-hole|domain/i, '🌐'],
            [/email|mail|smtp|sende.*mail/i, '📧'],
            [/ticket|glpi|helpdesk|issue/i, '🎫'],
            [/docker|container|image/i, '🐳'],
            [/netzwerk|network|fritz|router|ip.adress/i, '🔌'],
            [/home.?assistant|smarthome|smart home|automation/i, '🏠'],
            [/suche|search|web|internet|aktuell/i, '🔍'],
            [/telegram|teams|nachricht|sende.*message/i, '💬'],
            [/fehler|error|fail|kaputt|crash/i, '⚠️'],
            [/backup|sicherung/i, '💾'],
            [/update|upgrade|patch/i, '🔄'],
            [/status|health|check|monitor/i, '📊'],
            [/speicher|storage|disk|festplatte/i, '💿'],
            [/security|sicherheit|firewall|vpn/i, '🔒'],
            [/user|nutzer|benutzer|account|passwort/i, '👤'],
            [/log|protokoll/i, '📋'],
            [/workflow|pipeline|automatisier/i, '⚙️'],
        ];
        for (const [pattern, emoji] of map) {
            if (pattern.test(t)) return emoji + ' ';
        }
        return '💬 ';
    },

    _ensureHistoryEntry(userMsg) {
        // Erstellt den History-Eintrag sofort beim Absenden (ohne AI-Antwort)
        const existing = this.chatHistory.find(h => h.id === this.currentHistoryId);
        if (existing) return; // Bereits vorhanden (laufende Session)

        const emoji = this._emojiForTitle(userMsg);
        const conversation = {
            id: this.currentHistoryId,
            title: emoji + userMsg.slice(0, 48),
            sessionId: this.sessionId,
            messages: [],
            createdAt: Date.now(),
            updatedAt: Date.now(),
        };
        this.chatHistory.unshift(conversation);
        if (this.chatHistory.length > 50) this.chatHistory.pop();
        this.saveHistory(conversation);
        this.renderHistory();

        const label = document.getElementById('chat-session-label');
        if (label) label.textContent = emoji + userMsg.slice(0, 58);
    },

    _saveToHistory(userMsg, aiMsg, historyIdOverride = null) {
        // historyIdOverride: wenn der Caller einen request-lokalen Snapshot
        // hat (z.B. sendMessage), nutze diesen, um Race-Conditions bei
        // schnellem Chat-Switching zu vermeiden.
        const targetId = historyIdOverride !== null
            ? historyIdOverride
            : this.currentHistoryId;
        const existing = this.chatHistory.find(h => h.id === targetId);
        if (existing) {
            existing.messages.push({ role: 'user', text: userMsg }, { role: 'ai', text: aiMsg });
            existing.updatedAt = Date.now();
            this.saveHistory(existing);
        }
    },

    // --- Chat History ---
    async loadHistory() {
        // SECURITY: Chat history wird NICHT in localStorage gespeichert (XSS/CWE-200)
        // da sie potenziell sensitive Daten enthalten kann.
        // Nur Server-Side History wird verwendet.
        try { localStorage.removeItem('ninko_chat_history'); } catch {}
        try {
            const res = await fetch('/api/chat/ui-history');
            if (res.ok) {
                const data = await res.json();
                this.chatHistory = data.conversations || [];
            } else {
                throw new Error('API nicht erreichbar');
            }
        } catch {
            this.chatHistory = [];
        }
        this.renderHistory();
    },

    async saveHistory(conversation) {
        // Auf Server speichern
        try {
            await fetch('/api/chat/ui-history', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(conversation),
            });
        } catch (err) { console.warn('syncHistoryToBackend failed', err); }
    },

    async deleteHistoryEntry(id) {
        try {
            await fetch(`/api/chat/ui-history/${id}`, { method: 'DELETE' });
        } catch (err) { console.warn('deleteHistory failed', err); }
        this.chatHistory = this.chatHistory.filter(h => h.id !== id);
        this.renderHistory();
    },

    renderHistory() {
        const list = document.getElementById('history-list');
        if (!list) return;

        if (this.chatHistory.length === 0) {
            list.innerHTML = `<div class="history-empty">${t('chat.noHistory')}</div>`;
            return;
        }

        list.innerHTML = this.chatHistory.map(h => {
            const historyId = this._escapeHtml(h.id);
            const plainTitle = this._stripHistoryDecorations(h.title || '');
            const historyTitle = this._escapeHtml(plainTitle);
            const historyTitleAttr = this._escapeAttr(h.title);
            return `
            <div class="history-item ${h.id === this.currentHistoryId ? 'active' : ''}"
                data-action="loadHistoryEntry" data-args="${JSON.stringify([historyId]).replace(/\"/g, '&quot;')}"
                title="${historyTitleAttr}">
                <span class="history-item-text">${historyTitle}</span>
                <button class="history-item-delete" data-action="deleteHistoryEntry" data-args="${JSON.stringify([historyId]).replace(/\"/g, '&quot;')}" data-stop-propagation="true" title="Chat löschen">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m5 0V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                </button>
            </div>
        `;
        }).join('');
    },

    _stripHistoryDecorations(title) {
        return String(title || '')
            .replace(/^[\p{Extended_Pictographic}\p{Emoji_Presentation}\p{So}\p{Sk}\uFE0F\u200D\s]+/u, '')
            .trim();
    },

    loadHistoryEntry(id) {
        const entry = this.chatHistory.find(h => h.id === id);
        if (!entry) return;

        // Clear current messages
        const container = document.getElementById('chat-messages');
        container.innerHTML = '';
        this._chatMessages = [];

        // Switch to active state (messages present)
        this._setChatState('active');

        // Replay messages
        for (const msg of entry.messages) {
            this.addChatMessage(msg.role, msg.text);
        }
        this._updateChatInputState('reply');

        // Update state
        this.currentHistoryId = id;
        this.sessionId = entry.sessionId;
        sessionStorage.setItem('ninko_session', this.sessionId);

        const label = document.getElementById('chat-session-label');
        if (label) label.textContent = entry.title;

        this.renderHistory();
    },

    newChat() {
        this._chatMessages = [];
        // Save current session to history first
        this.renderWelcomeState();

        // Switch back to centered state
        this._setChatState('centered');

        // Context-Window Ring zurücksetzen
        const arc = document.getElementById('ctx-arc');
        const pct = document.getElementById('ctx-pct');
        const ctxEl = document.getElementById('ctx-indicator');
        if (arc) { arc.setAttribute('stroke-dashoffset', '47.12'); arc.style.stroke = '#27ae60'; }
        if (pct) { pct.textContent = '—'; pct.style.color = '#27ae60'; }
        if (ctxEl) { ctxEl.classList.remove('visible', 'ctx-flash'); ctxEl.title = ''; }

        // New session
        this.sessionId = this.generateUUID();
        sessionStorage.setItem('ninko_session', this.sessionId);
        this.currentHistoryId = null;

        const label = document.getElementById('chat-session-label');
        if (label) label.textContent = t('chat.newChat');

        this.renderHistory();
    },

    _getWeekday() {
        const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
        return days[new Date().getDay()];
    },

    _getTimePeriod() {
        const hour = new Date().getHours();
        if (hour >= 5 && hour < 11) return 'morning';
        if (hour >= 11 && hour < 17) return 'day';
        if (hour >= 17 && hour < 22) return 'evening';
        return 'night';
    },

    _getWelcomeMessageCacheKey() {
        return `ninko_welcome_${I18n._lang}_${this.sessionId}`;
    },

    _getWelcomeMessageKey() {
        const weekday = this._getWeekday();
        const period = this._getTimePeriod();
        
        // Prioritätslogik: weekday+period → period → generic
        // 1. Versuche weekday.spezifisch + period (z.B. "monday.morning")
        const weekdayPeriodKey = `chat.welcome.message.weekday.${weekday}.${period}`;
        
        // Prüfe ob Keys für diese Kombination existieren
        let hasWeekdayPeriod = false;
        for (let i = 0; i < 25; i++) {
            if (t(weekdayPeriodKey + '.' + i) !== weekdayPeriodKey + '.' + i) {
                hasWeekdayPeriod = true;
                break;
            }
        }
        
        if (hasWeekdayPeriod) {
            return weekdayPeriodKey;
        }
        
        // 2. Fallback zu period-nur (z.B. "period.morning")
        const periodKey = `chat.welcome.message.period.${period}`;
        let hasPeriod = false;
        for (let i = 0; i < 25; i++) {
            if (t(periodKey + '.' + i) !== periodKey + '.' + i) {
                hasPeriod = true;
                break;
            }
        }
        
        if (hasPeriod) {
            return periodKey;
        }
        
        // 3. Fallback zu generic
        return 'chat.welcome.message.generic';
    },

    _getWelcomeMessageVariant(period) {
        // Neue Logik mit Wochentag, echten Zufall pro Chat
        // Altes Verhalten für Backward-Kompatibilität beibehalten
        
        const messageKey = this._getWelcomeMessageKey();
        const variants = [];
        
        for (let i = 0; i < 25; i += 1) {
            const key = `${messageKey}.${i}`;
            const translated = t(key);
            if (translated === key) break;
            variants.push(translated);
        }
        
        if (!variants.length) {
            // Fallback zu alter Logik für Kompatibilität
            const oldVariants = [];
            for (let i = 0; i < 8; i += 1) {
                const key = `chat.welcome.message.${period}.${i}`;
                const translated = t(key);
                if (translated === key) break;
                oldVariants.push(translated);
            }
            if (oldVariants.length) {
                return oldVariants[Math.floor(Math.random() * oldVariants.length)];
            }
            return t('chat.input.ask');
        }
        
        // Echter Zufall pro neuem Chat, stabil innerhalb eines Chats
        const cacheKey = this._getWelcomeMessageCacheKey();
        let cachedIndex = sessionStorage.getItem(cacheKey);
        
        if (cachedIndex === null) {
            cachedIndex = Math.floor(Math.random() * variants.length).toString();
            sessionStorage.setItem(cacheKey, cachedIndex);
        } else {
            cachedIndex = parseInt(cachedIndex);
            if (cachedIndex >= variants.length) {
                cachedIndex = Math.floor(Math.random() * variants.length);
                sessionStorage.setItem(cacheKey, cachedIndex.toString());
            }
        }
        
        return variants[cachedIndex];
    },

    _updateChatInputState(mode = 'ask') {
        const input = document.getElementById('chat-input');
        if (!input) return;
        const key = mode === 'reply' ? 'chat.input.reply' : 'chat.input.ask';
        input.dataset.i18nPlaceholder = key;
        input.placeholder = t(key);
    },

    _getDashboardHomeHtml() {
        const headline = this._escapeHtml(this._getWelcomeMessageVariant(this._getTimePeriod()));
        const dashboardLogo = this._escapeHtml(this._branding?.login_image_url || '/static/images/logo_dashboard_new.png?v=3');

        return `
            <div class="welcome-message dashboard-home">
                <div class="dh-shell dh-shell-minimal">
                    <div class="dh-intro dh-intro-plain">
                        <div class="dh-headline">
                            <div class="logo-wrapper dh-headline-logo" aria-hidden="true">
                                <img class="dh-headline-icon" src="${dashboardLogo}" alt="Ninko">
                                <div class="eye eye-left"></div>
                                <div class="eye eye-right"></div>
                            </div>
                            <h2>${headline}</h2>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    getWelcomeHtml() {
        return this._getDashboardHomeHtml();
    },

    renderWelcomeState() {
        const container = document.getElementById('chat-messages');
        if (!container) return;
        // In-place Update wenn das Welcome-Markup bereits steht (statisches HTML
        // oder früherer Render): verhindert Logo-Remount, Bild-Reflash und
        // Layout-Shift ("Dashboard-Flackern") bei Branding-/Sprach-/Theme-Updates.
        const existing = container.querySelector('.welcome-message');
        const h2 = existing?.querySelector('.dh-headline h2');
        const img = existing?.querySelector('.dh-headline-icon');
        if (existing && h2 && img && container.children.length === 1) {
            const headline = this._getWelcomeMessageVariant(this._getTimePeriod());
            const logoSrc = this._branding?.login_image_url || '/static/images/logo_dashboard_new.png?v=3';
            if (h2.textContent !== headline) h2.textContent = headline;
            // data-i18n entfernen, damit spätere i18n-Sweeps die Variante nicht überschreiben
            h2.removeAttribute('data-i18n');
            if (img.getAttribute('src') !== logoSrc) img.setAttribute('src', logoSrc);
        } else {
            container.innerHTML = this.getWelcomeHtml();
        }
        this._setChatState('centered');
        this._updateChatInputState('ask');
    },

    // --- Context Clear ---
    async clearContext() {
        if (!await this.confirm(t('chat.clearContextConfirm'))) return;

        // New session ID = fresh context on the server
        this.sessionId = this.generateUUID();
        sessionStorage.setItem('ninko_session', this.sessionId);
        this.currentHistoryId = null;

        // Also clear visible messages
        const container = document.getElementById('chat-messages');
        container.innerHTML = '<div class="history-empty" style="padding:2rem;text-align:center;color:var(--text-muted);">Kontext gelöscht. Stelle eine neue Frage.</div>';
        this._setChatState('active');
        this._updateChatInputState('ask');

        const label2 = document.getElementById('chat-session-label');
        if (label2) label2.textContent = t('chat.newChat');
        showNotification(t('chat.contextClearedNotif'), 'info');
    },

    // --- Chat HTML Export ---
    exportChatAsHtml() {
        if (this._chatMessages.length === 0) {
            showNotification(t('chat.exportEmpty'), 'info');
            return;
        }

        const sessionLabel = document.getElementById('chat-session-label');
        const chatTitle = (sessionLabel && sessionLabel.textContent.trim()) || 'Ninko Chat';
        const exportDate = new Date().toLocaleString('de-DE', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });

        const messagesHtml = this._chatMessages.map(msg => {
            const roleLabel = msg.role === 'user' ? t('chat.exportRoleUser') : t('chat.exportRoleAi');
            const roleClass = msg.role === 'user' ? 'user' : 'ai';
            let rendered = this.formatText(msg.text);
            // Zweiter Sanitize-Pass für den Export-Kontext — DOMPurify muss verfügbar sein
            // da das exportierte Dokument als standalone file:// geöffnet wird (kein CORS-Schutz)
            if (typeof DOMPurify !== 'undefined') {
                rendered = DOMPurify.sanitize(rendered, {
                    ADD_ATTR: ['target', 'rel'],
                    FORBID_TAGS: ['script', 'style', 'iframe', 'form', 'input'],
                    ALLOWED_URI_REGEXP: /^(https?|mailto):/i,
                });
            } else {
                // DOMPurify nicht geladen — nur escaped Plain-Text ausgeben (kein Markdown-Rendering)
                rendered = `<pre style="white-space:pre-wrap">${this._escapeHtml(msg.text)}</pre>`;
            }
            return `<div class="message ${roleClass}"><div class="role-label">${this._escapeHtml(roleLabel)}</div><div class="bubble">${rendered}</div></div>`;
        }).join('\n');

        const html = `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${this._escapeHtml(chatTitle)} — Ninko Export</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    margin: 0;
    padding: 2rem 1rem;
    line-height: 1.6;
  }
  .export-container { max-width: 780px; margin: 0 auto; }
  header { border-bottom: 1px solid #2d3748; padding-bottom: 1rem; margin-bottom: 2rem; }
  header h1 { margin: 0 0 0.25rem; font-size: 1.3rem; color: #f8fafc; }
  header .meta { font-size: 0.8rem; color: #718096; }
  .message { display: flex; flex-direction: column; margin-bottom: 1.5rem; }
  .message.user { align-items: flex-end; }
  .message.ai { align-items: flex-start; }
  .role-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; color: #718096; margin-bottom: 0.3rem; }
  .bubble {
    max-width: 80%;
    padding: 0.75rem 1rem;
    border-radius: 12px;
    font-size: 0.92rem;
    word-break: break-word;
  }
  .message.user .bubble { background: #2563eb; color: #fff; border-radius: 12px 12px 2px 12px; }
  .message.ai .bubble { background: #1e2535; color: #e2e8f0; border-radius: 2px 12px 12px 12px;
    border: 1px solid #2d3748; }
  .bubble pre { background: #0d1117; border: 1px solid #2d3748; border-radius: 6px;
    padding: 0.75rem; overflow-x: auto; font-size: 0.85rem; }
  .bubble code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    background: #0d1117; padding: 0.1em 0.35em; border-radius: 4px; font-size: 0.85em; }
  .bubble pre code { background: none; padding: 0; }
  .bubble a { color: #60a5fa; }
  .bubble table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
  .bubble th, .bubble td { border: 1px solid #2d3748; padding: 0.4rem 0.7rem; font-size: 0.88rem; }
  .bubble th { background: #1a2030; }
  footer { text-align: center; color: #4a5568; font-size: 0.75rem;
    margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #2d3748; }
</style>
</head>
<body>
<div class="export-container">
  <header>
    <h1>${this._escapeHtml(chatTitle)}</h1>
    <div class="meta">Ninko — Exportiert am ${this._escapeHtml(exportDate)}</div>
  </header>
  <main>
${messagesHtml}
  </main>
  <footer>Erstellt mit Ninko · ${this._escapeHtml(exportDate)}</footer>
</div>
</body>
</html>`;

        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const safeTitle = chatTitle.replace(/[^a-zA-Z0-9\u00C0-\u024F _-]/g, '').trim().replace(/\s+/g, '_') || 'ninko_chat';
        const ts = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '-');
        a.href = url;
        a.download = `${safeTitle}_${ts}.html`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 100);
        showNotification(t('chat.exportDone'), 'success');
    },

    restoreTheme() {
        // Dark mode only — no theme toggle
        document.body.classList.remove('light-mode');
    },

    _clearThemeVars() {
        if (!this._appliedThemeVars?.length) return;
        for (const key of this._appliedThemeVars) {
            document.documentElement.style.removeProperty(key);
        }
        this._appliedThemeVars = [];
    },

    applyActiveThemeTokens() {
        this._clearThemeVars();
        const theme = this._activeThemeDefinition;
        if (!theme) return;
        const tokens = theme.tokens_dark || {};
        const keys = [];
        for (const [k, v] of Object.entries(tokens)) {
            if (!k?.startsWith('--')) continue;
            document.documentElement.style.setProperty(k, String(v));
            keys.push(k);
        }
        this._appliedThemeVars = keys;
    },

    async loadActiveTheme() {
        try {
            const res = await fetch('/api/themes/active', { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            this._activeThemeId = data.theme_id || 'default';
            this._activeThemeDefinition = data.theme || null;
        } catch (err) { console.warn('loadActiveTheme failed', err); }
    },

    async activateTheme(themeId, silent = false) {
        try {
            const res = await fetch('/api/themes/active', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme_id: themeId }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Theme konnte nicht aktiviert werden.');
            await this.loadActiveTheme();
            this.applyActiveThemeTokens();
            if (document.querySelector('.welcome-message')) this.renderWelcomeState();
            if (!silent) showNotification(`Theme "${themeId}" aktiv`, 'success');
            this._renderThemeCards();
        } catch (e) {
            if (!silent) showNotification(e.message || 'Theme konnte nicht aktiviert werden.', 'error');
        }
    },


    // --- Hintergrundfarben (Settings → Themes → Hintergrundfarben) ---

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

    sendQuick(textOrKey) {
        if (!textOrKey || textOrKey === 'undefined') return;
        const input = document.getElementById('chat-input');
        input.value = textOrKey;
        this._updateChatInputState('reply');
        this.sendMessage();
    },

    addChatMessage(role, text, trackInMemory = true) {
        const container = document.getElementById('chat-messages');

        // Remove welcome message & switch to active state
        const welcome = container.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
            this._setChatState('active');
        }
        this._updateChatInputState('reply');

        // Track in memory
        const msgId = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
        if (trackInMemory && (role === 'user' || role === 'ai')) {
            this._chatMessages.push({ id: msgId, role, text });
        }

        const avatarUser = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>';
        const avatarAi = '<img src="/static/images/chat_fox.png" class="chat-avatar-fox" alt="AI">';

        const avatar = role === 'user' ? avatarUser : avatarAi;

        const retryBtn = role === 'ai'
            ? `<button class="chat-action-btn" title="Wiederholen" data-action="retryMessage" data-args="${JSON.stringify([msgId]).replace(/\"/g, '&quot;')}">↺</button>`
            : '';

        const copyIcon = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
        const copyBtn = `<button class="chat-action-btn chat-action-copy" title="${t('copy.copy')}" data-action="copyMessage" data-args="${JSON.stringify([msgId]).replace(/\"/g, '&quot;')}" data-self="true">${copyIcon}</button>`;

        const speakerIcon = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;
        const ttsBtn = (role === 'ai' && this._ttsAvailable)
            ? `<button class="chat-action-btn chat-action-tts" data-tts-id="${msgId}" title="Vorlesen" data-action="speakMessage" data-args="${JSON.stringify([msgId]).replace(/\"/g, '&quot;')}">${speakerIcon}</button>`
            : '';

        const div = document.createElement('div');
        div.className = `chat-message ${role}`;
        div.dataset.msgId = msgId;
        div.innerHTML = `
            <div class="chat-bubble-group">
                <div class="chat-bubble">
                    <div class="chat-bubble-text">${this.formatText(text)}</div>
                </div>
                <div class="chat-actions">
                    ${copyBtn}
                    ${ttsBtn}
                    ${retryBtn}
                    <button class="chat-action-btn chat-action-delete" title="Löschen" data-action="deleteMessage" data-args="${JSON.stringify([msgId]).replace(/\"/g, '&quot;')}"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
                </div>
            </div>
        `;

        // Denkschritte-Wrapper aus dem letzten Typing-Cycle vor dem Text einbetten
        if (role === 'ai' && this._savedSteps) {
            const hasSteps = this._savedSteps.querySelector('.typing-step');
            if (hasSteps) {
                const bubble = div.querySelector('.chat-bubble');
                this._savedSteps.classList.add('typing-steps-preserved');
                bubble.insertBefore(this._savedSteps, bubble.querySelector('.chat-bubble-text'));
            }
            this._savedSteps = null;
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
        return div;
    },

    addChatMeta(text) {
        const container = document.getElementById('chat-messages');
        const span = document.createElement('div');
        span.style.cssText = 'text-align:center;font-size:0.75rem;color:var(--text-muted);margin:-0.5rem 0 1rem;';
        span.textContent = text;
        container.appendChild(span);
    },

    async _syncHistoryToBackend() {
        // Schreibt _chatMessages als neue Redis-History
        const messages = this._chatMessages.map(m => ({
            role: m.role === 'ai' ? 'assistant' : 'user',
            content: m.text,
        }));
        await fetch(`/api/chat/history/${encodeURIComponent(this.sessionId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages }),
        });
    },

    async deleteMessage(msgId) {
        const idx = this._chatMessages.findIndex(m => m.id === msgId);
        if (idx === -1) return;

        this._chatMessages.splice(idx, 1);
        document.querySelector(`[data-msg-id="${msgId}"]`)?.remove();
        await this._syncHistoryToBackend();
    },

    async copyMessage(msgId, btnElement) {
        const msg = this._chatMessages.find(m => m.id === msgId);
        if (!msg) return;

        const showCopied = () => {
            btnElement.title = t('copy.copied');
            btnElement.classList.add("copied");
            setTimeout(() => {
                btnElement.title = t('copy.copy');
                btnElement.classList.remove("copied");
            }, 2000);
        };

        const showError = () => {
            btnElement.title = t('copy.error');
            setTimeout(() => {
                btnElement.title = t('copy.copy');
            }, 2000);
        };

        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(msg.text);
                showCopied();
                return;
            }

            const textArea = document.createElement("textarea");
            textArea.value = msg.text;
            textArea.style.position = "fixed";
            textArea.style.left = "-9999px";
            textArea.style.top = "0";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (successful) {
                    showCopied();
                } else {
                    showError();
                }
            } catch (err) {
                document.body.removeChild(textArea);
                console.error("Copy failed:", err);
                showError();
            }
        } catch (err) {
            console.error("Copy failed:", err);
            showError();
        }
    },

    async _checkTtsAvailable() {
        try {
            const res = await fetch('/api/settings/tts');
            if (res.ok) {
                const data = await res.json();
                this._ttsAvailable = !!data.TTS_ENABLED;
            }
        } catch (err) { console.warn('loadTTS failed, TTS stays disabled', err); }
    },

    initScrollbarVisibility() {
        const selectors = [
            '.sidebar-subnav',
            '.sidebar-history-section .history-list',
            '.nav-tabs',
            '.sidebar-panel-body',
            '.module-subnav-list',
        ];
        const bound = new WeakSet();

        const attach = (el) => {
            if (!el || bound.has(el)) return;
            bound.add(el);

            let hideTimer = null;
            el.addEventListener('scroll', () => {
                el.classList.add('is-scrolling');
                if (hideTimer) clearTimeout(hideTimer);
                hideTimer = setTimeout(() => {
                    el.classList.remove('is-scrolling');
                }, 900);
            }, { passive: true });
        };

        selectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach(attach);
        });
    },

    // --- Chat Messages / TTS ---
    async speakMessage(msgId) {
        const stopIcon = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>`;
        const speakerIcon = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;

        const btn = document.querySelector(`[data-tts-id="${msgId}"]`);

        // Läuft gerade diese Nachricht? → stoppen
        if (this._ttsSpeakingMsgId === msgId && this._ttsAudio) {
            this._ttsAudio.pause();
            this._ttsAudio = null;
            this._ttsSpeakingMsgId = null;
            if (btn) { btn.classList.remove('speaking'); btn.innerHTML = speakerIcon; }
            return;
        }

        // Andere Nachricht läuft? → vorher stoppen
        if (this._ttsAudio) {
            this._ttsAudio.pause();
            this._ttsAudio = null;
            const prevBtn = document.querySelector(`[data-tts-id="${this._ttsSpeakingMsgId}"]`);
            if (prevBtn) { prevBtn.classList.remove('speaking'); prevBtn.innerHTML = speakerIcon; }
            this._ttsSpeakingMsgId = null;
        }

        const msg = this._chatMessages.find(m => m.id === msgId);
        if (!msg) return;

        if (btn) { btn.classList.add('speaking'); btn.innerHTML = stopIcon; }
        this._ttsSpeakingMsgId = msgId;

        try {
            const res = await fetch('/api/tts/synthesize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: msg.text }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                showNotification(err.detail || 'TTS-Fehler', 'error');
                if (btn) { btn.classList.remove('speaking'); btn.innerHTML = speakerIcon; }
                this._ttsSpeakingMsgId = null;
                return;
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            this._ttsAudio = audio;
            audio.onended = () => {
                URL.revokeObjectURL(url);
                this._ttsAudio = null;
                this._ttsSpeakingMsgId = null;
                if (btn) { btn.classList.remove('speaking'); btn.innerHTML = speakerIcon; }
            };
            audio.onerror = () => {
                URL.revokeObjectURL(url);
                this._ttsAudio = null;
                this._ttsSpeakingMsgId = null;
                if (btn) { btn.classList.remove('speaking'); btn.innerHTML = speakerIcon; }
            };
            audio.play();
        } catch (err) {
            showNotification('TTS-Fehler: ' + err.message, 'error');
            if (btn) { btn.classList.remove('speaking'); btn.innerHTML = speakerIcon; }
            this._ttsSpeakingMsgId = null;
        }
    },

    async retryMessage(aiMsgId) {
        const aiIdx = this._chatMessages.findIndex(m => m.id === aiMsgId);
        if (aiIdx === -1) return;

        // Vorherige User-Nachricht suchen
        const userMsg = this._chatMessages.slice(0, aiIdx).reverse().find(m => m.role === 'user');
        if (!userMsg) return;

        const userText = userMsg.text;
        const userIdx = this._chatMessages.indexOf(userMsg);

        // Beide Nachrichten entfernen (user + ai)
        this._chatMessages.splice(userIdx, aiIdx - userIdx + 1);
        document.querySelector(`[data-msg-id="${aiMsgId}"]`)?.remove();
        document.querySelector(`[data-msg-id="${userMsg.id}"]`)?.remove();

        // History synchronisieren
        await this._syncHistoryToBackend();

        // User-Text erneut senden
        const input = document.getElementById('chat-input');
        if (input) input.value = userText;
        await this.sendMessage();
    },

    async _initCtxIndicator() {
        // Context-Window des aktiven Providers laden und in den Ring schreiben
        // (noch ohne used_tokens — zeigt nur dass der Ring sichtbar ist)
        try {
            const res = await fetch('/api/settings/llm/context-window');
            if (!res.ok) return;
            const data = await res.json();
            const win = data.context_window || 0;
            if (win > 0) {
                // Virtuelles leeres Budget aufbauen: 0 Tokens genutzt, Threshold = 25% des Fensters
                const threshold = Math.floor(win * 0.25);
                this._updateCtxIndicator({
                    used_tokens: 0,
                    threshold_tokens: threshold,
                    max_tokens: threshold,
                    usage_percent: 0,
                    should_reset: false,
                });
            }
        } catch (err) { console.warn('initTTS failed', err); }
    },

    _bindCtxIndicatorAction() {
        const el = document.getElementById('ctx-indicator');
        if (!el || el.dataset.clearBound === '1') return;

        el.dataset.clearBound = '1';
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.setAttribute('aria-label', t('chat.clearContext'));
        if (!el.title) el.title = t('chat.clearContext');

        el.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this.clearContext();
        });

        el.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            event.preventDefault();
            this.clearContext();
        });
    },

    _updateCtxIndicator(budget) {
        const el  = document.getElementById('ctx-indicator');
        const arc = document.getElementById('ctx-arc');
        const pct = document.getElementById('ctx-pct');
        if (!el || !arc || !pct || !budget) return;

        const { used_tokens, threshold_tokens, max_tokens } = budget;
        const limit    = threshold_tokens || max_tokens || 1;
        const fillPct  = Math.min(100, (used_tokens / limit) * 100);

        // SVG arc: r=7.5 → circumference ≈ 47.12
        const circ = 47.12;
        arc.setAttribute('stroke-dashoffset', (circ * (1 - fillPct / 100)).toFixed(2));

        // Farbe: grün → gelb → orange → rot
        let color;
        if      (fillPct < 40) color = '#27ae60';
        else if (fillPct < 65) color = '#f0b429';
        else if (fillPct < 85) color = '#e67e22';
        else                   color = '#e74c3c';
        arc.style.stroke = color;
        pct.style.color  = color;

        // Label
        pct.textContent = budget.should_reset ? '!' : Math.round(fillPct) + '%';

        // Tooltip
        const fmt = n => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
        const remaining = Math.max(0, limit - used_tokens);
        el.title = `Kontext: ${fmt(used_tokens)} / ${fmt(limit)} Tokens\nKomprimierung in ~${fmt(remaining)} Tokens\n${t('chat.clearContext')}`;

        el.classList.add('visible');
    },

    addCompactionNotice() {
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = 'chat-compaction-notice';
        div.innerHTML = `
            <span class="compaction-icon">⟳</span>
            <span>Gesprächsverlauf komprimiert – ältere Nachrichten wurden zusammengefasst</span>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    _typingSteps: [],
    _pendingToolSteps: {},
    _thinkingStep: null,
    _thinkingStepStart: null,
    _pendingTraceSteps: {},
    _savedSteps: null,

    showTyping() {
        this._typingSteps = [];
        this._pendingToolSteps = {};
        this._thinkingStep = null;
        this._thinkingStepStart = null;
        this._pendingTraceSteps = {};
        this._savedSteps = null;
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = 'chat-message ai';
        div.id = 'typing-indicator';
        div.innerHTML = `
            <div class="chat-bubble typing-bubble">
                <div class="typing-live">
                    <span class="typing-live-label" id="typing-live-label" data-active-text=""></span>
                </div>
                <details class="denkschritte-wrapper denkschritte-running">
                    <summary class="denkschritte-summary"><span class="denkschritte-label">Denke nach…</span></summary>
                    <div class="typing-steps" id="typing-steps"></div>
                </details>
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    hideTyping() {
        const indicator = document.getElementById('typing-indicator');
        const wrapper = indicator ? indicator.querySelector('.denkschritte-wrapper') : null;
        const stepsEl = wrapper ? wrapper.querySelector('.typing-steps') : null;

        // Ganzen Wrapper (inkl. "Denkschritte"-Header) retten bevor Indicator entfernt wird
        if (stepsEl && stepsEl.children.length > 0) {
            const saved = wrapper.cloneNode(true);

            // ⚠️ KRITISCH: ID-Attribute aus dem Klon entfernen,
            // sonst findet document.getElementById('typing-steps') den Klon
            // statt des nächsten Typing-Indicators → neue Steps landen in alter Bubble
            saved.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));

            // Header: "Denke nach…" → "Denkschritte", Animation stoppen
            saved.classList.remove('denkschritte-running');
            const label = saved.querySelector('.denkschritte-label');
            if (label) label.textContent = 'Denkschritte';

            // Laufende Steps auf "done" setzen (Antwort ist da)
            saved.querySelectorAll('.typing-step-running').forEach(el => {
                el.classList.remove('typing-step-running');
                el.classList.add('typing-step-done');
            });
            this._savedSteps = saved;
        } else {
            this._savedSteps = null;
        }

        indicator?.remove();
        this._typingSteps = [];
        this._pendingToolSteps = {};
        this._thinkingStep = null;
        this._thinkingStepStart = null;
        this._pendingTraceSteps = {};
    },

    _settleThinkingHeader() {
        const wrapper = document.querySelector('#typing-indicator .denkschritte-wrapper');
        if (!wrapper) return;
        wrapper.classList.remove('denkschritte-running');
        const label = wrapper.querySelector('.denkschritte-label');
        if (label) label.textContent = 'Denkschritte';
    },

    _formatDuration(ms) {
        if (!ms && ms !== 0) return '';
        if (ms < 1000) return `${Math.round(ms)} ms`;
        return `${(ms / 1000).toFixed(2)} s`;
    },

    _formatSize(bytes) {
        if (!bytes && bytes !== 0) return '';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    },

    _sanitizeArgs(args) {
        if (!args || typeof args !== 'object') return '';
        // _raw-Fallback (kaputtes JSON vom Backend) → nicht anzeigen
        if ('_raw' in args && Object.keys(args).length === 1) return '';
        const sensitiveKeys = ['password', 'secret', 'token', 'api_key', 'apikey', 'key'];
        const scrub = (obj) => {
            if (Array.isArray(obj)) return obj.slice(0, 20).map(scrub);
            if (obj && typeof obj === 'object') {
                const out = {};
                for (const [k, v] of Object.entries(obj)) {
                    const lower = k.toLowerCase();
                    if (sensitiveKeys.some(s => lower.includes(s))) {
                        out[k] = '***';
                    } else {
                        out[k] = scrub(v);
                    }
                }
                return out;
            }
            if (typeof obj === 'string') return obj.length > 180 ? obj.slice(0, 180) + '…' : obj;
            return obj;
        };
        try {
            const cleaned = scrub(args);
            return JSON.stringify(cleaned, null, 2);
        } catch {
            return '';
        }
    },

    _buildInlineHint(toolName, args) {
        if (!args || typeof args !== 'object') return '';
        // _raw-Key überspringen (Fallback aus kaputtem JSON-Parse)
        if ('_raw' in args && Object.keys(args).length === 1) return '';

        const fmt = (v) => {
            const s = String(v);
            return s.length > 55 ? s.slice(0, 52) + '…' : s;
        };

        // Primärer Wert (Pattern, Query, Input etc.)
        const primary = args.pattern ?? args.query ?? args.input ?? args.command ?? args.text ?? null;
        // Sekundärer Kontext (Pfad, Datei)
        const secondary = args.path ?? args.file_path ?? args.filename ?? args.directory ?? null;

        if (primary != null && secondary != null) {
            return `"${fmt(primary)}" (in ${fmt(secondary)})`;
        }
        if (primary != null) return `"${fmt(primary)}"`;
        if (secondary != null) return fmt(secondary);

        // Erster kurzer String-Wert (kein _raw, kein UUID-artiger Wert)
        const uuidRe = /^[0-9a-f\-]{20,}$/i;
        for (const [k, v] of Object.entries(args)) {
            if (k === '_raw') continue;
            if (typeof v === 'string' && v.length > 0 && v.length < 80 && !uuidRe.test(v)) {
                return fmt(v);
            }
        }
        return '';
    },

    _appendStep(text, meta = {}) {
        const stepsEl = document.getElementById('typing-steps');
        if (!stepsEl) return null;

        const hint = meta.hint ?? this._buildInlineHint(meta.tool, meta.args);
        const hintHtml = hint ? ` <span class="step-hint">${this._escapeHtml(hint)}</span>` : '';
        const phaseClass = meta.phase
            ? String(meta.phase).toLowerCase().replace(/[^a-z0-9_-]/g, '-')
            : '';
        const phaseLabel = String(meta.phaseLabel || meta.phase || 'Trace').trim() || 'Trace';
        const phaseHtml = meta.phase
            ? `<span class="trace-phase trace-phase-${phaseClass}">${this._escapeHtml(phaseLabel)}</span>`
            : '';
        const durationHtml = meta.duration_ms != null
            ? `<span class="step-duration">${this._escapeHtml(this._formatDuration(meta.duration_ms))}</span>`
            : '';

        const argsText = meta.args ? this._sanitizeArgs(meta.args) : '';
        const argsBlock = argsText
            ? `<pre class="typing-step-args">${this._escapeHtml(argsText)}</pre>`
            : '';
        const previewText = meta.preview ? this._escapeHtml(meta.preview) : '';
        const previewBlock = previewText
            ? `<pre class="typing-step-preview">${previewText}</pre>`
            : '';

        // Thinking-Steps immer mit aufklappbarem Body (Timing wird später eingefügt)
        const isThinking = meta.isThinking === true;
        const hasBody = !!(argsBlock || previewBlock || isThinking);

        const step = document.createElement('details');
        step.className = 'typing-step';
        if (meta.state) step.classList.add(`typing-step-${meta.state}`);
        if (meta.phase) step.dataset.phase = meta.phase;
        if (!hasBody) step.classList.add('typing-step-noexpand');
        if (meta.runId) step.dataset.runId = meta.runId;

        const thinkingPlaceholder = isThinking ? `<span class="typing-step-thinking-placeholder">${this._escapeHtml(this._getThinkingPlaceholder())}</span>` : '';
        step.innerHTML = `
            <summary>
                ${phaseHtml}
                <span class="typing-step-label">${this._escapeHtml(text)}${hintHtml}</span>
                ${durationHtml}
                ${hasBody ? '<span class="step-chevron">›</span>' : ''}
            </summary>
            <div class="typing-step-body">
                ${isThinking ? `<div class="typing-step-thinking-note">${thinkingPlaceholder}</div>` : ''}
                ${argsBlock}
                ${previewBlock}
            </div>
        `;

        // Details nur öffenbar wenn Body-Inhalt vorhanden
        if (!hasBody) step.removeAttribute('open');

        stepsEl.appendChild(step);
        const all = stepsEl.querySelectorAll('.typing-step');
        if (all.length > 30) all[0].remove();
        return step;
    },

    _formatTraceData(data) {
        if (!data || typeof data !== 'object') return '';
        try {
            return JSON.stringify(data, null, 2);
        } catch {
            return '';
        }
    },

    _tracePhaseLabel(phase) {
        const labels = {
            request: 'Request',
            safeguard: 'SafeGuard',
            context: 'Kontext',
            routing: 'Routing',
            pipeline: 'Pipeline',
            agent: 'Agent',
            tool: 'Tool',
            llm: 'LLM',
        };
        return labels[phase] || phase || 'Trace';
    },

    _traceKey(evt) {
        if (!evt) return '';
        return [evt.phase || 'trace', evt.label || '', evt.detail || ''].join('::');
    },

    _traceRunningKey(evt) {
        if (!evt) return '';
        const data = evt.data && typeof evt.data === 'object' ? evt.data : {};
        const subject = data.agent || data.module || data.force_module || evt.detail || '';
        return [evt.phase || 'trace', subject].join('::');
    },

    _handleTraceEvent(evt) {
        if (!evt || !evt.label) return;
        const stepsEl = document.getElementById('typing-steps');
        if (!stepsEl) return;

        const phase = String(evt.phase || 'trace').toLowerCase();
        const state = evt.status === 'error' ? 'error' : (evt.status === 'running' ? 'running' : 'done');
        const dataText = this._formatTraceData(evt.data);
        const detail = evt.detail ? String(evt.detail) : '';
        const key = this._traceKey(evt);
        const runningKey = this._traceRunningKey(evt);

        const existing = (key && this._pendingTraceSteps[key])
            || (runningKey && this._pendingTraceSteps[runningKey])
            || null;
        if (existing && state !== 'running') {
            existing.classList.remove('typing-step-running', 'typing-step-enter');
            existing.classList.add(state === 'error' ? 'typing-step-error' : 'typing-step-done');
            const body = existing.querySelector('.typing-step-body');
            if (body && (detail || dataText) && !body.querySelector('.typing-step-preview')) {
                const pre = document.createElement('pre');
                pre.className = 'typing-step-preview';
                pre.textContent = [detail, dataText].filter(Boolean).join('\n\n');
                body.appendChild(pre);
                existing.classList.remove('typing-step-noexpand');
                const summary = existing.querySelector('summary');
                if (summary && !summary.querySelector('.step-chevron')) {
                    const ch = document.createElement('span');
                    ch.className = 'step-chevron';
                    ch.textContent = '›';
                    summary.appendChild(ch);
                }
            }
            delete this._pendingTraceSteps[key];
            delete this._pendingTraceSteps[runningKey];
            return;
        }

        const step = this._appendStep(evt.label, {
            state,
            phase,
            phaseLabel: this._tracePhaseLabel(phase),
            preview: [detail, dataText].filter(Boolean).join('\n\n'),
        });
        if (step && state === 'running' && key) {
            this._pendingTraceSteps[key] = step;
            if (runningKey) this._pendingTraceSteps[runningKey] = step;
        }

    },

    updateTypingStatus(text) {
        if (!document.getElementById('typing-steps')) return;
        // Kein separater Thinking-Step — Header zeigt "Denke nach…" solange running
        if (!this._thinkingStepStart) {
            this._thinkingStepStart = Date.now();
        }
        const container = document.getElementById('chat-messages');
        if (container) container.scrollTop = container.scrollHeight;
    },

    _handleThinkingContent(text) {
        if (!text || !this._thinkingStep) return;
        const note = this._thinkingStep.querySelector('.typing-step-thinking-note');
        if (!note) return;
        const placeholder = note.querySelector('.typing-step-thinking-placeholder');
        if (placeholder) placeholder.remove();
        const existing = note.textContent || '';
        note.textContent = existing ? existing + '\n\n' + text : text;
    },

    _finalizeThinkingStep() {
        if (!this._thinkingStep) return;
        const step = this._thinkingStep;
        const dur = this._thinkingStepStart ? Date.now() - this._thinkingStepStart : null;

        step.classList.remove('typing-step-running', 'typing-step-enter');
        step.classList.add('typing-step-done');
        void step.offsetHeight;

        // Dauer in Summary eintragen
        if (dur != null) {
            const summary = step.querySelector('summary');
            if (summary) {
                let d = summary.querySelector('.step-duration');
                if (!d) {
                    d = document.createElement('span');
                    d.className = 'step-duration';
                    summary.insertBefore(d, summary.querySelector('.step-chevron'));
                }
                d.textContent = this._formatDuration(dur);
            }
        }

        this._thinkingStep = null;
        this._thinkingStepStart = null;
    },

    _getThinkingPlaceholder() {
        const lang = (navigator.language || 'en').slice(0, 2).toLowerCase();
        const hints = {
            de: ['Kontext analysiert', 'Nächste Schritte geplant', 'Ergebnisse ausgewertet', 'Strategie gewählt', 'Informationen verarbeitet', 'Analysiert Daten', 'Bereitet Antwort vor'],
            en: ['Context analysed', 'Next steps planned', 'Results evaluated', 'Strategy selected', 'Information processed', 'Analyzing data', 'Preparing response'],
            fr: ['Contexte analysé', 'Étapes planifiées', 'Résultats évalués', 'Stratégie choisie', 'Analyse des données'],
            es: ['Contexto analizado', 'Pasos planificados', 'Resultados evaluados', 'Estrategia seleccionada', 'Analizando datos'],
            it: ['Contesto analizzato', 'Passi pianificati', 'Risultati valutati', 'Strategia scelta', 'Analisi dati'],
            nl: ['Context geanalyseerd', 'Stappen gepland', 'Resultaten beoordeeld', 'Strategie gekozen', 'Gegevens analyseren'],
            pl: ['Kontekst przeanalizowany', 'Kroki zaplanowane', 'Wyniki ocenione', 'Strategia wybrana', 'Analiza danych'],
            pt: ['Contexto analisado', 'Passos planeados', 'Resultados avaliados', 'Estratégia selecionada', 'Analisando dados'],
            ja: ['文脈を分析', '次のステップを計画', '結果を評価', '戦略を選択', 'データを分析'],
            zh: ['已分析上下文', '已规划步骤', '已评估结果', '已选择策略', '正在分析数据'],
            ru: ['Контекст проанализирован', 'Шаги запланированы', 'Результаты оценены', 'Стратегия выбрана', 'Анализ данных'],
        };
        const list = hints[lang] || hints.en;
        return list[Math.floor(Math.random() * list.length)];
    },

    handleToolEvent(evt) {
        if (!evt || !evt.type) return;
        if (evt.type === 'tool_start') {
            // Thinking-Step abschließen, bevor das erste Tool startet
            if (this._thinkingStep) {
                this._finalizeThinkingStep();
            }

            const label = evt.label || evt.tool_name || 'Tool läuft';
            const step = this._appendStep(label, {
                state: 'running',
                phase: 'tool',
                phaseLabel: this._tracePhaseLabel('tool'),
                tool: evt.tool_name,
                agent: evt.agent,
                runId: evt.run_id,
                args: evt.args || null,
            });
            if (step && evt.run_id) {
                this._pendingToolSteps[evt.run_id] = step;
            }
            return;
        }
        if (evt.type === 'tool_end') {
            const step = evt.run_id ? this._pendingToolSteps[evt.run_id] : null;
            if (step) {
                step.classList.remove('typing-step-running', 'typing-step-enter');
                step.classList.add(evt.error ? 'typing-step-error' : 'typing-step-done');
                void step.offsetHeight;

                // Duration in die Summary eintragen
                const summary = step.querySelector('summary');
                if (summary && evt.duration_ms != null) {
                    let dur = summary.querySelector('.step-duration');
                    if (!dur) {
                        dur = document.createElement('span');
                        dur.className = 'step-duration';
                        summary.insertBefore(dur, summary.querySelector('.step-chevron'));
                    }
                    dur.textContent = this._formatDuration(evt.duration_ms);
                }

                // Preview in den Body einfügen + Chevron sichtbar machen
                if (evt.preview) {
                    const body = step.querySelector('.typing-step-body');
                    if (body) {
                        const pre = document.createElement('pre');
                        pre.className = 'typing-step-preview';
                        pre.textContent = evt.preview;
                        body.appendChild(pre);
                    }
                    // Chevron einblenden wenn noch nicht vorhanden
                    if (summary && !summary.querySelector('.step-chevron')) {
                        const ch = document.createElement('span');
                        ch.className = 'step-chevron';
                        ch.textContent = '›';
                        summary.appendChild(ch);
                    }
                    step.classList.remove('typing-step-noexpand');
                }

                delete this._pendingToolSteps[evt.run_id];
            } else {
                // Kein Start-Step gefunden → eigenständigen Ergebnis-Step erzeugen
                const resultLabel = evt.tool_name || 'Tool-Ergebnis';
                this._appendStep(resultLabel, {
                    state: evt.error ? 'error' : 'done',
                    phase: 'tool',
                    phaseLabel: this._tracePhaseLabel('tool'),
                    tool: evt.tool_name,
                    duration_ms: evt.duration_ms,
                    result_size: evt.result_size,
                    error: evt.error,
                    preview: evt.preview || '',
                });
            }
        }
    },

    _closeOpenMarkdownFence(text) {
        const lines = String(text || '').split('\n');
        let openFence = null;

        for (const line of lines) {
            const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
            if (!match) continue;

            const marker = match[1];
            const markerChar = marker[0];
            if (!openFence) {
                openFence = { markerChar, length: marker.length };
            } else if (markerChar === openFence.markerChar && marker.length >= openFence.length) {
                openFence = null;
            }
        }

        if (!openFence) return text;
        const closingFence = openFence.markerChar.repeat(openFence.length);
        return text.endsWith('\n') ? `${text}${closingFence}` : `${text}\n${closingFence}`;
    },

    _renderMarkdownSafe(buffer, { final }) {
        if (!buffer) return '';
        if (final) return this.formatText(buffer);
        let preview = this._closeOpenMarkdownFence(buffer);
        const ls = preview.split('\n');
        const tl = ls.filter(l => /^\|.*\|/.test(l.trim()));
        if (tl.length >= 3) {
            const [h, s] = [tl[0], tl[1]];
            const stable = /^\|?[\s\-:|]+\|?$/.test(s) && s.includes('---');
            const hasData = /^\|.*\|/.test(tl[tl.length - 1]);
            if (!stable || !hasData) {
                const fp = preview.indexOf('|');
                const ln = preview.lastIndexOf('\n', fp);
                preview = ln > 0 ? preview.slice(0, ln) : preview.slice(0, fp > 0 ? fp : preview.length);
            }
        }
        preview = preview.replace(/\[([^\]]*?)$/, '&#91;$1');
        let html;
        if (typeof marked !== 'undefined') {
            html = marked.parse(preview, { breaks: true, gfm: true });
        } else {
            html = this._escapeHtml(preview).replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\n/g, '<br>');
        }
        const sanitized = (typeof DOMPurify !== 'undefined') ? DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'rel'], FORBID_TAGS: ['script', 'style', 'iframe', 'form', 'input'], ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/api\/images\/|data:image\/(?:png|jpeg|jpg|webp);base64,)/i }) : this._escapeHtml(preview);
        return sanitized.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ');
    },

    async _streamResponse(text, res, historyIdOverride = null) {
        let aiBubble = null, aiTextEl = null, buffer = '', msgId = null, meta = null, done = false;
        let lastRender = 0;
        const COOLDOWN = 40;
        let pending = false;
        let pendingTimeout = null;
        // Typing-Bubble (mit Denkschritten) bleibt sichtbar, BIS final-Frame kommt.
        // Tokens streamen daneben in eine eigene AI-Bubble, die beim ersten Token
        // angelegt wird (typing-Bubble bleibt im Hintergrund sichtbar).
        const ensureBubble = () => {
            if (aiBubble) return;
            aiBubble = this.addChatMessage('ai', '');
            if (aiBubble && msgId) aiBubble.dataset.serverMsgId = msgId;
            aiTextEl = aiBubble?.querySelector('.chat-bubble-text') || aiBubble?.querySelector('.message-text') || null;
        };
        // Beim Abschluss: Typing-Bubble in Denkschritte-Wrapper umwandeln und in
        // die AI-Bubble einbetten (preserveSteps).
        const finalizeBubble = () => {
            document.querySelectorAll('#typing-steps .typing-step-running').forEach((step) => {
                step.classList.remove('typing-step-running', 'typing-step-enter');
                step.classList.add('typing-step-done');
            });
            this.hideTyping();
            if (!aiBubble || !this._savedSteps) return;
            const hasSteps = this._savedSteps.querySelector('.typing-step');
            if (!hasSteps) { this._savedSteps = null; return; }
            const bubble = aiBubble.querySelector('.chat-bubble');
            const textEl = bubble?.querySelector('.chat-bubble-text');
            if (bubble && textEl && !bubble.querySelector('.typing-steps-preserved')) {
                this._savedSteps.classList.add('typing-steps-preserved');
                bubble.insertBefore(this._savedSteps, textEl);
            }
            this._savedSteps = null;
        };
        const update = (txt, final) => {
            ensureBubble();
            if (!aiTextEl) return;
            if (final && pendingTimeout) { clearTimeout(pendingTimeout); pendingTimeout = null; pending = false; }
            const now = Date.now();
            if (!final && now - lastRender < COOLDOWN && !pending) {
                pending = true;
                pendingTimeout = setTimeout(() => {
                    pendingTimeout = null;
                    pending = false;
                    if (!aiTextEl) return;
                    aiTextEl.innerHTML = this._renderMarkdownSafe(txt, { final: false });
                    lastRender = Date.now();
                }, COOLDOWN - (now - lastRender));
                return;
            }
            lastRender = now;
            aiTextEl.innerHTML = this._renderMarkdownSafe(txt, { final });
            if (aiBubble?.dataset?.msgId) { const tr = this._chatMessages.find(m => m.id === aiBubble.dataset.msgId); if (tr) tr.text = txt; }
            if (final) document.getElementById('chat-messages')?.scrollTo(0, document.getElementById('chat-messages').scrollHeight);
        };
        let reader = null;
        try {
            reader = res.body.getReader();
            const decoder = new TextDecoder();
            let remainder = '';
            while (!done) {
                const { done: rd, value } = await reader.read();
                if (rd) break;
                const chunk = decoder.decode(value, { stream: true });
                const lines = (remainder + chunk).split('\n');
                remainder = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const jsonStr = line.slice(6);
                    if (!jsonStr.trim()) continue;
                    let frame;
                    try { frame = JSON.parse(jsonStr); } catch (_) { continue; }
                    switch (frame.type) {
                        case 'start':
                            // Typing-Bubble bleibt absichtlich sichtbar — Denkschritte
                            // werden erst beim ersten echten Token oder beim final-Frame
                            // ersetzt (lazy via ensureBubble()).
                            msgId = frame.message_id;
                            break;
                        case 'token':
                            this._settleThinkingHeader();
                            buffer += frame.text;
                            update(buffer);
                            break;
                        case 'final':
                            done = true;
                            meta = frame.meta || {};
                            if (frame.response || buffer) update(frame.response || buffer, true);
                            finalizeBubble();
                            if (meta.confirmation_required && meta.safeguard) { this._safeguardPendingMessage = text; this._showSafeguardConfirmPrompt(meta.safeguard); }
                            if (meta.safeguard?.auto_decided && meta.safeguard?.auto_decision === 'allow') this.addChatMeta(`⚡ ${t('safeguard.autoAllowed')}`);
                            if (meta.compacted) { this.addCompactionNotice(); const ctxEl = document.getElementById('ctx-indicator'); if (ctxEl) { ctxEl.classList.remove('ctx-flash'); void ctxEl.offsetWidth; ctxEl.classList.add('ctx-flash'); setTimeout(() => ctxEl.classList.remove('ctx-flash'), 1000); } }
                            if (meta.context_budget) this._updateCtxIndicator(meta.context_budget);
                            if (meta.routing_confidence !== null && meta.routing_confidence < 0.7) this.addChatMeta(`⚠️ Unsicheres Routing (${Math.round(meta.routing_confidence * 100)} % Konfidenz) – Modul-Zuweisung könnte ungenau sein.`);
                            if (frame.response || buffer) this._saveToHistory(text, frame.response || buffer, historyIdOverride);
                            break;
                        case 'cancelled':
                            done = true;
                            update(frame.partial_response || buffer, true);
                            finalizeBubble();
                            this.addChatMeta(tf('chat.cancelled', 'Antwort wurde abgebrochen.'));
                            break;
                        case 'error':
                            done = true;
                            update(buffer || frame.message || t('chat.errorProcessing'), true);
                            finalizeBubble();
                            break;
                    }
                }
            }
        } catch (err) {
            this.hideTyping();
            if (err.name !== 'AbortError') this.addChatMessage('ai', t('chat.errorConnection'));
        } finally {
            if (pendingTimeout) { clearTimeout(pendingTimeout); pendingTimeout = null; }
            if (reader) { try { await reader.cancel(); } catch (_) { /* already closed */ } }
        }
    },

    formatText(text) {
        // [NINKO_IMAGE:url] → inline <img> Tag
        // SECURITY NOTE: Erlaubt beliebige https:// URLs als img src.
        // Wenn der LLM kompromittiert ist, könnte er bösartige Bilder einbetten.
        // Dies ist eine bewusste Design-Entscheidung (IT-Dashboard zeigt Screenshots/Diagramme).
        // Soll dies eingeschränkt werden: ALLOWED_URI_REGEXP anpassen und nur /api/images/ erlauben.
        text = text.replace(/\[(?:NINKO_IMAGE|KUMIO_IMAGE):([^\]]+)\]/g, (_, url) =>
            `<img src="${this._escapeAttr(url)}" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">`);
        // Fallback: /api/images/ URLs die der LLM als Link formatiert hat
        text = text.replace(/<a[^>]*href="(\/api\/images\/[\w\-]+\.\w+)"[^>]*>[^<]*<\/a>/g, (_, url) =>
            `<img src="${this._escapeAttr(url)}" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">`);
        // Fallback: nackte /api/images/ URLs im Text
        text = text.replace(/(?<![="])(\/api\/images\/[\w\-]+\.\w+)/g, (_, url) =>
            `<img src="${this._escapeAttr(url)}" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">`);
        text = text.replace(/(data:image\/(?:png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+)/g, (_, dataUrl) =>
            `<img src="${this._escapeAttr(dataUrl)}" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">`);
        if (typeof marked !== 'undefined') {
            // marked.js verfügbar: vollständiges Markdown-Rendering (Tabellen, Listen, etc.)
            const html = marked.parse(text, {
                breaks: true,
                gfm: true,
            });
            // HTML sanitisieren mit DOMPurify (graceful fallback wenn nicht verfügbar)
            const sanitized = (typeof DOMPurify !== 'undefined')
                ? DOMPurify.sanitize(html, {
                    ADD_ATTR: ['target', 'rel'],
                    FORBID_TAGS: ['script', 'style', 'iframe', 'form', 'input'],
                    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/api\/images\/|data:image\/(?:png|jpeg|jpg|webp);base64,)/i,
                })
                : this._escapeHtml(text);
            // Links immer in neuem Tab öffnen
            return sanitized.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ');
        }
        // Fallback: einfaches Inline-Rendering
        const escaped = this._escapeHtml(text);
        return escaped
            .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
            .replace(/\n/g, '<br>');
    },

    // --- WebSocket ---
    _wsReconnectTimer: null,  // Cancelt vorherigen Reconnect, falls connectWebSocket mehrfach aufgerufen wird
    _wsReconnectAttempts: 0,   // Counter für exponential backoff (cap 6 → max ~32s)
    _wsMaxReconnectAttempts: 6,

    connectWebSocket() {
        // Vorherigen pending Reconnect canceln, damit nicht mehrere Reconnect-Loops parallel laufen
        if (this._wsReconnectTimer != null) {
            clearTimeout(this._wsReconnectTimer);
            this._wsReconnectTimer = null;
        }

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${proto}//${location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                this._wsReconnectAttempts = 0;  // Reset backoff bei erfolgreichem Connect
                this.setStatus('connected', 'status.connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWsMessage(data);
                } catch {
                    // Non-JSON
                }
            };

            this.ws.onclose = () => {
                this.setStatus('disconnected', 'status.disconnected');
                // Reconnect mit exponential backoff (5s, 10s, 20s, 40s, 80s, 160s, dann aufgeben)
                if (this._wsReconnectAttempts >= this._wsMaxReconnectAttempts) {
                    logger.warn('WebSocket reconnect limit reached; user must reload');
                    return;
                }
                const delayMs = Math.min(5000 * Math.pow(2, this._wsReconnectAttempts), 160000);
                this._wsReconnectAttempts += 1;
                this._wsReconnectTimer = setTimeout(() => this.connectWebSocket(), delayMs);
            };

            this.ws.onerror = () => {
                this.setStatus('disconnected', 'status.error');
            };
        } catch {
            this.setStatus('disconnected', 'status.error');
        }
    },

    handleWsMessage(data) {
        const type = data.type || data.event_type || '';
        const severity = data.severity || 'info';

        if (type === 'alert' || type === 'incident_detected') {
            showNotification(
                data.message || data.data?.error || 'Alarm erkannt',
                severity === 'critical' ? 'error' : 'warning'
            );
            // Alert zu Cache hinzufügen für Settings-Panel
            this._handleWsAlert(data);
        } else if (type === 'task_executed') {
            showNotification(
                `Aufgabe "${data.task_name}" ausgeführt (${data.duration_ms}ms)`,
                data.status === 'ok' ? 'success' : 'error'
            );
        } else if (type === 'agent_job_finished') {
            showNotification(
                `Agent-Job "${data.agent_name}" beendet: ${data.status} (${data.duration_ms}ms)`,
                data.status === 'succeeded' ? 'success' : 'error'
            );
            // Offenes Jobs-Panel aktualisieren
            if (this._agentJobsAgentId === data.agent_id) this.loadAgentJobs();
        } else if (type === 'module_health') {
            // Update module health indicators
        } else if (type === 'log') {
            console.log('[WS Log]', data);
        }
    },

    setStatus(state, labelKey) {
        const dot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');

        if (dot) dot.className = `status-dot ${state}`;
        if (statusText) {
            statusText.dataset.i18n = labelKey;
            statusText.textContent = t(labelKey);
        }
    },

    // --- Settings ---
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

    toggleSettings() {
        this.switchTab('settings');
    },

    switchSettingsTab(tabId) {
        // Stop log polling when leaving logs sub-panel
        this.stopLogPolling();

        const tabButtons = Array.from(document.querySelectorAll('#subnav-settings .settings-tab[data-settings-tab]'));
        const validTabs = new Set(tabButtons.map((btn) => btn.dataset.settingsTab).filter(Boolean));
        const fallbackTab = tabButtons[0]?.dataset.settingsTab || 'llm';
        const targetTab = validTabs.has(tabId) ? tabId : fallbackTab;

        document.querySelectorAll('#subnav-settings .settings-tab').forEach(t => {
            t.classList.remove('active');
            t.removeAttribute('aria-current');
        });
        document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));

        const activeBtn = document.querySelector(`#subnav-settings .settings-tab[data-settings-tab="${targetTab}"]`);
        activeBtn?.classList.add('active');
        activeBtn?.setAttribute('aria-current', 'page');
        document.getElementById(`settings-panel-${targetTab}`)?.classList.add('active');

        // Load content when switching tabs
        if (targetTab === 'llm') { this.loadLlmSettings(); this.loadLlmProviders(); this.loadEmbedModel(); this.loadRoutingMode(); }
        if (targetTab === 'modules') { this.loadModulesSettings(); this.loadMarketplaceConfig(); }
        if (targetTab === 'skills') { this.loadSettingsSkillsList(); }
        if (targetTab === 'system') this.loadBrandingForm();
        if (targetTab === 'themes') this.loadThemesSettings();
        if (targetTab === 'language') this.renderLanguageTab();
        if (targetTab === 'tts') { this.loadSttSettings(); this.loadTtsSettings(); this.loadTtsVoices(); }
        if (targetTab === 'imagegen') { this.loadImageGenProvider(); this.loadOcrSettings(); }
        if (targetTab === 'access') this.loadRbacSettings();
        if (targetTab === 'safeguard') this.renderSafeguardSettingsPanel();
        if (targetTab === 'logs') this.startLogPolling();
        if (targetTab === 'alerts') this.loadAlerts();
        this._updateBreadcrumb();
        this._persistRoute();
    },

    // --- Language ---
    async setLanguage(lang) {
        // UI sofort aktualisieren
        await I18n.load(lang);
        localStorage.setItem('ninko_lang', lang);
        if (document.querySelector('.welcome-message')) this.renderWelcomeState();
        else this._updateChatInputState(this._chatMessages.length ? 'reply' : 'ask');
        // JS-gerenderte Kategorie-Labels der Modul-Sidebar sofort in neuer Sprache zeigen
        if (this._moduleNavItems?.length) this._renderModuleSidebar();
        // Preset-Namen der Hintergrundfarben ebenfalls live umschalten
        if (document.getElementById('bg-preset-list')) this._renderBackgroundPresets();

        // Aktiven Zustand der Sprach-Buttons aktualisieren
        document.querySelectorAll('.lang-btn').forEach(btn => {
            btn.classList.toggle('lang-btn-active', btn.dataset.lang === lang);
        });

        // Im Backend speichern
        try {
            await fetch('/api/settings/language', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ language: lang }),
            });
            showNotification(t('settings.langSaved'), 'success');
        } catch {
            showNotification('Error saving language', 'error');
        }
    },

    renderLanguageTab() {
        const container = document.getElementById('settings-panel-language');
        if (!container) return;

        const currentLang = localStorage.getItem('ninko_lang') || 'de';
        const languages = [
            { code: 'de', flag: '🇩🇪', label: 'Deutsch' },
            { code: 'en', flag: '🇬🇧', label: 'English' },
            { code: 'fr', flag: '🇫🇷', label: 'Français' },
            { code: 'es', flag: '🇪🇸', label: 'Español' },
            { code: 'it', flag: '🇮🇹', label: 'Italiano' },
            { code: 'nl', flag: '🇳🇱', label: 'Nederlands' },
            { code: 'pl', flag: '🇵🇱', label: 'Polski' },
            { code: 'pt', flag: '🇵🇹', label: 'Português' },
            { code: 'ja', flag: '🇯🇵', label: '日本語' },
            { code: 'zh', flag: '🇨🇳', label: '中文' },
        ];

        container.innerHTML = `
            <div class="settings-header">
                <h2 data-i18n="settings.language">${t('settings.language')}</h2>
                <p class="settings-description" data-i18n="settings.langDesc">${t('settings.langDesc')}</p>
            </div>
            <div class="setting-group">
                <h4 data-i18n="settings.langTitle">${t('settings.langTitle')}</h4>
                <div class="lang-grid">
                    ${languages.map(l => `
                        <button class="lang-btn ${l.code === currentLang ? 'lang-btn-active' : ''}"
                            data-lang="${l.code}"
                            data-action="setLanguage" data-args="${JSON.stringify([l.code]).replace(/\"/g, '&quot;')}">
                            <span class="lang-flag">${l.flag}</span>
                            <span class="lang-name">${l.label}</span>
                        </button>
                    `).join('')}
                </div>
            </div>`;
    },

    async loadSettingsContent() {
        const activeTab = document.querySelector('#subnav-settings .settings-tab.active[data-settings-tab]')?.dataset.settingsTab || 'llm';
        this.switchSettingsTab(activeTab);
    },

    // --- LLM Settings ---
    async loadLlmSettings() {
        try {
            const res = await fetch('/api/settings/llm');
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();

            document.getElementById('llm-backend').value = data.backend;
            document.getElementById('llm-base-url').value = data.base_url;
            document.getElementById('llm-model').value = data.model;
            document.getElementById('llm-embed-model').value = data.embed_model;

            const statusEl = document.getElementById('llm-save-status');
            statusEl.innerHTML = data.source === 'redis' ? '<span class="sf sf-ok">Gespeichert</span>' : '<span class="sf sf-loading">Standard</span>';
            statusEl.className = 'save-status';
        } catch {
            document.getElementById('llm-save-status').innerHTML = '<span class="sf sf-error">Fehler beim Laden</span>';
        }
    },

    async saveLlmSettings() {
        const statusEl = document.getElementById('llm-save-status');
        statusEl.innerHTML = '<span class="sf sf-loading">Speichere…</span>';
        statusEl.className = 'save-status';

        try {
            const body = {
                backend: document.getElementById('llm-backend').value,
                base_url: document.getElementById('llm-base-url').value,
                model: document.getElementById('llm-model').value,
                embed_model: document.getElementById('llm-embed-model').value,
            };

            const res = await fetch('/api/settings/llm', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (res.ok) {
                statusEl.innerHTML = '<span class="sf sf-ok">Gespeichert</span>';
                statusEl.className = 'save-status';
                showNotification('LLM-Settings gespeichert', 'info');
            } else {
                statusEl.innerHTML = '<span class="sf sf-error">Fehler</span>';
                statusEl.className = 'save-status';
            }
        } catch {
            statusEl.innerHTML = '<span class="sf sf-error">Verbindungsfehler</span>';
            statusEl.className = 'save-status';
        }
    },

    // --- Memory & Secrets ---
    async viewMemoryStats() {
        try {
            const res = await fetch('/api/memory/stats');
            if (!res.ok) throw new Error(res.statusText);
            const stats = await res.json();
            showNotification(`Memory: ${stats.total_entries || 0} Einträge, ${stats.collections || 0} Collections`, 'info');
        } catch {
            showNotification('Memory-Stats nicht verfügbar', 'error');
        }
    },

    async viewSecrets() {
        try {
            const res = await fetch('/api/secrets/');
            if (!res.ok) throw new Error(res.statusText);
            const secrets = await res.json();
            const count = secrets.keys?.length || secrets.secrets?.length || 0;
            showNotification(`${count} Secrets konfiguriert`, 'info');
        } catch {
            showNotification('Secrets-API nicht verfügbar', 'error');
        }
    },

    // --- Textarea Auto-Resize ---
    autoResizeTextarea() {
        const textarea = document.getElementById('chat-input');
        if (textarea) {
            textarea.addEventListener('input', () => {
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 300) + 'px';
            });
        }
    },

    // --- Resizing ---
    initResizers() {
        // Migrate sidebar width when defaults change
        if (!localStorage.getItem('ninko_sidebar_migrated_v2')) {
            const savedWidth = localStorage.getItem('ninko_sidebar_width');
            if (savedWidth) {
                const boosted = Math.min(Math.round(parseInt(savedWidth) * 1.2), 500);
                localStorage.setItem('ninko_sidebar_width', boosted);
            }
            localStorage.setItem('ninko_sidebar_migrated_v2', '1');
        }

        this.setupResizer('sidebar-resizer', 'sidebar', 'ninko_sidebar_width');
        // history-resizer removed — history is now integrated into sidebar
    },

    setupResizer(resizerId, panelId, storageKey) {
        const resizer = document.getElementById(resizerId);
        const panel = document.getElementById(panelId) || document.querySelector(`.${panelId}`);
        if (!resizer || !panel) return;

        // Restore saved width
        const savedWidth = localStorage.getItem(storageKey);
        if (savedWidth) {
            panel.style.width = savedWidth + 'px';
        }

        let startX, startWidth;

        const onMouseDown = (e) => {
            startX = e.clientX;
            startWidth = panel.getBoundingClientRect().width;
            resizer.classList.add('active');
            document.body.classList.add('resizing');

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        };

        const onMouseMove = (e) => {
            const width = startWidth + (e.clientX - startX);
            // Apply limits (matching CSS)
            if (width >= 60 && width <= 600) {
                panel.style.width = width + 'px';
            }
        };

        const onMouseUp = () => {
            resizer.classList.remove('active');
            document.body.classList.remove('resizing');
            localStorage.setItem(storageKey, panel.getBoundingClientRect().width);

            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };

        resizer.addEventListener('mousedown', onMouseDown);
    },


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

    // -------------------------------------------------------
    //  LOGS
    // -------------------------------------------------------

    _logActiveLevels: new Set(['INFO', 'WARN', 'ERROR', 'CRIT']),
    _logAutoScroll: true,
    _logPollTimer: null,
    _logCache: [],

    async startLogPolling() {
        clearInterval(this._logPollTimer);
        await this.applyLogFilters();
        this._logPollTimer = setInterval(() => this.applyLogFilters(), 2000);
    },

    stopLogPolling() { clearInterval(this._logPollTimer); },

    toggleLogLevel(level, btn) {
        if (this._logActiveLevels.has(level)) {
            this._logActiveLevels.delete(level);
            btn.classList.remove('active');
        } else {
            this._logActiveLevels.add(level);
            btn.classList.add('active');
        }
        this.applyLogFilters();
    },

    async applyLogFilters() {
        const params = new URLSearchParams();
        if (this._logActiveLevels.size < 4 && this._logActiveLevels.size > 0) {
            params.set('level', [...this._logActiveLevels].join(','));
        }
        const cat = document.getElementById('log-filter-category')?.value;
        if (cat) params.set('category', cat);
        const search = document.getElementById('log-filter-search')?.value;
        if (search) params.set('search', search);
        const time = document.getElementById('log-filter-time')?.value;
        if (time) params.set('from_ts', (Date.now() / 1000 - parseInt(time) * 60).toString());
        params.set('limit', '500');

        try {
            const res = await fetch(`/api/logs/?${params}`);
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            this._logCache = data.entries || [];
            this._renderLogs();
        } catch (err) { console.warn('loadLogs failed', err); }
    },

    _renderLogs() {
        const tbody = document.getElementById('log-table-body');
        if (!tbody) return;
        if (!this._logCache.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Keine Log-Einträge gefunden.</td></tr>';
            return;
        }
        const levelColors = { INFO: 'log-info', WARN: 'log-warn', ERROR: 'log-error', CRIT: 'log-crit' };
        // Älteste zuerst anzeigen (neueste am Ende, Auto-Scroll zeigt aktuellste)
        const displayEntries = [...this._logCache].reverse();
        tbody.innerHTML = displayEntries.map((entry, idx) => `
            <tr class="log-row log-row-${(entry.level || 'INFO').toLowerCase()}" data-action="_showLogDetail" data-args="${JSON.stringify([this._logCache.length - 1 - idx]).replace(/\"/g, '&quot;')}">
                <td class="log-ts">${entry.timestamp || ''}</td>
                <td><span class="log-level-badge ${levelColors[entry.level] || 'log-info'}">${entry.level || 'INFO'}</span></td>
                <td class="log-cat">${entry.category || ''}</td>
                <td class="log-msg">${this._escapeHtml(entry.message || '')}</td>
            </tr>
        `).join('');
        if (this._logAutoScroll) {
            const wrapper = document.getElementById('log-table-wrapper');
            if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
        }
    },

    hideLogDetailPanel() {
        const p = document.getElementById('log-detail-panel');
        if (p) p.classList.add('hidden');
    },

    _showLogDetail(idx) {
        const entry = this._logCache[idx];
        if (!entry) return;
        const panel = document.getElementById('log-detail-panel');
        const content = document.getElementById('log-detail-content');
        panel.classList.remove('hidden');
        content.innerHTML = `
            <p><strong>Timestamp:</strong> ${entry.timestamp}</p>
            <p><strong>Level:</strong> ${entry.level}</p>
            <p><strong>Logger:</strong> ${entry.logger}</p>
            <p><strong>Kategorie:</strong> ${entry.category}</p>
            <p><strong>Message:</strong><br><code>${this._escapeHtml(entry.message || '')}</code></p>
            ${entry.traceback ? `<p><strong>Traceback:</strong></p><pre class="log-traceback">${this._escapeHtml(entry.traceback)}</pre>` : ''}
        `;
    },

    _escapeHtml(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    },

    _escapeAttr(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    _esc(str) {
        return this._escapeHtml(str);
    },

    toggleLogAutoScroll(enabled) { this._logAutoScroll = enabled; },

    exportLogs(format) {
        const data = this._logCache;
        if (!data.length) { showNotification('Keine Daten zum Exportieren', 'info'); return; }
        let content, type, ext;
        if (format === 'json') {
            content = JSON.stringify(data, null, 2);
            type = 'application/json'; ext = 'json';
        } else {
            const header = 'Timestamp,Level,Kategorie,Message\n';
            content = header + data.map(e => `"${e.timestamp}","${e.level}","${e.category}","${(e.message || '').replace(/"/g, "'")}"`).join('\n');
            type = 'text/csv'; ext = 'csv';
        }
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `ninko-logs.${ext}`;
        a.click(); URL.revokeObjectURL(url);
    },

    _handleSubagentStepSSE(data) {
        const stepType = data.step_type || '';
        const title = data.title || '';
        const stepId = data.step_id || '';
        const module = data.module || '';
        const stepsEl = document.getElementById('typing-steps');
        if (!stepsEl) return;

        if (stepType === 'step_start') {
            // Neuen aktiven Step einfügen (nutzt vorhandene Mechanik)
            this.updateTypingStatus(title);

        } else if (stepType === 'step_done') {
            // Bereits durch den nächsten step_start erledigt — kein Zusatz nötig

        } else if (stepType === 'step_error') {
            // Aktiven Step als Fehler markieren + Retry-Button hinzufügen
            const activeStep = stepsEl.querySelector('.typing-step-active');
            if (activeStep) {
                activeStep.classList.remove('typing-step-active');
                activeStep.classList.add('typing-step-error');
                const spinner = activeStep.querySelector('.typing-spinner');
                if (spinner) spinner.outerHTML = '<span class="typing-error-icon">✗</span>';

                if (data.suggested_retry) {
                    const retryBtn = document.createElement('button');
                    retryBtn.className = 'btn-step-retry';
                    retryBtn.title = 'Schritt wiederholen';
                    retryBtn.textContent = '↺';
                    retryBtn.onclick = () => this._retrySubagentStep(stepId, module);
                    activeStep.appendChild(retryBtn);
                }
            }
        }
    },

    async _retrySubagentStep(stepId, module) {
        try {
            const res = await fetch('/api/subagent/retry-step', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    module,
                    step_id: stepId,
                }),
            });
            const data = await res.json();
            if (data.status !== 'success') {
                showNotification(`Retry fehlgeschlagen: ${data.error || 'Unbekannter Fehler'}`, 'error');
            }
        } catch (e) {
            showNotification('Retry-Anfrage fehlgeschlagen', 'error');
        }
    },
};


// --- Global Helpers ---
function showNotification(message, type = 'info') {
    const container = document.getElementById('notifications');
    const div = document.createElement('div');
    div.className = `notification ${type}`;
    div.textContent = message;
    container.appendChild(div);

    setTimeout(() => {
        div.style.opacity = '0';
        div.style.transform = 'translateX(100px)';
        div.style.transition = 'all 300ms ease';
        setTimeout(() => div.remove(), 300);
    }, 5000);
}

function switchTab(tabId) {
    Ninko.switchTab(tabId);
}

// --- Export für HTML-Event-Handler ---
window.Ninko = Ninko;
window.I18n = I18n;

// --- Boot ---
(() => {
    let bootStarted = false;
    const boot = () => {
        if (bootStarted) return;
        bootStarted = true;
        Ninko.init();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot, { once: true });
    } else {
        boot();
    }

    window.addEventListener('pageshow', () => {
        if (!bootStarted) boot();
    });
})();

// ── Event-Delegation Dispatcher ────────────────────────────────────────────
(function () {
    function _callNinko(method, args) {
        if (typeof Ninko[method] !== 'function') return;
        Ninko[method](...args);
    }

    document.addEventListener('click', function (e) {
        let el = e.target.closest('[data-actions]');
        if (el) {
            try {
                JSON.parse(el.dataset.actions).forEach(([m, ...a]) => _callNinko(m, a));
            } catch (_) {}
            return;
        }
        el = e.target.closest('[data-action]');
        if (!el) return;
        if (el.dataset.stopPropagation === 'true') e.stopPropagation();
        const method = el.dataset.action;
        let args = [];
        try { args = el.dataset.args ? JSON.parse(el.dataset.args) : []; } catch (_) {}
        if (el.dataset.event === 'true') args = [e, ...args];
        if (el.dataset.self === 'true') args = [...args, el];
        _callNinko(method, args);
    });

    document.addEventListener('change', function (e) {
        const el = e.target;
        const method = el.dataset.change;
        if (!method) return;
        let args = [];
        if (el.dataset.useValue === 'true') args = [el.value];
        else if (el.dataset.useChecked === 'true') args = [el.checked];
        _callNinko(method, args);
    });

    document.addEventListener('input', function (e) {
        const el = e.target;
        const method = el.dataset.input;
        if (!method) return;
        const args = el.dataset.useValue === 'true' ? [el.value] : [];
        _callNinko(method, args);
    });

    // Textarea Enter-Shortcut (ersetzt inline onkeydown)
    document.addEventListener('DOMContentLoaded', function () {
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    Ninko.sendMessage();
                }
            });
        }
    });
})();
