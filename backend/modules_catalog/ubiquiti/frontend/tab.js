(function () {
    console.log("Ubiquiti Tab Init");

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
                ? `/api/ubiquiti/status?connection_id=${state.connectionId}`
                : `/api/ubiquiti/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('ubiquiti-info').innerHTML =
                    '<p class="empty-state text-error">' + I18n.t('modules.ubiquiti.loadError') + '</p>';
                return;
            }

            document.getElementById('ubiquiti-devices-count').textContent = data.devices_count || "0";
            document.getElementById('ubiquiti-clients-count').textContent = data.clients_count || "0";
            document.getElementById('ubiquiti-wlans-count').textContent = data.wlans_count || "0";

            document.getElementById('ubiquiti-info').innerHTML = `
                <table class="data-table">
                    <tr><td>${I18n.t('modules.ubiquiti.devices')}</td><td>${esc(data.devices_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.ubiquiti.clients')}</td><td>${esc(data.clients_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.ubiquiti.wlans')}</td><td>${esc(data.wlans_count || 0)}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Ubiquiti Load Status failed", e);
            document.getElementById('ubiquiti-info').innerHTML =
                '<p class="empty-state text-error">' + I18n.t('modules.ubiquiti.loadError') + '</p>';
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
        if (btn.dataset.action === 'ubiquiti-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['ubiquiti'] = {
        id: 'ubiquiti',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();