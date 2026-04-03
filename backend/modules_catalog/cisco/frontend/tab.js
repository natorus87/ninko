(function () {
    console.log("Cisco Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/cisco/status?connection_id=${state.connectionId}`
                : `/api/cisco/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('cisco-info').innerHTML =
                    '<p class="empty-state text-error">Verbindungsfehler: ' + data.error + '</p>';
                return;
            }

            document.getElementById('cisco-hostname').textContent = data.hostname || "-";
            document.getElementById('cisco-model').textContent = data.model || "-";
            document.getElementById('cisco-interfaces-count').textContent = data.interfaces_count || "0";
            document.getElementById('cisco-vlans-count').textContent = data.vlans_count || "0";

            document.getElementById('cisco-info').innerHTML = `
                <table class="data-table">
                    <tr><td>Hostname</td><td>${data.hostname || '-'}</td></tr>
                    <tr><td>Model</td><td>${data.model || '-'}</td></tr>
                    <tr><td>Interfaces</td><td>${data.interfaces_count || 0}</td></tr>
                    <tr><td>VLANs</td><td>${data.vlans_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Cisco Load Status failed", e);
            document.getElementById('cisco-info').innerHTML =
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
        if (btn.dataset.action === 'cisco-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['cisco'] = {
        id: 'cisco',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();