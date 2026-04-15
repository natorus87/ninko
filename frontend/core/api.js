/**
 * Ninko Core API Client
 * Centralized fetch wrapper with error handling.
 */

const NinkoAPI = {
    baseURL: '',

    async request(path, options = {}) {
        const url = `${this.baseURL}${path}`;
        const defaults = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const config = {
            ...defaults,
            ...options,
            headers: {
                ...defaults.headers,
                ...options.headers,
            },
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        try {
            const response = await fetch(url, config);
            const data = await response.json().catch(() => null);

            if (!response.ok) {
                throw new Error(data?.detail || `HTTP ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error(`API Error (${path}):`, error);
            throw error;
        }
    },

    get(path) {
        return this.request(path, { method: 'GET' });
    },

    post(path, body) {
        return this.request(path, { method: 'POST', body });
    },

    put(path, body) {
        return this.request(path, { method: 'PUT', body });
    },

    delete(path) {
        return this.request(path, { method: 'DELETE' });
    },
};

if (typeof window !== 'undefined') {
    window.NinkoAPI = NinkoAPI;
}
