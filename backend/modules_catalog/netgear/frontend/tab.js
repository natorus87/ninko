(function () {
    console.log("Netgear Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/netgear/status?connection_id=${state.connectionId}`
                : `/api/netgear/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('netgear-info').innerHTML =
                    '<p class="empty-state text-error">' + I18n.t('modules.netgear.loadError') + '</p>';
                return;
            }

            document.getElementById('netgear-model').textContent = data.model || "-";
            document.getElementById('netgear-firmware').textContent = data.firmware || "-";
            document.getElementById('netgear-ports-count').textContent = data.ports_count || "0";

            document.getElementById('netgear-info').innerHTML = `
                <table class="data-table">
                    <tr><td>${I18n.t('modules.netgear.model')}</td><td>${data.model || '-'}</td></tr>
                    <tr><td>${I18n.t('modules.netgear.firmware')}</td><td>${data.firmware || '-'}</td></tr>
                    <tr><td>${I18n.t('modules.netgear.ports')}</td><td>${data.ports_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Netgear Load Status failed", e);
            document.getElementById('netgear-info').innerHTML =
                '<p class="empty-state text-error">' + I18n.t('modules.netgear.loadError') + '</p>';
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
        if (btn.dataset.action === 'netgear-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['netgear'] = {
        id: 'netgear',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();