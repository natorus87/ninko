(function () {
    console.log("Microsoft Entra Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/microsoft_entra/status?connection_id=${state.connectionId}`
                : `/api/microsoft_entra/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('entra-activities').innerHTML =
                    '<p class="empty-state text-error">Verbindungsfehler: ' + data.error + '</p>';
                return;
            }

            document.getElementById('entra-users-count').textContent = data.users_count || "0";
            document.getElementById('entra-groups-count').textContent = data.groups_count || "0";
            document.getElementById('entra-devices-count').textContent = data.devices_count || "0";

            document.getElementById('entra-activities').innerHTML = `
                <table class="data-table">
                    <tr><td>Benutzer</td><td>${data.users_count || 0}</td></tr>
                    <tr><td>Gruppen</td><td>${data.groups_count || 0}</td></tr>
                    <tr><td>Geräte</td><td>${data.devices_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Entra Load Status failed", e);
            document.getElementById('entra-activities').innerHTML =
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
        if (btn.dataset.action === 'entra-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['microsoft_entra'] = {
        id: 'microsoft_entra',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();