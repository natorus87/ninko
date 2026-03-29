/**
 * Template Dashboard Tab – JavaScript
 *
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║  NINKO MODULE TEMPLATE — tab.js                                      ║
 * ║  Design & Interaction Guidelines (enforced since v0.7.1)            ║
 * ╠══════════════════════════════════════════════════════════════════════╣
 * ║                                                                      ║
 * ║  MODULE LOADING RULES:                                               ║
 * ║  • No import/export (ES Modules) — loaded via <script> tag without  ║
 * ║    type="module". All code must be in a single IIFE or global object.║
 * ║  • Plugin registration (catalog modules): use Ninko._pluginTabs      ║
 * ║    (see bottom of file). Never edit app.js:getTabObject() for plugins.║
 * ║                                                                      ║
 * ║  EVENT HANDLING — data-action delegation pattern:                    ║
 * ║  • Attach ONE click listener to the tab root element.                ║
 * ║  • Read e.target.closest('[data-action]')?.dataset.action to route.  ║
 * ║  • Never use inline onclick="..." in JS-generated HTML strings.      ║
 * ║    Reason: inline handlers in innerHTML are an XSS vector and cannot ║
 * ║    be unit-tested or linted.                                         ║
 * ║  ✓  button.dataset.action = 'template-refresh'  (safe)               ║
 * ║  ✗  innerHTML = '<button onclick="fn()">...'    (unsafe)             ║
 * ║                                                                      ║
 * ║  ACCESSIBLE MARKUP — rules for JS-generated HTML:                    ║
 * ║  • All <button> elements need type="button"                          ║
 * ║  • Icon-only buttons need aria-label="Descriptive action"            ║
 * ║  • Status icons / decorative SVGs need aria-hidden="true"            ║
 * ║  • Use role="status" / aria-live="polite" for dynamically updated    ║
 * ║    regions so screen readers announce changes                        ║
 * ║                                                                      ║
 * ║  HTML GENERATION — safe string building:                             ║
 * ║  • Escape user-supplied values before inserting into innerHTML:       ║
 * ║      function esc(s) {                                               ║
 * ║          const d = document.createElement('div');                    ║
 * ║          d.textContent = s; return d.innerHTML;                      ║
 * ║      }                                                               ║
 * ║  • Or use textContent/setAttribute instead of innerHTML for values.  ║
 * ║                                                                      ║
 * ║  ICONS IN GENERATED HTML — inline SVG only, no emoji:               ║
 * ║  • Copy SVG strings with stroke="currentColor" from the icon set.   ║
 * ║  • Add aria-hidden="true" to all decorative SVGs.                   ║
 * ║  • Define SVG strings as module-level constants to avoid repetition. ║
 * ║    Example:                                                          ║
 * ║      const ICON_CHECK = '<svg viewBox="0 0 24 24" width="14"         ║
 * ║          height="14" fill="none" stroke="currentColor"               ║
 * ║          stroke-width="2" stroke-linecap="round"                     ║
 * ║          stroke-linejoin="round" aria-hidden="true">                 ║
 * ║          <polyline points="20 6 9 17 4 12"/></svg>';                 ║
 * ║                                                                      ║
 * ║  STATE MANAGEMENT — always show feedback:                            ║
 * ║  • Loading:  container.innerHTML = '<p class="empty-state">Lade…</p>'║
 * ║  • Error:    container.innerHTML =                                   ║
 * ║              '<p class="empty-state text-error">Error message</p>'   ║
 * ║  • Empty:    '<p class="empty-state">No items found.</p>'           ║
 * ║  • Never leave a container blank (no hidden loading failures).       ║
 * ║                                                                      ║
 * ║  NUMBER FORMATTING — tabular numerals for status values:             ║
 * ║  • When setting .status-value or any numeric metric via JS:          ║
 * ║      el.style.fontVariantNumeric = 'tabular-nums';                  ║
 * ║  • Or set it in CSS on the container class.                          ║
 * ║                                                                      ║
 * ║  POLLING — lifecycle discipline:                                     ║
 * ║  • Always call stopPolling() before startPolling() (prevents leaks). ║
 * ║  • Always call stopPolling() in destroy() when tab is deactivated.  ║
 * ║  • Default interval: 30 000ms. Adjust to service rate limits.       ║
 * ║                                                                      ║
 * ║  CSS TRANSITIONS — never add "transition: all" in inline styles:    ║
 * ║  ✓  el.style.transition = 'opacity 0.15s, transform 0.15s'          ║
 * ║  ✗  el.style.transition = 'all 0.15s'                               ║
 * ║                                                                      ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 *
 * PLUGIN REGISTRATION:
 *   The key ('template') must match manifest.py dashboard_tab.id.
 *   Registered at bottom of file (not inside init() — must be synchronous).
 */

/* ── SVG Icon Constants — inline SVG with currentColor, aria-hidden ── */
const _TMPL_ICON_REFRESH = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>';
const _TMPL_ICON_CHECK    = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
const _TMPL_ICON_ERROR    = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

/* ── HTML Escape Helper — always escape user data before innerHTML ── */
function _tmplEsc(s) {
    const d = document.createElement('div');
    d.textContent = String(s ?? '');
    return d.innerHTML;
}

