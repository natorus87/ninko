(function () {
    console.log("FritzBox Tab Init");

    const state = {
        connectionId: ""
    };

    async function loadStatus() {
        try {
            const res = await fetch(`/api/fritzbox/status?connection_id=${state.connectionId}`);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            // System Info
            document.getElementById('fritzbox-model-info').textContent =
                `${I18n.t('modules.fritzbox.model')} ${data.system.model} | ${I18n.t('modules.fritzbox.firmware')} ${data.system.firmware_version} | ${I18n.t('modules.fritzbox.uptime')} ${Math.floor(data.system.uptime / 3600)}h`;

            // WAN
            const stBadge = document.getElementById('fritzbox-wan-status');
            if (data.wan.connected) {
                stBadge.textContent = I18n.t('modules.fritzbox.online');
                stBadge.className = "status-badge status-ok";
            } else {
                stBadge.textContent = I18n.t('modules.fritzbox.offline');
                stBadge.className = "status-badge status-error";
            }
            const wanCard = document.getElementById('fritzbox-wan-card');
            if (wanCard) wanCard.className = data.wan.connected ? 'status-card running' : 'status-card failing';
            const wanVal = document.getElementById('fritzbox-wan-status-val');
            if (wanVal) wanVal.textContent = data.wan.connected ? I18n.t('modules.fritzbox.online') : I18n.t('modules.fritzbox.offline');
            document.getElementById('fritzbox-wan-ip').textContent = data.wan.ip_address || "N/A";

            // Bandwidth
            document.getElementById('fritzbox-downstream').textContent = (data.bandwidth.ds_current / 1000000).toFixed(2) + " Mbit/s";
            document.getElementById('fritzbox-upstream').textContent = (data.bandwidth.us_current / 1000000).toFixed(2) + " Mbit/s";

            // WLAN
            const wlanList = document.getElementById('fritzbox-wlan-list');
            wlanList.innerHTML = '';
            data.wlan.forEach((w, i) => {
                wlanList.innerHTML += `
                    <tr>
                        <td>${w.ssid || (I18n.t('modules.fritzbox.wlanService') + (i + 1))}</td>
                        <td>${w.channel || "-"}</td>
                        <td>${w.enabled ? '<span class="status-badge status-ok">' + I18n.t('modules.fritzbox.on') + '</span>' : '<span class="status-badge status-unknown">' + I18n.t('modules.fritzbox.off') + '</span>'}</td>
                    </tr>
                `;
            });

        } catch (e) {
            console.error("FritzBox Load Status failed", e);
            document.getElementById('fritzbox-model-info').textContent = I18n.t('modules.fritzbox.loadError');
        }
    }

    async function loadDevices() {
        const tbody = document.getElementById('fritzbox-devices-list');
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">' + I18n.t('modules.fritzbox.loadingDevices') + '</td></tr>';

        try {
            const res = await fetch(`/api/fritzbox/devices?connection_id=${state.connectionId}`);
            if (!res.ok) throw new Error("Device API Error");
            const devices = await res.json();

            tbody.innerHTML = '';

            // Sort: online first
            devices.sort((a, b) => {
                const aOn = (a.status === "Online");
                const bOn = (b.status === "Online");
                return (bOn === aOn) ? 0 : bOn ? 1 : -1;
            });

            devices.forEach(d => {
                const statusBadge = (d.status === "Online") ?
                    '<span class="status-badge status-ok">' + I18n.t('modules.fritzbox.online') + '</span>' :
                    '<span class="status-badge status-unknown">' + I18n.t('modules.fritzbox.offline') + '</span>';

                tbody.innerHTML += `
                    <tr>
                        <td>${d.name}</td>
                        <td style="font-family: monospace; color: var(--accent-blue);">${d.ip || "-"}</td>
                        <td style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">${d.mac || "-"}</td>
                        <td>${d.interface || "-"}</td>
                        <td>${statusBadge}</td>
                    </tr>
                `;
            });

        } catch (e) {
            console.error("FritzBox Load Devices failed", e);
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="color: var(--accent-red);">' + I18n.t('modules.fritzbox.devicesLoadError') + '</td></tr>';
        }
    }

    async function init() {
        // Find selected connection from main app header dropdown if it exists
        const connSelect = document.getElementById('connection-selector');
        if (connSelect && connSelect.value) {
            state.connectionId = connSelect.value;
        }

        await loadStatus();
        await loadDevices();
    }

    window.fritzboxApp = {
        init,
        loadDevices,
        loadStatus,
        setConnectionContext: (connId) => {
            state.connectionId = connId;
            init();
        }
    };

    // Auto-Init if possible
    setTimeout(init, 300);
})();
