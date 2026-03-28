/**
 * Ninko – Main Application JavaScript
 */

// ─── i18n ─────────────────────────────────────────────
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
        if (typeof Ninko !== 'undefined') Ninko._updateSafeguardBtn?.();
    },
};

/** Globale Shorthand-Funktion */
function t(key, ...args) { return I18n.t(key, ...args); }

// ──────────────────────────────────────────────────────

const Ninko = {
    ws: null,
    sessionId: null,
    modules: [],
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

    // ─── SVG Icon Library (Lucide-style, currentColor) ───
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
        // 18×18 – Run-Step Status Icons
        hourglass:`<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/></svg>`,
        loader:  `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:ic-spin .9s linear infinite"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>`,
        check:   `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
        xcircle: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        skip:    `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`,
    },

    // ─── Init ───
    async init() {
        console.log('Ninko: Initializing v1.0.1...');

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
            } catch { /* Fallback */ }
        }

        this.switchTab('chat');

        document.addEventListener('change', (e) => {
            if (e.target.name === 'sched-type') {
                this.toggleSchedType();
            }
        });
        this.sessionId = this.getSessionId();
        this.restoreTheme();
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
        this.connectWebSocket();
        this.autoResizeTextarea();
        this.initResizers();
        this.initSidebarTransitions();
        this._checkTtsAvailable();
        this.initSafeguard();
        document.documentElement.classList.remove('light-mode-pre');
        document.body.style.opacity = '1';
    },

    /** Custom Confirm Promise */
    confirm(message, title = 'Bestätigung') {
        return new Promise((resolve) => {
            const modal = document.getElementById('ninko-confirm-modal');
            const msgEl = document.getElementById('ninko-confirm-message');
            const titleEl = document.getElementById('ninko-confirm-title');

            if (msgEl) msgEl.innerText = message;
            if (titleEl) titleEl.innerText = title;
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

    getSessionId() {
        let id = sessionStorage.getItem('ninko_session');
        if (!id) {
            id = this.generateUUID();
            sessionStorage.setItem('ninko_session', id);
        }
        return id;
    },

    // ─── Modules ───
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

            const modulesSidebar = document.getElementById('modules-nav-sidebar');
            const mainContent = document.getElementById('main-content');

            for (const mod of this.modules) {
                if (!mod.enabled) continue;

                const tab = mod.dashboard_tab || {};
                const tabId = tab.id || mod.name;

                // Nav Button in modules sidebar
                const btn = document.createElement('button');
                btn.className = 'settings-tab';
                btn.dataset.moduleTab = tabId;
                btn.innerHTML = `${tab.icon || '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>'}<span>${tab.label || mod.display_name}</span>`;
                btn.addEventListener('click', () => {
                    this.switchModuleTab(tabId);
                });
                modulesSidebar.appendChild(btn);

                // Tab Panel
                const panel = document.createElement('div');
                panel.id = `tab-${tabId}`;
                panel.className = 'tab-panel';

                try {
                    const htmlRes = await fetch(`/api/modules/${mod.name}/frontend/tab.html`);
                    if (htmlRes.ok) {
                        panel.innerHTML = await htmlRes.text();
                    } else {
                        panel.innerHTML = `<div class="module-tab-content"><p class="empty-state">${t('module.noDashboard', mod.display_name)}</p></div>`;
                    }
                } catch {
                    panel.innerHTML = `<div class="module-tab-content"><p class="empty-state">${t('module.dashboardError')}</p></div>`;
                }

                mainContent.appendChild(panel);

                // Load JS
                try {
                    const jsRes = await fetch(`/api/modules/${mod.name}/frontend/tab.js?v=${Date.now()}`);
                    if (jsRes.ok) {
                        const jsCode = await jsRes.text();
                        const script = document.createElement('script');
                        script.textContent = jsCode;
                        document.body.appendChild(script);
                    }
                } catch {
                    // JS optional
                }
            }
            this._buildModulePicker();
        } catch (err) {
            console.error('Module konnten nicht geladen werden:', err);
        }
    },

    _buildModulePicker() {
        const dropdown = document.getElementById('module-picker-dropdown');
        if (!dropdown) return;
        const enabledMods = this.modules.filter(m => m.enabled);
        const autoLabel = t('chat.moduleAuto');
        const items = [
            `<button class="module-picker-item${this._forcedModule === null ? ' selected' : ''}" onclick="Ninko.setForcedModule(null)">
                ${autoLabel}
            </button>`,
            enabledMods.length ? '<div class="module-picker-divider"></div>' : '',
            ...enabledMods.map(m => {
                const icon = m.dashboard_tab?.icon || '';
                const label = m.display_name || m.name;
                return `<button class="module-picker-item${this._forcedModule === m.name ? ' selected' : ''}" onclick="Ninko.setForcedModule('${m.name}')">
                    ${icon ? icon + ' ' : ''}${label}
                </button>`;
            }),
        ];
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

    setForcedModule(name) {
        this._forcedModule = name;
        const btn = document.getElementById('module-picker-btn');
        const label = document.getElementById('module-picker-label');
        if (name === null) {
            label.textContent = t('chat.moduleAuto');
            btn.classList.remove('active');
        } else {
            const mod = this.modules.find(m => m.name === name);
            label.textContent = mod ? (mod.display_name || name) : name;
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


    // ─── Tab Switching ───
    switchTab(tabId) {
        // Redirect tasks/agents/workflows through the automatisierung tab
        if (['tasks', 'agents', 'workflows'].includes(tabId)) {
            if (this.activeTab !== 'automatisierung') {
                this._doSwitchTab('automatisierung');
            }
            this.switchAutoTab(tabId);
            return;
        }
        this._doSwitchTab(tabId);
    },

    _doSwitchTab(tabId) {
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
        document.querySelector(`.nav-tab[data-tab="${tabId}"]`)?.classList.add('active');
        const panel = document.getElementById(`tab-${tabId}`);
        if (panel) panel.classList.add('active');

        this.activeTab = tabId;

        // Show/hide sidebar history section (only in chat tab)
        const historySection = document.getElementById('sidebar-history-section');
        if (historySection) {
            historySection.style.display = tabId === 'chat' ? '' : 'none';
        }

        // Tab-specific init
        if (tabId === 'automatisierung') {
            // Show last active sub-tab, default to tasks
            this.switchAutoTab(this._activeAutoTab || 'tasks');
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
        if (tabId === 'logs') this.startLogPolling();
        if (tabId === 'settings') this.loadSettingsContent();

        // Init module tab if navigated directly (e.g. from chat toolbar)
        const tabObj = this.getTabObject(tabId);
        if (tabObj && typeof tabObj.init === 'function' && !tabObj._initialized) {
            tabObj.init();
            tabObj._initialized = true;
        }
    },

    // ─── Automatisierung Sub-Tab Switching ───
    switchAutoTab(tabId) {
        // Stop workflows timer when leaving workflows sub-tab
        if (this._activeAutoTab === 'workflows' && tabId !== 'workflows') {
            clearInterval(this._wfRunRefreshTimer);
        }

        // Restore previous panel back to main-content (hidden)
        if (this._activeAutoTab && this._activeAutoTab !== tabId) {
            const prev = document.getElementById(`tab-${this._activeAutoTab}`);
            if (prev) {
                document.getElementById('main-content')?.appendChild(prev);
                prev.classList.remove('active');
            }
        }

        // Update sidebar active state
        document.querySelectorAll('#auto-sidebar .settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`#auto-sidebar .settings-tab[data-auto-tab="${tabId}"]`)?.classList.add('active');

        // Move panel into auto-content and activate
        const autoContent = document.getElementById('auto-content');
        const panel = document.getElementById(`tab-${tabId}`);
        if (autoContent && panel) {
            autoContent.appendChild(panel);
            panel.classList.add('active');
        }

        this._activeAutoTab = tabId;

        // Load content
        if (tabId === 'tasks') this.loadScheduledTasks();
        if (tabId === 'agents') this.loadAgents();
        if (tabId === 'workflows') this.loadWorkflows();
    },

    // ─── Module Sub-Tab Switching ───
    switchModuleTab(tabId) {
        // Restore previous module panel back to main-content
        if (this._activeModuleTab && this._activeModuleTab !== tabId) {
            const prev = document.getElementById(`tab-${this._activeModuleTab}`);
            if (prev) {
                document.getElementById('main-content')?.appendChild(prev);
                prev.classList.remove('active');
            }
        }

        // Update sidebar active state
        document.querySelectorAll('#modules-nav-sidebar .settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`#modules-nav-sidebar .settings-tab[data-module-tab="${tabId}"]`)?.classList.add('active');

        // Move panel into modules-content and activate
        const modContent = document.getElementById('modules-content');
        const panel = document.getElementById(`tab-${tabId}`);
        if (modContent && panel) {
            modContent.appendChild(panel);
            panel.classList.add('active');
        }

        this._activeModuleTab = tabId;

        // Init module tab if it has an init function
        const tabObj = this.getTabObject(tabId);
        if (tabObj && typeof tabObj.init === 'function' && !tabObj._initialized) {
            tabObj.init();
            tabObj._initialized = true;
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
        };
        // Fallback: dynamisch registrierte Plugin-Tabs (via Ninko._pluginTabs)
        return map[tabId] || this._pluginTabs[tabId] || null;
    },

    // ─── Chat ───
    _setChatBusy(busy) {
        const btnSend = document.getElementById('btn-send');
        const input = document.getElementById('chat-input');
        if (btnSend) {
            btnSend.classList.toggle('is-stop', busy);
            btnSend.querySelector('.icon-send').style.display = busy ? 'none' : '';
            btnSend.querySelector('.icon-stop').style.display = busy ? '' : 'none';
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

    // ─── Spracheingabe ───
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

        // AbortController für Stop-Funktion
        this._abortController = new AbortController();

        // History-Eintrag sofort anlegen (vor API-Call)
        if (!this.currentHistoryId) {
            this.currentHistoryId = Date.now().toString();
        }
        this._ensureHistoryEntry(text);

        // SSE-Stream für Live-Status öffnen (vor dem POST)
        let evtSource = null;
        try {
            evtSource = new EventSource(`/api/chat/stream?session_id=${encodeURIComponent(this.sessionId)}`);
            evtSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === 'status') {
                        this.updateTypingStatus(data.text);
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: this.sessionId,
                    confirmed: confirmedNow,
                    ...(this._forcedModule ? { force_module: this._forcedModule } : {}),
                }),
                signal: this._abortController.signal,
            });

            evtSource?.close();
            this.hideTyping();

            if (res.ok) {
                const data = await res.json();
                this.addChatMessage('ai', data.response);

                if (data.confirmation_required && data.safeguard) {
                    this._safeguardPendingMessage = text;
                    this._showSafeguardConfirmPrompt(data.safeguard);
                }

                if (data.compacted) {
                    this.addCompactionNotice();
                }

                if (data.module_used) {
                    this.addChatMeta(t('chat.moduleUsed', data.module_used));
                }

                // Save conversation to localStorage history
                this._saveToHistory(text, data.response);
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

    _saveToHistory(userMsg, aiMsg) {
        const existing = this.chatHistory.find(h => h.id === this.currentHistoryId);
        if (existing) {
            existing.messages.push({ role: 'user', text: userMsg }, { role: 'ai', text: aiMsg });
            existing.updatedAt = Date.now();
            this.saveHistory(existing);
        }
    },

    // ─── Chat History ───
    async loadHistory() {
        try {
            const res = await fetch('/api/chat/ui-history');
            if (res.ok) {
                const data = await res.json();
                this.chatHistory = data.conversations || [];
                // Lokalen Cache aktualisieren
                try { localStorage.setItem('ninko_chat_history', JSON.stringify(this.chatHistory)); } catch { /**/ }
            } else {
                throw new Error('API nicht erreichbar');
            }
        } catch {
            // Fallback auf localStorage wenn Server nicht erreichbar
            try {
                const raw = localStorage.getItem('ninko_chat_history');
                this.chatHistory = raw ? JSON.parse(raw) : [];
            } catch {
                this.chatHistory = [];
            }
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
        } catch { /* Server nicht erreichbar – localStorage-Fallback reicht */ }
        // Immer auch lokal cachen
        try { localStorage.setItem('ninko_chat_history', JSON.stringify(this.chatHistory)); } catch { /**/ }
    },

    async deleteHistoryEntry(id) {
        try {
            await fetch(`/api/chat/ui-history/${id}`, { method: 'DELETE' });
        } catch { /**/ }
        this.chatHistory = this.chatHistory.filter(h => h.id !== id);
        try { localStorage.setItem('ninko_chat_history', JSON.stringify(this.chatHistory)); } catch { /**/ }
        this.renderHistory();
    },

    renderHistory() {
        const list = document.getElementById('history-list');
        if (!list) return;

        if (this.chatHistory.length === 0) {
            list.innerHTML = `<div class="history-empty">${t('chat.noHistory')}</div>`;
            return;
        }

        list.innerHTML = this.chatHistory.map(h => `
            <div class="history-item ${h.id === this.currentHistoryId ? 'active' : ''}"
                onclick="Ninko.loadHistoryEntry('${h.id}')"
                title="${h.title}">
                <span class="history-item-text">${h.title}</span>
                <button class="history-item-delete" onclick="event.stopPropagation(); Ninko.deleteHistoryEntry('${h.id}')" title="Chat löschen">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m5 0V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                </button>
            </div>
        `).join('');
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
        const container = document.getElementById('chat-messages');
        container.innerHTML = `
            <div class="welcome-message">
                <div class="logo-wrapper">
                    <img src="/static/images/logo_dashboard_new.png?v=3" alt="Ninko Core" class="welcome-illustration" />
                    <div class="eye eye-left"></div>
                    <div class="eye eye-right"></div>
                </div>
                <h2>Ninko</h2>
                <p>${t('chat.welcome.desc')}</p>
                <div class="quick-actions">
                    <button class="quick-action" onclick="Ninko.sendQuick(this.dataset.msg)" data-msg="${t('quick.createAgentMsg')}">${t('quick.createAgent')}</button>
                    <button class="quick-action" onclick="Ninko.sendQuick(this.dataset.msg)" data-msg="${t('quick.rememberFactMsg')}">${t('quick.rememberFact')}</button>
                    <button class="quick-action" onclick="Ninko.sendQuick(this.dataset.msg)" data-msg="${t('quick.webSearchMsg')}">${t('quick.webSearch')}</button>
                    <button class="quick-action" onclick="Ninko.sendQuick(this.dataset.msg)" data-msg="${t('quick.showAgentsMsg')}">${t('quick.showAgents')}</button>
                </div>
            </div>`;

        // Switch back to centered state
        this._setChatState('centered');

        // New session
        this.sessionId = this.generateUUID();
        sessionStorage.setItem('ninko_session', this.sessionId);
        this.currentHistoryId = null;

        const label = document.getElementById('chat-session-label');
        if (label) label.textContent = t('chat.newChat');

        this.renderHistory();
    },

    // ─── Context Clear ───
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

        const label2 = document.getElementById('chat-session-label');
        if (label2) label2.textContent = t('chat.newChat');
        showNotification(t('chat.contextClearedNotif'), 'info');
    },

    // ─── Theme Toggle ───
    restoreTheme() {
        const saved = localStorage.getItem('ninko_theme');
        if (saved === 'light') {
            document.body.classList.add('light-mode');
            const btn = document.getElementById('theme-toggle');
            if (btn) btn.innerHTML = '<svg id="theme-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>';
        }
    },

    toggleTheme() {
        const isLight = document.body.classList.toggle('light-mode');
        localStorage.setItem('ninko_theme', isLight ? 'light' : 'dark');
        const btn = document.getElementById('theme-toggle');
        if (btn) {
            btn.innerHTML = isLight
                ? '<svg id="theme-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>'
                : '<svg id="theme-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
        }
    },

    sendQuick(textOrKey) {
        if (!textOrKey || textOrKey === 'undefined') return;
        const input = document.getElementById('chat-input');
        input.value = textOrKey;
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

        // Track in memory
        const msgId = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
        if (trackInMemory && (role === 'user' || role === 'ai')) {
            this._chatMessages.push({ id: msgId, role, text });
        }

        const avatarUser = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>';
        const avatarAi = '<img src="/static/images/chat_fox.png" class="chat-avatar-fox" alt="AI">';

        const avatar = role === 'user' ? avatarUser : avatarAi;

        const retryBtn = role === 'ai'
            ? `<button class="chat-action-btn" title="Wiederholen" onclick="Ninko.retryMessage('${msgId}')">↺</button>`
            : '';

        const speakerIcon = `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>`;
        const ttsBtn = (role === 'ai' && this._ttsAvailable)
            ? `<button class="chat-action-btn chat-action-tts" data-tts-id="${msgId}" title="Vorlesen" onclick="Ninko.speakMessage('${msgId}')">${speakerIcon}</button>`
            : '';

        const div = document.createElement('div');
        div.className = `chat-message ${role}`;
        div.dataset.msgId = msgId;
        div.innerHTML = `
            <div class="chat-bubble-group">
                <div class="chat-bubble">${this.formatText(text)}</div>
                <div class="chat-actions">
                    ${ttsBtn}
                    ${retryBtn}
                    <button class="chat-action-btn chat-action-delete" title="Löschen" onclick="Ninko.deleteMessage('${msgId}')"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
                </div>
            </div>
        `;

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
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

    async _checkTtsAvailable() {
        try {
            const res = await fetch('/api/settings/tts');
            if (res.ok) {
                const data = await res.json();
                this._ttsAvailable = !!data.TTS_ENABLED;
            }
        } catch { /* TTS bleibt deaktiviert */ }
    },

    // ─── Safeguard Toggle ───────────────────────────────────────────────────

    async initSafeguard() {
        try {
            const res = await fetch('/api/safeguard/status');
            if (res.ok) {
                const data = await res.json();
                this._safeguardEnabled = !!data.enabled;
                this._updateSafeguardBtn();
            }
        } catch { /* Safeguard-Status nicht abfragbar — Default: on */ }
    },

    async toggleSafeguard() {
        const newState = !this._safeguardEnabled;
        const endpoint = newState ? '/api/safeguard/enable' : '/api/safeguard/disable';
        try {
            const res = await fetch(endpoint, { method: 'POST' });
            if (res.ok) {
                this._safeguardEnabled = newState;
                this._updateSafeguardBtn();
            }
        } catch { /* Zustandsänderung fehlgeschlagen */ }
    },

    _updateSafeguardBtn() {
        const btn = document.getElementById('btn-safeguard');
        if (!btn) return;
        if (this._safeguardEnabled) {
            btn.classList.add('safeguard-on');
            btn.classList.remove('safeguard-off');
            btn.title = t('safeguard.btnTitleOn');
        } else {
            btn.classList.remove('safeguard-on');
            btn.classList.add('safeguard-off');
            btn.title = t('safeguard.btnTitleOff');
        }
    },

    _showSafeguardConfirmPrompt(sg) {
        document.getElementById('safeguard-confirm-prompt')?.remove();
        const container = document.getElementById('chat-messages');
        const catClass = `sg-${(sg.category || 'unknown').toLowerCase()}`;
        const div = document.createElement('div');
        div.className = 'safeguard-confirm-prompt';
        div.id = 'safeguard-confirm-prompt';
        div.innerHTML = `
            <div class="safeguard-confirm-content">
                <span class="safeguard-confirm-category ${catClass}">${sg.category}</span>
                <div class="safeguard-confirm-actions">
                    <button class="btn-confirm-action btn-confirm-run" onclick="Ninko.confirmSafeguardAction()">${t('safeguard.confirmRun')}</button>
                    <button class="btn-confirm-action btn-confirm-cancel" onclick="Ninko.cancelSafeguardAction()">${t('safeguard.confirmCancel')}</button>
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

    showTyping() {
        this._typingSteps = [];
        const container = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.className = 'chat-message ai';
        div.id = 'typing-indicator';
        div.innerHTML = `
            <div class="chat-bubble typing-bubble">
                <div class="typing-steps" id="typing-steps">
                    <div class="typing-step typing-step-active">
                        <span class="typing-spinner"></span>
                        <span class="typing-step-text">…</span>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    hideTyping() {
        document.getElementById('typing-indicator')?.remove();
        this._typingSteps = [];
    },

    updateTypingStatus(text) {
        const stepsEl = document.getElementById('typing-steps');
        if (!stepsEl) return;

        // Aktiven Step als erledigt markieren
        const activeStep = stepsEl.querySelector('.typing-step-active');
        if (activeStep) {
            activeStep.classList.remove('typing-step-active');
            activeStep.classList.add('typing-step-done');
            const spinner = activeStep.querySelector('.typing-spinner');
            if (spinner) spinner.outerHTML = '<span class="typing-check">✓</span>';
        }

        // Alten Steps begrenzen (max. 3 erledigte anzeigen)
        const done = stepsEl.querySelectorAll('.typing-step-done');
        if (done.length > 3) done[0].remove();

        // Neuen aktiven Step hinzufügen
        const newStep = document.createElement('div');
        newStep.className = 'typing-step typing-step-active typing-step-enter';
        newStep.innerHTML = `<span class="typing-spinner"></span><span class="typing-step-text">${text}</span>`;
        stepsEl.appendChild(newStep);
        // Animation starten
        requestAnimationFrame(() => newStep.classList.add('typing-step-visible'));

        const container = document.getElementById('chat-messages');
        if (container) container.scrollTop = container.scrollHeight;
    },

    formatText(text) {
        // [KUMIO_IMAGE:url] → inline <img> Tag
        text = text.replace(/\[KUMIO_IMAGE:(\/api\/images\/[^\]]+)\]/g,
            '<img src="$1" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">');
        // Fallback: /api/images/ URLs die der LLM als Link formatiert hat
        text = text.replace(/<a[^>]*href="(\/api\/images\/[\w\-]+\.\w+)"[^>]*>[^<]*<\/a>/g,
            '<img src="$1" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">');
        // Fallback: nackte /api/images/ URLs im Text
        text = text.replace(/(?<![="])(\/api\/images\/[\w\-]+\.\w+)/g,
            '<img src="$1" alt="Generiertes Bild" style="max-width:100%;border-radius:8px;margin:0.5rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.15);">');
        if (typeof marked !== 'undefined') {
            // marked.js verfügbar: vollständiges Markdown-Rendering (Tabellen, Listen, etc.)
            const html = marked.parse(text, {
                breaks: true,
                gfm: true,
            });
            // Links immer in neuem Tab öffnen
            return html.replace(/<a /g, '<a target="_blank" rel="noopener noreferrer" ');
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

    // ─── WebSocket ───
    connectWebSocket() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${proto}//${location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
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
                // Reconnect nach 5s
                setTimeout(() => this.connectWebSocket(), 5000);
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

    // ─── Settings ───
    toggleSettings() {
        this.switchTab('settings');
    },

    switchSettingsTab(tabId) {
        // Stop log polling when leaving logs sub-panel
        this.stopLogPolling();

        document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));

        document.querySelector(`.settings-tab[data-settings-tab="${tabId}"]`)?.classList.add('active');
        document.getElementById(`settings-panel-${tabId}`)?.classList.add('active');

        // Load content when switching tabs
        if (tabId === 'llm') { this.loadLlmSettings(); this.loadLlmProviders(); this.loadEmbedModel(); }
        if (tabId === 'modules') { this.loadModulesSettings(); this.loadMarketplaceConfig(); }
        if (tabId === 'k8s') this.loadK8sClusters();
        if (tabId === 'language') this.renderLanguageTab();
        if (tabId === 'tts') { this.loadSttSettings(); this.loadTtsSettings(); this.loadTtsVoices(); }
        if (tabId === 'imagegen') this.loadImageGenProvider();
        if (tabId === 'logs') this.startLogPolling();
    },

    // ─── Language ───
    async setLanguage(lang) {
        // UI sofort aktualisieren
        await I18n.load(lang);
        localStorage.setItem('ninko_lang', lang);

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
                            onclick="Ninko.setLanguage('${l.code}')">
                            <span class="lang-flag">${l.flag}</span>
                            <span class="lang-name">${l.label}</span>
                        </button>
                    `).join('')}
                </div>
            </div>`;
    },

    async loadSettingsContent() {
        // Load default tab (LLM)
        await this.loadLlmSettings();
        this.loadLlmProviders();
        this.loadEmbedModel();
    },

    // ─── STT Settings ───
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
            if (keyEl) keyEl.value = d.STT_API_KEY ? '••••••••' : '';
            if (keyEl) keyEl.dataset.hasKey = d.STT_API_KEY ? '1' : '';

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
            st.innerHTML = `<span class="sf sf-error">${err.message}</span>`;
        } finally {
            btn.disabled = false;
        }
    },

    // ─── TTS Settings ───
    async loadTtsSettings() {
        // Stimmen laden und Select befüllen
        let voices = [];
        try {
            const vRes = await fetch('/api/tts/voices');
            if (vRes.ok) voices = await vRes.json();
        } catch { /* ignore */ }
        const sel = document.getElementById('tts-default-voice');
        if (sel) {
            sel.innerHTML = '<option value="">-- Stimme wählen --</option>' +
                voices.map(v => `<option value="${v.lang}/${v.name}">${v.lang}/${v.name} (${v.quality})</option>`).join('');
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
            st.innerHTML = `<span class="sf sf-error">${err.message}</span>`;
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
                sel.innerHTML = '<option value="">-- Stimme wählen --</option>' +
                    voices.map(v => `<option value="${v.lang}/${v.name}">${v.lang}/${v.name} (${v.quality})</option>`).join('');
                if (current) sel.value = current;
            }
            if (voices.length === 0) {
                container.innerHTML = '<p class="text-muted">Keine Stimmen installiert. Stimme unten herunterladen.</p>';
                return;
            }
            container.innerHTML = `<table class="data-table"><thead><tr><th>Sprache</th><th>Name</th><th>Qualität</th><th></th></tr></thead><tbody>
                ${voices.map(v => `<tr>
                    <td>${v.lang}</td>
                    <td>${v.name}</td>
                    <td>${v.quality}</td>
                    <td><button class="btn btn-outline btn-sm" style="color:var(--error-color);border-color:var(--error-color);"
                        onclick="Ninko.deleteTtsVoice('${v.lang}','${v.name}')"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button></td>
                </tr>`).join('')}
            </tbody></table>`;
        } catch (err) {
            container.innerHTML = `<p class="text-muted">Fehler: ${err.message}</p>`;
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
                st.innerHTML = `<span class="sf sf-ok">${lang}/${voice} installiert</span>`;
                st.className = 'save-status';
                this.loadTtsVoices();
            }
        } catch (err) {
            st.innerHTML = `<span class="sf sf-error">${err.message}</span>`;
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

    // ─── LLM Settings ───
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

    // ─── Image Generation Provider ───
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
        };
        modelInput.placeholder = placeholders[backend] || 'Leer = Standard-Modell';
    },

    // ─── Module Settings & Connections ───
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
        ],
        kubernetes: [
            { key: 'context', label: 'Context (optional)', placeholder: 'kubernetes-admin@prod' },
            { key: 'kubeconfig', label: 'Kubeconfig-Datei', type: 'file', isSecret: true },
        ],
        pihole: [
            { key: 'url', label: 'Pi-hole URL', placeholder: 'http://192.168.1.2' },
            { key: 'password', label: 'Passwort', placeholder: '••••••', type: 'password', isSecret: true },
        ],
        ionos: [
            { key: 'api_key', label: 'API-Key', placeholder: 'prefix.secret', type: 'password', isSecret: true },
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
        teams: [
            { key: 'MICROSOFT_APP_ID', label: 'Microsoft App ID', placeholder: 'e.g. 1234abcd-1234-abcd-1234-abcd1234abcd' },
            { key: 'MICROSOFT_APP_PASSWORD', label: 'Microsoft App Password / Client Secret', placeholder: '••••••', type: 'password', isSecret: true },
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
        ],
        opnsense: [
            { key: 'host', label: 'Host / IP (ohne https://)', placeholder: '192.168.1.1:4443' },
            { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password', isSecret: true },
            { key: 'OPNSENSE_API_SECRET', label: 'API Secret', placeholder: '••••••', type: 'password', isSecret: true },
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
    },

    async loadModulesSettings() {
        const container = document.getElementById('settings-modules-list');
        try {
            const res = await fetch('/api/settings/modules');
            if (!res.ok) throw new Error(res.statusText);
            const modules = await res.json();

            if (!modules.length) {
                container.innerHTML = '<p class="empty-state">Keine Module gefunden.</p>';
                return;
            }

            container.innerHTML = modules.map(mod => `
                <div class="module-config-card" id="module-card-${mod.name}">
                    <div class="module-config-header">
                        <div class="module-config-info">
                            <span class="module-config-name">${mod.display_name}</span>
                            <span class="module-config-version">v${mod.version}</span>
                        </div>
                        <div style="display: flex; gap: 0.5rem; align-items: center; flex-shrink: 0;">
                            <label class="toggle-switch" title="Aktivieren/Deaktivieren">
                                <input type="checkbox" ${mod.enabled ? 'checked' : ''}
                                    id="mod-toggle-${mod.name}"
                                    onchange="Ninko.toggleModule('${mod.name}', this.checked)">
                                <span class="toggle-slider"></span>
                            </label>
                            <button class="btn-icon btn-icon-sm" onclick="Ninko.toggleModuleSettings('${mod.name}')" title="Einstellungen">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                            </button>
                            <button class="btn-icon btn-icon-sm" onclick="Ninko.deletePlugin('${mod.name}')" title="Plugin unwiderruflich deinstallieren" style="color: var(--error-color);">
                                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            </button>
                        </div>
                    </div>
                    <p class="module-config-desc">${mod.description}</p>
                    <div id="mod-connections-container-${mod.name}" style="display: none; border-top: 1px dashed var(--border-color); padding-top: 1rem; margin-top: 1rem;">
                        <h5 style="margin-top:0; margin-bottom: 0.5rem; color: var(--text-color);">Verbindungen / Umgebungen</h5>
                        <div id="connections-list-${mod.name}">Lade Verbindungen...</div>
                        ${this._renderModuleConnectionForm(mod.name)}
                    </div>
                </div>
            `).join('');

            // Load connections for enabled modules
            for (const mod of this.modules) {
                if (mod.enabled && this.ACTION_FIELDS[mod.name]) {
                    await this.loadModuleConnections(mod.name);
                } else if (mod.enabled) {
                    const lc = document.getElementById(`connections-list-${mod.name}`);
                    if (lc) lc.innerHTML = '<p class="text-muted" style="margin:0; font-size: 0.85rem">Keine konfigurationspflichtigen Verbindungen.</p>';
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
            connContainer.style.display = connContainer.style.display === 'none' ? 'block' : 'none';
        }
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

        return `
            <div class="add-connection-section" style="margin-top: 1rem; padding: 1rem; background: var(--bg-body); border-radius: 6px; border: 1px solid var(--border-color)">
                <h6 id="conn-form-title-${moduleName}" style="margin-top:0; margin-bottom: 1rem;">Neue Verbindung hinzufügen</h6>
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
                ${moduleFields.map(f => {
            if (f.type === 'checkbox') {
                return `
                        <div class="form-row form-row-sm">
                            <label class="form-label">
                                <input type="checkbox" id="conn-new-${moduleName}-${f.key}" checked>
                                ${f.label}
                            </label>
                        </div>`;
            }
            if (f.type === 'file') {
                return `
                        <div class="form-row form-row-sm">
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <input type="file" id="conn-new-${moduleName}-${f.key}" class="form-input form-file">
                        </div>`;
            }
            return `
                        <div class="form-row form-row-sm">
                            <label class="form-label" for="conn-new-${moduleName}-${f.key}">${f.label}</label>
                            <input type="${f.type || 'text'}" id="conn-new-${moduleName}-${f.key}"
                                class="form-input" placeholder="${f.placeholder || ''}">
                        </div>`;
        }).join('')}
                <div class="form-row form-row-sm">
                    <label class="form-label">
                        <input type="checkbox" id="conn-new-${moduleName}-default">
                        Als Standard-Verbindung für dieses Modul setzen
                    </label>
                </div>
                <div class="form-actions" style="margin-top: 1rem; display: flex; gap: 0.5rem; align-items: center;">
                    <span id="mod-save-status-${moduleName}" class="save-status"></span>
                    <button class="btn btn-sm btn-primary" id="conn-save-btn-${moduleName}"
                        onclick="Ninko.saveConnection('${moduleName}')">
                        ➕ Speichern
                    </button>
                    <button class="btn btn-sm btn-outline hidden" id="conn-cancel-btn-${moduleName}"
                        onclick="Ninko.cancelEditConnection('${moduleName}')">
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
                <div class="cluster-card ${c.is_default ? 'cluster-default' : ''}" style="margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 1rem; background: var(--bg-hover); border-radius: 4px; border: 1px solid var(--border-color);">
                    <div class="cluster-info" style="display: flex; flex-direction: column; gap: 0.25rem;">
                        <span class="cluster-name" style="font-weight: 500;">
                            ${this._escapeHtml(c.name)}
                            <span class="status-badge" style="font-size: 0.6rem; padding: 0.1rem 0.4rem; background: var(--bg-body); border: 1px solid var(--border-color); color: var(--text-color); margin-left: 0.5rem;">${this._escapeHtml(c.environment || '')}</span>
                        </span>
                        ${c.description ? `<span style="font-size: 0.8rem; color: var(--text-muted);">${this._escapeHtml(c.description)}</span>` : ''}
                        ${c.is_default ? '<span class="status-badge status-ok" style="align-self: flex-start; margin-top: 0.25rem;">Standard</span>' : ''}
                    </div>
                    <div class="cluster-actions" style="display: flex; gap: 0.5rem; align-items: center;">
                        ${!c.is_default ? `<button class="btn btn-sm btn-outline" onclick="Ninko.setDefaultConnection('${moduleName}', '${c.id}')">⭐ Standard</button>` : ''}
                        <button class="btn btn-sm btn-outline" onclick="Ninko.editConnection('${moduleName}', '${c.id}')">✎</button>
                        <button class="btn btn-sm btn-danger" onclick="Ninko.deleteConnection('${moduleName}', '${c.id}')">${this._ic.trash}</button>
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
                    el.checked = val === 'true';
                } else if (f.type !== 'file' && !f.isSecret) {
                    el.value = val || '';
                } else if (f.isSecret) {
                    el.placeholder = '•••••• (Leer lassen, um beizubehalten)';
                    el.value = '';
                }
            }

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
            else el.value = '';

            if (f.isSecret) el.placeholder = f.placeholder || '';
        }
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

    // ─── Textarea Auto-Resize ───
    autoResizeTextarea() {
        const textarea = document.getElementById('chat-input');
        if (textarea) {
            textarea.addEventListener('input', () => {
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 300) + 'px';
            });
        }
    },

    // ─── Resizing ───
    initResizers() {
        // Migrate sidebar width: boost by 20% for unified sidebar with history
        if (!localStorage.getItem('ninko_sidebar_migrated')) {
            const savedWidth = localStorage.getItem('ninko_sidebar_width');
            if (savedWidth) {
                const boosted = Math.min(Math.round(parseInt(savedWidth) * 1.2), 500);
                localStorage.setItem('ninko_sidebar_width', boosted);
            }
            localStorage.setItem('ninko_sidebar_migrated', '1');
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


    // ─── Scheduled Tasks ───
    openTaskEditor() {
        document.getElementById('tasks-overview')?.classList.add('hidden');
        document.getElementById('tasks-logs')?.classList.add('hidden');
        document.getElementById('tasks-editor')?.classList.remove('hidden');
        // Formular zurücksetzen
        document.getElementById('sched-name').value = '';
        document.getElementById('sched-cron').value = '';
        document.getElementById('sched-prompt').value = '';
        const agentPromptEl = document.getElementById('sched-agent-prompt');
        if (agentPromptEl) agentPromptEl.value = '';
        if (document.getElementById('sched-agent')) document.getElementById('sched-agent').value = '';
        if (document.getElementById('sched-workflow')) document.getElementById('sched-workflow').value = '';
        if (document.getElementById('sched-module')) document.getElementById('sched-module').value = '';
        const typePrompt = document.querySelector('input[name="sched-type"][value="prompt"]');
        if (typePrompt) { typePrompt.checked = true; this.toggleSchedType(); }
        const status = document.getElementById('sched-save-status');
        if (status) status.textContent = '';
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
                card.querySelector('[data-action="logs"]')?.addEventListener('click', e => {
                    const name = e.currentTarget.dataset.taskName || '';
                    this.viewTaskLogs(id, name);
                });
                card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteScheduledTask(id));
            });

        } catch (err) {
            container.innerHTML = `<p class="text-error">Fehler: ${err.message}</p>`;
        }
    },

    async addScheduledTask() {
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
                // Hide card immediately, then reload to remove sidebar tab
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

    // ── Marketplace (Multi-Repo) ──────────────────────────────────────────────

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
        return `
        <div class="module-config-card" id="repo-card-${repo.id}" style="margin-bottom:0.75rem;">
            <div class="module-config-header">
                <div class="module-config-info" style="min-width:0;">
                    <span class="module-config-name">${repo.name}</span>
                    ${isOfficial ? `<span class="module-config-version" style="background:rgba(var(--primary-color-rgb),0.15);">${t('marketplace.official')}</span>` : ''}
                    <span class="text-muted" style="font-size:0.75rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; margin-top:0.1rem;">${repo.repo_url} · ${repo.branch}</span>
                </div>
                <div style="display:flex; gap:0.35rem; align-items:center; flex-shrink:0;">
                    <button class="btn btn-outline" onclick="Ninko.loadRepoModules('${repo.id}')"
                        id="repo-load-btn-${repo.id}"
                        style="font-size:0.78rem; padding:0.2rem 0.6rem;">
                        ${t('marketplace.loadModules')}
                    </button>
                    <button class="btn-icon btn-icon-sm" onclick="Ninko.toggleRepoEdit('${repo.id}')" title="${t('marketplace.editRepo')}">
                        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    </button>
                    ${!isOfficial ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.deleteRepo('${repo.id}')" title="${t('marketplace.deleteRepo')}" style="color:var(--error-color);">
                        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>` : ''}
                </div>
            </div>

            <!-- Edit-Form (hidden) -->
            <div id="repo-edit-${repo.id}" style="display:none; border-top:1px dashed var(--border-color); padding-top:0.75rem; margin-top:0.75rem;">
                <div class="form-row form-row-sm">
                    <label class="form-label">${t('marketplace.repoName')}</label>
                    <input id="edit-repo-name-${repo.id}" type="text" class="form-input" value="${repo.name}">
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label">${t('marketplace.repoUrl')}</label>
                    <input id="edit-repo-url-${repo.id}" type="text" class="form-input" value="${repo.repo_url}" ${isOfficial ? 'readonly style="opacity:0.6;"' : ''}>
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label">${t('marketplace.repoBranch')}</label>
                    <input id="edit-repo-branch-${repo.id}" type="text" class="form-input" value="${repo.branch}" style="max-width:130px;">
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label">${t('marketplace.repoPath')}</label>
                    <input id="edit-repo-path-${repo.id}" type="text" class="form-input" value="${repo.modules_path}">
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label">${t('marketplace.repoToken')} ${repo.github_token_set ? `<span class="text-muted">${t('marketplace.repoTokenSet')}</span>` : ''}</label>
                    <input id="edit-repo-token-${repo.id}" type="password" class="form-input" placeholder="${t('marketplace.repoTokenPlaceholder')}">
                </div>
                <div class="form-row form-row-sm">
                    <label class="form-label"></label>
                    <label style="font-size:0.82rem; cursor:pointer; display:flex; align-items:center; gap:0.35rem;">
                        <input type="checkbox" id="edit-repo-token-clear-${repo.id}"> ${t('marketplace.repoTokenClear')}
                    </label>
                </div>
                <div style="display:flex; gap:0.5rem; margin-top:0.5rem;">
                    <button class="btn btn-primary" onclick="Ninko.saveRepoEdit('${repo.id}')" style="font-size:0.82rem;">${t('marketplace.save')}</button>
                    <button class="btn btn-outline" onclick="Ninko.toggleRepoEdit('${repo.id}')" style="font-size:0.82rem;">${t('marketplace.cancel')}</button>
                    <span id="edit-repo-status-${repo.id}" class="save-status" style="display:inline; align-self:center;"></span>
                </div>
            </div>

            <!-- Modul-Liste -->
            <div id="repo-modules-${repo.id}" style="margin-top:0.5rem;"></div>
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
            return `
            <div class="module-config-card" id="mkt-card-${repoId}-${mod.name}" style="transition:opacity 0.3s;">
                <div class="module-config-header">
                    <div class="module-config-info">
                        <span class="module-config-name">${mod.display_name || mod.name}</span>
                        ${versionInfo}
                    </div>
                    <button class="${btnClass}" onclick="Ninko.installFromRepo('${mod.name}','${repoId}')"
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
                container.innerHTML = `<p style="font-size:0.82rem; color:var(--error-color); padding:0.25rem 0;">${data.error}</p>`;
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
            const res = await fetch(`/api/plugins/install-from-repo/${moduleName}?repo_id=${encodeURIComponent(repoId)}`, { method: 'POST' });
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
            list.innerHTML = `<p class="text-error">Fehler: ${err.message}</p>`;
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

    // ═══════════════════════════════════════════════════════
    //  AGENTEN
    // ═══════════════════════════════════════════════════════

    _agentSteps: [],
    _agentEditId: null,

    async loadAgents() {
        const container = document.getElementById('agents-list');
        try {
            const res = await fetch('/api/agents/');
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const agents = data.agents || [];
            if (!agents.length) {
                container.innerHTML = '<p class="empty-state">Noch keine Agenten konfiguriert.<br><span style="font-size:0.85rem;opacity:0.7">Klicke auf „➕ Neuen Agenten erstellen", um loszulegen.</span></p>';
                return;
            }
            container.innerHTML = agents.map(a => `
                <div class="agent-card ${a.enabled ? '' : 'agent-card-disabled'}" data-agent-id="${this._escapeHtml(a.id)}">
                    <div class="agent-card-header">
                        <div>
                            <span class="agent-card-name">${this._escapeHtml(a.name)}</span>
                            <span class="agent-card-badge ${a.enabled ? 'badge-active' : 'badge-inactive'}">${a.enabled ? 'Aktiv' : 'Inaktiv'}</span>
                        </div>
                        <div class="agent-card-actions">
                            <button class="btn-icon btn-icon-sm" data-action="edit" title="Bearbeiten">${this._ic.edit}</button>
                            <button class="btn-icon btn-icon-sm" data-action="duplicate" title="Duplizieren">${this._ic.copy}</button>
                            <button class="btn-icon btn-icon-sm" data-action="delete" title="Löschen" style="color:var(--error-color)">${this._ic.trash}</button>
                        </div>
                    </div>
                    <p class="agent-card-desc">${a.description ? this._escapeHtml(a.description) : '<em style="color:var(--text-muted)">Keine Beschreibung</em>'}</p>
                    <div class="agent-card-footer">
                        <span>${this._ic.cpu} ${a.llm_provider_id ? this._escapeHtml(a.llm_provider_id) : 'Standard LLM'}</span>
                        <span>${this._ic.layers} ${(a.module_names || []).length} Module</span>
                        <span>${this._ic.steps} ${(a.steps || []).length} Schritte</span>
                        ${a.updated_at ? `<span title="Zuletzt geändert">${this._ic.clock} ${new Date(a.updated_at).toLocaleDateString('de')}</span>` : ''}
                    </div>
                </div>
            `).join('');
            // Event-Delegation – sicher bei beliebigen Agent-Namen
            container.querySelectorAll('.agent-card').forEach(card => {
                const id = card.dataset.agentId;
                const name = card.querySelector('.agent-card-name')?.textContent || '';
                card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.openAgentEditor(id));
                card.querySelector('[data-action="duplicate"]')?.addEventListener('click', () => this.duplicateAgent(id));
                card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteAgent(id, name));
            });
        } catch (e) {
            container.innerHTML = '<p class="empty-state">Fehler beim Laden der Agenten.</p>';
        }
    },

    // ═══════════════════════════════════════════════════════
    //  SKILLS
    // ═══════════════════════════════════════════════════════

    _agentEditorContext: null,   // Agenten-Name beim Öffnen des Skill-Editors aus Agent heraus

    async openSkillsPanel() {
        document.getElementById('agenten-overview').classList.add('hidden');
        document.getElementById('agenten-editor').classList.add('hidden');
        document.getElementById('agenten-skill-editor').classList.add('hidden');
        document.getElementById('agenten-skills').classList.remove('hidden');
        await this.loadSkillsList();
    },

    closeSkillsPanel() {
        document.getElementById('agenten-skills').classList.add('hidden');
        document.getElementById('agenten-overview').classList.remove('hidden');
    },

    async loadSkillsList() {
        const container = document.getElementById('skills-list');
        if (!container) return;
        container.innerHTML = '<p class="empty-state">Lade…</p>';
        try {
            const res = await fetch('/api/skills/');
            const skills = await res.json();
            if (!skills.length) {
                container.innerHTML = '<p class="empty-state">Keine Skills vorhanden.</p>';
                return;
            }
            container.innerHTML = skills.map(s => `
                <div class="agent-card" style="position:relative;">
                    <div class="agent-card-header">
                        <div style="display:flex;align-items:center;gap:0.5rem;flex:1;min-width:0;">
                            <span style="font-size:1.1rem;">${s.builtin ? '🔒' : '📝'}</span>
                            <div style="min-width:0;">
                                <div class="agent-card-name">${s.name}</div>
                                <div class="agent-card-desc">${s.description}</div>
                            </div>
                        </div>
                        <div class="agent-card-actions">
                            ${!s.builtin ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditor('${s.name}')" title="Bearbeiten">${this._ic.edit}</button>` : `<button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditor('${s.name}')" title="Ansehen/Override">${this._ic.edit}</button>`}
                            ${!s.builtin ? `<button class="btn-icon btn-icon-sm" onclick="Ninko.deleteSkill('${s.name}')" title="Löschen" style="color:var(--error-color);">${this._ic.trash}</button>` : ''}
                        </div>
                    </div>
                    <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin-top:0.5rem;">
                        ${s.builtin ? '<span class="status-badge status-unknown" style="font-size:0.7rem;">built-in</span>' : '<span class="status-badge status-ok" style="font-size:0.7rem;">custom</span>'}
                        ${s.modules.length ? s.modules.map(m => `<span class="status-badge" style="font-size:0.7rem;background:rgba(92,158,235,0.15);color:var(--accent-blue);border:1px solid var(--accent-blue);">${m}</span>`).join('') : '<span class="status-badge status-unknown" style="font-size:0.7rem;">alle Agenten</span>'}
                    </div>
                </div>
            `).join('');
        } catch {
            container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden.</p>';
        }
    },

    async openSkillEditor(name) {
        this._agentEditorContext = null;
        await this._showSkillEditorPanel(name);
    },

    openSkillEditorFromAgent() {
        const agentName = document.getElementById('agent-name')?.value?.trim() || '';
        this._agentEditorContext = agentName;
        // Skills-Panel öffnen ohne Overview zu zeigen
        document.getElementById('agenten-overview').classList.add('hidden');
        document.getElementById('agenten-editor').classList.add('hidden');
        document.getElementById('agenten-skills').classList.add('hidden');
        document.getElementById('agenten-skill-editor').classList.remove('hidden');
        this._clearSkillEditor();
        if (agentName) document.getElementById('skill-modules').value = agentName;
        this._updateSkillFrontmatterPreview();
    },

    async _showSkillEditorPanel(name) {
        document.getElementById('agenten-overview').classList.add('hidden');
        document.getElementById('agenten-skills').classList.add('hidden');
        document.getElementById('agenten-editor').classList.add('hidden');
        document.getElementById('agenten-skill-editor').classList.remove('hidden');

        if (name) {
            document.getElementById('skill-editor-title').textContent = 'Skill bearbeiten';
            document.getElementById('skill-edit-name').value = name;
            try {
                const res = await fetch(`/api/skills/${encodeURIComponent(name)}`);
                const s = await res.json();
                document.getElementById('skill-name').value = s.name;
                document.getElementById('skill-name').disabled = true;  // Name nicht änderbar
                document.getElementById('skill-description').value = s.description;
                document.getElementById('skill-modules').value = (s.modules || []).join(', ');
                document.getElementById('skill-content').value = s.content;
                const saveBtn = document.getElementById('skill-save-btn');
                if (saveBtn) saveBtn.textContent = s.builtin ? '💾 Als Override speichern' : '💾 Speichern';
            } catch { showNotification('Fehler beim Laden des Skills', 'error'); }
        } else {
            document.getElementById('skill-editor-title').textContent = 'Neuer Skill';
            this._clearSkillEditor();
        }
        this._updateSkillFrontmatterPreview();
        // Live-Preview bei Eingabe
        ['skill-name', 'skill-description', 'skill-modules'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.oninput = () => this._updateSkillFrontmatterPreview();
        });
    },

    _clearSkillEditor() {
        document.getElementById('skill-edit-name').value = '';
        document.getElementById('skill-name').value = '';
        document.getElementById('skill-name').disabled = false;
        document.getElementById('skill-description').value = '';
        document.getElementById('skill-modules').value = '';
        document.getElementById('skill-content').value = '';
        const saveBtn = document.getElementById('skill-save-btn');
        if (saveBtn) saveBtn.textContent = '💾 Speichern';
    },

    _updateSkillFrontmatterPreview() {
        const name = document.getElementById('skill-name')?.value?.trim() || 'mein-skill';
        const desc = document.getElementById('skill-description')?.value?.trim() || '...';
        const mods = document.getElementById('skill-modules')?.value?.trim();
        const modsLine = mods ? `\nmodules: [${mods}]` : '';
        const pre = document.getElementById('skill-frontmatter-preview');
        if (pre) pre.textContent = `---\nname: ${name}\ndescription: ${desc}${modsLine}\n---`;
    },

    closeSkillEditor() {
        document.getElementById('agenten-skill-editor').classList.add('hidden');
        if (this._agentEditorContext !== null) {
            // Zurück zum Agent-Editor
            document.getElementById('agenten-editor').classList.remove('hidden');
            this._populateAgentSkills();
            this._agentEditorContext = null;
        } else {
            document.getElementById('agenten-skills').classList.remove('hidden');
            this.loadSkillsList();
        }
    },

    async saveSkill() {
        const editName = document.getElementById('skill-edit-name').value;
        const name = document.getElementById('skill-name').value.trim();
        const description = document.getElementById('skill-description').value.trim();
        const content = document.getElementById('skill-content').value.trim();
        const modulesRaw = document.getElementById('skill-modules').value.trim();
        const modules = modulesRaw ? modulesRaw.split(',').map(m => m.trim()).filter(Boolean) : [];

        if (!name || !description || !content) {
            showNotification('Name, Beschreibung und Inhalt sind Pflichtfelder.', 'error');
            return;
        }
        if (!/^[a-z0-9\-]+$/.test(name)) {
            showNotification('Name darf nur Kleinbuchstaben, Zahlen und Bindestriche enthalten.', 'error');
            return;
        }

        const btn = document.getElementById('skill-save-btn');
        if (btn) btn.disabled = true;
        try {
            const isEdit = !!editName;
            const url = isEdit ? `/api/skills/${encodeURIComponent(editName)}` : '/api/skills/';
            const method = isEdit ? 'PUT' : 'POST';
            const body = { name, description, content, modules };
            // Bei PUT wird name nicht gesendet (Teil der URL)
            const bodyToSend = isEdit ? { description, content, modules } : body;

            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bodyToSend),
            });
            if (res.ok) {
                showNotification(`Skill "${name}" gespeichert.`, 'success');
                this.closeSkillEditor();
            } else {
                const err = await res.json();
                showNotification('Fehler: ' + (err.detail || res.statusText), 'error');
            }
        } catch { showNotification('Verbindungsfehler', 'error'); }
        finally { if (btn) btn.disabled = false; }
    },

    async deleteSkill(name) {
        if (!await this.confirm(`Skill "${name}" löschen?`)) return;
        try {
            const res = await fetch(`/api/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (res.ok || res.status === 204) {
                showNotification(`Skill "${name}" gelöscht.`, 'info');
                this.loadSkillsList();
            } else {
                const err = await res.json().catch(() => ({}));
                showNotification('Fehler: ' + (err.detail || 'Unbekannt'), 'error');
            }
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async _populateAgentSkills() {
        const container = document.getElementById('agent-skills-list');
        if (!container) return;
        const agentName = document.getElementById('agent-name')?.value?.trim() || '';
        try {
            const res = await fetch('/api/skills/');
            const skills = await res.json();
            const relevant = skills.filter(s => !s.modules.length || s.modules.includes(agentName));
            if (!relevant.length) {
                container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Keine Skills vorhanden.</p>';
                return;
            }
            container.innerHTML = relevant.map(s => `
                <div style="display:flex;align-items:center;justify-content:space-between;gap:0.5rem;padding:0.3rem 0.5rem;border-radius:4px;background:var(--bg-body);border:1px solid var(--border-color);">
                    <div style="min-width:0;">
                        <span style="font-size:0.82rem;color:var(--text-color);font-weight:500;">${s.name}</span>
                        ${s.builtin ? '<span class="status-badge status-unknown" style="font-size:0.68rem;margin-left:4px;">built-in</span>' : ''}
                        <div style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${s.description}</div>
                    </div>
                    <button class="btn-icon btn-icon-sm" onclick="Ninko.openSkillEditorFromAgentWithName('${s.name}')" title="Bearbeiten" style="flex-shrink:0;">${this._ic.edit}</button>
                </div>
            `).join('');
        } catch {
            container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">Fehler beim Laden.</p>';
        }
    },

    async openSkillEditorFromAgentWithName(skillName) {
        this._agentEditorContext = document.getElementById('agent-name')?.value?.trim() || '';
        document.getElementById('agenten-editor').classList.add('hidden');
        document.getElementById('agenten-skill-editor').classList.remove('hidden');
        await this._showSkillEditorPanel(skillName);
    },

    // ═══════════════════════════════════════════════════════
    //  AGENTEN
    // ═══════════════════════════════════════════════════════

    async openAgentEditor(agentId) {
        this._agentEditId = agentId;
        this._agentSteps = [];
        document.getElementById('agenten-overview').classList.add('hidden');
        document.getElementById('agenten-editor').classList.remove('hidden');

        // Load LLM providers for dropdown
        await this._populateLlmDropdown('agent-llm');
        // Load module list
        await this._populateModuleChecklist();

        if (agentId) {
            document.getElementById('agent-editor-title').textContent = 'Agent bearbeiten';
            try {
                const res = await fetch(`/api/agents/${agentId}`);
                const a = await res.json();
                document.getElementById('agent-name').value = a.name || '';
                document.getElementById('agent-desc').value = a.description || '';
                document.getElementById('agent-system-prompt').value = a.system_prompt || '';
                document.getElementById('agent-llm').value = a.llm_provider_id || '';
                document.getElementById('agent-enabled').checked = a.enabled !== false;
                this._agentSteps = a.steps || [];
                // Check modules
                (a.module_names || []).forEach(name => {
                    const cb = document.getElementById(`agent-mod-${name}`);
                    if (cb) cb.checked = true;
                });
                // Load per-agent safeguard state
                try {
                    const sgRes = await fetch(`/api/safeguard/agents/${agentId}`);
                    if (sgRes.ok) {
                        const sgData = await sgRes.json();
                        const sgCb = document.getElementById('agent-safeguard');
                        if (sgCb) {
                            sgCb.checked = sgData.safeguard_enabled !== false;
                        }
                    }
                } catch { }
            } catch { }
        } else {
            document.getElementById('agent-editor-title').textContent = 'Neuer Agent';
            document.getElementById('agent-name').value = '';
            document.getElementById('agent-desc').value = '';
            document.getElementById('agent-system-prompt').value = '';
            document.getElementById('agent-enabled').checked = true;
            const sgCb = document.getElementById('agent-safeguard');
            if (sgCb) sgCb.checked = true;
        }
        this._renderAgentSteps();
        await this._populateAgentSkills();
    },

    closeAgentEditor() {
        document.getElementById('agenten-overview').classList.remove('hidden');
        document.getElementById('agenten-editor').classList.add('hidden');
        this.loadAgents();
    },

    async _populateLlmDropdown(selectId) {
        const sel = document.getElementById(selectId);
        if (!sel) return;
        try {
            const res = await fetch('/api/settings/llm/providers');
            if (!res.ok) throw new Error(res.statusText);
            const providers = await res.json();
            const extra = providers.map(p => `<option value="${p.id}">${this._escapeHtml(p.name)}${p.is_default ? ' (Standard)' : ''}</option>`).join('');
            sel.innerHTML = '<option value="">Standard verwenden</option>' + extra;
        } catch { }
    },

    async _populateModuleChecklist() {
        const container = document.getElementById('agent-modules-list');
        if (!container) return;
        try {
            const res = await fetch('/api/modules/');
            const modules = await res.json();
            if (!modules.length) { container.innerHTML = '<p class="text-muted">Keine Module verfügbar.</p>'; return; }
            container.innerHTML = modules.filter(m => m.enabled).map(m => `
                <label class="module-checkbox-item">
                    <input type="checkbox" id="agent-mod-${m.name}" value="${m.name}">
                    <span>${m.display_name || m.name}</span>
                </label>
            `).join('');
        } catch { container.innerHTML = '<p class="text-muted">Fehler beim Laden.</p>'; }
    },

    _renderAgentSteps() {
        const container = document.getElementById('agent-steps-list');
        if (!container) return;
        if (!this._agentSteps.length) { container.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Noch keine Schritte definiert.</p>'; return; }
        const typeOptions = [
            { value: 'llm_call',       label: 'LLM-Call' },
            { value: 'module_action',  label: 'Modul' },
            { value: 'condition',      label: 'Bedingung' },
            { value: 'set_variable',   label: 'Variable' },
        ];
        container.innerHTML = this._agentSteps.map((step, idx) => `
            <div class="sequence-step" draggable="true" data-step-idx="${idx}">
                <span class="step-drag-handle">⠿</span>
                <select class="form-select form-select-sm step-type-sel" data-idx="${idx}" style="min-width:130px;">
                    ${typeOptions.map(t => `<option value="${t.value}" ${step.type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                </select>
                <input type="text" class="form-input form-input-sm step-label-inp" data-idx="${idx}"
                    value="${this._escapeHtml(step.label || '')}" placeholder="Beschreibung…">
                <select class="form-select form-select-sm step-err-sel" data-idx="${idx}" style="min-width:80px;">
                    ${['retry', 'skip', 'abort'].map(e => `<option value="${e}" ${step.error_handling === e ? 'selected' : ''}>${e}</option>`).join('')}
                </select>
                <button class="btn-icon btn-icon-sm step-remove-btn" data-idx="${idx}" style="color:var(--error-color)">✕</button>
            </div>
        `).join('');
        // Event-Listener statt inline-onchange
        container.querySelectorAll('.step-type-sel').forEach(sel => {
            sel.addEventListener('change', () => { this._agentSteps[+sel.dataset.idx].type = sel.value; });
        });
        container.querySelectorAll('.step-label-inp').forEach(inp => {
            inp.addEventListener('input', () => { this._agentSteps[+inp.dataset.idx].label = inp.value; });
        });
        container.querySelectorAll('.step-err-sel').forEach(sel => {
            sel.addEventListener('change', () => { this._agentSteps[+sel.dataset.idx].error_handling = sel.value; });
        });
        container.querySelectorAll('.step-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => { this._removeAgentStep(+btn.dataset.idx); });
        });
        this._setupStepDragDrop(container);
    },

    _setupStepDragDrop(container) {
        let dragIdx = null;
        container.querySelectorAll('.sequence-step').forEach(el => {
            el.addEventListener('dragstart', () => {
                dragIdx = +el.dataset.stepIdx;
                el.classList.add('dragging');
            });
            el.addEventListener('dragend', () => {
                el.classList.remove('dragging');
                container.querySelectorAll('.sequence-step').forEach(s => s.classList.remove('drag-over'));
                dragIdx = null;
            });
            el.addEventListener('dragover', e => {
                e.preventDefault();
                el.classList.add('drag-over');
            });
            el.addEventListener('dragleave', () => {
                el.classList.remove('drag-over');
            });
            el.addEventListener('drop', e => {
                e.preventDefault();
                el.classList.remove('drag-over');
                const dropIdx = +el.dataset.stepIdx;
                if (dragIdx === null || dragIdx === dropIdx) return;
                const [moved] = this._agentSteps.splice(dragIdx, 1);
                this._agentSteps.splice(dropIdx, 0, moved);
                this._renderAgentSteps();
            });
        });
    },

    addAgentStep() {
        this._agentSteps.push({ id: Date.now().toString(36), order: this._agentSteps.length, type: 'llm_call', label: '', config: {}, error_handling: 'abort' });
        this._renderAgentSteps();
    },

    _removeAgentStep(idx) {
        this._agentSteps.splice(idx, 1);
        this._renderAgentSteps();
    },

    async saveAgent() {
        const name = document.getElementById('agent-name').value.trim();
        if (!name) { showNotification('Name ist Pflichtfeld', 'error'); return; }
        const saveBtn = document.querySelector('#agenten-editor .btn-primary');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Speichern…'; }
        const selectedModules = [...document.querySelectorAll('#agent-modules-list input[type=checkbox]:checked')].map(cb => cb.value);
        const body = {
            name,
            description: document.getElementById('agent-desc').value,
            system_prompt: document.getElementById('agent-system-prompt').value,
            llm_provider_id: document.getElementById('agent-llm').value || null,
            enabled: document.getElementById('agent-enabled').checked,
            module_names: selectedModules,
            steps: this._agentSteps,
        };
        try {
            const url = this._agentEditId ? `/api/agents/${this._agentEditId}` : '/api/agents/';
            const method = this._agentEditId ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (res.ok) {
                const saved = await res.json();
                const savedId = saved.id || this._agentEditId;
                // Persist per-agent safeguard setting
                if (savedId) {
                    const sgEnabled = document.getElementById('agent-safeguard')?.checked !== false;
                    const sgEndpoint = sgEnabled ? 'enable' : 'disable';
                    try { await fetch(`/api/safeguard/agents/${savedId}/${sgEndpoint}`, { method: 'POST' }); } catch { }
                }
                showNotification(`Agent "${name}" gespeichert`, 'success');
                this.closeAgentEditor();
            } else {
                showNotification('Fehler beim Speichern', 'error');
            }
        } catch { showNotification('Verbindungsfehler', 'error'); }
        finally {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = '💾 Speichern'; }
        }
    },

    async deleteAgent(id, name) {
        if (!await this.confirm(`Agent "${name}" löschen?`)) return;
        try {
            const res = await fetch(`/api/agents/${id}`, { method: 'DELETE' });
            if (res.ok) { showNotification(`Agent "${name}" gelöscht`, 'info'); this.loadAgents(); }
            else showNotification('Fehler beim Löschen', 'error');
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async duplicateAgent(id) {
        try {
            const res = await fetch(`/api/agents/${id}/duplicate`, { method: 'POST' });
            if (res.ok) { showNotification('Agent dupliziert', 'success'); this.loadAgents(); }
            else showNotification('Fehler beim Duplizieren', 'error');
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    // ═══════════════════════════════════════════════════════
    //  WORKFLOWS
    // ═══════════════════════════════════════════════════════

    _wfNodes: [],
    _wfEdges: [],
    _wfSelectedNode: null,
    _wfConnecting: null,
    _wfRunRefreshTimer: null,
    _wfCurrentRunId: null,
    _wfCurrentWorkflowId: null,
    _wfRunNodes: [],
    _wfRunEdges: [],

    async loadWorkflows() {
        const container = document.getElementById('workflows-list');
        try {
            const res = await fetch('/api/workflows/');
            const data = await res.json();
            const wfs = data.workflows || [];
            if (!wfs.length) {
                container.innerHTML = '<p class="empty-state">Noch keine Workflows konfiguriert.<br><span style="font-size:0.85rem;opacity:0.7">Klicke auf „➕ Neuen Workflow erstellen", um loszulegen.</span></p>';
                return;
            }
            container.innerHTML = wfs.map(wf => `
                <div class="workflow-card" data-wf-id="${this._escapeHtml(wf.id)}">
                    <div class="workflow-card-header">
                        <span class="workflow-card-name">${this._escapeHtml(wf.name)}</span>
                        <span class="run-status-badge run-${this._escapeHtml(wf.last_run_status || 'idle')}">${this._escapeHtml(wf.last_run_status || 'idle')}</span>
                    </div>
                    <p class="workflow-card-desc">${this._escapeHtml(wf.description || '')}</p>
                    <div class="workflow-card-meta">
                        <span>${(wf.nodes || []).length} Nodes</span>
                        ${wf.last_run_at ? `<span>Letzter Run: ${new Date(wf.last_run_at).toLocaleString('de')}</span>` : ''}
                        ${wf.updated_at ? `<span title="Zuletzt gespeichert">${this._ic.clock} ${new Date(wf.updated_at).toLocaleDateString('de')}</span>` : ''}
                    </div>
                    <div class="workflow-card-actions">
                        <button class="btn btn-sm btn-primary" data-action="run">${this._ic.play} Run</button>
                        <button class="btn btn-sm btn-outline" data-action="edit">${this._ic.edit} Bearbeiten</button>
                        <button class="btn btn-sm btn-outline" data-action="logs">${this._ic.list} Logs</button>
                        <button class="btn btn-sm btn-outline" data-action="delete" title="Löschen" style="color:var(--error-color)">${this._ic.trash} Löschen</button>
                    </div>
                </div>
            `).join('');
            // Event-Delegation – sicher bei beliebigen Workflow-Namen
            container.querySelectorAll('.workflow-card').forEach(card => {
                const id = card.dataset.wfId;
                const name = card.querySelector('.workflow-card-name')?.textContent || '';
                card.querySelector('[data-action="run"]')?.addEventListener('click', () => this.runWorkflow(id, name));
                card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.openWorkflowEditor(id));
                card.querySelector('[data-action="logs"]')?.addEventListener('click', () => this.openRunHistory(id, name));
                card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteWorkflow(id, name));
            });
        } catch { container.innerHTML = '<p class="empty-state">Fehler beim Laden der Workflows.</p>'; }
    },

    async openWorkflowEditor(wfId) {
        this._wfNodes = [];
        this._wfEdges = [];
        this._wfSelectedNode = null;
        document.getElementById('workflows-overview').classList.add('hidden');
        document.getElementById('workflow-run-dashboard').classList.add('hidden');
        document.getElementById('workflow-editor').classList.remove('hidden');
        document.getElementById('wf-edit-id').value = wfId || '';

        if (wfId) {
            try {
                const res = await fetch(`/api/workflows/${wfId}`);
                const wf = await res.json();
                document.getElementById('wf-name-input').value = wf.name || '';
                document.getElementById('wf-desc-input').value = wf.description || '';
                this._wfNodes = wf.nodes || [];
                this._wfEdges = wf.edges || [];
            } catch { }
        } else {
            document.getElementById('wf-name-input').value = '';
            document.getElementById('wf-desc-input').value = '';
        }
        this._wfRenderCanvas();

        // Scroll to node centroid (existing workflow) or canvas center (new workflow)
        setTimeout(() => {
            const container = document.getElementById('wf-canvas-container');
            if (!container) return;
            if (this._wfNodes.length) {
                const xs = this._wfNodes.map(n => n.position.x);
                const ys = this._wfNodes.map(n => n.position.y);
                const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
                const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
                container.scrollLeft = cx - container.clientWidth / 2 + 75;
                container.scrollTop  = cy - container.clientHeight / 2 + 40;
            } else {
                container.scrollLeft = 1500 - container.clientWidth / 2;
                container.scrollTop  = 1500 - container.clientHeight / 2;
            }
        }, 10);
    },

    closeWorkflowEditor() {
        document.getElementById('workflow-editor').classList.add('hidden');
        document.getElementById('workflows-overview').classList.remove('hidden');
        this.loadWorkflows();
    },

    _wfNodeIcon(type) {
        return { trigger: this._ic.zap, agent: this._ic.bot, condition: this._ic.branch, loop: this._ic.loop, variable: this._ic.box, end: this._ic.stopci }[type] || '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/></svg>';
    },

    _wfNodeDefaults(type) {
        const defaults = {
            trigger: { label: 'Trigger', config: { mode: 'manual' } },
            agent: { label: 'Agent', config: { agent_id: '', prompt: '' } },
            condition: { label: 'Bedingung', config: { expression: 'output.contains("error")', true_label: 'true', false_label: 'false' } },
            loop: { label: 'Loop', config: { mode: 'foreach', variable: 'items' } },
            variable: { label: 'Variable', config: { name: 'myVar', value: '' } },
            end: { label: 'Ende', config: { status: 'succeeded' } },
        };
        return defaults[type] || { label: type, config: {} };
    },

    wfAddNode(type) {
        const defs = this._wfNodeDefaults(type);
        const id = Date.now().toString(36);
        // Nodes near visible center of the 3000×3000 canvas
        const container = document.getElementById('wf-canvas-container');
        const cx = container ? container.scrollLeft + Math.floor(container.clientWidth / 2) - 75 : 1450;
        const cy = container ? container.scrollTop  + Math.floor(container.clientHeight / 2) - 40 : 1450;
        const idx = this._wfNodes.length;
        const node = {
            id,
            type,
            label: defs.label,
            config: { ...defs.config },
            position: { x: cx + (idx % 3) * 220, y: cy + Math.floor(idx / 3) * 160 }
        };
        this._wfNodes.push(node);
        this._wfRenderCanvas();
    },

    _wfRenderCanvas() {
        const canvas = document.getElementById('wf-canvas');
        const svg = document.getElementById('wf-edges-svg');
        if (!canvas || !svg) return;

        // Render nodes
        canvas.innerHTML = '';
        this._wfNodes.forEach(node => {
            const el = document.createElement('div');
            el.className = `wf-node wf-node-${node.type}${this._wfSelectedNode === node.id ? ' wf-node-selected' : ''}`;
            el.id = `wf-node-${node.id}`;
            el.style.left = `${node.position.x}px`;
            el.style.top = `${node.position.y}px`;
            el.innerHTML = `
                <div class="wf-node-header">
                    <span class="wf-node-icon">${this._wfNodeIcon(node.type)}</span>
                    <span class="wf-node-label">${this._escapeHtml(node.label)}</span>
                </div>
                <div class="wf-node-port wf-port-out" title="Verbinden" data-node="${node.id}"></div>
            `;
            // Click to select
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                this._wfSelectNode(node.id);
            });
            // Drag to move
            this._wfMakeDraggable(el, node);
            // Port click to connect
            el.querySelector('.wf-port-out').addEventListener('click', (e) => {
                e.stopPropagation();
                this._wfStartConnection(node.id);
            });
            canvas.appendChild(el);
        });
        this._wfUpdateSvgEdges();

        // Click canvas to deselect 
        canvas.onclick = (e) => {
            if (e.target === canvas) {
                this._wfSelectedNode = null;
                canvas.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
                document.getElementById('wf-node-inspector')?.classList.add('hidden');
                if (this._wfConnecting) {
                    this._wfConnecting = null;
                    canvas.style.cursor = 'default';
                }
            }
        };
    },

    _wfMakeDraggable(el, node) {
        let startX, startY, origX, origY;
        el.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('wf-port-out')) return;
            startX = e.clientX; startY = e.clientY;
            origX = node.position.x; origY = node.position.y;
            const onMove = (e) => {
                node.position.x = origX + (e.clientX - startX);
                node.position.y = origY + (e.clientY - startY);
                el.style.left = `${node.position.x}px`;
                el.style.top = `${node.position.y}px`;
                this._wfUpdateSvgEdges();
            };
            const onUp = () => {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            e.preventDefault();
        });
    },

    _wfStartConnection(sourceId) {
        if (this._wfConnecting) {
            // Complete connection: port of a different node was clicked
            document.querySelector('.wf-node-connecting')?.classList.remove('wf-node-connecting');
            if (this._wfConnecting !== sourceId) {
                const exists = this._wfEdges.some(e => e.source_id === this._wfConnecting && e.target_id === sourceId);
                if (!exists) {
                    this._wfEdges.push({ id: Date.now().toString(36), source_id: this._wfConnecting, target_id: sourceId, label: '' });
                    this._wfUpdateSvgEdges();
                    showNotification('Verbindung erstellt', 'info');
                } else {
                    showNotification('Verbindung bereits vorhanden', 'info');
                }
            }
            this._wfConnecting = null;
            document.getElementById('wf-canvas').style.cursor = 'default';
        } else {
            this._wfConnecting = sourceId;
            document.getElementById('wf-canvas').style.cursor = 'crosshair';
            document.getElementById(`wf-node-${sourceId}`)?.classList.add('wf-node-connecting');
            showNotification('Klicke auf einen Ziel-Node, um die Verbindung herzustellen', 'info');
        }
    },

    _wfGetPortPos(nodeId, side) {
        // Port positions relative to wf-canvas-container (shared SVG coordinate space)
        const el = document.getElementById(`wf-node-${nodeId}`);
        const canvas = document.getElementById('wf-canvas');
        if (!el || !canvas) return null;
        // node positions are relative to wf-canvas; SVG is sibling with same origin in container
        const x = canvas.offsetLeft + el.offsetLeft + el.offsetWidth / 2;
        if (side === 'in') {
            return { x, y: canvas.offsetTop + el.offsetTop };
        }
        // 'out': bottom-center
        return { x, y: canvas.offsetTop + el.offsetTop + el.offsetHeight };
    },

    async _wfUpdateSvgEdges() {
        const svg = document.getElementById('wf-edges-svg');
        if (!svg) return;

        // Always define arrow marker first
        // Use hardcoded color #3b82f6 (blue) to match CSS
        svg.innerHTML = `<defs>
            <marker id="wf-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                <path d="M0,0 L10,5 L0,10 Z" fill="#3b82f6" />
            </marker>
        </defs>`;

        this._wfEdges.forEach(edge => {
            const src = this._wfGetPortPos(edge.source_id, 'out');
            const tgt = this._wfGetPortPos(edge.target_id, 'in');
            if (!src || !tgt) return;

            // 1. Invisible "Hitbox" path (very thick) to capture clicks easily
            const hitbox = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            hitbox.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
            hitbox.setAttribute('stroke', 'transparent');
            hitbox.setAttribute('stroke-width', '15');
            hitbox.setAttribute('fill', 'none');
            hitbox.style.cursor = 'pointer';
            hitbox.style.pointerEvents = 'stroke';

            // 2. Visible Edge Path
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
            path.setAttribute('class', 'wf-edge-path');
            path.setAttribute('marker-end', 'url(#wf-arrow)');
            path.setAttribute('stroke', '#3b82f6');
            path.setAttribute('stroke-width', '3');
            path.setAttribute('fill', 'none');
            // Ensure the visible path doesn't steal pointer events from the hitbox
            path.style.pointerEvents = 'none';

            // Click on hit box to delete it
            hitbox.setAttribute('data-edge-id', edge.id);
            hitbox.addEventListener('click', async (e) => {
                e.stopPropagation();
                if (await this.confirm('Verbindung löschen?')) {
                    this._wfEdges = this._wfEdges.filter(ed => ed.id !== edge.id);
                    this._wfUpdateSvgEdges();
                    if (this._wfSelectedNode) this._wfShowInspector(this._wfSelectedNode);
                }
            });

            svg.appendChild(path);
            svg.appendChild(hitbox);

            if (edge.label) {
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', (src.x + tgt.x) / 2);
                text.setAttribute('y', (src.y + tgt.y) / 2 - 6);
                text.setAttribute('class', 'wf-edge-label');
                text.textContent = edge.label;
                svg.appendChild(text);
            }
        });
    },

    _wfSelectNode(nodeId) {
        // If in connecting mode, complete the connection to this node
        if (this._wfConnecting && this._wfConnecting !== nodeId) {
            // Prevent duplicate edges
            const exists = this._wfEdges.some(e => e.source_id === this._wfConnecting && e.target_id === nodeId);
            if (!exists) {
                this._wfEdges.push({ id: Date.now().toString(36), source_id: this._wfConnecting, target_id: nodeId, label: '' });
            }
            document.querySelector('.wf-node-connecting')?.classList.remove('wf-node-connecting');
            this._wfConnecting = null;
            document.getElementById('wf-canvas').style.cursor = 'default';
            this._wfUpdateSvgEdges();
            showNotification('Verbindung erstellt', 'info');
            return;
        }

        this._wfSelectedNode = nodeId;
        document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
        document.getElementById(`wf-node-${nodeId}`)?.classList.add('wf-node-selected');
        this._wfShowInspector(nodeId);
    },

    async _wfShowInspector(nodeId) {
        const node = this._wfNodes.find(n => n.id === nodeId);
        if (!node) return;
        const inspector = document.getElementById('wf-node-inspector');
        const content = document.getElementById('wf-inspector-content');
        const deleteBtn = document.getElementById('wf-node-delete-btn');
        document.getElementById('wf-inspector-title').innerHTML = `${this._wfNodeIcon(node.type)} ${this._escapeHtml(node.label)}`;
        inspector.classList.remove('hidden');
        if (deleteBtn) deleteBtn.style.display = 'block';

        // Build label field
        let html = `<div class="form-row"><label class="form-label">Label</label>
            <input type="text" class="form-input" value="${this._escapeHtml(node.label)}"
                onchange="Ninko._wfUpdateNode('${nodeId}', 'label', this.value)">
        </div>`;

        // Smart fields per node type
        for (const [k, v] of Object.entries(node.config)) {
            if (node.type === 'agent' && k === 'agent_id') {
                // Render agent list as select, loaded async below
                html += `<div class="form-row"><label class="form-label">Agent</label>
                    <select id="wf-inspect-agent_id" class="form-select"
                        onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'agent_id', this.value)">
                        <option value="">– Laden… –</option>
                    </select>
                </div>`;
            } else if (k === 'mode' && node.type === 'trigger') {
                html += `<div class="form-row"><label class="form-label">Modus</label>
                    <select class="form-select" onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'mode', this.value)">
                        <option value="manual" ${v === 'manual' ? 'selected' : ''}>Manuell</option>
                        <option value="cron" ${v === 'cron' ? 'selected' : ''}>Zeitplan (Cron)</option>
                        <option value="webhook" ${v === 'webhook' ? 'selected' : ''}>Webhook</option>
                        <option value="event" ${v === 'event' ? 'selected' : ''}>Event</option>
                    </select>
                </div>`;
            } else if (k === 'status' && node.type === 'end') {
                html += `<div class="form-row"><label class="form-label">Status</label>
                    <select class="form-select" onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'status', this.value)">
                        <option value="succeeded" ${v === 'succeeded' ? 'selected' : ''}>Erfolgreich</option>
                        <option value="failed" ${v === 'failed' ? 'selected' : ''}>Fehlgeschlagen</option>
                    </select>
                </div>`;
            } else {
                html += `<div class="form-row"><label class="form-label">${this._escapeHtml(k)}</label>
                    <input type="text" class="form-input" value="${this._escapeHtml(String(v ?? ''))}"
                        onchange="Ninko._wfUpdateNodeConfig('${nodeId}', '${k}', this.value)">
                </div>`;
            }
        }

        // Edge connections list
        const outEdges = this._wfEdges.filter(e => e.source_id === nodeId);
        const inEdges = this._wfEdges.filter(e => e.target_id === nodeId);
        if (outEdges.length || inEdges.length) {
            html += `<div class="form-row" style="margin-top:1rem;border-top:1px solid var(--border-color);padding-top:0.75rem">
                <label class="form-label" style="font-weight:600">Verbindungen</label>`;
            inEdges.forEach(e => {
                const src = this._wfNodes.find(n => n.id === e.source_id);
                html += `<div style="font-size:0.8rem;display:flex;align-items:center;justify-content:space-between;margin-bottom:0.3rem">
                    <span>↩ ${src?.label || e.source_id}</span>
                    <button class="btn-icon btn-icon-sm" style="color:var(--error-color)" onclick="Ninko._wfDeleteEdge('${e.id}')" title="Entfernen">✕</button>
                </div>`;
            });
            outEdges.forEach(e => {
                const tgt = this._wfNodes.find(n => n.id === e.target_id);
                html += `<div style="font-size:0.8rem;display:flex;align-items:center;justify-content:space-between;margin-bottom:0.3rem">
                    <span>↪ ${tgt?.label || e.target_id}</span>
                    <button class="btn-icon btn-icon-sm" style="color:var(--error-color)" onclick="Ninko._wfDeleteEdge('${e.id}')" title="Entfernen">✕</button>
                </div>`;
            });
            html += `</div>`;
        }

        content.innerHTML = html;

        // Populate agent dropdown if agent node
        if (node.type === 'agent') {
            try {
                const res = await fetch('/api/agents/');
                const data = await res.json();
                const sel = document.getElementById('wf-inspect-agent_id');
                if (sel) {
                    sel.innerHTML = '<option value="">– Agenten wählen –</option>' +
                        (data.agents || []).map(a =>
                            `<option value="${a.id}" ${a.id === node.config.agent_id ? 'selected' : ''}>${a.name}</option>`
                        ).join('');
                    // If no current selection, preselect by stored id
                    if (node.config.agent_id) sel.value = node.config.agent_id;
                }
            } catch { /* agents not available */ }
        }
    },

    _wfUpdateNode(nodeId, field, value) {
        const node = this._wfNodes.find(n => n.id === nodeId);
        if (node) {
            node[field] = value;
            this._wfRenderCanvas();
            if (field === 'label' && this._wfSelectedNode === nodeId) {
                const titleEl = document.getElementById('wf-inspector-title');
                if (titleEl) titleEl.innerHTML = `${this._wfNodeIcon(node.type)} ${this._escapeHtml(value)}`;
            }
        }
    },
    _wfUpdateNodeConfig(nodeId, key, value) {
        const node = this._wfNodes.find(n => n.id === nodeId);
        if (node) node.config[key] = value;
    },
    _wfDeleteEdge(edgeId) {
        this._wfEdges = this._wfEdges.filter(e => e.id !== edgeId);
        this._wfUpdateSvgEdges();
        if (this._wfSelectedNode) this._wfShowInspector(this._wfSelectedNode);
    },

    wfCloseInspector() {
        document.getElementById('wf-node-inspector')?.classList.add('hidden');
        this._wfSelectedNode = null;
        document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
    },

    async wfDeleteSelectedNode() {
        if (!this._wfSelectedNode) return;
        if (!await this.confirm('Möchtest du diesen Node wirklich löschen?')) return;

        this._wfNodes = this._wfNodes.filter(n => n.id !== this._wfSelectedNode);
        this._wfEdges = this._wfEdges.filter(e => e.source_id !== this._wfSelectedNode && e.target_id !== this._wfSelectedNode);
        this._wfSelectedNode = null;
        document.getElementById('wf-node-inspector')?.classList.add('hidden');
        this._wfRenderCanvas();
    },

    async saveWorkflow() {
        const name = document.getElementById('wf-name-input').value.trim();
        if (!name) { showNotification('Name ist Pflichtfeld', 'error'); return; }
        const saveBtn = document.querySelector('.wf-editor-toolbar .btn-primary');
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Speichern…'; }
        const wfId = document.getElementById('wf-edit-id').value;
        const description = document.getElementById('wf-desc-input')?.value.trim() || '';
        const body = { name, description, nodes: this._wfNodes, edges: this._wfEdges, variables: [], enabled: true };
        try {
            const url = wfId ? `/api/workflows/${wfId}` : '/api/workflows/';
            const method = wfId ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (res.ok) { showNotification(`Workflow "${name}" gespeichert`, 'success'); this.closeWorkflowEditor(); }
            else showNotification('Fehler beim Speichern', 'error');
        } catch { showNotification('Verbindungsfehler', 'error'); }
        finally { if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Speichern'; } }
    },

    async deleteWorkflow(id, name) {
        const displayName = name || 'Workflow';
        if (!await this.confirm(`Workflow "${displayName}" wirklich unwiderruflich löschen?`)) return;
        try {
            const res = await fetch(`/api/workflows/${id}`, { method: 'DELETE' });
            if (res.ok) {
                showNotification(`Workflow "${displayName}" gelöscht`, 'info');
                this.loadWorkflows();
            } else {
                const err = await res.json().catch(() => ({}));
                showNotification(`Fehler beim Löschen: ${err.detail || 'Unbekannter Fehler'}`, 'error');
            }
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async runWorkflow(id, name) {
        try {
            const res = await fetch(`/api/workflows/${id}/run`, { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                showNotification(`Workflow "${name}" gestartet`, 'success');
                this.openRunDashboard(id, name, data.run_id);
            } else showNotification('Fehler beim Starten', 'error');
        } catch { showNotification('Verbindungsfehler', 'error'); }
    },

    async openRunHistory(wfId, name) {
        this._wfCurrentWorkflowId = wfId;
        this._wfCurrentRunId = null;
        this._wfRunNodes = [];
        this._wfRunEdges = [];
        document.getElementById('workflows-overview').classList.add('hidden');
        document.getElementById('workflow-run-dashboard').classList.remove('hidden');
        document.getElementById('run-dashboard-title').textContent = name;
        document.getElementById('run-dashboard-status').textContent = 'Historie';
        document.getElementById('run-dashboard-status').className = 'run-status-badge run-idle';
        document.getElementById('run-progress-fill').style.width = '0%';
        document.getElementById('run-progress-text').textContent = '';
        document.getElementById('wf-node-inspector')?.classList.add('hidden');
        try {
            const res = await fetch(`/api/workflows/${wfId}`);
            const wf = await res.json();
            this._wfRunNodes = wf.nodes || [];
            this._wfRunEdges = wf.edges || [];
            this._wfRunRenderCanvas([]);
            this._wfRunScrollToCentroid();
        } catch {}
        await this._loadRunHistory(wfId);
    },

    openRunDashboard(wfId, name, runId) {
        this._wfCurrentWorkflowId = wfId;
        this._wfCurrentRunId = runId;
        this._wfRunNodes = [];
        this._wfRunEdges = [];
        document.getElementById('workflows-overview').classList.add('hidden');
        document.getElementById('workflow-editor').classList.add('hidden');
        document.getElementById('workflow-run-dashboard').classList.remove('hidden');
        document.getElementById('run-dashboard-title').textContent = name;
        document.getElementById('run-dashboard-status').textContent = 'gestartet';
        document.getElementById('run-dashboard-status').className = 'run-status-badge run-running';
        document.getElementById('wf-node-inspector')?.classList.add('hidden');
        fetch(`/api/workflows/${wfId}`)
            .then(r => r.json())
            .then(wf => {
                this._wfRunNodes = wf.nodes || [];
                this._wfRunEdges = wf.edges || [];
                this._wfRunRenderCanvas([]);
                this._wfRunScrollToCentroid();
            }).catch(() => {});
        clearInterval(this._wfRunRefreshTimer);
        this._wfRunRefreshTimer = setInterval(() => this._refreshRunStatus(), 3000);
        this._refreshRunStatus();
    },

    closeRunDashboard() {
        clearInterval(this._wfRunRefreshTimer);
        document.getElementById('workflow-run-dashboard').classList.add('hidden');
        document.getElementById('workflows-overview').classList.remove('hidden');
        this.loadWorkflows();
    },

    async _refreshRunStatus() {
        if (!this._wfCurrentWorkflowId) return;
        await this._loadRunHistory(this._wfCurrentWorkflowId);
        // If no active run or run finished, stop timer
        const statusEl = document.getElementById('run-dashboard-status');
        if (statusEl && (statusEl.textContent === 'succeeded' || statusEl.textContent === 'failed')) {
            clearInterval(this._wfRunRefreshTimer);
        }
    },

    async _loadRunHistory(wfId) {
        try {
            const res = await fetch(`/api/workflows/${wfId}/runs`);
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const runs = data.runs || [];
            const historyEl = document.getElementById('run-history-list');
            if (historyEl) {
                historyEl.innerHTML = runs.map(r => `
                    <div class="run-history-item" onclick="Ninko._showRunDetail('${wfId}', '${r.id}')">
                        <span class="run-status-badge run-${r.status}">${r.status}</span>
                        <span>${r.started_at ? new Date(r.started_at).toLocaleString('de') : '–'}</span>
                        <span>${r.duration_ms ? (r.duration_ms / 1000).toFixed(1) + 's' : '–'}</span>
                    </div>
                `).join('') || '<p class="text-muted">Noch keine Runs.</p>';
            }
            // Show latest run steps if we have an active runId
            if (this._wfCurrentRunId && runs.length) {
                const activeRun = runs.find(r => r.id === this._wfCurrentRunId) || runs[0];
                this._renderRunSteps(activeRun);
            }
        } catch { }
    },

    _wfRunRenderCanvas(steps = []) {
        const canvas = document.getElementById('wf-run-canvas');
        const svg = document.getElementById('wf-run-edges-svg');
        if (!canvas || !svg) return;
        const stepMap = {};
        steps.forEach(s => { stepMap[s.node_id] = s; });
        canvas.innerHTML = '';
        this._wfRunNodes.forEach(node => {
            const step = stepMap[node.id] || {};
            const status = step.status || 'pending';
            const el = document.createElement('div');
            el.className = `wf-node wf-node-${node.type} wf-run-node wf-run-node-${status}`;
            el.id = `wf-run-node-${node.id}`;
            el.style.left = `${node.position.x}px`;
            el.style.top = `${node.position.y}px`;
            const durHtml = step.duration_ms != null
                ? `<span class="wf-run-node-dur">${step.duration_ms}ms</span>` : '';
            el.innerHTML = `
                <div class="wf-node-header">
                    <span class="wf-node-icon">${this._wfNodeIcon(node.type)}</span>
                    <span class="wf-node-label">${this._escapeHtml(node.label)}</span>
                    <span class="wf-run-status-pip wf-run-pip-${status}"></span>
                </div>
                ${durHtml}
            `;
            if (step.status) {
                el.style.cursor = 'pointer';
                el.addEventListener('click', () => this._wfRunShowStepDetail(step, node));
            }
            canvas.appendChild(el);
        });
        this._wfRunUpdateEdges();
    },

    _wfRunGetPortPos(nodeId, side) {
        const el = document.getElementById(`wf-run-node-${nodeId}`);
        const canvas = document.getElementById('wf-run-canvas');
        if (!el || !canvas) return null;
        const x = canvas.offsetLeft + el.offsetLeft + el.offsetWidth / 2;
        if (side === 'in') return { x, y: canvas.offsetTop + el.offsetTop };
        return { x, y: canvas.offsetTop + el.offsetTop + el.offsetHeight };
    },

    _wfRunUpdateEdges() {
        const svg = document.getElementById('wf-run-edges-svg');
        if (!svg) return;
        svg.innerHTML = `<defs>
            <marker id="wf-run-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                <path d="M0,0 L10,5 L0,10 Z" fill="#3b82f6" />
            </marker>
        </defs>`;
        this._wfRunEdges.forEach(edge => {
            const src = this._wfRunGetPortPos(edge.source_id, 'out');
            const tgt = this._wfRunGetPortPos(edge.target_id, 'in');
            if (!src || !tgt) return;
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
            path.setAttribute('stroke', '#3b82f6');
            path.setAttribute('stroke-width', '2.5');
            path.setAttribute('fill', 'none');
            path.setAttribute('marker-end', 'url(#wf-run-arrow)');
            path.style.pointerEvents = 'none';
            svg.appendChild(path);
        });
    },

    _wfRunScrollToCentroid() {
        setTimeout(() => {
            const container = document.getElementById('wf-run-canvas-container');
            if (!container || !this._wfRunNodes.length) return;
            const xs = this._wfRunNodes.map(n => n.position.x);
            const ys = this._wfRunNodes.map(n => n.position.y);
            const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
            const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
            container.scrollLeft = cx - container.clientWidth / 2 + 75;
            container.scrollTop  = cy - container.clientHeight / 2 + 40;
        }, 60);
    },

    _wfRunShowStepDetail(step, node) {
        const inspector = document.getElementById('wf-run-inspector');
        const content = document.getElementById('wf-run-inspector-content');
        if (!inspector || !content) return;
        inspector.classList.remove('hidden');
        document.getElementById('wf-run-inspector-title').innerHTML =
            `${this._wfNodeIcon(node.type)} ${this._escapeHtml(node.label)}`;
        const outputHtml = step.output
            ? `<pre class="wf-run-output">${this._escapeHtml(step.output)}</pre>`
            : '<p style="font-size:0.85rem;color:var(--text-muted);margin:0;">Keine Ausgabe.</p>';
        content.innerHTML = `
            <div class="form-row">
                <label class="form-label">Status</label>
                <span class="run-status-badge run-${this._escapeHtml(step.status)}">${this._escapeHtml(step.status)}</span>
            </div>
            <div class="form-row">
                <label class="form-label">Dauer</label>
                <span style="font-size:0.85rem;">${step.duration_ms != null ? step.duration_ms + ' ms' : '–'}</span>
            </div>
            ${step.error ? `<div class="form-row"><label class="form-label" style="color:var(--error-color);">Fehler</label><div class="wf-run-error">${this._escapeHtml(step.error)}</div></div>` : ''}
            <div class="form-row" style="flex:1;display:flex;flex-direction:column;min-height:0;">
                <label class="form-label">Ausgabe</label>
                ${outputHtml}
            </div>
        `;
    },

    _wfRunCloseInspector() {
        document.getElementById('wf-run-inspector')?.classList.add('hidden');
    },

    _showRunDetail(wfId, runId) {
        this._wfCurrentRunId = runId;
        this._loadRunHistory(wfId);
    },

    _renderRunSteps(run) {
        const statusEl = document.getElementById('run-dashboard-status');
        const progressFill = document.getElementById('run-progress-fill');
        const progressText = document.getElementById('run-progress-text');
        if (statusEl) {
            statusEl.textContent = run.status;
            statusEl.className = `run-status-badge run-${run.status}`;
        }
        const steps = run.steps || [];
        const done = steps.filter(s => ['succeeded', 'failed', 'skipped'].includes(s.status)).length;
        if (progressFill) progressFill.style.width = steps.length ? `${(done / steps.length) * 100}%` : '0%';
        if (progressText) progressText.textContent = steps.length ? `${done} / ${steps.length} Schritte` : '';
        this._wfRunRenderCanvas(steps);
    },

    _showRunStepDetail(step) {
        const inspector = document.getElementById('wf-node-inspector');
        const content = document.getElementById('wf-inspector-content');
        const deleteBtn = document.getElementById('wf-node-delete-btn');
        if (!inspector || !content) return;

        document.getElementById('wf-inspector-title').textContent = `Node: ${step.node_label || step.node_type}`;
        inspector.classList.remove('hidden');
        if (deleteBtn) deleteBtn.style.display = 'none';

        let outputHtml = step.output ? this._formatOutput(step.output) : '<p class="text-muted">Keine Ausgabe vorhanden.</p>';
        if (step.error) {
            outputHtml += `<div class="error-box" style="margin-top:1rem; color:var(--error-color);"><strong>Fehler:</strong><br>${this._escapeHtml(step.error)}</div>`;
        }

        content.innerHTML = `
            <div class="setting-group">
                <label class="form-label">Status</label>
                <div class="run-status-badge run-${step.status}">${step.status}</div>
            </div>
            <div class="setting-group">
                <label class="form-label">Dauer</label>
                <span>${step.duration_ms ? step.duration_ms + 'ms' : '–'}</span>
            </div>
            <div class="setting-group" style="flex:1; display:flex; flex-direction:column; min-height:0;">
                <label class="form-label">Ausgabe</label>
                <div class="node-output-container" style="background:rgba(0,0,0,0.2); padding:1rem; border-radius:8px; font-family:monospace; font-size:0.9rem; white-space:pre-wrap; overflow-y:auto; flex:1;">${outputHtml}</div>
            </div>
        `;
    },

    _formatOutput(text) {
        if (!text) return '';
        // Einfache Formatierung für Zeilenumbrüche und escaping
        return this._escapeHtml(text);
    },

    // ═══════════════════════════════════════════════════════
    //  LOGS
    // ═══════════════════════════════════════════════════════

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
        } catch { }
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
            <tr class="log-row log-row-${(entry.level || 'INFO').toLowerCase()}" onclick="Ninko._showLogDetail(${this._logCache.length - 1 - idx})">
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

    // ═══════════════════════════════════════════════════════
    //  LLM MULTI-PROVIDER
    // ═══════════════════════════════════════════════════════

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
                            <button class="btn btn-sm btn-outline" onclick="Ninko.testLlmProvider('${p.id}')">Test</button>
                            <button class="btn-icon btn-icon-sm" onclick="Ninko.openProviderEditor('${p.id}')">${this._ic.edit}</button>
                            <button class="btn-icon btn-icon-sm" onclick="Ninko.deleteLlmProvider('${p.id}', ${this._escapeHtml(JSON.stringify(p.name))})" style="color:var(--error-color)">${this._ic.trash}</button>
                        </div>
                    </div>
                    <div class="provider-meta">
                        <span>${this._escapeHtml({ollama:'Ollama',lmstudio:'LM Studio',openai_compatible:'OpenAI'}[p.backend] || p.backend || '')}</span> · <span>${this._escapeHtml(p.base_url || '')}</span> · <span>${this._escapeHtml(p.model || '')}</span>
                    </div>
                    ${!p.is_default ? `<button class="btn btn-sm btn-outline" style="margin-top:0.5rem;" onclick="Ninko.setDefaultProvider('${p.id}')">Als Standard setzen</button>` : ''}
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
                    document.getElementById('provider-is-default').checked = p.is_default;
                }
            } catch { }
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
        const body = {
            name: document.getElementById('provider-name').value,
            backend: document.getElementById('provider-backend').value,
            base_url: document.getElementById('provider-url').value,
            model: document.getElementById('provider-model').value,
            api_key: document.getElementById('provider-api-key').value,
            is_default: document.getElementById('provider-is-default').checked,
        };
        const id = document.getElementById('provider-edit-id').value;
        try {
            const url = id ? `/api/settings/llm/providers/${id}` : '/api/settings/llm/providers';
            const method = id ? 'PUT' : 'POST';
            const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            if (res.ok) {
                statusEl.textContent = 'Gespeichert';
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
        if (row) row.style.display = backend === 'openai_compatible' ? '' : 'none';
    },

    async loadEmbedModel() {
        try {
            const res = await fetch('/api/settings/llm/embed-model');
            const data = await res.json();
            document.getElementById('global-embed-model').value = data.embed_model || '';
        } catch { }
    },

    async saveEmbedModel() {
        const statusEl = document.getElementById('embed-model-status');
        const model = document.getElementById('global-embed-model').value.trim();
        if (!model) { statusEl.textContent = 'Modellname darf nicht leer sein'; return; }
        statusEl.textContent = 'Speichere…';
        try {
            const res = await fetch('/api/settings/llm/embed-model', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ embed_model: model }),
            });
            if (res.ok) { statusEl.textContent = 'Gespeichert'; showNotification('Embedding-Modell gespeichert', 'success'); }
            else { statusEl.textContent = 'Fehler'; }
        } catch { statusEl.textContent = 'Verbindungsfehler'; }
    },
};


// ─── Global Helpers ───
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

// ─── Export für HTML-Event-Handler ───
window.Ninko = Ninko;
window.I18n = I18n;

// ─── Boot ───
document.addEventListener('DOMContentLoaded', () => Ninko.init());
