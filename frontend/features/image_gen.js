/**
 * Ninko Image Generation Settings Feature Module
 *
 * Provider-Konfiguration für KI-Bildgenerierung (Together/OpenAI/Google/
 * Stability/HuggingFace). Aus app.js extrahiert; via Object.assign gemergt.
 */

(function() {
    'use strict';

    const ImageGenFeature = {
        async loadImageGenProvider() {
            try {
                const res = await fetch('/api/settings/image-provider');
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById('imggen-backend').value = data.backend || '';
                document.getElementById('imggen-model').value = data.model || '';
                document.getElementById('imggen-api-key').value = '';
                document.getElementById('imggen-api-key-masked').textContent = data.api_key_masked || '';
            } catch { /* ignore */ }
        },

        async saveImageGenProvider() {
            const statusEl = document.getElementById('imggen-save-status');
            statusEl.textContent = 'Speichere…';
            statusEl.className = 'save-status';
            try {
                const body = {
                    backend: document.getElementById('imggen-backend').value,
                    api_key: document.getElementById('imggen-api-key').value,
                    model: document.getElementById('imggen-model').value,
                };
                const res = await fetch('/api/settings/image-provider', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (res.ok) {
                    statusEl.textContent = 'Gespeichert';
                    statusEl.className = 'save-status save-ok';
                    showNotification('Image-Provider gespeichert', 'info');
                    this.loadImageGenProvider();
                } else {
                    statusEl.textContent = 'Fehler';
                    statusEl.className = 'save-status save-error';
                }
            } catch {
                statusEl.textContent = 'Verbindungsfehler';
                statusEl.className = 'save-status save-error';
            }
        },

        onImageGenBackendChange() {
            const backend = document.getElementById('imggen-backend').value;
            const modelInput = document.getElementById('imggen-model');
            const placeholders = {
                'together_ai': 'black-forest-labs/FLUX.1-schnell-Free',
                'openai': 'dall-e-3',
                'google': 'imagen-3.0-generate-002',
                'stability_ai': 'stable-image-core',
                'huggingface': 'black-forest-labs/FLUX.1-schnell',
            };
            modelInput.placeholder = placeholders[backend] || 'Leer = Standard-Modell';
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, ImageGenFeature);
    } else {
        window.ImageGenFeature = ImageGenFeature;
    }
})();