const TemplateTab = {
    API_PREFIX: '/api/template',
    pollInterval: null,
    currentConnectionId: '',

    async init() {
        this._setupEvents();
        this._setupClickOutside();
        await this.loadConnections();

        if (this.currentConnectionId) {
            await this.refresh();
        }
    },

    // ── Event Delegation ───────────────────────────────────────────────
    // ONE listener on the root, route by data-action.
    // Never use inline onclick in JS-generated HTML strings.

    _setupEvents() {
        document.getElementById('template-tab-content')
            ?.addEventListener('click', (e) => {
                const action = e.target.closest('[data-action]')?.dataset.action;
                if (action === 'template-refresh') this.refresh();
                // Add more actions here:
                // if (action === 'template-delete') this._handleDelete(e);
            });
    },

    // ── Custom Select ──────────────────────────────────────────────────

    toggleSelect(selectId) {
        const el = document.getElementById(selectId);
        if (!el) return;
        const isOpen = el.classList.contains('open');
        document.querySelectorAll('#template-tab-content .cl-select.open')
            .forEach(s => s.classList.remove('open'));
        if (!isOpen) el.classList.add('open');
    },

    _setupClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#template-tab-content .cl-select')) {
                document.querySelectorAll('#template-tab-content .cl-select.open')
                    .forEach(s => s.classList.remove('open'));
            }
        });
    },

    _setSelectOptions(optionsContainerId, options, onSelect) {
        const container = document.getElementById(optionsContainerId);
        if (!container) return;
        // ✓ Values are escaped via _tmplEsc before insertion
        container.innerHTML = options.map(o =>
            `<div class="cl-select-option${o.selected ? ' selected' : ''}"
                  data-value="${_tmplEsc(o.value)}"
                  role="option"
                  aria-selected="${o.selected ? 'true' : 'false'}">${_tmplEsc(o.label)}</div>`
        ).join('');
        container.querySelectorAll('.cl-select-option').forEach(opt => {
            opt.addEventListener('click', () => {
                container.querySelectorAll('.cl-select-option')
                    .forEach(o => { o.classList.remove('selected'); o.setAttribute('aria-selected', 'false'); });
                opt.classList.add('selected');
                opt.setAttribute('aria-selected', 'true');
                const wrapper = container.closest('.cl-select');
                if (wrapper) {
                    const lbl = wrapper.querySelector('.cl-select-label');
                    if (lbl) lbl.textContent = opt.textContent;
                    wrapper.classList.remove('open');
                }
                onSelect(opt.dataset.value);
            });
        });
    },

    _setSelectLabel(wrapperId, label) {
        const el = document.getElementById(wrapperId);
        if (el) {
            const lbl = el.querySelector('.cl-select-label');
            if (lbl) lbl.textContent = label;
        }
    },

    // ── Polling ────────────────────────────────────────────────────────
    // Always stopPolling() first to prevent duplicate intervals.

    startPolling(intervalMs = 30000) {
        this.stopPolling();
        this.pollInterval = setInterval(() => this.refresh(), intervalMs);
    },

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    },

    // ── Query Params Helper ────────────────────────────────────────────

    getQueryParams(additional = {}) {
        const params = new URLSearchParams();
        if (this.currentConnectionId) {
            params.append('connection_id', this.currentConnectionId);
        }
        for (const [k, v] of Object.entries(additional)) {
            params.append(k, String(v));
        }
        const str = params.toString();
        return str ? `?${str}` : '';
    },

    // ── Load Connections ───────────────────────────────────────────────

    async loadConnections() {
        try {
            const res = await fetch('/api/connections/template');
            const data = await res.json();
            const conns = data.connections || [];

            if (conns.length === 0) {
                this._setSelectLabel('template-conn-select', 'Keine Verbindungen');
                this.currentConnectionId = '';
                return;
            }

            const defaultConn = conns.find(c => c.is_default) || conns[0];
            this.currentConnectionId = defaultConn.id;

            this._setSelectOptions(
                'template-conn-options',
                conns.map(c => ({
                    value: c.id,
                    label: `${c.name} (${c.environment})`,
                    selected: c.id === defaultConn.id,
                })),
                (id) => {
                    this.currentConnectionId = id;
                    this.refresh();
                }
            );
            this._setSelectLabel(
                'template-conn-select',
                `${defaultConn.name} (${defaultConn.environment})`
            );
        } catch (err) {
            console.error('Template: connection load error', err);
            this._setSelectLabel('template-conn-select', 'Fehler beim Laden');
        }
    },

    // ── Data Refresh ───────────────────────────────────────────────────
    // Always show loading → data or error. Never leave container blank.

    async refresh() {
        if (!this.currentConnectionId) return;

        const container = document.getElementById('template-content');
        if (!container) return;

        // Show loading state
        container.innerHTML = '<p class="empty-state">Lade…</p>';

        try {
            const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            // ✓ Update stat values (font-variant-numeric applied in CSS)
            const stat1 = document.getElementById('template-stat-1');
            if (stat1) stat1.textContent = data.total ?? '-';

            // TODO: Replace with real rendering logic
            // ✓ Escape any user-controlled data before innerHTML
            container.innerHTML = data.items?.length
                ? data.items.map(item => `
                    <div class="cluster-card">
                        <strong>${_tmplEsc(item.name)}</strong>
                        <span class="status-badge ${_tmplEsc(item.status === 'ok' ? 'status-ok' : 'status-error')}">
                            ${_tmplEsc(item.status)}
                        </span>
                    </div>`).join('')
                : '<p class="empty-state">Keine Einträge gefunden.</p>';

        } catch (err) {
            console.error('Template: refresh error', err);
            // ✓ Always show an error state — never leave container blank
            if (container) {
                container.innerHTML = '<p class="empty-state text-error">Fehler beim Laden der Daten.</p>';
            }
        }
    },

    // ── Cleanup ────────────────────────────────────────────────────────
    // Called by app.js when the user navigates away from this tab.

    destroy() {
        this.stopPolling();
    },
};

// ── Plugin Registration ────────────────────────────────────────────────
// Key must match manifest.py dashboard_tab.id.
// Must be synchronous and at module level (not inside init()).
if (typeof Ninko !== 'undefined') {
    Ninko._pluginTabs['template'] = TemplateTab;
}
