// IONOS DNS Tab – wird als normales Script geladen (kein ES-Modul)

let currentIonosConnectionId = '';

(async function initIonosTab() {
    console.log("IONOS DNS Tab initialized");

    const btnTest = document.getElementById("btn-ionos-test");
    if (btnTest) {
        btnTest.addEventListener("click", fetchIonosStatus);
    }

    await loadIonosConnections();

    if (currentIonosConnectionId) {
        await fetchIonosStatus();
    }

    document.getElementById('ionos-connection-select')
        ?.addEventListener('change', async (e) => {
            currentIonosConnectionId = e.target.value;
            fetchIonosStatus();
        });
})();

function getIonosQueryParams() {
    return currentIonosConnectionId ? `?connection_id=${currentIonosConnectionId}` : '';
}

async function loadIonosConnections() {
    try {
        const res = await fetch('/api/connections/ionos');
        const data = await res.json();
        const conns = data.connections || [];
        const select = document.getElementById('ionos-connection-select');
        if (!select) return;

        if (conns.length === 0) {
            select.innerHTML = '<option value="">' + I18n.t('modules.ionos.noConnections') + '</option>';
            currentIonosConnectionId = '';
            return;
        }

        select.innerHTML = conns.map(c =>
            `<option value="${c.id}" ${c.is_default ? 'selected' : ''}>${c.name} (${c.environment})</option>`
        ).join('');

        const defaultConn = conns.find(c => c.is_default) || conns[0];
        currentIonosConnectionId = defaultConn.id;
    } catch (err) {
        console.error('IONOS Connections Fehler:', err);
    }
}

const IonosTab = {
    async init() {
        await loadIonosConnections();
        if (currentIonosConnectionId) await fetchIonosStatus();
    },
    destroy() {}
};
if (typeof Ninko !== 'undefined') Ninko._pluginTabs['ionos'] = IonosTab;

async function fetchIonosStatus() {
    if (!currentIonosConnectionId) return;

    const statusVal = document.getElementById("ionos-status-val");
    if (!statusVal) return;

    statusVal.textContent = I18n.t('modules.ionos.checking');
    statusVal.style.color = "var(--text-muted)";
    const card = statusVal.closest('.status-card');

    try {
        const response = await fetch(`/api/ionos/status${getIonosQueryParams()}`);
        if (response.ok) {
            const data = await response.json();
            if (data.status === "ok") {
                statusVal.textContent = data.message || I18n.t('modules.ionos.connected');
                statusVal.style.color = "var(--accent-green)";
                if (card) card.className = "status-card running";
            } else {
                statusVal.textContent = data.message || I18n.t('modules.ionos.error');
                statusVal.style.color = "var(--accent-red)";
                if (card) card.className = "status-card failing";
                console.error("IONOS API Error:", data.message);
            }
        } else {
            statusVal.textContent = I18n.t('modules.ionos.apiError') + response.status;
            statusVal.style.color = "var(--accent-red)";
            if (card) card.className = "status-card failing";
        }
    } catch (error) {
        statusVal.textContent = I18n.t('modules.ionos.offline');
        statusVal.style.color = "var(--accent-red)";
        if (card) card.className = "status-card failing";
        console.error("Fetch error:", error);
    }
}
