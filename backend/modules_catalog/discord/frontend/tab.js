(function() {
    console.log("Discord Tab Init");

    const state = {
        connectionId: ""
    };

    function esc(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    const DiscordTab = {
        async load() {
            const select = document.getElementById('discord-conn-select');
            const connId = select?.value || '';
            state.connectionId = connId;
            await this._loadConnections();
            await this.loadStatus();
        },

        async _loadConnections() {
            try {
                const res = await fetch('/api/connections/discord');
                const data = await res.json();
                const select = document.getElementById('discord-conn-select');
                if (!select) return;
                
                const connections = data.connections || [];
                select.innerHTML = connections.map(c => 
                    `<option value="${c.id}">${c.name}</option>`
                ).join('');
                
                if (connections.length === 0) {
                    select.innerHTML = `<option value="">${I18n.t('discord.noConnections', 'Keine Verbindungen')}</option>`;
                }
            } catch (e) {
                console.error('Failed to load connections:', e);
            }
        },

        async loadStatus() {
            try {
                const url = state.connectionId 
                    ? `/api/discord/status?connection_id=${state.connectionId}` 
                    : '/api/discord/status';
                const res = await fetch(url);
                const data = await res.json();

                if (data.error) {
                    this._showError(data.error);
                    return;
                }

                document.getElementById('discord-server-name').textContent = data.data?.name || '-';
                document.getElementById('discord-member-count').textContent = data.data?.member_count || 0;
                document.getElementById('discord-card-server').className = 'status-card running';

                await this.loadChannels();

            } catch (e) {
                console.error('Discord status error:', e);
                this._showError(I18n.t('discord.loadError', 'Fehler beim Laden.'));
            }
        },

        async loadChannels() {
            try {
                const url = state.connectionId 
                    ? `/api/discord/channels?connection_id=${state.connectionId}` 
                    : '/api/discord/channels';
                const res = await fetch(url);
                const data = await res.json();

                const container = document.getElementById('discord-channels-list');
                if (!container) return;

                const channels = data.data || [];
                document.getElementById('discord-channel-count').textContent = channels.length;

                if (channels.length === 0) {
                    container.innerHTML = `<p class="empty-state">${I18n.t('discord.noChannels', 'Keine Kanäle')}</p>`;
                    return;
                }

                container.innerHTML = channels.map(ch => `
                    <div class="channel-item">
                        <span class="channel-type">${ch.type === 0 ? '📝' : ch.type === 2 ? '🎤' : '📁'}</span>
                        <span>${esc(ch.name)}</span>
                    </div>
                `).join('');

            } catch (e) {
                console.error('Discord channels error:', e);
            }
        },

        async sendMessage() {
            const channelInput = document.getElementById('discord-channel-input');
            const messageInput = document.getElementById('discord-message-input');
            
            const channelId = channelInput?.value?.trim();
            const content = messageInput?.value?.trim();

            if (!channelId || !content) {
                alert(I18n.t('discord.enterChannelAndMessage', 'Bitte Channel-ID und Nachricht eingeben.'));
                return;
            }

            try {
                const url = state.connectionId 
                    ? `/api/discord/message?connection_id=${state.connectionId}` 
                    : '/api/discord/message';
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({channel_id: channelId, content})
                });
                const data = await res.json();

                if (data.error) {
                    alert(I18n.t('discord.error', 'Fehler') + ': ' + data.error);
                } else {
                    messageInput.value = '';
                    alert(I18n.t('discord.sent', 'Nachricht gesendet!'));
                }
            } catch (e) {
                console.error('Discord send error:', e);
                alert(I18n.t('discord.error', 'Fehler') + ': ' + e.message);
            }
        },

        _showError(msg) {
            const container = document.getElementById('discord-channels-list');
            if (container) container.innerHTML = `<p class="empty-state text-error">${esc(msg)}</p>`;
        }
    };

    window.DiscordTab = DiscordTab;
    if (typeof Ninko !== 'undefined') Ninko._pluginTabs['discord'] = DiscordTab;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => DiscordTab.load?.());
    } else {
        setTimeout(() => DiscordTab.load?.(), 100);
    }
})();
