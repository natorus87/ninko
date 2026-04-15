/**
 * Ninko Core Module Registry
 * Central module registration system for frontend components.
 */

const NinkoRegistry = {
    _modules: new Map(),
    _initialized: false,

    register(id, moduleDef) {
        if (this._modules.has(id)) {
            console.warn(`Module ${id} already registered, overwriting`);
        }

        const defaults = {
            id,
            init: null,
            mount: null,
            unmount: null,
            dependencies: [],
            api: {},
        };

        this._modules.set(id, { ...defaults, ...moduleDef });
        return this;
    },

    get(id) {
        return this._modules.get(id);
    },

    has(id) {
        return this._modules.has(id);
    },

    list() {
        return Array.from(this._modules.keys());
    },

    async init(id) {
        const mod = this._modules.get(id);
        if (!mod) {
            throw new Error(`Module ${id} not found`);
        }

        for (const depId of mod.dependencies) {
            if (!this._initialized.has(depId)) {
                await this.init(depId);
            }
        }

        if (mod.init && !mod._initialized) {
            await mod.init();
            mod._initialized = true;
        }

        return mod;
    },

    mount(id, container) {
        const mod = this._modules.get(id);
        if (mod?.mount) {
            return mod.mount(container);
        }
    },

    unmount(id) {
        const mod = this._modules.get(id);
        if (mod?.unmount) {
            return mod.unmount();
        }
    },
};

if (typeof window !== 'undefined') {
    window.NinkoRegistry = NinkoRegistry;
}
