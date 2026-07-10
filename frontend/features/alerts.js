/**
 * Ninko Alert Management Feature Module
 *
 * Aktive Alerts aus Monitor-Agent/Workflows: Laden, Tabellen-Rendering,
 * Auflösen, Badge und WS-Live-Update. Aus app.js extrahiert; via Object.assign
 * gemergt. _handleWsAlert wird aus dem WS-Handler (app.js) via this. gerufen.
 */

(function() {
    'use strict';

    const AlertsFeature = {
        _alertsCache: [],

        async loadAlerts() {
            const container = document.getElementById('alerts-content');
            const loading = document.getElementById('alerts-loading');
            const emptyState = document.getElementById('alerts-empty-state');
            const table = document.getElementById('alerts-table');

            loading.style.display = 'block';
            emptyState.style.display = 'none';
            table.style.display = 'none';

            try {
                const res = await fetch('/api/alerts');
                const data = await res.json();

                if (data.success && data.data && data.data.alerts) {
                    this._alertsCache = data.data.alerts;
                    this._renderAlertsTable();
                    this._updateAlertsBadge();
                }
            } catch (err) {
                console.error('Fehler beim Laden der Alerts:', err);
            } finally {
                loading.style.display = 'none';
            }
        },

        _renderAlertsTable() {
            const emptyState = document.getElementById('alerts-empty-state');
            const table = document.getElementById('alerts-table');
            const tbody = document.getElementById('alerts-table-body');

            if (this._alertsCache.length === 0) {
                emptyState.style.display = 'block';
                table.style.display = 'none';
                return;
            }

            emptyState.style.display = 'none';
            table.style.display = 'table';

            const severityClass = {
                critical: 'alert-severity-critical',
                warning: 'alert-severity-warning',
                info: 'alert-severity-info'
            };

            const severityLabel = {
                critical: t('alerts.critical'),
                warning: t('alerts.warning'),
                info: t('alerts.info')
            };

            tbody.innerHTML = this._alertsCache.map(alert => {
                const firstSeen = new Date(alert.first_seen).toLocaleString();
                const lastSeen = new Date(alert.last_seen).toLocaleString();
                const sevClass = severityClass[alert.severity] || 'alert-severity-info';
                const sevLabel = severityLabel[alert.severity] || alert.severity;

                return `
                    <tr data-alert-id="${alert.alert_id}">
                        <td><span class="alert-severity ${sevClass}">${sevLabel}</span></td>
                        <td>${alert.module}</td>
                        <td>${alert.summary}</td>
                        <td>${firstSeen}</td>
                        <td>${lastSeen}</td>
                        <td>
                            <button class="btn-icon-sm" data-action="resolveAlert" data-args="${JSON.stringify([alert.alert_id]).replace(/\"/g, '&quot;')}" title="Resolve">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        },

        async resolveAlert(alertId) {
            if (!confirm(t('alerts.resolveConfirm'))) return;

            try {
                const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: 'POST' });
                const data = await res.json();

                if (data.success) {
                    showNotification(t('alerts.resolved'), 'success');
                    this._alertsCache = this._alertsCache.filter(a => a.alert_id !== alertId);
                    this._renderAlertsTable();
                    this._updateAlertsBadge();
                } else {
                    showNotification(data.message || t('alerts.resolveError'), 'error');
                }
            } catch (err) {
                showNotification(t('alerts.resolveError'), 'error');
            }
        },

        _updateAlertsBadge() {
            const badge = document.getElementById('alerts-badge');
            if (!badge) return;

            const count = this._alertsCache.length;
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        },

        _handleWsAlert(data) {
            if (!data.alert_id) return;

            const exists = this._alertsCache.some(a => a.alert_id === data.alert_id);
            if (!exists) {
                this._alertsCache.push(data);
                this._renderAlertsTable();
                this._updateAlertsBadge();

                const panel = document.getElementById('settings-panel-alerts');
                if (panel && panel.classList.contains('active')) {
                    this._renderAlertsTable();
                }
            }
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, AlertsFeature);
    } else {
        window.AlertsFeature = AlertsFeature;
    }
})();
