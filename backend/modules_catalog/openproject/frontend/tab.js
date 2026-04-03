(function () {
    console.log("OpenProject Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/openproject/status?connection_id=${state.connectionId}`
                : `/api/openproject/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            if (data.error) {
                document.getElementById('openproject-info').innerHTML =
                    '<p class="empty-state text-error">Verbindungsfehler: ' + data.error + '</p>';
                return;
            }

            document.getElementById('openproject-projects-count').textContent = data.projects_count || "0";
            document.getElementById('openproject-wp-count').textContent = data.work_packages_count || "0";
            document.getElementById('openproject-users-count').textContent = data.users_count || "0";

            document.getElementById('openproject-info').innerHTML = `
                <table class="data-table">
                    <tr><td>Projekte</td><td>${data.projects_count || 0}</td></tr>
                    <tr><td>Work Packages</td><td>${data.work_packages_count || 0}</td></tr>
                    <tr><td>Benutzer</td><td>${data.users_count || 0}</td></tr>
                </table>
            `;
        } catch (e) {
            console.error("OpenProject Load Status failed", e);
            document.getElementById('openproject-info').innerHTML =
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
        if (btn.dataset.action === 'openproject-refresh') {
            refresh();
        }
    });

    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['openproject'] = {
        id: 'openproject',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();