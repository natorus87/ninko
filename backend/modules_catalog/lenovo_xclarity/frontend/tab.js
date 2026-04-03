(function () {
    console.log("Lenovo XClarity Tab Init");

    const state = {
        connectionId: ""
    };

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
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
                    '<p class="empty-state text-error">Verbindungsfehler: ' + escapeHtml(data.error) + '</p>';
                return;
            }

            document.getElementById('xclarity-servers-count').textContent = data.servers_count || "0";
            document.getElementById('xclarity-chassis-count').textContent = data.chassis_count || "0";
            document.getElementById('xclarity-storage-count').textContent = data.storage_count || "0";

            document.getElementById('xclarity-info').innerHTML = `
                <table class="data-table">
                    <tr><td>Server</td><td>${data.servers_count || 0}</td></tr>
                    <tr><td>Chassis</td><td>${data.chassis_count || 0}</td></tr>
                    <tr><td>Storage</td><td>${data.storage_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("XClarity Load Status failed", e);
            document.getElementById('xclarity-info').innerHTML =
                '<p class="empty-state text-error">Fehler beim Laden.</p>';
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
