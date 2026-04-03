(function () {
    console.log("MikroTik Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/mikrotik/status?connection_id=${state.connectionId}`
                : `/api/mikrotik/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('mikrotik-info').innerHTML =
                    '<p class="empty-state text-error">' + I18n.t('modules.mikrotik.loadError') + '</p>';
                return;
            }

            document.getElementById('mikrotik-hostname').textContent = data.hostname || "-";
            document.getElementById('mikrotik-interfaces-count').textContent = data.interfaces_count || "0";
            document.getElementById('mikrotik-routes-count').textContent = data.routes_count || "0";
            document.getElementById('mikrotik-leases-count').textContent = data.dhcp_leases_count || "0";

            document.getElementById('mikrotik-info').innerHTML = `
                <table class="data-table">
                    <tr><td>${I18n.t('modules.mikrotik.hostname')}</td><td>${data.hostname || '-'}</td></tr>
                    <tr><td>${I18n.t('modules.mikrotik.interfaces')}</td><td>${data.interfaces_count || 0}</td></tr>
                    <tr><td>${I18n.t('modules.mikrotik.routes')}</td><td>${data.routes_count || 0}</td></tr>
                    <tr><td>${I18n.t('modules.mikrotik.dhcpLeases')}</td><td>${data.dhcp_leases_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("MikroTik Load Status failed", e);
            document.getElementById('mikrotik-info').innerHTML =
                '<p class="empty-state text-error">' + I18n.t('modules.mikrotik.loadError') + '</p>';
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
        if (btn.dataset.action === 'mikrotik-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['mikrotik'] = {
        id: 'mikrotik',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();