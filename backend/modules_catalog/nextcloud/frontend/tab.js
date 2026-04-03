(function () {
    console.log("Nextcloud Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/nextcloud/status?connection_id=${state.connectionId}`
                : `/api/nextcloud/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('nextcloud-info').innerHTML =
                    '<p class="empty-state text-error">Verbindungsfehler: ' + data.error + '</p>';
                return;
            }

            const users = data.users_count || 0;
            const shares = data.shares_count || 0;
            const storage = data.storage_used || 0;
            const storageGB = (storage / 1024 / 1024 / 1024).toFixed(2);

            document.getElementById('nextcloud-users-count').textContent = users;
            document.getElementById('nextcloud-shares-count').textContent = shares;
            document.getElementById('nextcloud-storage-used').textContent = storageGB + " GB";

            document.getElementById('nextcloud-info').innerHTML = `
                <table class="data-table">
                    <tr><td>Benutzer</td><td>${users}</td></tr>
                    <tr><td>Shares</td><td>${shares}</td></tr>
                    <tr><td>Speicher</td><td>${storageGB} GB</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Nextcloud Load Status failed", e);
            document.getElementById('nextcloud-info').innerHTML =
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
        if (btn.dataset.action === 'nextcloud-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['nextcloud'] = {
        id: 'nextcloud',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();