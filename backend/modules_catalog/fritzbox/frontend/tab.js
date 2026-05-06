(function () {
    console.log("FritzBox Tab Init");

    const state = {
        connectionId: ""
    };

    // HTML escape helper — never put unescaped user data into innerHTML
    function esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    // Helper for i18n with fallback (English)
    function t(key, fallback) {
        if (typeof I18n !== 'undefined' && I18n.t) {
            const val = I18n.t(key);
            // If the translation returns the key itself, it wasn't found
            if (val !== key) return val;
        }
        return fallback || key;
    }

    async function loadStatus() {
        try {
            const res = await fetch(`/api/fritzbox/status?connection_id=${state.connectionId}`);
            if (!res.ok) throw new Error("Status API Error");
            const data = await res.json();

            // System Info
            document.getElementById('fritzbox-model-info').textContent =
                `${t('fritzbox.model', 'Model:')} ${data.system.model} | ${t('fritzbox.firmware', 'Firmware:')} ${data.system.firmware_version} | ${t('fritzbox.uptime', 'Uptime:')} ${Math.floor(data.system.uptime / 3600)}h`;

            // WAN
            const stBadge = document.getElementById('fritzbox-wan-status');
            if (data.wan.connected) {
                stBadge.textContent = t('fritzbox.online', 'Online');
                stBadge.className = "status-badge status-ok";
            } else {
                stBadge.textContent = t('fritzbox.offline', 'Offline');
                stBadge.className = "status-badge status-error";
            }
            const wanCard = document.getElementById('fritzbox-wan-card');
            if (wanCard) wanCard.className = data.wan.connected ? 'status-card running' : 'status-card failing';
            const wanVal = document.getElementById('fritzbox-wan-status-val');
            if (wanVal) wanVal.textContent = data.wan.connected ? t('fritzbox.online', 'Online') : t('fritzbox.offline', 'Offline');
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
                        <td>${esc(w.ssid) || (t('fritzbox.wlanService', 'WLAN Service ') + (i + 1))}</td>
                        <td>${esc(w.channel) || "-"}</td>
                        <td>${w.enabled ? '<span class="status-badge status-ok">' + t('fritzbox.on', 'On') + '</span>' : '<span class="status-badge status-unknown">' + t('fritzbox.off', 'Off') + '</span>'}</td>
                    </tr>
                `;
            });

        } catch (e) {
            console.error("FritzBox Load Status failed", e);
            document.getElementById('fritzbox-model-info').textContent = t('fritzbox.loadError', 'Error loading FritzBox data.');
        }
    }

    async function loadDevices() {
        const tbody = document.getElementById('fritzbox-devices-list');
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">' + t('fritzbox.loadingDevices', 'Loading devices...') + '</td></tr>';

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
                    '<span class="status-badge status-ok">' + t('fritzbox.online', 'Online') + '</span>' :
                    '<span class="status-badge status-unknown">' + t('fritzbox.offline', 'Offline') + '</span>';

                tbody.innerHTML += `
                    <tr>
                        <td>${esc(d.name)}</td>
                        <td style="font-family: monospace; color: var(--accent-blue);">${esc(d.ip) || "-"}</td>
                        <td style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted);">${esc(d.mac) || "-"}</td>
                        <td>${esc(d.interface) || "-"}</td>
                        <td>${statusBadge}</td>
                    </tr>
                `;
            });

        } catch (e) {
            console.error("FritzBox Load Devices failed", e);
            tbody.innerHTML = '<tr><td colspan="5" class="empty-state" style="color: var(--accent-red);">' + t('fritzbox.devicesLoadError', 'Could not load devices.') + '</td></tr>';
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
    if (typeof Ninko !== 'undefined') Ninko._pluginTabs['fritzbox'] = window.fritzboxApp;
})();
