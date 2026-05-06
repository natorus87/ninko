(function () {
    console.log("Lenovo XClarity Tab Init");

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
                ? `/api/lenovo_xclarity/status?connection_id=${encodeURIComponent(state.connectionId)}`
                : `/api/lenovo_xclarity/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('xclarity-info').innerHTML =
                    '<p class="empty-state text-error">' + I18n.t('modules.lenovo_xclarity.loadError') + '</p>';
                return;
            }

            document.getElementById('xclarity-servers-count').textContent = data.servers_count || "0";
            document.getElementById('xclarity-chassis-count').textContent = data.chassis_count || "0";
            document.getElementById('xclarity-storage-count').textContent = data.storage_count || "0";

            document.getElementById('xclarity-info').innerHTML = `
                <table class="data-table">
                    <tr><td>${I18n.t('modules.lenovo_xclarity.servers')}</td><td>${esc(data.servers_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.lenovo_xclarity.chassis')}</td><td>${esc(data.chassis_count || 0)}</td></tr>
                    <tr><td>${I18n.t('modules.lenovo_xclarity.storage')}</td><td>${esc(data.storage_count || 0)}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("XClarity Load Status failed", e);
            document.getElementById('xclarity-info').innerHTML =
                '<p class="empty-state text-error">' + I18n.t('modules.lenovo_xclarity.loadError') + '</p>';
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
        if (btn.dataset.action === 'xclarity-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['lenovo_xclarity'] = {
        id: 'lenovo_xclarity',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();
