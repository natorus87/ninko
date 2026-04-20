(function () {
    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function isTextInputTarget(target) {
        if (!target) return false;
        const tag = (target.tagName || '').toLowerCase();
        if (target.isContentEditable) return true;
        return tag === 'input' || tag === 'textarea' || tag === 'select';
    }

    function create(ninko) {
        return {
            ninko,
            commands: [],
            filtered: [],
            selectedIndex: 0,
            initialized: false,
            root: null,
            input: null,
            results: null,

            init() {
                if (this.initialized) return;
                this.initialized = true;

                this.root = document.getElementById('command-palette');
                this.input = document.getElementById('cmd-search');
                this.results = document.getElementById('cmd-results');
                if (!this.root || !this.input || !this.results) return;

                this._registerCommands();
                this._bindUi();
                this._bindHotkeys();
            },

            _registerCommands() {
                const openModulePicker = () => {
                    this.ninko.switchTab('chat');
                    const btn = document.getElementById('module-picker-btn');
                    if (btn) btn.click();
                };

                this.commands = [
                    {
                        id: 'new-chat',
                        title: 'New Chat',
                        subtitle: 'Startet eine neue Session',
                        shortcut: 'Ctrl/Cmd+N',
                        keywords: ['chat', 'new', 'neu', 'session'],
                        run: () => this.ninko.newChat(),
                    },
                    {
                        id: 'open-settings',
                        title: 'Open Settings',
                        subtitle: 'Öffnet die Einstellungen',
                        shortcut: 'Ctrl/Cmd+,',
                        keywords: ['settings', 'einstellungen', 'config'],
                        run: () => this.ninko.switchTab('settings'),
                    },
                    {
                        id: 'switch-module',
                        title: 'Switch Module',
                        subtitle: 'Öffnet den Modul-Picker im Chat',
                        shortcut: 'Ctrl/Cmd+Shift+M',
                        keywords: ['module', 'picker', 'modul'],
                        run: openModulePicker,
                    },
                    {
                        id: 'toggle-theme',
                        title: 'Toggle Theme',
                        subtitle: 'Wechselt zwischen Light und Dark',
                        shortcut: 'Ctrl/Cmd+Shift+T',
                        keywords: ['theme', 'light', 'dark'],
                        run: () => this.ninko.toggleTheme(),
                    },
                    {
                        id: 'clear-context',
                        title: 'Clear Context',
                        subtitle: 'Löscht den Chat-Kontext',
                        shortcut: 'Ctrl/Cmd+Shift+C',
                        keywords: ['clear', 'context', 'kontext', 'reset'],
                        run: () => this.ninko.clearContext(),
                    },
                ];
            },

            _bindUi() {
                const overlay = this.root.querySelector('.cmd-palette-overlay');
                overlay?.addEventListener('click', () => this.close());

                this.input.addEventListener('input', () => {
                    this._filter(this.input.value);
                    this._renderResults();
                });

                this.input.addEventListener('keydown', (e) => {
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (!this.filtered.length) return;
                        this.selectedIndex = (this.selectedIndex + 1) % this.filtered.length;
                        this._renderResults();
                        return;
                    }
                    if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (!this.filtered.length) return;
                        this.selectedIndex = (this.selectedIndex - 1 + this.filtered.length) % this.filtered.length;
                        this._renderResults();
                        return;
                    }
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        const selected = this.filtered[this.selectedIndex];
                        if (selected) this.execute(selected.id);
                        return;
                    }
                    if (e.key === 'Escape') {
                        e.preventDefault();
                        this.close();
                    }
                });
            },

            _bindHotkeys() {
                document.addEventListener('keydown', (e) => {
                    const cmd = e.metaKey || e.ctrlKey;
                    if (!cmd) return;

                    if (e.key.toLowerCase() === 'k') {
                        e.preventDefault();
                        this.toggle();
                        return;
                    }

                    if (this.isOpen()) return;
                    if (isTextInputTarget(e.target)) return;

                    if (!e.shiftKey && e.key.toLowerCase() === 'n') {
                        e.preventDefault();
                        this.execute('new-chat');
                        return;
                    }
                    if (!e.shiftKey && e.key === ',') {
                        e.preventDefault();
                        this.execute('open-settings');
                        return;
                    }
                    if (e.shiftKey && e.key.toLowerCase() === 'm') {
                        e.preventDefault();
                        this.execute('switch-module');
                        return;
                    }
                    if (e.shiftKey && e.key.toLowerCase() === 't') {
                        e.preventDefault();
                        this.execute('toggle-theme');
                        return;
                    }
                    if (e.shiftKey && e.key.toLowerCase() === 'c') {
                        e.preventDefault();
                        this.execute('clear-context');
                    }
                });
            },

            _filter(query) {
                const q = (query || '').trim().toLowerCase();
                if (!q) {
                    this.filtered = [...this.commands];
                    this.selectedIndex = 0;
                    return;
                }
                this.filtered = this.commands.filter((cmd) => {
                    const haystack = [
                        cmd.title,
                        cmd.subtitle,
                        cmd.shortcut,
                        ...(cmd.keywords || []),
                    ].join(' ').toLowerCase();
                    return haystack.includes(q);
                });
                this.selectedIndex = 0;
            },

            _renderResults() {
                if (!this.results) return;
                if (!this.filtered.length) {
                    this.results.innerHTML = '<div class="cmd-empty">Keine Treffer</div>';
                    return;
                }
                this.results.innerHTML = this.filtered.map((cmd, idx) => `
                    <button class="cmd-item${idx === this.selectedIndex ? ' active' : ''}" data-cmd-id="${escapeHtml(cmd.id)}">
                        <span class="cmd-item-main">
                            <span class="cmd-item-title">${escapeHtml(cmd.title)}</span>
                            <span class="cmd-item-subtitle">${escapeHtml(cmd.subtitle || '')}</span>
                        </span>
                        <span class="cmd-item-shortcut">${escapeHtml(cmd.shortcut || '')}</span>
                    </button>
                `).join('');

                this.results.querySelectorAll('.cmd-item').forEach((el) => {
                    el.addEventListener('mouseenter', () => {
                        const id = el.getAttribute('data-cmd-id');
                        const idx = this.filtered.findIndex((c) => c.id === id);
                        if (idx >= 0) {
                            this.selectedIndex = idx;
                            this._renderResults();
                        }
                    });
                    el.addEventListener('click', () => {
                        const id = el.getAttribute('data-cmd-id');
                        this.execute(id);
                    });
                });
            },

            execute(id) {
                const cmd = this.commands.find((c) => c.id === id);
                if (!cmd) return;
                this.close();
                cmd.run();
            },

            isOpen() {
                return this.root?.classList.contains('open');
            },

            open() {
                if (!this.root) return;
                this.root.classList.add('open');
                this.input.value = '';
                this._filter('');
                this._renderResults();
                requestAnimationFrame(() => this.input.focus());
            },

            close() {
                this.root?.classList.remove('open');
            },

            toggle() {
                if (this.isOpen()) this.close();
                else this.open();
            },
        };
    }

    window.NinkoCommandPalette = { create };
})();
