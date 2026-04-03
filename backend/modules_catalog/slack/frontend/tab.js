(function () {
    console.log("Slack Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/slack/status?connection_id=${state.connectionId}`
                : `/api/slack/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('slack-info').innerHTML =
                    '<p class="empty-state text-error">Verbindungsfehler: ' + data.error + '</p>';
                return;
            }

            document.getElementById('slack-workspace-name').textContent = data.workspace || "-";
            document.getElementById('slack-channels-count').textContent = data.channels_count || "0";
            document.getElementById('slack-users-count').textContent = data.users_count || "0";

            document.getElementById('slack-info').innerHTML = `
                <table class="data-table">
                    <tr><td>Workspace</td><td>${data.workspace || '-'}</td></tr>
                    <tr><td>Channels</td><td>${data.channels_count || 0}</td></tr>
                    <tr><td>Users</td><td>${data.users_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("Slack Load Status failed", e);
            document.getElementById('slack-info').innerHTML =
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
        if (btn.dataset.action === 'slack-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['slack'] = {
        id: 'slack',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();