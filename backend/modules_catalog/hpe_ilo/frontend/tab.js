(function () {
    console.log("HPE iLO Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const url = state.connectionId
                ? `/api/hpe_ilo/status?connection_id=${state.connectionId}`
                : `/api/hpe_ilo/status`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            // iLO Manager
            const managerEl = document.getElementById('ilo-manager-type');
            const managerCard = document.getElementById('ilo-card-manager');
            if (data.manager) {
                managerEl.textContent = data.manager.manager_type || "iLO";
                managerCard.className = 'status-card ' + (data.manager.firmware_version ? 'running' : '');
            } else {
                managerEl.textContent = "-";
            }

            // Server
            const serverEl = document.getElementById('ilo-server-model');
            const serverCard = document.getElementById('ilo-card-server');
            if (data.system) {
                serverEl.textContent = data.system.model || "-";
                serverCard.className = 'status-card ' + (data.system.power_state === "On" ? 'running' : 'failing');
            } else {
                serverEl.textContent = "-";
            }

            // Power
            const powerEl = document.getElementById('ilo-power-state');
            const powerCard = document.getElementById('ilo-card-power');
            if (data.system) {
                powerEl.textContent = data.system.power_state || "-";
                powerCard.className = 'status-card ' + (data.system.power_state === "On" ? 'running' : 'failing');
            } else {
                powerEl.textContent = "-";
            }

            // Health
            const healthEl = document.getElementById('ilo-health-state');
            const healthCard = document.getElementById('ilo-card-health');
            if (data.system) {
                const health = data.system.health || "OK";
                healthEl.textContent = health;
                healthCard.className = 'status-card ' + (health === "OK" ? "running" : "warning");
            } else {
                healthEl.textContent = "-";
            }

            // Details
            const detailsEl = document.getElementById('ilo-details');
            if (data.system && data.manager) {
                detailsEl.innerHTML = `
                    <table class="data-table">
                        <tr><td>Manufacturer</td><td>${data.system.manufacturer || "-"}</td></tr>
                        <tr><td>Serial Number</td><td style="font-family:monospace">${data.system.serial_number || "-"}</td></tr>
                        <tr><td>UUID</td><td style="font-family:monospace;font-size:0.75rem">${data.system.uuid || "-"}</td></tr>
                        <tr><td>Firmware</td><td>${data.manager.firmware_version || "-"}</td></tr>
                        <tr><td>License</td><td>${data.manager.license || "-"}</td></tr>
                    </table>
                `;
            } else {
                detailsEl.innerHTML = '<p class="empty-state">Keine Daten verfügbar.</p>';
            }

        } catch (e) {
            console.error("HPE iLO Load Status failed", e);
            document.getElementById('ilo-details').innerHTML =
                '<p class="empty-state text-error">Fehler beim Laden. Verbindung prüfen.</p>';
        }
    }

    function init() {
        const connSelect = document.getElementById('connection-selector');
        if (connSelect && connSelect.value) {
            state.connectionId = connSelect.value;
        }
        loadStatus();
    }

    function destroy() {
        // Cleanup if needed
    }

    function refresh() {
        loadStatus();
    }

    // Event delegation via data-action
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const action = btn.dataset.action;
        if (action === 'ilo-refresh') {
            refresh();
        }
    });

    // Expose to global
    window.Ninko = window.Ninko || {};
    window.Ninko._pluginTabs = window.Ninko._pluginTabs || {};
    window.Ninko._pluginTabs['hpe_ilo'] = {
        id: 'hpe_ilo',
        init: init,
        destroy: destroy,
        refresh: refresh,
    };
})();