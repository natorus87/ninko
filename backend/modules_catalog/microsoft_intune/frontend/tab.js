(function () {
    console.log("Microsoft Intune Tab Init");

    const state = {
        connectionId: ""
    };

    function esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/microsoft_intune/status?connection_id=${state.connectionId}`
                : `/api/microsoft_intune/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('intune-devices-list').innerHTML =
                    '<p class="empty-state text-error">' + I18n.t('modules.microsoft_intune.loadError') + '</p>';
                return;
            }

            document.getElementById('intune-devices-count').textContent = data.devices_count || "0";
            document.getElementById('intune-policies-count').textContent = data.policies_count || "0";
            document.getElementById('intune-apps-count').textContent = data.apps_count || "0";

            document.getElementById('intune-devices-list').innerHTML = `
                <table class="data-table">
                    <tr><td>${I18n.t('modules.microsoft_intune.devices')}</td><td>${esc(data.devices_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.microsoft_intune.policies')}</td><td>${esc(data.policies_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.microsoft_intune.apps')}</td><td>${esc(data.apps_count || 0)}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Intune Load Status failed", e);
            document.getElementById('intune-devices-list').innerHTML =
                '<p class="empty-state text-error">' + I18n.t('modules.microsoft_intune.loadError') + '</p>';
        }
    }

    function init() {
        const connSelect = document.getElementById('connection-selector');
        if (connSelect && connSelect.value) {
            state.connectionId = connSelect.value;
        }
        loadStatus();
    }

    function destroy() {}

    function refresh() {
        loadStatus();
    }

    document.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        if (btn.dataset.action === 'intune-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['microsoft_intune'] = {
        id: 'microsoft_intune',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();