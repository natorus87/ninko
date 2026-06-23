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
            parts.push('Settings');
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
        const labels = {
            infrastructure: '🏗️ Infrastructure',
            network: '🌐 Network',
            monitoring: '📊 Monitoring',
            productivity: '📋 Productivity',
            communication: '💬 Communication',
            cloud: '☁️ Cloud & Hosting',
            iot: '🏠 IoT & Smart Home',
            other: '📦 Other',
        };
        return labels[category] || labels.other;
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
                    <button class="settings-tab settings-tab-sub module-nav-btn${active}" data-module-tab="${this._escapeHtml(item.tabId)}">
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
            parts.push('<div class="module-nav-group-label">⭐ Favorites</div>');
            parts.push(...renderUniqueRows(favorites));
        }
        if (recent.length) {
            parts.push('<div class="module-nav-group-label">🕐 Recently Used</div>');
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
            parts.push('<div class="module-subnav-empty">Keine Module gefunden.</div>');
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
        document.querySelectorAll('#subnav-automatisierung .settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(
            `#subnav-automatisierung .settings-tab[data-auto-tab="${tabId}"], ` +
            `#subnav-automatisierung .settings-tab[data-auto-link="${tabId}"]`
        )?.classList.add('active');
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
        menu.style.display = isOpen ? 'none' : 'block';
        wrap.classList.toggle('open', !isOpen);
    },

    closeChatPlusMenu() {
        const wrap = document.getElementById('chat-plus-menu');
        const menu = document.getElementById('chat-plus-dropdown');
        if (menu) menu.style.display = 'none';
        if (wrap) wrap.classList.remove('open');
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
        container.innerHTML = this.getWelcomeHtml();
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

    // --- SafeGuard (Profile-System) -----------------------------------------

    // _safeguardProfiles: alle Profile (built-in + custom)
    // _safeguardActiveId: aktuell globales Profil
    // _safeguardPickerOpen: Popover-Status

    async initSafeguard() {
        try {
            const [statusRes, profilesRes] = await Promise.all([
                fetch('/api/safeguard/status'),
                fetch('/api/safeguard/profiles'),
            ]);
            if (statusRes.ok) {
                const data = await statusRes.json();
                this._safeguardEnabled = !!data.enabled;
                this._safeguardActiveId = data.profile_id || 'moderate';
            }
            if (profilesRes.ok) {
                this._safeguardProfiles = await profilesRes.json();
            }
            this._updateSafeguardBtn();
        } catch (err) { console.warn('loadSafeguardActive failed', err); }
    },

    // Öffnet/schließt den Profil-Picker im Chat-Toolbar
    toggleSafeguardPicker(event) {
        event.stopPropagation();
        const picker = document.getElementById('safeguard-picker');
        if (!picker) return;
        if (this._safeguardPickerOpen) {
            this._closeSafeguardPicker();
            return;
        }
        this._renderSafeguardPicker(picker);
        picker.style.display = 'block';
        this._safeguardPickerOpen = true;
        // Außerhalb klicken → schließen
        setTimeout(() => {
            document.addEventListener('click', this._onPickerOutsideClick, { once: true });
        }, 0);
    },

    _onPickerOutsideClick(e) {
        const picker = document.getElementById('safeguard-picker');
        if (picker && !picker.contains(e.target)) {
            Ninko._closeSafeguardPicker();
        }
    },

    _closeSafeguardPicker() {
        const picker = document.getElementById('safeguard-picker');
        if (picker) picker.style.display = 'none';
        this._safeguardPickerOpen = false;
    },

    _renderSafeguardPicker(picker) {
        const profiles = this._safeguardProfiles || [];
        const activeId = this._safeguardActiveId || 'moderate';
        const header = document.createElement('div');
        header.className = 'sg-picker-header';
        header.textContent = t('safeguard.pickProfile');
        const buttons = profiles.map(p => {
            const isActive = p.id === activeId;
            const scopeBadge = this._sgScopeBadge(p);
            const btn = document.createElement('button');
            btn.className = 'sg-picker-item' + (isActive ? ' active' : '');
            btn.dataset.action = '_selectSafeguardProfile';
            btn.dataset.args = JSON.stringify([p.id]);
            const nameSpan = document.createElement('span');
            nameSpan.className = 'sg-picker-name';
            nameSpan.textContent = p.name;
            const scopeSpan = document.createElement('span');
            scopeSpan.className = 'sg-picker-scope';
            scopeSpan.textContent = scopeBadge;
            btn.append(nameSpan, scopeSpan);
            return btn;
        });
        const footer = document.createElement('div');
        footer.className = 'sg-picker-footer';
        const settingsBtn = document.createElement('button');
        settingsBtn.className = 'sg-picker-settings';
        settingsBtn.dataset.actions = '[["_closeSafeguardPicker"],["switchTab","settings"],["switchSettingsTab","safeguard"]]';
        settingsBtn.textContent = t('safeguard.manageProfiles');
        footer.appendChild(settingsBtn);
        picker.replaceChildren(header, ...buttons, footer);
    },

    _sgScopeBadge(p) {
        if (p.auto_mode) return '⚡';
        if (!p.check_user_messages && !p.check_tool_calls) return '⊘';
        if (p.check_user_messages && p.check_tool_calls) return '●●';
        if (p.check_user_messages) return '👤';
        return '🤖';
    },

    _sgToggleAutoPolicy() {
        const on = document.getElementById('sg-editor-auto-mode')?.checked;
        const row = document.getElementById('sg-editor-policy-row');
        if (row) row.style.display = on ? 'flex' : 'none';
    },

    async _selectSafeguardProfile(profileId) {
        this._closeSafeguardPicker();
        try {
            const res = await fetch('/api/safeguard/active', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_id: profileId }),
            });
            if (res.ok) {
                this._safeguardActiveId = profileId;
                const profile = (this._safeguardProfiles || []).find(p => p.id === profileId);
                this._safeguardEnabled = profile ? (profile.check_user_messages || profile.check_tool_calls) : true;
                this._updateSafeguardBtn();
            }
        } catch (err) { console.warn('selectSafeguardProfile failed', err); }
    },

    // Backward-compat: einfacher Toggle (Moderate ↔ Disabled)
    async toggleSafeguard() {
        const targetId = this._safeguardEnabled ? 'disabled' : 'moderate';
        await this._selectSafeguardProfile(targetId);
    },

    _updateSafeguardBtn() {
        const btn = document.getElementById('btn-safeguard');
        if (!btn) return;
        const profile = (this._safeguardProfiles || []).find(p => p.id === this._safeguardActiveId);
        const name = profile ? profile.name : (this._safeguardEnabled ? 'Moderate' : 'Disabled');
        if (this._safeguardEnabled) {
            btn.classList.add('safeguard-on');
            btn.classList.remove('safeguard-off');
        } else {
            btn.classList.remove('safeguard-on');
            btn.classList.add('safeguard-off');
        }
        btn.title = `SafeGuard: ${name}`;
    },

    _showSafeguardConfirmPrompt(sg) {
        document.getElementById('safeguard-confirm-prompt')?.remove();
        const container = document.getElementById('chat-messages');
        const catClass = `sg-${(sg.category || 'unknown').toLowerCase().replace('_', '-')}`;
        const isInjection = sg.category === 'PROMPT_INJECTION';
        const div = document.createElement('div');
        div.className = 'safeguard-confirm-prompt';
        div.id = 'safeguard-confirm-prompt';
        div.innerHTML = `
            <div class="safeguard-confirm-content">
                <span class="safeguard-confirm-category ${catClass}">${sg.category}</span>
                ${isInjection ? `<p class="sg-injection-warning">${t('safeguard.injectionWarning')}</p>` : ''}
                <p class="sg-rationale">${this._escapeHtml(sg.rationale || '')}</p>
                <div class="safeguard-confirm-actions">
                    <button class="btn-confirm-action btn-confirm-run" data-action="confirmSafeguardAction">${t('safeguard.confirmRun')}</button>
                    <button class="btn-confirm-action btn-confirm-cancel" data-action="cancelSafeguardAction">${t('safeguard.confirmCancel')}</button>
                </div>
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    async confirmSafeguardAction() {
        if (!this._safeguardPendingMessage) return;
        document.getElementById('safeguard-confirm-prompt')?.remove();
        const msg = this._safeguardPendingMessage;
        this._safeguardPendingMessage = null;
        const input = document.getElementById('chat-input');
        input.value = msg;
        this._confirmedPending = true;
        await this.sendMessage();
    },

    cancelSafeguardAction() {
        this._safeguardPendingMessage = null;
        document.getElementById('safeguard-confirm-prompt')?.remove();
    },

    // --- SafeGuard Settings Panel -------------------------------------------

    async renderSafeguardSettingsPanel() {
        try {
            const [profilesRes, activeRes] = await Promise.all([
                fetch('/api/safeguard/profiles'),
                fetch('/api/safeguard/active'),
            ]);
            if (!profilesRes.ok || !activeRes.ok) return;
            this._safeguardProfiles = await profilesRes.json();
            const activeData = await activeRes.json();
            this._safeguardActiveId = activeData.profile_id;
            this._safeguardEnabled = this._safeguardActiveId !== 'disabled';
            this._updateSafeguardBtn();
        } catch { return; }

        this._renderSgGlobalSelect();
        this._renderSgProfileLists();
    },

    _renderSgGlobalSelect() {
        const sel = document.getElementById('sg-global-profile');
        if (!sel) return;
        sel.innerHTML = (this._safeguardProfiles || []).map(p =>
            `<option value="${this._escapeHtml(p.id)}" ${p.id === this._safeguardActiveId ? 'selected' : ''}>${this._escapeHtml(p.name)}</option>`
        ).join('');
        this._updateSgProfileDetails(this._safeguardActiveId);
    },

    _updateSgProfileDetails(profileId) {
        const profile = (this._safeguardProfiles || []).find(p => p.id === profileId);
        const box = document.getElementById('sg-profile-details');
        const badges = document.getElementById('sg-profile-badges');
        if (!profile || !box || !badges) return;
        box.style.display = 'block';
        const scopeLabel = profile.auto_mode ? t('safeguard.scopeAuto')
            : profile.check_user_messages && profile.check_tool_calls ? t('safeguard.scopeBoth')
            : profile.check_user_messages ? t('safeguard.scopeUser')
            : profile.check_tool_calls ? t('safeguard.scopeLLM')
            : t('safeguard.scopeNone');
        badges.innerHTML = `
            <span class="sg-detail-badge${profile.auto_mode ? ' sg-cat-auto' : ''}">${scopeLabel}</span>
            ${profile.confirm_categories.map(c => `<span class="sg-cat-badge sg-cat-${this._escapeHtml(c.toLowerCase().replace('_','-'))}">${this._escapeHtml(c)}</span>`).join('')}
            ${profile.detect_prompt_injection ? `<span class="sg-detail-badge sg-injection-badge">${t('safeguard.injectionDetect')}</span>` : ''}
            ${profile.fail_open ? `<span class="sg-detail-badge sg-failopen-badge">${t('safeguard.failOpen')}</span>` : ''}
            ${profile.auto_mode ? `<span class="sg-cat-badge sg-cat-auto">⚡ ${t('safeguard.autoMode')}</span>` : ''}
        `;
    },

    async setSafeguardGlobalProfile(profileId) {
        try {
            const res = await fetch('/api/safeguard/active', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_id: profileId }),
            });
            if (res.ok) {
                this._safeguardActiveId = profileId;
                this._safeguardEnabled = profileId !== 'disabled';
                this._updateSafeguardBtn();
                this._updateSgProfileDetails(profileId);
            }
        } catch (err) { console.warn('selectSafeguardProfile failed', err); }
    },

    _renderSgProfileLists() {
        const profiles = this._safeguardProfiles || [];
        const custom = profiles.filter(p => !p.builtin);
        const builtin = profiles.filter(p => p.builtin);

        const customList = document.getElementById('sg-custom-profiles-list');
        if (customList) {
            if (custom.length === 0) {
                customList.innerHTML = `<p class="text-muted" style="font-size:0.85rem;" data-i18n="safeguard.noCustomProfiles">${t('safeguard.noCustomProfiles')}</p>`;
            } else {
                customList.innerHTML = custom.map(p => this._renderSgProfileCard(p, false)).join('');
            }
        }

        const builtinList = document.getElementById('sg-builtin-profiles-list');
        if (builtinList) {
            builtinList.innerHTML = builtin.map(p => this._renderSgProfileCard(p, true)).join('');
        }
    },

    _renderSgProfileCard(p, readonly) {
        const cats = p.confirm_categories.map(c =>
            `<span class="sg-cat-badge sg-cat-${this._escapeHtml(c.toLowerCase().replace('_','-'))}">${this._escapeHtml(c)}</span>`
        ).join('');
        const scopeIco = this._sgScopeBadge(p);
        const injIco = p.detect_prompt_injection ? ' 🔍' : '';
        const autoIco = p.auto_mode ? ` <span class="sg-cat-badge sg-cat-auto" title="${this._escapeHtml(t('safeguard.autoModeDesc'))}">⚡ ${this._escapeHtml(t('safeguard.autoMode'))}</span>` : '';
        const escapedId = this._escapeHtml(p.id);
        const escapedName = this._escapeHtml(p.name);
        return `<div class="sg-profile-card">
            <div class="sg-profile-card-header">
                <span class="sg-profile-card-name">${escapedName}</span>
                <span class="sg-profile-card-id text-muted">${escapedId}</span>
                ${!readonly ? `
                    <div class="sg-profile-card-actions">
                        <button class="btn btn-xs btn-outline" data-action="openSafeguardProfileEditor" data-args="${JSON.stringify([escapedId]).replace(/\"/g, '&quot;')}">${t('safeguard.edit')}</button>
                        <button class="btn btn-xs btn-danger" data-action="deleteSafeguardProfile" data-args="${JSON.stringify([escapedId]).replace(/\"/g, '&quot;')}">${t('safeguard.delete')}</button>
                    </div>` : ''}
            </div>
            <div class="sg-profile-card-meta">
                <span class="sg-detail-badge">${scopeIco}</span>${cats}${injIco}${autoIco}
            </div>
        </div>`;
    },

    openSafeguardProfileEditor(profileId) {
        const editor = document.getElementById('sg-profile-editor');
        if (!editor) return;
        const title = document.getElementById('sg-editor-title');
        editor._editingId = profileId || null;

        if (profileId) {
            const p = (this._safeguardProfiles || []).find(x => x.id === profileId);
            if (!p) return;
            document.getElementById('sg-editor-id').value = p.id;
            document.getElementById('sg-editor-id').disabled = true; // ID nicht änderbar
            document.getElementById('sg-editor-name').value = p.name;
            document.getElementById('sg-editor-check-user').checked = p.check_user_messages;
            document.getElementById('sg-editor-check-tools').checked = p.check_tool_calls;
            document.getElementById('sg-editor-cat-destructive').checked = p.confirm_categories.includes('DESTRUCTIVE');
            document.getElementById('sg-editor-cat-state').checked = p.confirm_categories.includes('STATE_CHANGING');
            document.getElementById('sg-editor-cat-injection').checked = p.confirm_categories.includes('PROMPT_INJECTION');
            document.getElementById('sg-editor-injection').checked = p.detect_prompt_injection;
            document.getElementById('sg-editor-fail-open').checked = p.fail_open;
            document.getElementById('sg-editor-auto-mode').checked = !!p.auto_mode;
            document.getElementById('sg-editor-auto-policy').value = p.auto_mode_policy || '';
            if (title) title.textContent = t('safeguard.editProfile');
        } else {
            document.getElementById('sg-editor-id').value = '';
            document.getElementById('sg-editor-id').disabled = false;
            document.getElementById('sg-editor-name').value = '';
            document.getElementById('sg-editor-check-user').checked = true;
            document.getElementById('sg-editor-check-tools').checked = true;
            document.getElementById('sg-editor-cat-destructive').checked = true;
            document.getElementById('sg-editor-cat-state').checked = true;
            document.getElementById('sg-editor-cat-injection').checked = false;
            document.getElementById('sg-editor-injection').checked = false;
            document.getElementById('sg-editor-fail-open').checked = false;
            document.getElementById('sg-editor-auto-mode').checked = false;
            document.getElementById('sg-editor-auto-policy').value = '';
            if (title) title.textContent = t('safeguard.addProfile');
        }
        this._sgToggleAutoPolicy();
        document.getElementById('sg-editor-status').textContent = '';
        editor.style.display = 'block';
        editor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },

    closeSafeguardProfileEditor() {
        const editor = document.getElementById('sg-profile-editor');
        if (editor) editor.style.display = 'none';
    },

    async saveSafeguardProfile() {
        const editor = document.getElementById('sg-profile-editor');
        const status = document.getElementById('sg-editor-status');
        const editingId = editor?._editingId;
        const id = document.getElementById('sg-editor-id').value.trim();
        const name = document.getElementById('sg-editor-name').value.trim();
        if (!name || (!editingId && !id)) {
            if (status) { status.textContent = t('safeguard.errorMissingFields'); status.style.color = 'var(--error-color)'; }
            return;
        }
        const cats = ['DESTRUCTIVE', 'STATE_CHANGING', 'PROMPT_INJECTION']
            .filter(c => document.getElementById(`sg-editor-cat-${c === 'DESTRUCTIVE' ? 'destructive' : c === 'STATE_CHANGING' ? 'state' : 'injection'}`).checked);
        const body = {
            name,
            check_user_messages: document.getElementById('sg-editor-check-user').checked,
            check_tool_calls: document.getElementById('sg-editor-check-tools').checked,
            confirm_categories: cats,
            detect_prompt_injection: document.getElementById('sg-editor-injection').checked,
            fail_open: document.getElementById('sg-editor-fail-open').checked,
            auto_mode: document.getElementById('sg-editor-auto-mode').checked,
            auto_mode_policy: document.getElementById('sg-editor-auto-policy').value.trim(),
        };
        try {
            let res;
            if (editingId) {
                res = await fetch(`/api/safeguard/profiles/${editingId}`, {
                    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
                });
            } else {
                res = await fetch('/api/safeguard/profiles', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id, ...body }),
                });
            }
            if (res.ok) {
                this.closeSafeguardProfileEditor();
                await this.renderSafeguardSettingsPanel();
            } else {
                const err = await res.json().catch(() => ({}));
                if (status) { status.textContent = err.detail || t('safeguard.errorSave'); status.style.color = 'var(--error-color)'; }
            }
        } catch {
            if (status) { status.textContent = t('safeguard.errorSave'); status.style.color = 'var(--error-color)'; }
        }
    },

    async deleteSafeguardProfile(profileId) {
        const ok = await this.showConfirmDialog(
            t('safeguard.deleteConfirmTitle'),
            t('safeguard.deleteConfirmMsg').replace('{id}', profileId),
        );
        if (!ok) return;
        try {
            const res = await fetch(`/api/safeguard/profiles/${profileId}`, { method: 'DELETE' });
            if (res.ok || res.status === 204) {
                await this.renderSafeguardSettingsPanel();
            }
        } catch (err) { console.warn('deleteSafeguardProfile failed', err); }
    },

    // Füllt den Profile-Select im Agent-Editor
    async _populateAgentSafeguardSelect(agentId) {
        const sel = document.getElementById('agent-safeguard-profile');
        if (!sel) return;
        const profiles = this._safeguardProfiles || [];
        // Option "globales Profil" als erster Eintrag
        const globalOpt = document.createElement('option');
        globalOpt.value = '';
        globalOpt.textContent = t('safeguard.useGlobal');
        const profileOpts = profiles.map(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            return opt;
        });
        sel.replaceChildren(globalOpt, ...profileOpts);
        if (agentId) {
            try {
                const res = await fetch(`/api/safeguard/agents/${agentId}/profile`);
                if (res.ok) {
                    const data = await res.json();
                    sel.value = data.source === 'agent' ? data.profile_id : '';
                }
            } catch (err) { console.warn('loadAgentSafeguardProfile failed', err); }
        }
    },

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

        document.querySelectorAll('#subnav-settings .settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));

        document.querySelector(`#subnav-settings .settings-tab[data-settings-tab="${targetTab}"]`)?.classList.add('active');
        document.getElementById(`settings-panel-${targetTab}`)?.classList.add('active');

        // Load content when switching tabs
        if (targetTab === 'llm') { this.loadLlmSettings(); this.loadLlmProviders(); this.loadEmbedModel(); this.loadRoutingMode(); }
        if (targetTab === 'modules') { this.loadModulesSettings(); this.loadMarketplaceConfig(); }
        if (targetTab === 'skills') { this.loadSettingsSkillsList(); }
        if (targetTab === 'system') this.loadBrandingForm();
        if (targetTab === 'themes') this.loadThemesSettings();
        if (targetTab === 'k8s') this.loadK8sClusters();
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
            <div class="setting-group">
                <h4 data-i18n="settings.langTitle">${t('settings.langTitle')}</h4>
                <p class="setting-desc" data-i18n="settings.langDesc">${t('settings.langDesc')}</p>
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

    // --- Themes ---
    async loadThemesSettings() {
        await this.loadActiveTheme();
        await this.loadThemesCatalog();
        await this.loadThemeRepos();
        this._renderThemeCards();
    },

    async loadThemesCatalog() {
        try {
            const res = await fetch('/api/themes/', { cache: 'no-store' });
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            this._themes = data.themes || [];
            this._activeThemeId = data.active_theme_id || this._activeThemeId || 'default';
        } catch (e) {
            const container = document.getElementById('themes-presets-list');
            if (container) container.innerHTML = '<p class="text-muted">Themes konnten nicht geladen werden.</p>';
            console.error('loadThemesCatalog:', e);
        }
    },

    _renderThemeCards() {
        const container = document.getElementById('themes-presets-list');
        const indicator = document.getElementById('themes-active-indicator');
        if (!container) return;
        if (indicator) indicator.textContent = `Aktiv: ${this._activeThemeId || 'default'}`;
        if (!this._themes.length) {
            container.innerHTML = '<p class="text-muted">Keine Themes gefunden.</p>';
            return;
        }
        container.innerHTML = this._themes.map((th) => {
            const active = th.id === this._activeThemeId;
            return `
                <div class="module-config-card">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${this._escapeHtml(th.name || th.id)}</span>
                            <span class="module-config-version">${this._escapeHtml(th.version || '')}</span>
                            ${active ? '<span class="module-config-version" style="background:rgba(34,197,94,0.2);border-color:rgba(34,197,94,0.35);">Aktiv</span>' : ''}
                            ${th.source === 'builtin' ? '<span class="module-config-version">Built-in</span>' : '<span class="module-config-version">Custom</span>'}
                        </div>
                        <div style="display:flex; gap:0.35rem;">
                            ${active ? '' : `<button class="btn btn-primary btn-sm" data-action="activateTheme" data-args="${JSON.stringify([th.id]).replace(/\"/g, '&quot;')}">Aktivieren</button>`}
                            <button class="btn btn-outline btn-sm" data-action="openThemeEditor" data-args="${JSON.stringify([th.id]).replace(/\"/g, '&quot;')}">Editor</button>
                        </div>
                    </div>
                    ${th.description ? `<p class="module-config-desc">${this._escapeHtml(th.description)}</p>` : ''}
                </div>
            `;
        }).join('');
    },

    async openThemeEditor(themeId) {
        const status = document.getElementById('theme-editor-status');
        try {
            const res = await fetch(`/api/themes/item/${encodeURIComponent(themeId)}`, { cache: 'no-store' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Theme nicht gefunden.');
            const th = data.theme || {};
            const setVal = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.value = value || '';
            };
            setVal('theme-editor-id', th.id || '');
            setVal('theme-editor-name', th.name || '');
            setVal('theme-editor-description', th.description || '');
            setVal('theme-editor-author', th.author || '');
            setVal('theme-editor-version', th.version || '1.0.0');
            setVal('theme-editor-preview', th.preview_url || '');
            setVal('theme-editor-tokens-dark', JSON.stringify(th.tokens_dark || {}, null, 2));
            setVal('theme-editor-tokens-light', JSON.stringify(th.tokens_light || {}, null, 2));
            if (status) {
                status.textContent = `Editor: ${themeId}`;
                status.className = 'save-status save-ok';
            }
        } catch (e) {
            if (status) {
                status.textContent = e.message || 'Theme konnte nicht geladen werden.';
                status.className = 'save-status save-error';
            }
        }
    },

    resetThemeEditor() {
        const setVal = (id, value = '') => {
            const el = document.getElementById(id);
            if (el) el.value = value;
        };
        setVal('theme-editor-id', '');
        setVal('theme-editor-name', '');
        setVal('theme-editor-description', '');
        setVal('theme-editor-author', 'Ninko User');
        setVal('theme-editor-version', '1.0.0');
        setVal('theme-editor-preview', '');
        setVal('theme-editor-tokens-dark', '{}');
        setVal('theme-editor-tokens-light', '{}');
        const st = document.getElementById('theme-editor-status');
        if (st) { st.textContent = ''; st.className = 'save-status'; }
    },

    _readThemeEditorPayload() {
        const get = (id) => document.getElementById(id)?.value?.trim() || '';
        const parseJson = (value, fieldName) => {
            try {
                if (!value) return {};
                const parsed = JSON.parse(value);
                if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                    throw new Error(`${fieldName} muss ein JSON-Objekt sein.`);
                }
                return parsed;
            } catch {
                throw new Error(`${fieldName} enthält ungültiges JSON.`);
            }
        };
        const payload = {
            id: get('theme-editor-id'),
            name: get('theme-editor-name'),
            description: get('theme-editor-description'),
            author: get('theme-editor-author') || 'Ninko User',
            version: get('theme-editor-version') || '1.0.0',
            preview_url: get('theme-editor-preview'),
            tokens_dark: parseJson(get('theme-editor-tokens-dark'), 'Tokens Dark'),
            tokens_light: parseJson(get('theme-editor-tokens-light'), 'Tokens Light'),
        };
        if (!/^[a-zA-Z0-9_-]{1,64}$/.test(payload.id)) {
            throw new Error('Theme ID ungültig. Erlaubt: a-z, A-Z, 0-9, _, -');
        }
        if (!payload.name) throw new Error('Theme Name fehlt.');
        return payload;
    },

    async saveThemeFromEditor() {
        const st = document.getElementById('theme-editor-status');
        if (st) { st.textContent = 'Speichere…'; st.className = 'save-status save-pending'; }
        try {
            const payload = this._readThemeEditorPayload();
            const existing = this._themes.find(t => t.id === payload.id);
            if (existing?.source === 'builtin') {
                throw new Error('Built-in Themes können nicht überschrieben werden. Bitte neue ID verwenden.');
            }
            const isUpdate = !!existing && existing.source === 'custom';
            const url = isUpdate ? `/api/themes/custom/${encodeURIComponent(payload.id)}` : '/api/themes/custom';
            const method = isUpdate ? 'PUT' : 'POST';
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Speichern fehlgeschlagen.');

            await this.loadThemesCatalog();
            await this.openThemeEditor(payload.id);
            showNotification('Theme gespeichert', 'success');
            if (st) { st.textContent = 'Gespeichert'; st.className = 'save-status save-ok'; }
        } catch (e) {
            if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
            showNotification(e.message || 'Theme konnte nicht gespeichert werden.', 'error');
        }
    },

    async duplicateThemeFromEditor() {
        const sourceId = document.getElementById('theme-editor-id')?.value?.trim();
        const st = document.getElementById('theme-editor-status');
        if (!sourceId) {
            if (st) { st.textContent = 'Zum Duplizieren erst ein Theme laden.'; st.className = 'save-status save-error'; }
            return;
        }
        if (st) { st.textContent = 'Dupliziere…'; st.className = 'save-status save-pending'; }
        try {
            const res = await fetch(`/api/themes/custom/${encodeURIComponent(sourceId)}/duplicate`, { method: 'POST' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Duplizieren fehlgeschlagen.');
            await this.loadThemesCatalog();
            await this.openThemeEditor(data.theme_id);
            this._renderThemeCards();
            if (st) { st.textContent = `Dupliziert als ${data.theme_id}`; st.className = 'save-status save-ok'; }
        } catch (e) {
            if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
        }
    },

    async deleteThemeFromEditor() {
        const themeId = document.getElementById('theme-editor-id')?.value?.trim();
        const st = document.getElementById('theme-editor-status');
        if (!themeId) {
            if (st) { st.textContent = 'Kein Theme ausgewählt.'; st.className = 'save-status save-error'; }
            return;
        }
        const existing = this._themes.find(t => t.id === themeId);
        if (existing?.source === 'builtin') {
            if (st) { st.textContent = 'Built-in Themes können nicht gelöscht werden.'; st.className = 'save-status save-error'; }
            return;
        }
        if (!await this.confirm(`Theme "${themeId}" wirklich löschen?`)) return;
        try {
            const res = await fetch(`/api/themes/custom/${encodeURIComponent(themeId)}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Löschen fehlgeschlagen.');
            this.resetThemeEditor();
            await this.loadThemesCatalog();
            await this.loadActiveTheme();
            this.applyActiveThemeTokens();
            this._renderThemeCards();
            if (st) { st.textContent = 'Theme gelöscht'; st.className = 'save-status save-ok'; }
        } catch (e) {
            if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
        }
    },

    async loadThemeRepos() {
        const container = document.getElementById('theme-repos-list');
        if (!container) return;
        try {
            const res = await fetch('/api/themes/repos', { cache: 'no-store' });
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            this._themeRepos = data.repos || [];
            this._renderThemeRepos();
        } catch (e) {
            container.innerHTML = '<p class="text-muted">Theme-Repos konnten nicht geladen werden.</p>';
            console.error('loadThemeRepos:', e);
        }
    },

    _renderThemeRepos() {
        const container = document.getElementById('theme-repos-list');
        if (!container) return;
        if (!this._themeRepos.length) {
            container.innerHTML = '<p class="text-muted">Keine Theme-Repos konfiguriert.</p>';
            return;
        }
        container.innerHTML = this._themeRepos.map((repo) => `
            <div class="module-config-card" id="theme-repo-card-${this._escapeHtml(repo.id)}" style="margin-bottom:0.75rem;">
                <div class="module-config-header">
                    <div class="module-config-info">
                        <span class="module-config-name">${this._escapeHtml(repo.name)}</span>
                        ${repo.id === 'official' ? '<span class="module-config-version">Official</span>' : ''}
                        <span class="text-muted" style="font-size:0.76rem;">${this._escapeHtml(repo.repo_url)} · ${this._escapeHtml(repo.branch || 'main')}</span>
                    </div>
                    <div style="display:flex; gap:0.35rem;">
                        <button class="btn btn-outline btn-sm" data-action="loadThemesFromRepo" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}">Themes laden</button>
                        ${repo.id === 'official' ? '' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteThemeRepo" data-args="${JSON.stringify([repo.id]).replace(/\"/g, '&quot;')}">Repo löschen</button>`}
                    </div>
                </div>
                <div id="theme-repo-themes-${this._escapeHtml(repo.id)}" style="margin-top:0.5rem;"></div>
            </div>
        `).join('');
    },

    async addThemeRepo() {
        const st = document.getElementById('theme-repo-status');
        const get = (id) => document.getElementById(id)?.value?.trim() || '';
        const body = {
            name: get('theme-repo-name'),
            repo_url: get('theme-repo-url'),
            branch: get('theme-repo-branch') || 'main',
            themes_path: get('theme-repo-path') || 'backend/themes',
            github_token: get('theme-repo-token'),
        };
        if (!body.name || !body.repo_url) {
            if (st) { st.textContent = 'Name und GitHub URL sind erforderlich.'; st.className = 'save-status save-error'; }
            return;
        }
        if (st) { st.textContent = 'Füge Repo hinzu…'; st.className = 'save-status save-pending'; }
        try {
            const res = await fetch('/api/themes/repos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Repo konnte nicht hinzugefügt werden.');
            ['theme-repo-name', 'theme-repo-url', 'theme-repo-branch', 'theme-repo-path', 'theme-repo-token'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            if (st) { st.textContent = 'Repo hinzugefügt'; st.className = 'save-status save-ok'; }
            await this.loadThemeRepos();
        } catch (e) {
            if (st) { st.textContent = e.message || 'Fehler'; st.className = 'save-status save-error'; }
        }
    },

    async deleteThemeRepo(repoId) {
        if (!await this.confirm('Theme-Repo wirklich löschen?')) return;
        try {
            const res = await fetch(`/api/themes/repos/${encodeURIComponent(repoId)}`, { method: 'DELETE' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Repo konnte nicht gelöscht werden.');
            await this.loadThemeRepos();
        } catch (e) {
            showNotification(e.message || 'Repo konnte nicht gelöscht werden.', 'error');
        }
    },

    async loadThemesFromRepo(repoId) {
        const container = document.getElementById(`theme-repo-themes-${repoId}`);
        if (!container) return;
        container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Lade Themes…</p>';
        try {
            const res = await fetch(`/api/themes/repos/${encodeURIComponent(repoId)}/themes`);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Theme-Liste konnte nicht geladen werden.');
            const themes = data.themes || [];
            if (!themes.length) {
                container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Keine Themes gefunden.</p>';
                return;
            }
            container.innerHTML = themes.map((th) => `
                <div class="module-config-card" id="theme-repo-theme-${this._escapeHtml(repoId)}-${this._escapeHtml(th.id)}" style="margin-top:0.5rem;">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${this._escapeHtml(th.name || th.id)}</span>
                            <span class="module-config-version">${this._escapeHtml(th.version || '')}</span>
                        </div>
                        <button class="btn btn-primary btn-sm" id="theme-install-btn-${this._escapeHtml(repoId)}-${this._escapeHtml(th.id)}"
                            data-action="installThemeFromRepo" data-args="${JSON.stringify([th.id, repoId]).replace(/\"/g, '&quot;')}">
                            Installieren
                        </button>
                    </div>
                    ${th.description ? `<p class="module-config-desc">${this._escapeHtml(th.description)}</p>` : ''}
                </div>
            `).join('');
        } catch (e) {
            container.innerHTML = `<p style="font-size:0.82rem;color:var(--error-color);">${this._escapeHtml(e.message || 'Fehler')}</p>`;
        }
    },

    async installThemeFromRepo(themeId, repoId = 'official') {
        const btn = document.getElementById(`theme-install-btn-${repoId}-${themeId}`);
        if (btn) { btn.disabled = true; btn.textContent = 'Installiere…'; }
        try {
            const res = await fetch(`/api/themes/install-from-repo/${encodeURIComponent(themeId)}?repo_id=${encodeURIComponent(repoId)}`, {
                method: 'POST',
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || 'Installation fehlgeschlagen.');
            await this.loadThemesCatalog();
            this._renderThemeCards();
            showNotification(`Theme "${themeId}" installiert`, 'success');
        } catch (e) {
            showNotification(e.message || 'Theme konnte nicht installiert werden.', 'error');
            if (btn) { btn.disabled = false; btn.textContent = 'Installieren'; }
        }
    },

    // --- STT Settings ---
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

    // --- Image Generation Provider ---
    async loadImageGenProvider() {
        try {
            const res = await fetch('/api/settings/image-provider');
            if (!res.ok) return;
            const data = await res.json();
            document.getElementById('imggen-backend').value = data.backend || '';
            document.getElementById('imggen-model').value = data.model || '';
            document.getElementById('imggen-api-key').value = '';
            document.getElementById('imggen-api-key-masked').textContent = data.api_key_masked || '';
        } catch { /* ignore */ }
    },

    async saveImageGenProvider() {
        const statusEl = document.getElementById('imggen-save-status');
        statusEl.textContent = 'Speichere…';
        statusEl.className = 'save-status';
        try {
            const body = {
                backend: document.getElementById('imggen-backend').value,
                api_key: document.getElementById('imggen-api-key').value,
                model: document.getElementById('imggen-model').value,
            };
            const res = await fetch('/api/settings/image-provider', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (res.ok) {
                statusEl.textContent = 'Gespeichert';
                statusEl.className = 'save-status save-ok';
                showNotification('Image-Provider gespeichert', 'info');
                this.loadImageGenProvider();
            } else {
                statusEl.textContent = 'Fehler';
                statusEl.className = 'save-status save-error';
            }
        } catch {
            statusEl.textContent = 'Verbindungsfehler';
            statusEl.className = 'save-status save-error';
        }
    },

    onImageGenBackendChange() {
        const backend = document.getElementById('imggen-backend').value;
        const modelInput = document.getElementById('imggen-model');
        const placeholders = {
            'together_ai': 'black-forest-labs/FLUX.1-schnell-Free',
            'openai': 'dall-e-3',
            'google': 'imagen-3.0-generate-002',
            'stability_ai': 'stable-image-core',
            'huggingface': 'black-forest-labs/FLUX.1-schnell',
        };
        modelInput.placeholder = placeholders[backend] || 'Leer = Standard-Modell';
    },

    // --- Access / RBAC Settings ---
    async loadRbacSettings() {
        const root = document.getElementById('rbac-root');
        if (!root) return;
        root.innerHTML = '<p class="text-muted">Lade Benutzerverwaltung…</p>';

        try {
            const [modsRes, rolesRes, groupsRes, usersRes] = await Promise.all([
                fetch('/api/auth/modules/available'),
                fetch('/api/auth/roles'),
                fetch('/api/auth/groups'),
                fetch('/api/auth/users'),
            ]);
            if (!modsRes.ok || !rolesRes.ok || !groupsRes.ok || !usersRes.ok) {
                throw new Error('RBAC-Endpunkte nicht verfügbar oder keine Berechtigung.');
            }

            const mods = await modsRes.json();
            const roles = await rolesRes.json();
            const groups = await groupsRes.json();
            const users = await usersRes.json();

            this._rbacModules = mods.modules || [];
            this._rbacRoles = roles.roles || [];
            this._rbacGroups = groups.groups || [];
            this._rbacUsers = users.users || [];
            if (!this._rbacSelectedUser && this._rbacUsers.length) {
                this._rbacSelectedUser = this._rbacUsers[0].username;
            }
            if (!this._rbacTokenSelectedUser && this._rbacUsers.length) {
                this._rbacTokenSelectedUser = this._rbacUsers[0].username;
            }

            this.renderRbacSettings();
        } catch (e) {
            root.innerHTML = `<p class="empty-state">${this._escapeHtml(e.message || 'Fehler beim Laden der Benutzerverwaltung.')}</p>`;
        }
    },

    _rbacUserOptions(selectedUsername = '') {
        return this._rbacUsers
            .map(u => `<option value="${this._escapeHtml(u.username)}" ${u.username === selectedUsername ? 'selected' : ''}>${this._escapeHtml(u.username)}</option>`)
            .join('');
    },

    renderRbacSettings() {
        const root = document.getElementById('rbac-root');
        if (!root) return;

        const roleOptions = this._rbacRoles
            .map(r => `<option value="${this._escapeHtml(r.id)}">${this._escapeHtml(r.name || r.id)}</option>`)
            .join('');
        const groupOptions = this._rbacGroups
            .map(g => `<option value="${this._escapeHtml(g.id)}">${this._escapeHtml(g.name || g.id)}</option>`)
            .join('');

        root.innerHTML = `
            <div class="setting-group">
                <h4>Benutzerverwaltung (RBAC)</h4>
                <p class="setting-desc">Verwalte Benutzer, Gruppen und Rollen. Rechte können pro Modul konfiguriert werden.</p>
                <div class="form-actions">
                    <span id="rbac-save-status" class="save-status"></span>
                    <button class="btn btn-outline btn-sm" data-action="loadRbacSettings">Neu laden</button>
                </div>
            </div>

            <div class="setting-group">
                <h4>Benutzer</h4>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                    <input id="rbac-user-username" type="text" class="form-input" placeholder="username" style="max-width:180px;">
                    <input id="rbac-user-password" type="password" class="form-input" placeholder="Passwort (>=8)" style="max-width:220px;">
                    <select id="rbac-user-role" class="form-select" style="max-width:200px;">
                        <option value="">Rolle (optional)</option>
                        ${roleOptions}
                    </select>
                    <select id="rbac-user-group" class="form-select" style="max-width:200px;">
                        <option value="">Gruppe (optional)</option>
                        ${groupOptions}
                    </select>
                    <button class="btn btn-primary btn-sm" data-action="createRbacUser">Benutzer anlegen</button>
                </div>
                <div id="rbac-users-list">${this._renderRbacUsersTable()}</div>
            </div>

            <div class="setting-group">
                <h4>API-Tokens</h4>
                <p class="setting-desc">API-Tokens werden nur von Admins erstellt und einmalig angezeigt. Zugriff erfolgt via <code>X-API-Key</code> oder <code>Authorization: Bearer ...</code>.</p>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                    <select id="rbac-token-user" class="form-select" style="max-width:220px;" onchange="Ninko.onRbacTokenUserChange(this.value)">
                        ${this._rbacUserOptions(this._rbacTokenSelectedUser || '')}
                    </select>
                    <input id="rbac-token-name" type="text" class="form-input" placeholder="Token-Name" style="max-width:220px;">
                    <input id="rbac-token-exp-hours" type="number" min="1" max="8760" class="form-input" placeholder="Ablauf in Stunden" value="720" style="max-width:180px;">
                    <button class="btn btn-primary btn-sm" data-action="createRbacUserApiToken">Token erstellen</button>
                </div>
                <div id="rbac-token-created" class="save-status" style="margin-bottom:0.6rem;"></div>
                <div id="rbac-token-list"><p class="text-muted">Bitte Benutzer auswählen.</p></div>
            </div>

            <div class="setting-group">
                <h4>Benutzerdefinierte Settings</h4>
                <p class="setting-desc">Freies JSON-Feld je Benutzer (z.B. individuelle Präferenzen oder Modulvorgaben).</p>
                <div class="form-row">
                    <label class="form-label" for="rbac-user-settings-user">Benutzer</label>
                    <select id="rbac-user-settings-user" class="form-select" style="max-width:220px;" onchange="Ninko.onRbacSettingsUserChange(this.value)">
                        ${this._rbacUserOptions(this._rbacSelectedUser || '')}
                    </select>
                </div>
                <div class="form-row">
                    <label class="form-label" for="rbac-user-custom-settings-json">Settings (JSON)</label>
                    <textarea id="rbac-user-custom-settings-json" class="form-input" rows="8" placeholder='{"dashboard":{"default_module":"kubernetes"}}'></textarea>
                </div>
                <div class="form-actions">
                    <button class="btn btn-outline btn-sm" data-action="loadRbacUserCustomSettings">Laden</button>
                    <button class="btn btn-primary btn-sm" data-action="saveRbacUserCustomSettings">Speichern</button>
                </div>
            </div>

            <div class="setting-group">
                <h4>Gruppen</h4>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                    <input id="rbac-group-id" type="text" class="form-input" placeholder="group_id" style="max-width:180px;">
                    <input id="rbac-group-name" type="text" class="form-input" placeholder="Anzeigename" style="max-width:220px;">
                    <select id="rbac-group-role" class="form-select" style="max-width:220px;">
                        <option value="">Rolle zuweisen (optional)</option>
                        ${roleOptions}
                    </select>
                    <button class="btn btn-primary btn-sm" data-action="createRbacGroup">Gruppe anlegen</button>
                </div>
                <div id="rbac-groups-list">${this._renderRbacGroupsTable()}</div>
            </div>

            <div class="setting-group">
                <h4>Rollen</h4>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                    <input id="rbac-role-id" type="text" class="form-input" placeholder="role_id" style="max-width:180px;">
                    <input id="rbac-role-name" type="text" class="form-input" placeholder="Anzeigename" style="max-width:220px;">
                    <select id="rbac-role-base" class="form-select" style="max-width:140px;">
                        <option value="read">read</option>
                        <option value="write">write</option>
                        <option value="admin">admin</option>
                    </select>
                    <button class="btn btn-primary btn-sm" data-action="createRbacRole">Rolle anlegen</button>
                </div>
                <div class="form-row">
                    <label class="form-label" for="rbac-role-edit-select">Rolle für Modulrechte bearbeiten</label>
                    <select id="rbac-role-edit-select" class="form-select" onchange="Ninko.renderRbacRolePermissions()">
                        <option value="">Bitte Rolle wählen…</option>
                        ${roleOptions}
                    </select>
                </div>
                <div id="rbac-role-permissions"></div>
                <div id="rbac-roles-list" style="margin-top:0.75rem;">${this._renderRbacRolesTable()}</div>
            </div>
        `;
        this.loadRbacUserApiTokens();
        this.loadRbacUserCustomSettings();
    },

    _setRbacStatus(message, ok = true) {
        const el = document.getElementById('rbac-save-status');
        if (!el) return;
        el.innerHTML = ok
            ? `<span class="sf sf-ok">${this._escapeHtml(message)}</span>`
            : `<span class="sf sf-error">${this._escapeHtml(message)}</span>`;
    },

    _renderRbacUsersTable() {
        if (!this._rbacUsers.length) return '<p class="text-muted">Keine Benutzer vorhanden.</p>';
        const rows = this._rbacUsers.map(u => `
            <tr>
                <td><code>${this._escapeHtml(u.username)}</code></td>
                <td>${u.active ? 'aktiv' : 'inaktiv'}</td>
                <td>${this._escapeHtml((u.roles || []).join(', ') || '-')}</td>
                <td>${this._escapeHtml((u.groups || []).join(', ') || '-')}</td>
                <td style="display:flex; gap:0.35rem;">
                    <button class="btn btn-outline btn-sm" data-action="toggleRbacUserActive" data-args="${JSON.stringify([u.username, !u.active]).replace(/\"/g, '&quot;')}">${u.active ? 'Deaktivieren' : 'Aktivieren'}</button>
                    <button class="btn btn-outline btn-sm" data-action="setRbacUserPassword" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Passwort</button>
                    <button class="btn btn-outline btn-sm" data-action="openRbacUserSettings" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Settings</button>
                    <button class="btn btn-outline btn-sm" data-action="openRbacUserTokens" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">API-Token</button>
                    <button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacUser" data-args="${JSON.stringify([u.username]).replace(/\"/g, '&quot;')}">Löschen</button>
                </td>
            </tr>
        `).join('');
        return `
            <div style="overflow:auto;">
                <table class="log-table">
                    <thead><tr><th>User</th><th>Status</th><th>Rollen</th><th>Gruppen</th><th>Aktionen</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    _renderRbacGroupsTable() {
        if (!this._rbacGroups.length) return '<p class="text-muted">Keine Gruppen vorhanden.</p>';
        const rows = this._rbacGroups.map(g => `
            <tr>
                <td><code>${this._escapeHtml(g.id)}</code></td>
                <td>${this._escapeHtml(g.name || '')}</td>
                <td>${this._escapeHtml((g.roles || []).join(', ') || '-')}</td>
                <td>${this._escapeHtml(((g.users || []).length).toString())}</td>
                <td>
                    ${g.id === 'group_admins' ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacGroup" data-args="${JSON.stringify([g.id]).replace(/\"/g, '&quot;')}">Löschen</button>`}
                </td>
            </tr>
        `).join('');
        return `
            <div style="overflow:auto;">
                <table class="log-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Rollen</th><th>Mitglieder</th><th>Aktion</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    _renderRbacRolesTable() {
        if (!this._rbacRoles.length) return '<p class="text-muted">Keine Rollen vorhanden.</p>';
        const rows = this._rbacRoles.map(r => `
            <tr>
                <td><code>${this._escapeHtml(r.id)}</code></td>
                <td>${this._escapeHtml(r.name || '')}</td>
                <td>${this._escapeHtml(r.base_role || 'read')}</td>
                <td>${this._escapeHtml(Object.keys(r.module_permissions || {}).join(', ') || '-')}</td>
                <td>
                    ${r.id === 'role_admin' ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="deleteRbacRole" data-args="${JSON.stringify([r.id]).replace(/\"/g, '&quot;')}">Löschen</button>`}
                </td>
            </tr>
        `).join('');
        return `
            <div style="overflow:auto;">
                <table class="log-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Base Role</th><th>Module</th><th>Aktion</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    renderRbacRolePermissions() {
        const roleId = document.getElementById('rbac-role-edit-select')?.value || '';
        const container = document.getElementById('rbac-role-permissions');
        if (!container) return;
        if (!roleId) {
            container.innerHTML = '';
            return;
        }
        const role = this._rbacRoles.find(r => r.id === roleId);
        if (!role) {
            container.innerHTML = '<p class="text-muted">Rolle nicht gefunden.</p>';
            return;
        }

        const currentPerms = role.module_permissions || {};
        const rows = this._rbacModules.map(m => {
            const key = (m.id || '').toLowerCase().replace(/-/g, '_');
            const wildcard = currentPerms['*'] || {};
            const specific = currentPerms[key] || {};
            const readChecked = (specific.read === true) || (specific.read !== false && wildcard.read === true);
            const writeChecked = (specific.write === true) || (specific.write !== false && wildcard.write === true);
            return `
                <tr>
                    <td>${this._escapeHtml(m.display_name || m.id)}</td>
                    <td><input type="checkbox" data-rbac-perm="read" data-module-id="${this._escapeHtml(key)}" ${readChecked ? 'checked' : ''}></td>
                    <td><input type="checkbox" data-rbac-perm="write" data-module-id="${this._escapeHtml(key)}" ${writeChecked ? 'checked' : ''}></td>
                </tr>
            `;
        }).join('');

        container.innerHTML = `
            <div style="margin-top:0.6rem;">
                <div class="text-muted" style="font-size:0.82rem; margin-bottom:0.4rem;">Rolle: <code>${this._escapeHtml(roleId)}</code></div>
                <div style="overflow:auto; max-height:280px;">
                    <table class="log-table">
                        <thead><tr><th>Modul</th><th>Read</th><th>Write</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div class="form-actions" style="margin-top:0.5rem;">
                    <button class="btn btn-primary btn-sm" data-action="saveRbacRolePermissions" data-args="${JSON.stringify([roleId]).replace(/\"/g, '&quot;')}">Modulrechte speichern</button>
                </div>
            </div>
        `;
    },

    async createRbacUser() {
        const username = document.getElementById('rbac-user-username')?.value?.trim() || '';
        const password = document.getElementById('rbac-user-password')?.value || '';
        const role = document.getElementById('rbac-user-role')?.value || '';
        const group = document.getElementById('rbac-user-group')?.value || '';
        if (!username || !password) return this._setRbacStatus('Username und Passwort sind Pflicht.', false);
        try {
            const res = await fetch('/api/auth/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username,
                    password,
                    active: true,
                    roles: role ? [role] : [],
                    groups: group ? [group] : [],
                }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
            this._setRbacStatus(`Benutzer ${username} angelegt.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async toggleRbacUserActive(username, active) {
        try {
            const user = this._rbacUsers.find(u => u.username === username);
            if (!user) throw new Error('Benutzer nicht gefunden');
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    active,
                    roles: user.roles || [],
                    groups: user.groups || [],
                }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Aktualisieren');
            this._setRbacStatus(`Benutzer ${username} aktualisiert.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async setRbacUserPassword(username) {
        const pw = prompt(`Neues Passwort für ${username} (mind. 8 Zeichen):`);
        if (!pw) return;
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/password`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pw }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Passwort-Update');
            this._setRbacStatus(`Passwort für ${username} gesetzt.`);
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async deleteRbacUser(username) {
        if (!confirm(`Benutzer ${username} wirklich löschen?`)) return;
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
            this._setRbacStatus(`Benutzer ${username} gelöscht.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    openRbacUserSettings(username) {
        this._rbacSelectedUser = username;
        const sel = document.getElementById('rbac-user-settings-user');
        if (sel) sel.value = username;
        this.loadRbacUserCustomSettings();
    },

    openRbacUserTokens(username) {
        this._rbacTokenSelectedUser = username;
        const sel = document.getElementById('rbac-token-user');
        if (sel) sel.value = username;
        this.loadRbacUserApiTokens();
    },

    onRbacSettingsUserChange(username) {
        this._rbacSelectedUser = username || '';
        this.loadRbacUserCustomSettings();
    },

    onRbacTokenUserChange(username) {
        this._rbacTokenSelectedUser = username || '';
        this.loadRbacUserApiTokens();
    },

    async loadRbacUserCustomSettings() {
        const username = this._rbacSelectedUser || document.getElementById('rbac-user-settings-user')?.value || '';
        const ta = document.getElementById('rbac-user-custom-settings-json');
        if (!username || !ta) return;
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/settings`);
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Laden der Settings');
            const data = await res.json();
            ta.value = JSON.stringify(data.settings || {}, null, 2);
            this._setRbacStatus(`Settings für ${username} geladen.`);
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async saveRbacUserCustomSettings() {
        const username = this._rbacSelectedUser || document.getElementById('rbac-user-settings-user')?.value || '';
        const ta = document.getElementById('rbac-user-custom-settings-json');
        if (!username || !ta) return this._setRbacStatus('Bitte Benutzer wählen.', false);
        let settings = {};
        try {
            settings = ta.value.trim() ? JSON.parse(ta.value) : {};
        } catch {
            return this._setRbacStatus('Ungültiges JSON in benutzerdefinierten Settings.', false);
        }
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/settings`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Speichern der Settings');
            this._setRbacStatus(`Settings für ${username} gespeichert.`);
            await this.loadRbacSettings();
            this._rbacSelectedUser = username;
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async loadRbacUserApiTokens() {
        const username = this._rbacTokenSelectedUser || document.getElementById('rbac-token-user')?.value || '';
        const listEl = document.getElementById('rbac-token-list');
        if (!listEl || !username) return;
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens`);
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Laden der API-Tokens');
            const data = await res.json();
            const tokens = data.tokens || [];
            if (!tokens.length) {
                listEl.innerHTML = '<p class="text-muted">Keine API-Tokens vorhanden.</p>';
                return;
            }
            const rows = tokens.map(t => `
                <tr>
                    <td><code>${this._escapeHtml(t.id || '')}</code></td>
                    <td>${this._escapeHtml(t.name || '')}</td>
                    <td>${this._escapeHtml(t.created_at || '-')}</td>
                    <td>${this._escapeHtml(t.expires_at || '-')}</td>
                    <td>${t.revoked ? 'revoked' : 'active'}</td>
                    <td>${t.revoked ? '-' : `<button class="btn btn-outline btn-sm" style="color:var(--error-color);" data-action="revokeRbacUserApiToken" data-args="${JSON.stringify([username, t.id || '']).replace(/\"/g, '&quot;')}">Revoke</button>`}</td>
                </tr>
            `).join('');
            listEl.innerHTML = `
                <div style="overflow:auto;">
                    <table class="log-table">
                        <thead><tr><th>ID</th><th>Name</th><th>Created</th><th>Expires</th><th>Status</th><th>Aktion</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        } catch (e) {
            listEl.innerHTML = `<p class="empty-state">${this._escapeHtml(e.message || 'Fehler')}</p>`;
        }
    },

    async createRbacUserApiToken() {
        const username = this._rbacTokenSelectedUser || document.getElementById('rbac-token-user')?.value || '';
        const name = document.getElementById('rbac-token-name')?.value?.trim() || 'api-token';
        const expiresHours = parseInt(document.getElementById('rbac-token-exp-hours')?.value || '720', 10);
        const out = document.getElementById('rbac-token-created');
        if (!username) return this._setRbacStatus('Bitte Benutzer für API-Token wählen.', false);
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, expires_hours: Number.isFinite(expiresHours) ? expiresHours : 720 }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Fehler beim Erstellen des API-Tokens');
            if (out) {
                out.innerHTML = `
                    <span class="sf sf-ok">Token erstellt (wird nur einmal angezeigt):</span>
                    <code style="display:block; margin-top:0.35rem; word-break:break-all;">${this._escapeHtml(data.token || '')}</code>
                `;
            }
            this._setRbacStatus(`API-Token für ${username} erstellt.`);
            await this.loadRbacUserApiTokens();
        } catch (e) {
            if (out) out.innerHTML = '';
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async revokeRbacUserApiToken(username, tokenId) {
        try {
            const res = await fetch(`/api/auth/users/${encodeURIComponent(username)}/api-tokens/${encodeURIComponent(tokenId)}`, {
                method: 'DELETE',
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Widerruf');
            this._setRbacStatus(`Token ${tokenId} widerrufen.`);
            await this.loadRbacUserApiTokens();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async createRbacGroup() {
        const group_id = document.getElementById('rbac-group-id')?.value?.trim() || '';
        const name = document.getElementById('rbac-group-name')?.value?.trim() || '';
        const role = document.getElementById('rbac-group-role')?.value || '';
        if (!group_id || !name) return this._setRbacStatus('group_id und Name sind Pflicht.', false);
        try {
            const res = await fetch('/api/auth/groups', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ group_id, name, description: '', roles: role ? [role] : [] }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
            this._setRbacStatus(`Gruppe ${group_id} angelegt.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async deleteRbacGroup(groupId) {
        if (!confirm(`Gruppe ${groupId} wirklich löschen?`)) return;
        try {
            const res = await fetch(`/api/auth/groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
            this._setRbacStatus(`Gruppe ${groupId} gelöscht.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async createRbacRole() {
        const role_id = document.getElementById('rbac-role-id')?.value?.trim() || '';
        const name = document.getElementById('rbac-role-name')?.value?.trim() || '';
        const base_role = document.getElementById('rbac-role-base')?.value || 'read';
        if (!role_id || !name) return this._setRbacStatus('role_id und Name sind Pflicht.', false);
        try {
            const res = await fetch('/api/auth/roles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    role_id,
                    name,
                    description: '',
                    base_role,
                    module_permissions: { '*': { read: true, write: base_role !== 'read' } },
                }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Anlegen');
            this._setRbacStatus(`Rolle ${role_id} angelegt.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async saveRbacRolePermissions(roleId) {
        const rows = Array.from(document.querySelectorAll('#rbac-role-permissions input[data-module-id]'));
        const module_permissions = {};
        const byModule = new Map();
        for (const input of rows) {
            const moduleId = input.dataset.moduleId;
            const perm = input.dataset.rbacPerm;
            if (!byModule.has(moduleId)) byModule.set(moduleId, { read: false, write: false });
            byModule.get(moduleId)[perm] = !!input.checked;
        }
        for (const [moduleId, perms] of byModule.entries()) module_permissions[moduleId] = perms;

        try {
            const res = await fetch(`/api/auth/roles/${encodeURIComponent(roleId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ module_permissions }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Speichern');
            this._setRbacStatus(`Modulrechte für ${roleId} gespeichert.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    async deleteRbacRole(roleId) {
        if (!confirm(`Rolle ${roleId} wirklich löschen?`)) return;
        try {
            const res = await fetch(`/api/auth/roles/${encodeURIComponent(roleId)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error((await res.json()).detail || 'Fehler beim Löschen');
            this._setRbacStatus(`Rolle ${roleId} gelöscht.`);
            await this.loadRbacSettings();
        } catch (e) {
            this._setRbacStatus(e.message || 'Fehler', false);
        }
    },

    // --- Module Settings & Connections ---
    ACTION_FIELDS: {
        proxmox: [
            { key: 'host', label: 'Host / URL', placeholder: '192.168.1.100:8006' },
            { key: 'user', label: 'Benutzer', placeholder: 'root@pam' },
            { key: 'token_id', label: 'Token-ID', placeholder: 'sophy' },
            { key: 'token_secret', label: 'Token-Secret', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren (Nein anklicken bei invalidem SSL Cert)', type: 'checkbox' },
        ],
        glpi: [
            { key: 'base_url', label: 'Base URL', placeholder: 'https://glpi.example.com' },
            { key: 'app_token', label: 'App-Token', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'user_token', label: 'User-Token', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren', type: 'checkbox' },
            { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
        ],
        kubernetes: [
            { key: 'context', label: 'Context (optional)', placeholder: 'kubernetes-admin@prod' },
            { key: 'kubeconfig', label: 'Kubeconfig-Datei', type: 'file', isSecret: true },
        ],
        licium: [
            { key: 'base_url', label: 'Licium URL', placeholder: 'https://licium.example.com' },
            { key: 'username', label: 'Benutzername', placeholder: 'admin' },
            { key: 'LICIUM_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
        ],
        pihole: [
            { key: 'url', label: 'Pi-hole URL', placeholder: 'http://192.168.1.2' },
            { key: 'password', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        ionos: [
            { key: 'api_key', label: 'API-Key', placeholder: 'prefix.secret', type: 'password', isSecret: true },
        ],
        jira: [
            { key: 'url', label: 'Jira URL', placeholder: 'https://company.atlassian.net' },
            { key: 'email', label: 'E-Mail', placeholder: 'user@company.com' },
            { key: 'JIRA_API_KEY', label: 'API-Token', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
        ],
        fritzbox: [
            { key: 'host', label: 'FritzBox Host/IP', placeholder: '192.168.178.1' },
            { key: 'user', label: 'Benutzername (optional)', placeholder: 'admin' },
            { key: 'password', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        telegram: [
            { key: 'TELEGRAM_BOT_TOKEN', label: 'Bot-Token (Von @BotFather auf Telegram)', placeholder: '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ', type: 'password', isSecret: true },
        ],
        email: [
            { key: 'imap_server', label: 'IMAP Server', placeholder: 'imap.gmx.net' },
            { key: 'imap_port', label: 'IMAP Port', placeholder: '993', type: 'number' },
            { key: 'smtp_server', label: 'SMTP Server', placeholder: 'mail.gmx.net' },
            { key: 'smtp_port', label: 'SMTP Port', placeholder: '587', type: 'number' },
            { key: 'email_address', label: 'E-Mail Adresse', placeholder: 'bot@domain.de' },
            { key: 'auth_type', label: 'Auth-Typ (basic oder oauth2)', placeholder: 'basic' },
            { key: 'EMAIL_SECRET', label: 'Passwort / Client Secret', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'client_id', label: 'OAuth2 Client ID (nur M365)', placeholder: '...' },
            { key: 'tenant_id', label: 'OAuth2 Tenant ID (nur M365)', placeholder: 'common' },
        ],
        homeassistant: [
            { key: 'url', label: 'Home Assistant URL', placeholder: 'http://homeassistant.local:8123' },
            { key: 'HOMEASSISTANT_API_TOKEN', label: 'Long-Lived Access Token', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        synology: [
            { key: 'url', label: 'DSM URL', placeholder: 'https://192.168.1.100:5001' },
            { key: 'username', label: 'Benutzername', placeholder: 'admin' },
            { key: 'SYNOLOGY_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'SYNOLOGY_API_KEY', label: 'API Key (optional)', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        redmine: [
            { key: 'url', label: 'Redmine URL', placeholder: 'https://redmine.example.com' },
            { key: 'REDMINE_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
        ],
        openproject: [
            { key: 'url', label: 'OpenProject URL', placeholder: 'https://openproject.example.com' },
            { key: 'OPENPROJECT_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
        ],
        teams: [
            { key: 'MICROSOFT_APP_ID', label: 'Microsoft App ID', placeholder: 'e.g. 1234abcd-1234-abcd-1234-abcd1234abcd' },
            { key: 'MICROSOFT_APP_PASSWORD', label: 'Microsoft App Password / Client Secret', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        confluence: [
            { key: 'url', label: 'Confluence URL', placeholder: 'https://company.atlassian.net' },
            { key: 'email', label: 'E-Mail', placeholder: 'user@company.com' },
            { key: 'CONFLUENCE_API_KEY', label: 'API-Key', placeholder: '••••••••••••••••', type: 'password', isSecret: true },
        ],
        docker: [
            { key: 'host', label: 'Docker Host', placeholder: '192.168.1.100' },
            { key: 'port', label: 'Docker API Port', placeholder: '2375', type: 'number' },
            { key: 'tls', label: 'TLS aktivieren', type: 'checkbox' },
            { key: 'api_version', label: 'API Version (optional)', placeholder: '1.43' },
        ],
        linux_server: [
            { key: 'host', label: 'Server Host / IP', placeholder: '192.168.1.100' },
            { key: 'port', label: 'SSH Port', placeholder: '22', type: 'number' },
            { key: 'user', label: 'Benutzer', placeholder: 'root' },
            { key: 'LINUX_SERVER_PASSWORD', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'LINUX_SERVER_SSH_KEY', label: 'RSA/Ed25519 Private Key (optional)', placeholder: '-----BEGIN OPENSSH PRIVATE KEY-----', type: 'password', isSecret: true },
        ],
        wordpress: [
            { key: 'url', label: 'WordPress URL', placeholder: 'https://meine-seite.de' },
            { key: 'username', label: 'Benutzername', placeholder: 'admin' },
            { key: 'WORDPRESS_APP_PASSWORD', label: 'Application Password', placeholder: 'xxxx xxxx xxxx xxxx', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren (Nein bei selbst-signierten Zertifikaten)', type: 'checkbox' },
            { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
        ],
        opnsense: [
            { key: 'host', label: 'Host / IP (ohne https://)', placeholder: '192.168.1.1:4443' },
            { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'OPNSENSE_API_SECRET', label: 'API Secret', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'verify_ssl', label: 'SSL verifizieren', type: 'checkbox' },
            { key: 'ca_cert_pem', label: 'CA-Zertifikat (PEM, optional)', type: 'file', isSecret: true },
        ],
        qdrant: [
            { key: 'url', label: 'Qdrant URL', placeholder: 'http://qdrant:6333' },
            { key: 'QDRANT_API_KEY', label: 'API Key (optional)', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'default_collection', label: 'Default Collection (optional)', placeholder: 'ninko_knowledge' },
        ],
        tasmota: [
            { key: 'host', label: 'Host / IP', placeholder: '192.168.1.50' },
        ],
        checkmk: [
            { key: 'url', label: 'Checkmk URL', placeholder: 'https://monitoring.example.com' },
            { key: 'site', label: 'Site', placeholder: 'mysite' },
            { key: 'username', label: 'Username', placeholder: 'automation' },
            { key: 'password', label: 'Password', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'api_token', label: 'API Token', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        mcp_server: [
            {
                key: 'transport',
                label: 'Transport',
                type: 'select',
                defaultValue: 'stdio',
                options: [
                    { value: 'stdio', label: 'stdio' },
                    { value: 'http', label: 'http' },
                    { value: 'sse', label: 'sse' },
                ],
            },
            {
                key: 'command',
                label: 'Command',
                placeholder: 'npx -y @modelcontextprotocol/server-filesystem /srv/data',
                showWhen: { key: 'transport', values: ['stdio'] },
            },
            {
                key: 'args_json',
                label: 'Command Args (JSON Array)',
                type: 'textarea',
                rows: 4,
                placeholder: '["/srv/data"]',
                showWhen: { key: 'transport', values: ['stdio'] },
            },
            {
                key: 'cwd',
                label: 'Working Directory (optional)',
                placeholder: '/srv/mcp',
                showWhen: { key: 'transport', values: ['stdio'] },
            },
            {
                key: 'env_json',
                label: 'Environment (JSON Object)',
                type: 'textarea',
                rows: 5,
                placeholder: '{"NODE_ENV":"production"}',
                showWhen: { key: 'transport', values: ['stdio'] },
            },
            {
                key: 'url',
                label: 'Server URL',
                placeholder: 'https://mcp.example.com/mcp',
                showWhen: { key: 'transport', values: ['http', 'sse'] },
            },
            {
                key: 'message_url',
                label: 'SSE Message URL (optional)',
                placeholder: 'https://mcp.example.com/messages',
                showWhen: { key: 'transport', values: ['sse'] },
            },
            {
                key: 'headers_json',
                label: 'Headers (JSON Object)',
                type: 'textarea',
                rows: 5,
                placeholder: '{"X-API-Key":"value"}',
                showWhen: { key: 'transport', values: ['http', 'sse'] },
            },
            {
                key: 'protocol_version',
                label: 'Protocol Version',
                placeholder: '2025-03-26',
                defaultValue: '2025-03-26',
            },
            {
                key: 'timeout_seconds',
                label: 'Timeout (seconds)',
                type: 'number',
                placeholder: '20',
                defaultValue: '20',
            },
            {
                key: 'MCP_AUTH_TOKEN',
                label: 'Bearer Token (optional)',
                placeholder: '••••••',
                type: 'password',
                isSecret: true,
            },
        ],
    },

    async loadModulesSettings() {
        // Don't repaint the module list while a bulk update is iterating over
        // the same DOM nodes — it would clobber per-card highlighting and the
        // pending-updates cache.
        if (this._bulkUpdating) return;

        const container = document.getElementById('settings-modules-list');
        try {
            const res = await fetch('/api/settings/modules');
            if (!res.ok) throw new Error(res.statusText);
            const modules = await res.json();

            const updatesRes = await fetch('/api/plugins/check-updates');
            const updatesData = await updatesRes.json();
            const updatesMap = {};
            for (const p of (updatesData.plugins || [])) {
                updatesMap[p.name] = p;
            }

            // Cache names with available updates for the bulk-update button
            this._pendingPluginUpdates = (updatesData.plugins || [])
                .filter(p => p.update_available)
                .map(p => p.name);
            this._updateBulkUpdateButton();

            if (!modules.length) {
                container.innerHTML = '<p class="empty-state">Keine Module gefunden.</p>';
                return;
            }

            container.innerHTML = modules.map(mod => {
                const updateInfo = updatesMap[mod.name] || {};
                const hasUpdate = updateInfo.update_available;
                const safeName = this._escapeHtml(mod.name);
                const safeDisplayName = this._escapeHtml(mod.display_name);
                const safeDesc = this._escapeHtml(mod.description || '');
                const safeVersion = this._escapeHtml(mod.version || '');
                const safeRepoVersion = this._escapeHtml(updateInfo.repo_version || '');
                return `
                <div class="module-config-card" id="module-card-${safeName}">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${safeDisplayName}</span>
                            <span class="module-config-version">v${safeVersion}${hasUpdate ? ' <span class="version-update-indicator">→ ' + safeRepoVersion + '</span>' : ''}</span>
                        </div>
                        <div style="display: flex; gap: 0.5rem; align-items: center; flex-shrink: 0;">
                            ${hasUpdate ? `<button class="btn-primary btn-sm btn-update" data-action="updatePlugin" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" data-self="true" title="Auf Version ${safeRepoVersion} aktualisieren"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px; vertical-align: middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>Update</button>` : ''}
                            <label class="toggle-switch" title="Aktivieren/Deaktivieren">
                                <input type="checkbox" ${mod.enabled ? 'checked' : ''}
                                    id="mod-toggle-${safeName}"
                                    onchange="Ninko.toggleModule('${safeName}', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                            <button class="btn-icon btn-icon-sm" data-action="toggleModuleSettings" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" title="Einstellungen">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                            </button>
                            <button class="btn-icon btn-icon-sm" data-action="deletePlugin" data-args="${JSON.stringify([safeName]).replace(/\"/g, '&quot;')}" title="Plugin unwiderruflich deinstallieren" style="color: var(--error-color);">
                                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            </button>
                        </div>
                    </div>
                    <p class="module-config-desc">${safeDesc}</p>
                    <div id="mod-connections-container-${safeName}" class="module-connections-container">
                        <h5 style="margin-top:0; margin-bottom: 0.5rem; color: var(--text-color);">Verbindungen / Umgebungen</h5>
                        <div id="connections-list-${safeName}">Lade Verbindungen...</div>
                        ${this._renderModuleConnectionForm(mod.name)}
                    </div>
                </div>
            `}).join('');

            // Load connections for enabled modules
            for (const mod of modules) {
                if (mod.enabled && this.ACTION_FIELDS[mod.name]) {
                    await this.loadModuleConnections(mod.name);
                } else if (mod.enabled) {
                    const lc = document.getElementById(`connections-list-${mod.name}`);
                    if (lc) lc.innerHTML = '<p class="text-muted" style="margin:0; font-size: 0.85rem">Keine konfigurationspflichtigen Verbindungen.</p>';
                }
                if (this.ACTION_FIELDS[mod.name]) {
                    this.updateConnectionFieldVisibility(mod.name);
                }
            }

        } catch (e) {
            console.error(e);
            container.innerHTML = '<p class="empty-state">Fehler beim Laden der Module.</p>';
        }
    },

    toggleModuleSettings(name) {
        const connContainer = document.getElementById(`mod-connections-container-${name}`);
        if (connContainer) {
            const opening = connContainer.style.display === 'none';
            connContainer.style.display = opening ? 'block' : 'none';
            if (opening && this.ACTION_FIELDS[name]) {
                this.loadModuleConnections(name);
                this.updateConnectionFieldVisibility(name);
            }
        }
    },

    _getConnectionFieldValue(moduleName, key) {
        const el = document.getElementById(`conn-new-${moduleName}-${key}`);
        if (!el) return '';
        if (el.type === 'checkbox') return el.checked ? 'true' : 'false';
        return (el.value || '').trim();
    },

    updateConnectionFieldVisibility(moduleName) {
        const container = document.getElementById(`mod-connections-container-${moduleName}`);
        if (!container) return;
        const rows = container.querySelectorAll('[data-show-when-key]');
        rows.forEach((row) => {
            const key = row.getAttribute('data-show-when-key');
            const values = (row.getAttribute('data-show-when-values') || '')
                .split(',')
                .map(v => v.trim())
                .filter(Boolean);
            const current = this._getConnectionFieldValue(moduleName, key);
            row.style.display = values.includes(current) ? '' : 'none';
        });
    },

    applyMcpPreset(moduleName, presetId) {
        if (moduleName !== 'mcp_server') return;
        const presets = {
            filesystem_stdio: {
                name: 'Filesystem MCP',
                environment: 'lab',
                description: 'Lokaler stdio-MCP-Server fuer Dateisystemzugriff',
                transport: 'stdio',
                command: 'npx',
                args_json: '["-y","@modelcontextprotocol/server-filesystem","/srv/data"]',
                cwd: '',
                env_json: '{}',
                url: '',
                message_url: '',
                headers_json: '{}',
                protocol_version: '2025-03-26',
                timeout_seconds: '20',
            },
            remote_http: {
                name: 'Remote MCP HTTP',
                environment: 'staging',
                description: 'HTTP-basierter MCP-Server',
                transport: 'http',
                command: '',
                args_json: '[]',
                cwd: '',
                env_json: '{}',
                url: 'https://mcp.example.com/mcp',
                message_url: '',
                headers_json: '{"X-API-Key":"replace-me"}',
                protocol_version: '2025-03-26',
                timeout_seconds: '20',
            },
            remote_sse: {
                name: 'Remote MCP SSE',
                environment: 'staging',
                description: 'SSE-basierter MCP-Server',
                transport: 'sse',
                command: '',
                args_json: '[]',
                cwd: '',
                env_json: '{}',
                url: 'https://mcp.example.com/sse',
                message_url: 'https://mcp.example.com/messages',
                headers_json: '{"Authorization":"Bearer replace-me"}',
                protocol_version: '2025-03-26',
                timeout_seconds: '20',
            },
        };
        const preset = presets[presetId];
        if (!preset) return;

        const setValue = (key, value) => {
            const el = document.getElementById(`conn-new-${moduleName}-${key}`);
            if (!el) return;
            if (el.type === 'checkbox') {
                el.checked = value === true || value === 'true';
            } else {
                el.value = value ?? '';
            }
        };

        document.getElementById(`conn-new-${moduleName}-name`).value = preset.name;
        document.getElementById(`conn-new-${moduleName}-environment`).value = preset.environment;
        document.getElementById(`conn-new-${moduleName}-desc`).value = preset.description;

        Object.entries(preset).forEach(([key, value]) => {
            if (['name', 'environment', 'description'].includes(key)) return;
            setValue(key, value);
        });

        this.updateConnectionFieldVisibility(moduleName);
        showNotification(`MCP-Beispielprofil "${preset.name}" eingefuellt`, 'info');
    },

    async toggleModule(name, enabled) {
        const connContainer = document.getElementById(`mod-connections-container-${name}`);
        if (connContainer && !enabled) {
            connContainer.style.display = 'none';
        }

        try {
            // connection legacy property is left Empty: {}
            await fetch(`/api/settings/modules/${name}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled, connection: {} }),
            });

            showNotification(`${name} ${enabled ? 'aktiviert' : 'deaktiviert'}. Neustart empfohlen.`, 'info');
            if (enabled && this.ACTION_FIELDS[name]) {
                await this.loadModuleConnections(name);
            }
        } catch {
            showNotification(`Fehler beim ${enabled ? 'Aktivieren' : 'Deaktivieren'} von ${name}`, 'error');
        }
    },

    _renderModuleConnectionForm(moduleName) {
        const moduleFields = this.ACTION_FIELDS[moduleName] || [];
        if (!moduleFields.length) return '';
        const presetSection = moduleName === 'mcp_server'
            ? `
                <div class="form-row form-row-sm">
                    <label class="form-label">Beispielprofile</label>
                    <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                        <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'filesystem_stdio']).replace(/\"/g, '&quot;')}">Filesystem stdio</button>
                        <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'remote_http']).replace(/\"/g, '&quot;')}">Remote HTTP</button>
                        <button type="button" class="btn btn-sm btn-outline" data-action="applyMcpPreset" data-args="${JSON.stringify([moduleName, 'remote_sse']).replace(/\"/g, '&quot;')}">Remote SSE</button>
                    </div>
                    <small class="text-muted">Füllt typische MCP-Server-Konfigurationen vor. Werte danach bei Bedarf anpassen.</small>
                </div>
            `
            : '';

        return `
            <div class="add-connection-section">
                <h6 id="conn-form-title-${moduleName}" class="add-connection-title">Neue Verbindung hinzufügen</h6>
                <input type="hidden" id="conn-edit-id-${moduleName}" value="">
                <div class="form-row form-row-sm">
                    <label class="form-label" for="conn-new-${moduleName}-name">Name</label>
                    <input type="text" id="conn-new-${moduleName}-name" class="form-input" placeholder="z.B. Prod Cluster">
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label" for="conn-new-${moduleName}-environment">Umgebung</label>
                    <select id="conn-new-${moduleName}-environment" class="form-select">
                        <option value="prod">Production</option>
                        <option value="staging">Staging</option>
                        <option value="dev">Development</option>
                        <option value="lab">Lab</option>
                    </select>
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label" for="conn-new-${moduleName}-desc">Beschreibung (optional)</label>
                    <input type="text" id="conn-new-${moduleName}-desc" class="form-input" placeholder="...">
                </div>
                ${presetSection}
                ${moduleFields.map(f => {
            const wrapperAttrs = f.showWhen
                ? ` data-show-when-key="${f.showWhen.key}" data-show-when-values="${f.showWhen.values.join(',')}"`
                : '';
            if (f.type === 'checkbox') {
                return `
                        <div class="form-row form-row-sm"${wrapperAttrs}>
                            <label class="form-label">
                                <input type="checkbox" id="conn-new-${moduleName}-${f.key}" checked>
                                ${f.label}
                            </label>
                        </div>`;
            }
            if (f.type === 'select') {
                const options = (f.options || []).map(opt => `
                                <option value="${this._escapeHtml(opt.value)}" ${opt.value === (f.defaultValue || '') ? 'selected' : ''}>${this._escapeHtml(opt.label)}</option>
                            `).join('');
                const handler = moduleName === 'mcp_server' && f.key === 'transport'
                    ? ` onchange="Ninko.updateConnectionFieldVisibility('${moduleName}')"`
                    : '';
                return `
                        <div class="form-row form-row-sm"${wrapperAttrs}>
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <select id="conn-new-${moduleName}-${f.key}" class="form-select"${handler}>
                                ${options}
                            </select>
                        </div>`;
            }
            if (f.type === 'file') {
                return `
                        <div class="form-row form-row-sm"${wrapperAttrs}>
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <input type="file" id="conn-new-${moduleName}-${f.key}" class="form-input form-file">
                            ${f.isSecret ? '<small class="text-muted">Leer lassen, um das vorhandene Zertifikat beizubehalten.</small>' : ''}
                        </div>`;
            }
            if (f.type === 'textarea') {
                return `
                        <div class="form-row form-row-sm"${wrapperAttrs}>
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <textarea id="conn-new-${moduleName}-${f.key}"
                                class="form-input form-textarea"
                                rows="${f.rows || 4}"
                                placeholder="${f.placeholder || ''}">${f.defaultValue || ''}</textarea>
                        </div>`;
            }
            return `
                        <div class="form-row form-row-sm"${wrapperAttrs}>
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <input type="${f.type || 'text'}" id="conn-new-${moduleName}-${f.key}"
                                class="form-input" placeholder="${f.placeholder || ''}" value="${f.defaultValue || ''}">
                        </div>`;
        }).join('')}
                <div class="form-row form-row-sm">
                    <label class="form-label">
                        <input type="checkbox" id="conn-new-${moduleName}-default">
                        Als Standard-Verbindung für dieses Modul setzen
                    </label>
                </div>
                <div class="form-actions add-connection-actions">
                    <span id="mod-save-status-${moduleName}" class="save-status"></span>
                    <button class="btn btn-sm btn-primary" id="conn-save-btn-${moduleName}"
                        data-action="saveConnection" data-args="${JSON.stringify([moduleName]).replace(/\"/g, '&quot;')}">
                        ➕ Speichern
                    </button>
                    <button class="btn btn-sm btn-outline hidden" id="conn-cancel-btn-${moduleName}"
                        data-action="cancelEditConnection" data-args="${JSON.stringify([moduleName]).replace(/\"/g, '&quot;')}">
                        Abbrechen
                    </button>
                </div>
            </div>`;
    },

    async loadModuleConnections(moduleName) {
        const container = document.getElementById(`connections-list-${moduleName}`);
        if (!container) return;

        try {
            const res = await fetch(`/api/connections/${moduleName}?_t=${Date.now()}`, { cache: 'no-store' });
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const connections = data.connections || [];

            if (!connections.length) {
                container.innerHTML = '<p class="text-sm text-muted" style="margin-bottom: 1rem;">Noch keine Verbindungen angelegt.</p>';
                return;
            }

            container.innerHTML = connections.map(c => `
                <div class="cluster-card ${c.is_default ? 'cluster-default' : ''}">
                    <div class="cluster-info">
                        <span class="cluster-name">
                            ${this._escapeHtml(c.name)}
                            <span class="status-badge status-unknown cluster-env-badge">${this._escapeHtml(c.environment || '')}</span>
                        </span>
                        ${c.description ? `<span class="cluster-desc">${this._escapeHtml(c.description)}</span>` : ''}
                        ${c.is_default ? '<span class="status-badge status-ok cluster-default-badge">Standard</span>' : ''}
                    </div>
                    <div class="cluster-actions">
                        ${!c.is_default ? `<button class="btn btn-sm btn-outline" data-action="setDefaultConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">⭐ Standard</button>` : ''}
                        <button class="btn btn-sm btn-outline" data-action="editConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">✎</button>
                        <button class="btn btn-sm btn-danger" data-action="deleteConnection" data-args="${JSON.stringify([moduleName, c.id]).replace(/\"/g, '&quot;')}">${this._ic.trash}</button>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error(`Fehler beim Laden der Connections für ${moduleName}:`, e);
            container.innerHTML = '<p class="text-sm save-error">Fehler beim Laden.</p>';
        }
    },

    async editConnection(moduleName, connectionId) {
        try {
            const res = await fetch(`/api/connections/${moduleName}`, { cache: 'no-store' });
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const conn = (data.connections || []).find(c => c.id === connectionId);
            if (!conn) return;

            // Fill form
            document.getElementById(`conn-edit-id-${moduleName}`).value = conn.id;
            document.getElementById(`conn-new-${moduleName}-name`).value = conn.name;
            document.getElementById(`conn-new-${moduleName}-environment`).value = conn.environment;
            document.getElementById(`conn-new-${moduleName}-desc`).value = conn.description || '';
            document.getElementById(`conn-new-${moduleName}-default`).checked = conn.is_default;

            const fields = this.ACTION_FIELDS[moduleName] || [];
            for (const f of fields) {
                const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
                const val = conn.config ? conn.config[f.key] : '';
                if (f.type === 'checkbox') {
                    // Default to true (checked) unless explicitly set to false
                    el.checked = val === undefined ? true : val === true || val === 'true';
                } else if (f.type !== 'file' && !f.isSecret) {
                    el.value = val || '';
                } else if (f.isSecret) {
                    el.placeholder = '•••••• (Leer lassen, um beizubehalten)';
                    el.value = '';
                }
            }
            this.updateConnectionFieldVisibility(moduleName);

            // Update UI state
            document.getElementById(`conn-form-title-${moduleName}`).textContent = 'Verbindung bearbeiten';
            const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
            saveBtn.innerHTML = '💾 Aktualisieren';
            document.getElementById(`conn-cancel-btn-${moduleName}`).classList.remove('hidden');

            document.getElementById(`conn-form-title-${moduleName}`).scrollIntoView({ behavior: 'smooth' });
        } catch (e) {
            console.error('Fehler beim Laden für Bearbeitung', e);
        }
    },

    cancelEditConnection(moduleName) {
        document.getElementById(`conn-edit-id-${moduleName}`).value = '';
        document.getElementById(`conn-new-${moduleName}-name`).value = '';
        document.getElementById(`conn-form-title-${moduleName}`).textContent = 'Neue Verbindung hinzufügen';

        const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
        saveBtn.innerHTML = '➕ Speichern';
        document.getElementById(`conn-cancel-btn-${moduleName}`).classList.add('hidden');

        const fields = this.ACTION_FIELDS[moduleName] || [];
        for (const f of fields) {
            const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
            if (f.type === 'checkbox') el.checked = true;
            else if (f.type === 'file') el.value = '';
            else el.value = f.defaultValue || '';

            if (f.isSecret) el.placeholder = f.placeholder || '';
        }
        this.updateConnectionFieldVisibility(moduleName);
    },

    async saveConnection(moduleName) {
        const statusEl = document.getElementById(`mod-save-status-${moduleName}`);
        const editId = document.getElementById(`conn-edit-id-${moduleName}`).value;
        const name = document.getElementById(`conn-new-${moduleName}-name`).value.trim();
        const env = document.getElementById(`conn-new-${moduleName}-environment`).value;
        const desc = document.getElementById(`conn-new-${moduleName}-desc`).value.trim();
        const isDefault = document.getElementById(`conn-new-${moduleName}-default`).checked;

        if (!name) {
            statusEl.textContent = 'Name erforderlich';
            statusEl.className = 'save-status save-error';
            return;
        }

        const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
        if (saveBtn) saveBtn.disabled = true;

        statusEl.textContent = 'Speichere…';
        statusEl.className = 'save-status save-pending';

        const config = {};
        const vault_keys = {};
        const fields = this.ACTION_FIELDS[moduleName] || [];

        try {
            for (const f of fields) {
                const el = document.getElementById(`conn-new-${moduleName}-${f.key}`);
                let val = '';
                if (f.type === 'checkbox') {
                    val = el.checked ? "true" : "false"; // bools are usually cast strings or handle natively
                } else if (f.type === 'file') {
                    if (el.files && el.files.length > 0) {
                        const file = el.files[0];
                        const text = await file.text();
                        val = btoa(text);
                    }
                } else {
                    val = el.value.trim();
                }

                if (val) {
                    if (f.isSecret) vault_keys[f.key] = val;
                    else config[f.key] = val;
                }
            }

            if (moduleName === 'mcp_server') {
                const transport = config.transport || 'stdio';
                const jsonChecks = [
                    { key: 'args_json', type: 'array', enabled: transport === 'stdio' },
                    { key: 'env_json', type: 'object', enabled: transport === 'stdio' },
                    { key: 'headers_json', type: 'object', enabled: transport === 'http' || transport === 'sse' },
                ];
                for (const check of jsonChecks) {
                    if (!check.enabled || !config[check.key]) continue;
                    const parsed = JSON.parse(config[check.key]);
                    const isValid =
                        (check.type === 'array' && Array.isArray(parsed)) ||
                        (check.type === 'object' && parsed && typeof parsed === 'object' && !Array.isArray(parsed));
                    if (!isValid) {
                        throw new Error(`${check.key} muss gültiges JSON vom Typ ${check.type} sein.`);
                    }
                }
                if (transport === 'stdio' && !config.command) {
                    throw new Error('Für stdio ist ein Command erforderlich.');
                }
                if ((transport === 'http' || transport === 'sse') && !config.url) {
                    throw new Error(`Für ${transport} ist eine URL erforderlich.`);
                }
            }

            const payload = {
                name: name,
                environment: env,
                description: desc,
                config: config,
                secrets: vault_keys,
                is_default: isDefault
            };

            const url = editId ? `/api/connections/${moduleName}/${editId}` : `/api/connections/${moduleName}`;
            const method = editId ? 'PUT' : 'POST';

            const res = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                statusEl.textContent = 'Gespeichert';
                statusEl.className = 'save-status save-ok';
                showNotification(`Verbindung "${name}" ${editId ? 'aktualisiert' : 'hinzugefügt'}`, 'info');

                this.cancelEditConnection(moduleName);
                await this.loadModuleConnections(moduleName);
            } else {
                const err = await res.json();
                statusEl.textContent = err.detail || 'Fehler';
                statusEl.className = 'save-status save-error';
            }
        } catch (e) {
            console.error(e);
            statusEl.textContent = 'Verbindungsfehler';
            statusEl.className = 'save-status save-error';
        } finally {
            const saveBtn = document.getElementById(`conn-save-btn-${moduleName}`);
            if (saveBtn) saveBtn.disabled = false;
        }
    },

    async deleteConnection(moduleName, connectionId) {
        // HINWEIS: Native confirm() Dialoge brechen in manchen Browsern (Chrome) sofort ab, 
        // wenn im Hintergrund DOM-Updates (durch Websockets/Traefik) getriggert werden.
        // Um ein "Flackern" des Popups zu verhindern, löschen wir direkt.
        if (!await this.confirm('Verbindung wirklich löschen?')) return;
        try {
            const res = await fetch(`/api/connections/${moduleName}/${connectionId}?_t=${Date.now()}`, { method: 'DELETE', cache: 'no-store' });
            if (res.ok) {
                showNotification('Verbindung gelöscht', 'info');
                await this.loadModuleConnections(moduleName);
            } else {
                showNotification('Fehler beim Löschen', 'error');
            }
        } catch {
            showNotification('Verbindungsfehler', 'error');
        }
    },

    async setDefaultConnection(moduleName, connectionId) {
        try {
            const res = await fetch(`/api/connections/${moduleName}/${connectionId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_default: true }),
            });
            if (res.ok) {
                showNotification('Standard-Verbindung aktualisiert', 'info');
                await this.loadModuleConnections(moduleName);
            } else {
                showNotification('Fehler beim Aktualisieren des Defaults', 'error');
            }
        } catch {
            showNotification('Verbindungsfehler', 'error');
        }
    },

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


    // --- Scheduled Tasks ---
    openTaskEditor() {
        document.getElementById('tasks-overview')?.classList.add('hidden');
        document.getElementById('tasks-logs')?.classList.add('hidden');
        document.getElementById('tasks-editor')?.classList.remove('hidden');
        // Formular zurücksetzen
        document.getElementById('sched-task-id').value = ''; // Reset task ID (neue Aufgabe)
        document.getElementById('sched-name').value = '';
        document.getElementById('sched-cron').value = '';
        document.getElementById('sched-prompt').value = '';
        const agentPromptEl = document.getElementById('sched-agent-prompt');
        if (agentPromptEl) agentPromptEl.value = '';
        if (document.getElementById('sched-agent')) document.getElementById('sched-agent').value = '';
        if (document.getElementById('sched-workflow')) document.getElementById('sched-workflow').value = '';
        if (document.getElementById('sched-module')) document.getElementById('sched-module').value = '';
        document.getElementById('sched-enabled').checked = true; // Default enabled
        const typePrompt = document.querySelector('input[name="sched-type"][value="prompt"]');
        if (typePrompt) { typePrompt.checked = true; this.toggleSchedType(); }
        const status = document.getElementById('sched-save-status');
        if (status) status.textContent = '';
        // Save Button zurücksetzen
        const saveBtn = document.getElementById('sched-save-btn');
        if (saveBtn) {
            saveBtn.textContent = '➕ Erstellen';
            saveBtn.onclick = () => this.saveScheduledTask();
        }
        // Dropdowns immer frisch befüllen wenn der Editor geöffnet wird
        this._loadSchedDropdowns();
    },

    async _loadSchedDropdowns() {
        const [wfRes, agRes] = await Promise.all([
            fetch('/api/workflows/'),
            fetch('/api/agents/'),
        ]);
        const wfSelect = document.getElementById('sched-workflow');
        if (wfSelect && wfRes.ok) {
            const wfData = await wfRes.json();
            const workflows = wfData.workflows || [];
            this._wfList = workflows;
            wfSelect.innerHTML = '<option value="">Workflow auswählen…</option>' +
                workflows.map(wf => `<option value="${this._escapeHtml(wf.id)}">${this._escapeHtml(wf.name)}</option>`).join('');
        }
        const agentSelect = document.getElementById('sched-agent');
        if (agentSelect && agRes.ok) {
            const agData = await agRes.json();
            const agents = (agData.agents || []).filter(a => a.enabled !== false);
            this._agentList = agents;
            agentSelect.innerHTML = '<option value="">Agent auswählen…</option>' +
                agents.map(a => `<option value="${this._escapeHtml(a.id)}">${this._escapeHtml(a.name)}</option>`).join('');
        }
    },

    closeTaskEditor() {
        document.getElementById('tasks-editor')?.classList.add('hidden');
        document.getElementById('tasks-overview')?.classList.remove('hidden');
    },

    async loadScheduledTasks() {
        const container = document.getElementById('scheduler-tasks-list');
        if (!container) return;

        try {
            const [workflowsRes, agentsRes, tasksRes] = await Promise.all([
                fetch('/api/workflows/'),
                fetch('/api/agents/'),
                fetch('/api/scheduler/tasks'),
            ]);

            const workflowData = workflowsRes.ok ? await workflowsRes.json() : { workflows: [] };
            const workflows = workflowData.workflows || [];
            this._wfList = workflows;

            const agentData = agentsRes.ok ? await agentsRes.json() : { agents: [] };
            const agents = agentData.agents || [];
            this._agentList = agents;

            // Dropdowns immer befüllen (auch wenn keine Tasks vorhanden)
            const wfSelect = document.getElementById('sched-workflow');
            if (wfSelect) {
                wfSelect.innerHTML = '<option value="">Workflow auswählen…</option>' +
                    workflows.map(wf => `<option value="${this._escapeHtml(wf.id)}">${this._escapeHtml(wf.name)}</option>`).join('');
            }
            const agentSelect = document.getElementById('sched-agent');
            if (agentSelect) {
                agentSelect.innerHTML = '<option value="">Agent auswählen…</option>' +
                    agents.filter(a => a.enabled !== false).map(a =>
                        `<option value="${this._escapeHtml(a.id)}">${this._escapeHtml(a.name)}</option>`
                    ).join('');
            }

            if (!tasksRes.ok) throw new Error(tasksRes.statusText);
            const data = await tasksRes.json();
            const tasks = data.tasks || [];

            if (tasks.length === 0) {
                container.innerHTML = '<p class="empty-state">Keine geplanten Aufgaben vorhanden.<br><span style="font-size:0.85rem;opacity:0.7">Klicke auf „➕ Neue Aufgabe", um loszulegen.</span></p>';
                return;
            }

            container.innerHTML = tasks.map(task => {
                const enabledClass = task.enabled ? '' : 'task-disabled';
                const statusBadge = task.last_result === 'ok'
                    ? '<span class="status-badge status-ok">Erfolgreich</span>'
                    : task.last_result === 'error'
                        ? '<span class="status-badge status-error">Fehlgeschlagen</span>'
                        : '<span class="status-badge status-idle">Ausstehend</span>';

                const nextRun = task.next_run ? new Date(task.next_run).toLocaleString('de-DE') : '-';
                const lastRun = task.last_run ? new Date(task.last_run).toLocaleString('de-DE') : 'Noch nie';

                let taskDetails = `<div class="task-prompt">${this._escapeHtml(task.prompt || '')}</div>`;
                if (task.workflow_id) {
                    const wf = workflows.find(w => w.id === task.workflow_id);
                    taskDetails = `<div class="task-badge task-badge-workflow">${this._ic.branch} Workflow: ${this._escapeHtml(wf ? wf.name : task.workflow_id)}</div>`;
                } else if (task.agent_id) {
                    const ag = agents.find(a => a.id === task.agent_id);
                    taskDetails = `<div class="task-badge task-badge-agent">🤖 Agent: ${this._escapeHtml(ag ? ag.name : task.agent_id)}</div>` +
                        (task.prompt ? `<div class="task-prompt" style="margin-top:0.25rem;">${this._escapeHtml(task.prompt)}</div>` : '');
                }

                return `
                    <div class="task-card ${enabledClass}" data-task-id="${this._escapeHtml(task.id)}">
                        <div class="task-card-header">
                            <div class="task-card-title">
                                <strong>${this._escapeHtml(task.name)}</strong>
                                ${statusBadge}
                                ${task.target_module ? `<span class="task-badge task-badge-module">${this._escapeHtml(task.target_module)}</span>` : ''}
                            </div>
                            <div class="task-card-actions">
                                <button class="btn-icon-sm" data-action="run" title="Jetzt ausführen">${this._ic.play}</button>
                                <button class="btn-icon-sm" data-action="toggle" title="${task.enabled ? 'Deaktivieren' : 'Aktivieren'}">${task.enabled ? this._ic.pause : this._ic.play}</button>
                                <button class="btn-icon-sm" data-action="edit" title="Bearbeiten">✎</button>
                                <button class="btn-icon-sm" data-action="logs" data-task-name="${this._escapeHtml(task.name)}" title="Logs">${this._ic.list}</button>
                                <button class="btn-icon-sm btn-danger-sm" data-action="delete" title="Löschen">${this._ic.trash}</button>
                            </div>
                        </div>
                        <div class="task-card-body">
                            ${taskDetails}
                            <div class="task-meta">
                                <span>${this._ic.cron} <code>${this._escapeHtml(task.cron)}</code></span>
                                <span>Nächste: ${nextRun}</span>
                                <span>Letzte: ${lastRun}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            // Event-Delegation
            container.querySelectorAll('.task-card').forEach(card => {
                const id = card.dataset.taskId;
                card.querySelector('[data-action="run"]')?.addEventListener('click', () => this.runScheduledTask(id));
                card.querySelector('[data-action="toggle"]')?.addEventListener('click', () => this.toggleScheduledTask(id));
                card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.editScheduledTask(id));
                card.querySelector('[data-action="logs"]')?.addEventListener('click', e => {
                    const name = e.currentTarget.dataset.taskName || '';
                    this.viewTaskLogs(id, name);
                });
                card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteScheduledTask(id));
            });

        } catch (err) {
            container.innerHTML = `<p class="text-error">Fehler: ${this._escapeHtml(err.message)}</p>`;
        }
    },

    async saveScheduledTask() {
        const name = document.getElementById('sched-name')?.value?.trim();
        const cron = document.getElementById('sched-cron')?.value?.trim();
        const status = document.getElementById('sched-save-status');

        const type = document.querySelector('input[name="sched-type"]:checked')?.value;
        const prompt = document.getElementById('sched-prompt')?.value?.trim() || "";
        const agentId = document.getElementById('sched-agent')?.value || null;
        const agentPrompt = document.getElementById('sched-agent-prompt')?.value?.trim() || "";
        const workflowId = document.getElementById('sched-workflow')?.value || null;
        const module = document.getElementById('sched-module')?.value || null;

        if (!name || !cron) {
            if (status) status.textContent = 'Name und Zeitplan sind Pflicht.';
            return;
        }

        if (type === 'prompt' && !prompt) {
            if (status) status.textContent = 'Prompt ist Pflicht für Agenten-Aufträge.';
            return;
        }

        if (type === 'agent' && !agentId) {
            if (status) status.textContent = 'Agent muss ausgewählt werden.';
            return;
        }

        if (type === 'workflow' && !workflowId) {
            if (status) status.textContent = 'Workflow muss ausgewählt werden.';
            return;
        }

        try {
            const body = {
                name, cron, enabled: true,
                target_module: module
            };

            if (type === 'prompt') {
                body.prompt = prompt;
            } else if (type === 'agent') {
                body.agent_id = agentId;
                body.prompt = agentPrompt || "";
            } else {
                body.workflow_id = workflowId;
                body.prompt = "";
            }

            const res = await fetch('/api/scheduler/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Fehler');
            }

            showNotification('Aufgabe erstellt!', 'success');
            this.closeTaskEditor();
            await this.loadScheduledTasks();
        } catch (err) {
            if (status) status.textContent = err.message || 'Fehler';
        }
    },

    toggleSchedType() {
        const type = document.querySelector('input[name="sched-type"]:checked')?.value;
        const promptRow = document.getElementById('sched-prompt-row');
        const agentRow = document.getElementById('sched-agent-row');
        const workflowRow = document.getElementById('sched-workflow-row');
        const moduleRow = document.getElementById('sched-module')?.parentElement;

        promptRow?.classList.toggle('hidden', type !== 'prompt');
        agentRow?.classList.toggle('hidden', type !== 'agent');
        workflowRow?.classList.toggle('hidden', type !== 'workflow');
        // Modul-Override nur bei Prompt sinnvoll
        moduleRow?.classList.toggle('hidden', type !== 'prompt');
    },

    async deleteScheduledTask(id) {
        if (!await this.confirm('Aufgabe wirklich löschen?')) return;

        try {
            await fetch(`/api/scheduler/tasks/${id}`, { method: 'DELETE' });
            showNotification('Aufgabe gelöscht.', 'info');
            await this.loadScheduledTasks();
        } catch (err) {
            showNotification(`Fehler: ${err.message}`, 'error');
        }
    },

    async editScheduledTask(id) {
        try {
            // Fetch task details
            const res = await fetch('/api/scheduler/tasks');
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const task = data.tasks?.find(t => t.id === id);
            if (!task) throw new Error('Aufgabe nicht gefunden');

            // Show editor
            this.openTaskEditor();

            // Fill form with task data
            document.getElementById('sched-task-id').value = task.id;
            document.getElementById('sched-name').value = task.name || '';
            document.getElementById('sched-cron').value = task.cron || '';
            document.getElementById('sched-module').value = task.target_module || '';
            document.getElementById('sched-enabled').checked = task.enabled !== false;

            // Determine type and fill accordingly
            let type = 'prompt';
            if (task.workflow_id) type = 'workflow';
            else if (task.agent_id) type = 'agent';

            // Set radio button
            const radio = document.querySelector(`input[name="sched-type"][value="${type}"]`);
            if (radio) radio.checked = true;
            this.toggleSchedType();

            // Fill type-specific fields
            if (type === 'prompt') {
                document.getElementById('sched-prompt').value = task.prompt || '';
            } else if (type === 'agent') {
                document.getElementById('sched-agent').value = task.agent_id || '';
                document.getElementById('sched-agent-prompt').value = task.prompt || '';
            } else {
                document.getElementById('sched-workflow').value = task.workflow_id || '';
            }

            // Update save button
            const saveBtn = document.getElementById('sched-save-btn');
            if (saveBtn) {
                saveBtn.textContent = '💾 Aktualisieren';
                saveBtn.onclick = () => this.updateScheduledTask(id);
            }
        } catch (err) {
            showNotification(`Fehler beim Laden: ${err.message}`, 'error');
        }
    },

    async updateScheduledTask(id) {
        const status = document.getElementById('sched-status');
        if (status) status.textContent = 'Speichere…';

        try {
            const name = document.getElementById('sched-name').value.trim();
            const cron = document.getElementById('sched-cron').value.trim();
            const targetModule = document.getElementById('sched-module').value.trim();
            const enabled = document.getElementById('sched-enabled').checked;
            const type = document.querySelector('input[name="sched-type"]:checked')?.value;

            if (!name || !cron) {
                if (status) status.textContent = 'Name und Cron-Ausdruck erforderlich.';
                return;
            }

            const body = {
                name,
                cron,
                target_module: targetModule || null,
                enabled,
            };

            if (type === 'prompt') {
                body.prompt = document.getElementById('sched-prompt').value.trim();
            } else if (type === 'agent') {
                body.agent_id = document.getElementById('sched-agent').value;
                body.prompt = document.getElementById('sched-agent-prompt').value.trim();
            } else {
                body.workflow_id = document.getElementById('sched-workflow').value;
            }

            const res = await fetch(`/api/scheduler/tasks/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Fehler beim Aktualisieren');
            }

            showNotification('Aufgabe aktualisiert!', 'success');
            this.closeTaskEditor();
            await this.loadScheduledTasks();
        } catch (err) {
            if (status) status.textContent = err.message || 'Fehler';
        }
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

    // -- Marketplace (Multi-Repo) ----------------------------------------------

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

    async toggleScheduledTask(id) {
        try {
            const res = await fetch(`/api/scheduler/tasks/${id}/toggle`, { method: 'PUT' });
            const task = await res.json();
            showNotification(
                `Aufgabe "${task.name}" ${task.enabled ? 'aktiviert' : 'deaktiviert'}.`,
                'info'
            );
            await this.loadScheduledTasks();
        } catch (err) {
            showNotification(`Fehler: ${err.message}`, 'error');
        }
    },

    async runScheduledTask(id) {
        showNotification('Aufgabe wird ausgeführt…', 'info');
        try {
            const res = await fetch(`/api/scheduler/tasks/${id}/run`, { method: 'POST' });
            const result = await res.json();
            showNotification(
                `Aufgabe ausgeführt (${result.duration_ms}ms)`,
                result.status === 'ok' ? 'success' : 'error'
            );
            await this.loadScheduledTasks();
        } catch (err) {
            showNotification(`Fehler: ${err.message}`, 'error');
        }
    },

    async viewTaskLogs(taskId, taskName) {
        const section = document.getElementById('tasks-logs');
        const list = document.getElementById('scheduler-logs-list');
        const nameEl = document.getElementById('scheduler-log-task-name');
        if (!section || !list) return;

        document.getElementById('tasks-overview')?.classList.add('hidden');
        document.getElementById('tasks-editor')?.classList.add('hidden');
        nameEl.textContent = taskName;
        section.classList.remove('hidden');
        list.innerHTML = 'Lade…';

        try {
            const res = await fetch(`/api/scheduler/tasks/${taskId}/logs?limit=20`);
            if (!res.ok) throw new Error(res.statusText);
            const logs = await res.json();

            if (!logs || logs.length === 0) {
                list.innerHTML = '<p class="text-muted"><em>Noch keine Ausführungen.</em></p>';
                return;
            }

            list.innerHTML = logs.map(log => {
                const statusIcon = log.status === 'ok' ? this._ic.check : this._ic.xcircle;
                const time = new Date(log.timestamp).toLocaleString('de-DE');
                const response = log.response ? log.response.substring(0, 300) : '—';
                const truncated = log.response?.length > 300 ? '…' : '';
                return `
                    <div class="log-entry log-entry-${this._escapeHtml(log.status)}">
                        <div class="log-entry-header">
                            <span>${statusIcon} ${time}</span>
                            <span class="log-meta">${Number(log.duration_ms) || 0}ms${log.module_used ? ' · ' + this._escapeHtml(log.module_used) : ''}</span>
                        </div>
                        <div class="log-entry-response">${this._escapeHtml(response)}${truncated}</div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            list.innerHTML = `<p class="text-error">Fehler: ${this._escapeHtml(err.message)}</p>`;
        }
    },

    hideTaskLogs() {
        document.getElementById('tasks-logs')?.classList.add('hidden');
        document.getElementById('tasks-overview')?.classList.remove('hidden');
    },


    applyCronPreset() {
        const preset = document.getElementById('sched-cron-preset')?.value;
        if (preset) {
            document.getElementById('sched-cron').value = preset;
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

    // -------------------------------------------------------
    //  LLM MULTI-PROVIDER
    // -------------------------------------------------------

    async loadLlmProviders() {
        const container = document.getElementById('llm-providers-list');
        if (!container) return;
        try {
            const res = await fetch('/api/settings/llm/providers');
            if (!res.ok) throw new Error(res.statusText);
            const providers = await res.json();
            if (!providers.length) {
                container.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Noch keine Provider konfiguriert.</p>';
                return;
            }
            const statusDot = { connected: '<span class="status-dot connected"></span>', unreachable: '<span class="status-dot disconnected"></span>', unknown: '<span class="status-dot"></span>' };
            container.innerHTML = providers.map(p => `
                <div class="provider-card ${p.is_default ? 'provider-default' : ''}">
                    <div class="provider-card-header">
                        <div>
                            <span class="provider-name">${this._escapeHtml(p.name)}</span>
                            ${p.is_default ? '<span class="badge-default">Standard</span>' : ''}
                        </div>
                        <div class="provider-actions">
                            <span class="provider-status" title="${this._escapeHtml(p.status || '')}">${statusDot[p.status] || statusDot.unknown}</span>
                            <button class="btn btn-sm btn-outline" data-action="testLlmProvider" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">Test</button>
                            <button class="btn-icon btn-icon-sm" data-action="openProviderEditor" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">${this._ic.edit}</button>
                            <button class="btn-icon btn-icon-sm" data-action="deleteLlmProvider" data-args="${JSON.stringify([p.id, p.name]).replace(/\"/g, '&quot;')}" style="color:var(--error-color)">${this._ic.trash}</button>
                        </div>
                    </div>
                    <div class="provider-meta">
                        <span>${this._escapeHtml({ollama:'Ollama',lmstudio:'LM Studio',mlx_server:'MLX Server',openai_compatible:'OpenAI',litellm:'LiteLLM'}[p.backend] || p.backend || '')}</span> · <span>${this._escapeHtml(p.base_url || '')}</span> · <span>${this._escapeHtml(p.model || '')}</span>${p.context_window > 0 ? ` · <span>${(p.context_window >= 1000 ? (p.context_window/1000).toFixed(0)+'k' : p.context_window)} ctx</span>` : ''}${p.verify_ssl === false ? ' · <span style="color:var(--warning-color,#f0b429)" title="SSL-Verifizierung deaktiviert">⚠ SSL off</span>' : ''}
                    </div>
                    ${!p.is_default ? `<button class="btn btn-sm btn-outline" style="margin-top:0.5rem;" data-action="setDefaultProvider" data-args="${JSON.stringify([p.id]).replace(/\"/g, '&quot;')}">Als Standard setzen</button>` : ''}
                </div>
            `).join('');
        } catch { container.innerHTML = '<p class="empty-state">Fehler beim Laden.</p>'; }
    },

    async openProviderEditor(providerId) {
        const editor = document.getElementById('llm-provider-editor');
        document.getElementById('provider-edit-id').value = providerId || '';
        document.getElementById('provider-editor-title').textContent = providerId ? 'Provider bearbeiten' : 'Neuer Provider';
        document.getElementById('provider-name').value = '';
        document.getElementById('provider-backend').value = 'ollama';
        document.getElementById('provider-url').value = '';
        document.getElementById('provider-model').value = '';
        document.getElementById('provider-api-key').value = '';
        document.getElementById('provider-api-key').dataset.hasKey = '0';
        document.getElementById('provider-context-window').value = 0;
        document.getElementById('provider-verify-ssl').checked = true;
        document.getElementById('provider-is-default').checked = false;

        if (providerId) {
            try {
                const res = await fetch('/api/settings/llm/providers');
                const providers = await res.json();
                const p = providers.find(x => x.id === providerId);
                if (p) {
                    document.getElementById('provider-name').value = p.name;
                    document.getElementById('provider-backend').value = p.backend;
                    document.getElementById('provider-url').value = p.base_url;
                    document.getElementById('provider-model').value = p.model;
                    document.getElementById('provider-api-key').value = p.api_key_set ? '••••••••' : '';
                    document.getElementById('provider-api-key').dataset.hasKey = p.api_key_set ? '1' : '0';
                    document.getElementById('provider-context-window').value = p.context_window || 0;
                    document.getElementById('provider-verify-ssl').checked = p.verify_ssl !== false;
                    document.getElementById('provider-is-default').checked = p.is_default;
                }
            } catch (err) { console.warn('loadLLMProviders failed', err); }
        }
        this.toggleProviderApiKey();
        editor.classList.remove('hidden');
    },

    closeProviderEditor() {
        document.getElementById('llm-provider-editor').classList.add('hidden');
    },

    async saveLlmProvider() {
        const statusEl = document.getElementById('provider-save-status');
        statusEl.textContent = 'Speichere…';
        const keyEl = document.getElementById('provider-api-key');
        const keyVal = keyEl?.value || '';
        const apiKey = keyVal && keyVal !== '••••••••' ? keyVal : '';
        const body = {
            name: document.getElementById('provider-name').value,
            backend: document.getElementById('provider-backend').value,
            base_url: document.getElementById('provider-url').value,
            model: document.getElementById('provider-model').value,
            api_key: apiKey,
            is_default: document.getElementById('provider-is-default').checked,
            context_window: parseInt(document.getElementById('provider-context-window').value || '0', 10),
            verify_ssl: document.getElementById('provider-verify-ssl').checked,
        };
        const id = document.getElementById('provider-edit-id').value;
        try {
            const url = id ? `/api/settings/llm/providers/${id}` : '/api/settings/llm/providers';
            const method = id ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (res.ok) {
                statusEl.textContent = 'Gespeichert';
                if (keyEl && body.api_key) {
                    keyEl.value = '••••••••';
                    keyEl.dataset.hasKey = '1';
                }
                showNotification(`Provider "${body.name}" gespeichert`, 'success');
                this.closeProviderEditor();
                this.loadLlmProviders();
            } else { statusEl.textContent = 'Fehler'; }
        } catch { statusEl.textContent = 'Verbindungsfehler'; }
    },

    async deleteLlmProvider(id, name) {
        if (!confirm(`Provider "${name}" löschen?`)) return;
        try {
            const res = await fetch(`/api/settings/llm/providers/${id}`, { method: 'DELETE' });
            if (res.ok) { showNotification(`Provider "${name}" gelöscht`, 'info'); this.loadLlmProviders(); }
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async testLlmProvider(id) {
        showNotification('Teste Verbindung…', 'info');
        try {
            const res = await fetch(`/api/settings/llm/providers/${id}/test`, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'connected') showNotification('Verbindung erfolgreich', 'success');
            else showNotification(`Nicht erreichbar: ${data.error || ''}`, 'error');
            this.loadLlmProviders();
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async setDefaultProvider(id) {
        try {
            const res = await fetch('/api/settings/llm/default', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider_id: id }) });
            if (res.ok) { showNotification('Standard-Provider gesetzt', 'success'); this.loadLlmProviders(); }
        } catch { showNotification('Fehler', 'error'); }
    },

    toggleProviderApiKey() {
        const backend = document.getElementById('provider-backend').value;
        const row = document.getElementById('provider-api-key-row');
        if (row) row.style.display = (backend === 'openai_compatible' || backend === 'litellm' || backend === 'mlx_server') ? '' : 'none';
    },

    async loadEmbedModel() {
        // Legacy-Wrapper – lädt jetzt den vollen Provider
        await this.loadEmbedProvider();
    },

    async loadEmbedProvider() {
        try {
            const res = await fetch('/api/settings/llm/embed-provider');
            if (!res.ok) return;
            const data = await res.json();

            const useCustom = !!data.use_custom;
            const cbEl = document.getElementById('embed-use-custom');
            if (cbEl) {
                cbEl.checked = useCustom;
                this.toggleEmbedCustom();
            }
            const backendEl = document.getElementById('embed-backend');
            if (backendEl && data.backend) backendEl.value = data.backend;
            const urlEl = document.getElementById('embed-base-url');
            if (urlEl) urlEl.value = data.base_url || '';
            // API-Key: nicht vorab befüllen (Sicherheit); Placeholder zeigen
            const modelEl = document.getElementById('embed-model');
            if (modelEl) modelEl.value = data.model || '';
            this.toggleEmbedApiKey();
        } catch { }
    },

    toggleEmbedCustom() {
        const checked = document.getElementById('embed-use-custom')?.checked;
        const fields = document.getElementById('embed-custom-fields');
        if (fields) fields.style.display = checked ? '' : 'none';
    },

    toggleEmbedApiKey() {
        const backend = document.getElementById('embed-backend')?.value;
        const row = document.getElementById('embed-api-key-row');
        if (row) row.style.display = (backend === 'openai_compatible' || backend === 'litellm') ? '' : 'none';
    },

    async loadRoutingMode() {
        try {
            const res = await fetch('/api/settings/routing/mode');
            if (!res.ok) return;
            const data = await res.json();
            const cb = document.getElementById('fn-call-enabled');
            if (cb) cb.checked = data.function_calling_enabled;
            const tcRow = document.getElementById('fn-call-tool-choice-row');
            if (tcRow) tcRow.style.display = data.function_calling_enabled ? '' : 'none';
            const tcEl = document.getElementById('fn-call-tool-choice');
            if (tcEl && data.tool_choice) tcEl.value = data.tool_choice;
        } catch { }
    },

    toggleFnCall() {
        const cb = document.getElementById('fn-call-enabled');
        const tcRow = document.getElementById('fn-call-tool-choice-row');
        if (tcRow) tcRow.style.display = cb?.checked ? '' : 'none';
    },

    async testFnCall() {
        const resultEl = document.getElementById('fn-call-test-result');
        if (resultEl) resultEl.textContent = 'Teste…';
        try {
            const res = await fetch('/api/settings/routing/mode/smoke-test', { method: 'POST' });
            const data = await res.json();
            if (resultEl) {
                if (data.supported) {
                    resultEl.innerHTML = '<span style="color:var(--success-color,#22c55e)">✓ Function Calling wird unterstützt</span>';
                } else {
                    resultEl.innerHTML = `<span style="color:var(--error-color)">✗ Nicht unterstützt: ${this._escapeHtml(data.error || data.recommendation || 'Unbekannt')}</span>`;
                }
            }
        } catch (e) {
            if (resultEl) resultEl.textContent = 'Fehler: ' + e.message;
        }
    },

    async saveRoutingMode() {
        const statusEl = document.getElementById('fn-call-status');
        const enabled = document.getElementById('fn-call-enabled')?.checked ?? true;
        const toolChoice = document.getElementById('fn-call-tool-choice')?.value || 'auto';
        if (statusEl) statusEl.textContent = 'Speichere…';
        try {
            const res = await fetch('/api/settings/routing/mode', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ function_calling_enabled: enabled, tool_choice: toolChoice }),
            });
            if (res.ok) {
                if (statusEl) statusEl.textContent = 'Gespeichert';
                showNotification('Routing-Modus gespeichert', 'success');
            } else {
                if (statusEl) statusEl.textContent = 'Fehler';
            }
        } catch {
            if (statusEl) statusEl.textContent = 'Verbindungsfehler';
        }
    },

    async saveEmbedProvider() {
        const statusEl = document.getElementById('embed-provider-status');
        const model = document.getElementById('embed-model')?.value.trim();
        if (!model) {
            if (statusEl) statusEl.textContent = t('settings.embedModelRequired') || 'Modellname darf nicht leer sein';
            return;
        }
        if (statusEl) statusEl.textContent = t('settings.saving') || 'Speichere…';

        const useCustom = !!document.getElementById('embed-use-custom')?.checked;
        const backend = document.getElementById('embed-backend')?.value || 'lmstudio';
        const baseUrl = document.getElementById('embed-base-url')?.value.trim() || '';
        const apiKey = document.getElementById('embed-api-key')?.value.trim() || '';

        try {
            const res = await fetch('/api/settings/llm/embed-provider', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ use_custom: useCustom, backend, base_url: baseUrl, api_key: apiKey, model }),
            });
            if (res.ok) {
                if (statusEl) statusEl.textContent = t('settings.saved') || 'Gespeichert';
                showNotification(t('settings.embedSaved') || 'Embedding-Provider gespeichert', 'success');
            } else {
                const err = await res.json().catch(() => ({}));
                if (statusEl) statusEl.textContent = err.detail || 'Fehler';
            }
        } catch {
            if (statusEl) statusEl.textContent = t('settings.connectionError') || 'Verbindungsfehler';
        }
    },

    // Legacy – falls irgendwo noch direkt aufgerufen
    async saveEmbedModel() { await this.saveEmbedProvider(); },

    // --- Alert Management ---
    _alertsCache: [],

    async loadAlerts() {
        const container = document.getElementById('alerts-content');
        const loading = document.getElementById('alerts-loading');
        const emptyState = document.getElementById('alerts-empty-state');
        const table = document.getElementById('alerts-table');
        
        loading.style.display = 'block';
        emptyState.style.display = 'none';
        table.style.display = 'none';
        
        try {
            const res = await fetch('/api/alerts');
            const data = await res.json();
            
            if (data.success && data.data && data.data.alerts) {
                this._alertsCache = data.data.alerts;
                this._renderAlertsTable();
                this._updateAlertsBadge();
            }
        } catch (err) {
            console.error('Fehler beim Laden der Alerts:', err);
        } finally {
            loading.style.display = 'none';
        }
    },

    _renderAlertsTable() {
        const emptyState = document.getElementById('alerts-empty-state');
        const table = document.getElementById('alerts-table');
        const tbody = document.getElementById('alerts-table-body');
        
        if (this._alertsCache.length === 0) {
            emptyState.style.display = 'block';
            table.style.display = 'none';
            return;
        }
        
        emptyState.style.display = 'none';
        table.style.display = 'table';
        
        const severityClass = {
            critical: 'alert-severity-critical',
            warning: 'alert-severity-warning',
            info: 'alert-severity-info'
        };
        
        const severityLabel = {
            critical: t('alerts.critical'),
            warning: t('alerts.warning'),
            info: t('alerts.info')
        };
        
        tbody.innerHTML = this._alertsCache.map(alert => {
            const firstSeen = new Date(alert.first_seen).toLocaleString();
            const lastSeen = new Date(alert.last_seen).toLocaleString();
            const sevClass = severityClass[alert.severity] || 'alert-severity-info';
            const sevLabel = severityLabel[alert.severity] || alert.severity;
            
            return `
                <tr data-alert-id="${alert.alert_id}">
                    <td><span class="alert-severity ${sevClass}">${sevLabel}</span></td>
                    <td>${alert.module}</td>
                    <td>${alert.summary}</td>
                    <td>${firstSeen}</td>
                    <td>${lastSeen}</td>
                    <td>
                        <button class="btn-icon-sm" data-action="resolveAlert" data-args="${JSON.stringify([alert.alert_id]).replace(/\"/g, '&quot;')}" title="Resolve">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    },

    async resolveAlert(alertId) {
        if (!confirm(t('alerts.resolveConfirm'))) return;
        
        try {
            const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: 'POST' });
            const data = await res.json();
            
            if (data.success) {
                showNotification(t('alerts.resolved'), 'success');
                this._alertsCache = this._alertsCache.filter(a => a.alert_id !== alertId);
                this._renderAlertsTable();
                this._updateAlertsBadge();
            } else {
                showNotification(data.message || t('alerts.resolveError'), 'error');
            }
        } catch (err) {
            showNotification(t('alerts.resolveError'), 'error');
        }
    },

    _updateAlertsBadge() {
        const badge = document.getElementById('alerts-badge');
        if (!badge) return;
        
        const count = this._alertsCache.length;
        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
    },

    _handleWsAlert(data) {
        if (!data.alert_id) return;

        const exists = this._alertsCache.some(a => a.alert_id === data.alert_id);
        if (!exists) {
            this._alertsCache.push(data);
            this._renderAlertsTable();
            this._updateAlertsBadge();

            const panel = document.getElementById('settings-panel-alerts');
            if (panel && panel.classList.contains('active')) {
                this._renderAlertsTable();
            }
        }
    },

    // Subagent-Step-Handling über SSE (während aktivem Chat-Request)
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
