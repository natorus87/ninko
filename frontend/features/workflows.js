/**
 * Ninko Workflows Feature Module
 * 
 * Enthält alle Workflow-bezogenen Funktionen:
 * - Workflow-Liste und CRUD
 * - Visueller Workflow-Editor (Canvas, Nodes, Edges)
 * - Workflow-Ausführung und Run-Dashboard
 * - Run-Historie und Step-Details
 */

(function() {
    'use strict';

    const WorkflowsFeature = {
        // -------------------------------------------------------
        //  WORKFLOWS
        // -------------------------------------------------------

        _wfNodes: [],
        _wfEdges: [],
        _wfSelectedNode: null,
        _wfConnecting: null,
        _wfRunRefreshTimer: null,
        _wfCurrentRunId: null,
        _wfCurrentWorkflowId: null,
        _wfRunNodes: [],
        _wfRunEdges: [],
        _wfZoom: 1,
        _wfHistory: [],
        _wfHistoryIndex: -1,
        _wfHistoryMax: 50,
        _wfEditorBindingsReady: false,

        async loadWorkflows() {
            const container = document.getElementById('workflows-list');
            try {
                const res = await fetch('/api/workflows/');
                const data = await res.json();
                const wfs = data.workflows || [];
                if (!wfs.length) {
                    container.innerHTML = '<p class="empty-state">Noch keine Workflows konfiguriert.<br><span style="font-size:0.85rem;opacity:0.7">Klicke auf „➕ Neuen Workflow erstellen", um loszulegen.</span></p>';
                    return;
                }
                container.innerHTML = wfs.map(wf => `
                    <div class="workflow-card" data-wf-id="${this._escapeHtml(wf.id)}">
                        <div class="workflow-card-header">
                            <span class="workflow-card-name">${this._escapeHtml(wf.name)}</span>
                            <span class="run-status-badge run-${this._escapeHtml(wf.last_run_status || 'idle')}">${this._escapeHtml(wf.last_run_status || 'idle')}</span>
                        </div>
                        <p class="workflow-card-desc">${this._escapeHtml(wf.description || '')}</p>
                        <div class="workflow-card-meta">
                            <span>${(wf.nodes || []).length} Nodes</span>
                            ${wf.last_run_at ? `<span>Letzter Run: ${new Date(wf.last_run_at).toLocaleString('de')}</span>` : ''}
                            ${wf.updated_at ? `<span title="Zuletzt gespeichert">${this._ic.clock} ${new Date(wf.updated_at).toLocaleDateString('de')}</span>` : ''}
                        </div>
                        <div class="workflow-card-actions">
                            <button class="btn btn-sm btn-primary" data-action="run">${this._ic.play} Run</button>
                            <button class="btn btn-sm btn-outline" data-action="edit">${this._ic.edit} Bearbeiten</button>
                            <button class="btn btn-sm btn-outline" data-action="logs">${this._ic.list} Logs</button>
                            <button class="btn btn-sm btn-outline" data-action="delete" title="Löschen" style="color:var(--error-color)">${this._ic.trash} Löschen</button>
                        </div>
                    </div>
                `).join('');
                container.querySelectorAll('.workflow-card').forEach(card => {
                    const id = card.dataset.wfId;
                    const name = card.querySelector('.workflow-card-name')?.textContent || '';
                    card.querySelector('[data-action="run"]')?.addEventListener('click', () => this.runWorkflow(id, name));
                    card.querySelector('[data-action="edit"]')?.addEventListener('click', () => this.openWorkflowEditor(id));
                    card.querySelector('[data-action="logs"]')?.addEventListener('click', () => this.openRunHistory(id, name));
                    card.querySelector('[data-action="delete"]')?.addEventListener('click', () => this.deleteWorkflow(id, name));
                });
            } catch (err) { console.error('loadWorkflows failed:', err); container.innerHTML = '<p class="empty-state">Fehler beim Laden der Workflows.</p>'; }
        },

        async openWorkflowEditor(wfId) {
            this._wfNodes = [];
            this._wfEdges = [];
            this._wfSelectedNode = null;
            this._wfConnecting = null;
            this._wfZoom = 1;
            this._wfHistory = [];
            this._wfHistoryIndex = -1;
            document.getElementById('workflows-overview').classList.add('hidden');
            document.getElementById('workflow-run-dashboard').classList.add('hidden');
            document.getElementById('workflow-editor').classList.remove('hidden');
            document.getElementById('wf-edit-id').value = wfId || '';

            if (wfId) {
                try {
                    const res = await fetch(`/api/workflows/${wfId}`);
                    const wf = await res.json();
                    document.getElementById('wf-name-input').value = wf.name || '';
                    document.getElementById('wf-desc-input').value = wf.description || '';
                    this._wfNodes = wf.nodes || [];
                    this._wfEdges = wf.edges || [];
                } catch (err) { console.error('Failed to load workflow for editor:', err); }
            } else {
                document.getElementById('wf-name-input').value = '';
                document.getElementById('wf-desc-input').value = '';
            }
            this._wfEnsureEditorBindings();
            this._wfApplyZoom();
            this._wfRenderCanvas();
            this._wfPushHistory();

            setTimeout(() => {
                const container = document.getElementById('wf-canvas-container');
                if (!container) return;
                if (this._wfNodes.length) {
                    const xs = this._wfNodes.map(n => n.position.x);
                    const ys = this._wfNodes.map(n => n.position.y);
                    const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
                    const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
                    container.scrollLeft = cx - container.clientWidth / 2 + 75;
                    container.scrollTop  = cy - container.clientHeight / 2 + 40;
                } else {
                    container.scrollLeft = 1500 - container.clientWidth / 2;
                    container.scrollTop  = 1500 - container.clientHeight / 2;
                }
                this._wfUpdateMiniMap();
            }, 10);
        },

        closeWorkflowEditor() {
            document.getElementById('workflow-editor').classList.add('hidden');
            document.getElementById('workflows-overview').classList.remove('hidden');
            this.loadWorkflows();
        },

        _wfSnapshot() {
            return {
                nodes: JSON.parse(JSON.stringify(this._wfNodes || [])),
                edges: JSON.parse(JSON.stringify(this._wfEdges || [])),
            };
        },

        _wfPushHistory() {
            const snap = this._wfSnapshot();
            const prev = this._wfHistory[this._wfHistoryIndex];
            if (prev && JSON.stringify(prev) === JSON.stringify(snap)) return;
            if (this._wfHistoryIndex < this._wfHistory.length - 1) {
                this._wfHistory = this._wfHistory.slice(0, this._wfHistoryIndex + 1);
            }
            this._wfHistory.push(snap);
            if (this._wfHistory.length > this._wfHistoryMax) this._wfHistory.shift();
            this._wfHistoryIndex = this._wfHistory.length - 1;
        },

        _wfApplySnapshot(snap) {
            if (!snap) return;
            this._wfNodes = JSON.parse(JSON.stringify(snap.nodes || []));
            this._wfEdges = JSON.parse(JSON.stringify(snap.edges || []));
            this._wfSelectedNode = null;
            document.getElementById('wf-node-inspector')?.classList.add('hidden');
            this._wfRenderCanvas();
        },

        wfUndo() {
            if (this._wfHistoryIndex <= 0) return;
            this._wfHistoryIndex -= 1;
            this._wfApplySnapshot(this._wfHistory[this._wfHistoryIndex]);
        },

        wfRedo() {
            if (this._wfHistoryIndex >= this._wfHistory.length - 1) return;
            this._wfHistoryIndex += 1;
            this._wfApplySnapshot(this._wfHistory[this._wfHistoryIndex]);
        },

        _wfUpdateZoomLabel() {
            const el = document.getElementById('wf-zoom-level');
            if (!el) return;
            el.textContent = `${Math.round(this._wfZoom * 100)}%`;
        },

        _wfApplyZoom() {
            const canvas = document.getElementById('wf-canvas');
            const svg = document.getElementById('wf-edges-svg');
            if (canvas) canvas.style.transform = `scale(${this._wfZoom})`;
            if (svg) svg.style.transform = `scale(${this._wfZoom})`;
            this._wfUpdateZoomLabel();
            this._wfUpdateMiniMap();
        },

        _wfSetZoom(nextZoom, anchorX = null, anchorY = null) {
            const container = document.getElementById('wf-canvas-container');
            if (!container) return;
            const oldZoom = this._wfZoom;
            const clamped = Math.max(0.35, Math.min(2.5, nextZoom));
            if (Math.abs(clamped - oldZoom) < 0.0001) return;

            const viewportX = anchorX != null ? anchorX : container.clientWidth / 2;
            const viewportY = anchorY != null ? anchorY : container.clientHeight / 2;
            const worldX = (container.scrollLeft + viewportX) / oldZoom;
            const worldY = (container.scrollTop + viewportY) / oldZoom;

            this._wfZoom = clamped;
            this._wfApplyZoom();

            container.scrollLeft = worldX * clamped - viewportX;
            container.scrollTop = worldY * clamped - viewportY;
            this._wfUpdateMiniMap();
        },

        wfZoomIn() { this._wfSetZoom(this._wfZoom * 1.12); },
        wfZoomOut() { this._wfSetZoom(this._wfZoom / 1.12); },

        wfFitToScreen() {
            const container = document.getElementById('wf-canvas-container');
            if (!container || !this._wfNodes.length) return;
            const minX = Math.min(...this._wfNodes.map((n) => n.position.x));
            const minY = Math.min(...this._wfNodes.map((n) => n.position.y));
            const maxX = Math.max(...this._wfNodes.map((n) => n.position.x + 160));
            const maxY = Math.max(...this._wfNodes.map((n) => n.position.y + 80));
            const width = Math.max(120, maxX - minX);
            const height = Math.max(80, maxY - minY);
            const targetZoom = Math.min(
                (container.clientWidth * 0.9) / width,
                (container.clientHeight * 0.9) / height
            );
            this._wfSetZoom(targetZoom);
            container.scrollLeft = Math.max(0, (minX + width / 2) * this._wfZoom - container.clientWidth / 2);
            container.scrollTop = Math.max(0, (minY + height / 2) * this._wfZoom - container.clientHeight / 2);
            this._wfUpdateMiniMap();
        },

        _wfUpdateMiniMap() {
            const minimap = document.getElementById('wf-minimap');
            const content = document.getElementById('wf-minimap-content');
            const viewport = document.getElementById('wf-minimap-viewport');
            const container = document.getElementById('wf-canvas-container');
            if (!minimap || !content || !viewport || !container) return;

            this._wfPositionCanvasOverlays();

            const mapW = minimap.clientWidth;
            const mapH = minimap.clientHeight;
            const worldW = 3000 * this._wfZoom;
            const worldH = 3000 * this._wfZoom;
            const scaleX = mapW / worldW;
            const scaleY = mapH / worldH;

            content.innerHTML = (this._wfNodes || []).map((n) => {
                const x = n.position.x * this._wfZoom * scaleX;
                const y = n.position.y * this._wfZoom * scaleY;
                return `<span class="wf-minimap-node" style="left:${x}px;top:${y}px"></span>`;
            }).join('');

            viewport.style.left = `${container.scrollLeft * scaleX}px`;
            viewport.style.top = `${container.scrollTop * scaleY}px`;
            viewport.style.width = `${container.clientWidth * scaleX}px`;
            viewport.style.height = `${container.clientHeight * scaleY}px`;
        },

        _wfPositionCanvasOverlays() {
            const container = document.getElementById('wf-canvas-container');
            if (!container) return;

            const offset = `translate(${container.scrollLeft}px, ${container.scrollTop}px)`;
            document.getElementById('wf-minimap')?.style.setProperty('transform', offset);
            document.getElementById('wf-zoom-controls')?.style.setProperty('transform', offset);
        },

        _wfEnsureEditorBindings() {
            if (this._wfEditorBindingsReady) return;
            this._wfEditorBindingsReady = true;

            const container = document.getElementById('wf-canvas-container');
            const minimap = document.getElementById('wf-minimap');
            if (container) {
                container.addEventListener('scroll', () => this._wfUpdateMiniMap());
                container.addEventListener('wheel', (e) => {
                    if (!(e.ctrlKey || e.metaKey)) return;
                    e.preventDefault();
                    const rect = container.getBoundingClientRect();
                    const anchorX = e.clientX - rect.left;
                    const anchorY = e.clientY - rect.top;
                    const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
                    this._wfSetZoom(this._wfZoom * factor, anchorX, anchorY);
                }, { passive: false });

                let panStart = null;
                container.addEventListener('mousedown', (e) => {
                    const canPan = e.button === 1 || (e.button === 0 && e.shiftKey);
                    if (!canPan) return;
                    panStart = { x: e.clientX, y: e.clientY, left: container.scrollLeft, top: container.scrollTop };
                    container.style.cursor = 'grabbing';
                    e.preventDefault();
                });
                document.addEventListener('mousemove', (e) => {
                    if (!panStart) return;
                    container.scrollLeft = panStart.left - (e.clientX - panStart.x);
                    container.scrollTop = panStart.top - (e.clientY - panStart.y);
                });
                document.addEventListener('mouseup', () => {
                    if (!panStart) return;
                    panStart = null;
                    container.style.cursor = '';
                });
            }

            minimap?.addEventListener('click', (e) => {
                const rect = minimap.getBoundingClientRect();
                const relX = e.clientX - rect.left;
                const relY = e.clientY - rect.top;
                const container = document.getElementById('wf-canvas-container');
                if (!container) return;
                const worldW = 3000 * this._wfZoom;
                const worldH = 3000 * this._wfZoom;
                const worldX = (relX / rect.width) * worldW;
                const worldY = (relY / rect.height) * worldH;
                container.scrollLeft = Math.max(0, worldX - container.clientWidth / 2);
                container.scrollTop = Math.max(0, worldY - container.clientHeight / 2);
                this._wfUpdateMiniMap();
            });

            document.addEventListener('keydown', (e) => {
                const editorVisible = !document.getElementById('workflow-editor')?.classList.contains('hidden');
                if (!editorVisible) return;
                const target = e.target;
                const tag = (target?.tagName || '').toLowerCase();
                const inInput = target?.isContentEditable || tag === 'input' || tag === 'textarea' || tag === 'select';
                const mod = e.ctrlKey || e.metaKey;
                if (!mod || inInput) return;
                const key = e.key.toLowerCase();
                if (key === 'z' && !e.shiftKey) {
                    e.preventDefault();
                    this.wfUndo();
                } else if (key === 'z' && e.shiftKey) {
                    e.preventDefault();
                    this.wfRedo();
                } else if (key === 'y') {
                    e.preventDefault();
                    this.wfRedo();
                }
            });
        },

        _wfNodeIcon(type) {
            return {
                trigger: this._ic.zap,
                agent: this._ic.bot,
                condition: this._ic.branch,
                loop: this._ic.loop,
                parallel: this._ic.parallel || '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12h4v-4H4v4zm6 0h4v-4h-4v4zm6 0h4v-4h-4v4z"/></svg>',
                subflow: this._ic.subflow || '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12h6l-2-2m2 2l-2 2M12 12h8"/></svg>',
                script: this._ic.script || '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
                variable: this._ic.box,
                end: this._ic.stopci
            }[type] || '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/></svg>';
        },

        _wfNodeDefaults(type) {
            const defaults = {
                trigger: { label: 'Trigger', config: { mode: 'manual' } },
                agent: { label: 'Agent', config: { agent_id: '', prompt: '' } },
                condition: { label: 'Bedingung', config: { expression: 'output.contains("error")', true_label: 'true', false_label: 'false' } },
                loop: { label: 'Loop', config: { mode: 'foreach', variable: 'items', prompt: 'Verarbeite: {loop_item}', max_iterations: '10' } },
                parallel: { label: 'Parallel', config: { prompts: ['Task 1', 'Task 2'] } },
                subflow: { label: 'Subflow', config: { workflow_id: '' } },
                script: { label: 'Script', config: { script_id: '', input_var: '', timeout: '30' } },
                variable: { label: 'Variable', config: { name: 'myVar', value: '' } },
                end: { label: 'Ende', config: { status: 'succeeded' } },
            };
            return defaults[type] || { label: type, config: {} };
        },

        wfAddNode(type) {
            const defs = this._wfNodeDefaults(type);
            const id = Date.now().toString(36);
            const container = document.getElementById('wf-canvas-container');
            const cx = container ? (container.scrollLeft / this._wfZoom) + Math.floor(container.clientWidth / this._wfZoom / 2) - 75 : 1450;
            const cy = container ? (container.scrollTop / this._wfZoom) + Math.floor(container.clientHeight / this._wfZoom / 2) - 40 : 1450;
            const idx = this._wfNodes.length;
            const node = {
                id,
                type,
                label: defs.label,
                config: { ...defs.config },
                position: { x: cx + (idx % 3) * 220, y: cy + Math.floor(idx / 3) * 160 }
            };
            this._wfNodes.push(node);
            this._wfRenderCanvas();
            this._wfPushHistory();
        },

        _wfRenderCanvas() {
            const canvas = document.getElementById('wf-canvas');
            const svg = document.getElementById('wf-edges-svg');
            if (!canvas || !svg) return;

            canvas.innerHTML = '';
            this._wfNodes.forEach(node => {
                const el = document.createElement('div');
                el.className = `wf-node wf-node-${node.type}${this._wfSelectedNode === node.id ? ' wf-node-selected' : ''}`;
                el.id = `wf-node-${node.id}`;
                el.style.left = `${node.position.x}px`;
                el.style.top = `${node.position.y}px`;
                el.innerHTML = `
                    <div class="wf-node-header">
                        <span class="wf-node-icon">${this._wfNodeIcon(node.type)}</span>
                        <span class="wf-node-label">${this._escapeHtml(node.label)}</span>
                    </div>
                    <div class="wf-node-port wf-port-out" title="Verbinden" data-node="${node.id}"></div>
                `;
                el.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._wfSelectNode(node.id);
                });
                this._wfMakeDraggable(el, node);
                el.querySelector('.wf-port-out').addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._wfStartConnection(node.id);
                });
                canvas.appendChild(el);
            });
            this._wfUpdateSvgEdges();

            canvas.onclick = (e) => {
                if (e.target === canvas) {
                    this._wfSelectedNode = null;
                    canvas.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
                    document.getElementById('wf-node-inspector')?.classList.add('hidden');
                    if (this._wfConnecting) {
                        this._wfConnecting = null;
                        canvas.style.cursor = 'default';
                    }
                }
            };
            this._wfUpdateMiniMap();
        },

        _wfMakeDraggable(el, node) {
            let startX, startY, origX, origY;
            el.addEventListener('mousedown', (e) => {
                if (e.target.classList.contains('wf-port-out')) return;
                if (e.button !== 0) return;
                startX = e.clientX; startY = e.clientY;
                origX = node.position.x; origY = node.position.y;
                const onMove = (e) => {
                    const dx = (e.clientX - startX) / this._wfZoom;
                    const dy = (e.clientY - startY) / this._wfZoom;
                    node.position.x = origX + dx;
                    node.position.y = origY + dy;
                    el.style.left = `${node.position.x}px`;
                    el.style.top = `${node.position.y}px`;
                    this._wfUpdateSvgEdges();
                    this._wfUpdateMiniMap();
                };
                const onUp = () => {
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                    this._wfPushHistory();
                };
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
                e.preventDefault();
            });
        },

        _wfStartConnection(sourceId) {
            if (this._wfConnecting) {
                document.querySelector('.wf-node-connecting')?.classList.remove('wf-node-connecting');
                if (this._wfConnecting !== sourceId) {
                    const exists = this._wfEdges.some(e => e.source_id === this._wfConnecting && e.target_id === sourceId);
                    if (!exists) {
                        this._wfEdges.push({ id: Date.now().toString(36), source_id: this._wfConnecting, target_id: sourceId, label: '' });
                        this._wfUpdateSvgEdges();
                        this._wfPushHistory();
                        showNotification('Verbindung erstellt', 'info');
                    } else {
                        showNotification('Verbindung bereits vorhanden', 'info');
                    }
                }
                this._wfConnecting = null;
                document.getElementById('wf-canvas').style.cursor = 'default';
            } else {
                this._wfConnecting = sourceId;
                document.getElementById('wf-canvas').style.cursor = 'crosshair';
                document.getElementById(`wf-node-${sourceId}`)?.classList.add('wf-node-connecting');
                showNotification('Klicke auf einen Ziel-Node, um die Verbindung herzustellen', 'info');
            }
        },

        _wfGetPortPos(nodeId, side) {
            const el = document.getElementById(`wf-node-${nodeId}`);
            const canvas = document.getElementById('wf-canvas');
            if (!el || !canvas) return null;
            const x = canvas.offsetLeft + el.offsetLeft + el.offsetWidth / 2;
            if (side === 'in') {
                return { x, y: canvas.offsetTop + el.offsetTop };
            }
            return { x, y: canvas.offsetTop + el.offsetTop + el.offsetHeight };
        },

        async _wfUpdateSvgEdges() {
            const svg = document.getElementById('wf-edges-svg');
            if (!svg) return;

            svg.innerHTML = `<defs>
                <marker id="wf-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                    <path d="M0,0 L10,5 L0,10 Z" fill="#3b82f6" />
                </marker>
            </defs>`;

            this._wfEdges.forEach(edge => {
                const src = this._wfGetPortPos(edge.source_id, 'out');
                const tgt = this._wfGetPortPos(edge.target_id, 'in');
                if (!src || !tgt) return;

                const hitbox = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                hitbox.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
                hitbox.setAttribute('stroke', 'transparent');
                hitbox.setAttribute('stroke-width', '15');
                hitbox.setAttribute('fill', 'none');
                hitbox.style.cursor = 'pointer';
                hitbox.style.pointerEvents = 'stroke';

                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
                path.setAttribute('class', 'wf-edge-path');
                path.setAttribute('marker-end', 'url(#wf-arrow)');
                path.setAttribute('stroke', '#3b82f6');
                path.setAttribute('stroke-width', '3');
                path.setAttribute('fill', 'none');
                path.style.pointerEvents = 'none';

                hitbox.setAttribute('data-edge-id', edge.id);
                hitbox.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (await this.confirm('Verbindung löschen?')) {
                        this._wfEdges = this._wfEdges.filter(ed => ed.id !== edge.id);
                        this._wfUpdateSvgEdges();
                        this._wfPushHistory();
                        if (this._wfSelectedNode) this._wfShowInspector(this._wfSelectedNode);
                    }
                });

                svg.appendChild(path);
                svg.appendChild(hitbox);

                if (edge.label) {
                    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    text.setAttribute('x', (src.x + tgt.x) / 2);
                    text.setAttribute('y', (src.y + tgt.y) / 2 - 6);
                    text.setAttribute('class', 'wf-edge-label');
                    text.textContent = edge.label;
                    svg.appendChild(text);
                }
            });
        },

        _wfSelectNode(nodeId) {
            if (this._wfConnecting && this._wfConnecting !== nodeId) {
                const exists = this._wfEdges.some(e => e.source_id === this._wfConnecting && e.target_id === nodeId);
                if (!exists) {
                    this._wfEdges.push({ id: Date.now().toString(36), source_id: this._wfConnecting, target_id: nodeId, label: '' });
                    this._wfPushHistory();
                }
                document.querySelector('.wf-node-connecting')?.classList.remove('wf-node-connecting');
                this._wfConnecting = null;
                document.getElementById('wf-canvas').style.cursor = 'default';
                this._wfUpdateSvgEdges();
                showNotification('Verbindung erstellt', 'info');
                return;
            }

            this._wfSelectedNode = nodeId;
            document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
            document.getElementById(`wf-node-${nodeId}`)?.classList.add('wf-node-selected');
            this._wfShowInspector(nodeId);
        },

        async _wfShowInspector(nodeId) {
            const node = this._wfNodes.find(n => n.id === nodeId);
            if (!node) return;
            const inspector = document.getElementById('wf-node-inspector');
            const content = document.getElementById('wf-inspector-content');
            const deleteBtn = document.getElementById('wf-node-delete-btn');
            document.getElementById('wf-inspector-title').innerHTML = `${this._wfNodeIcon(node.type)} ${this._escapeHtml(node.label)}`;
            inspector.classList.remove('hidden');
            if (deleteBtn) deleteBtn.style.display = 'block';

            let html = `<div class="form-row"><label class="form-label">Label</label>
                <input type="text" class="form-input" value="${this._escapeHtml(node.label)}"
                    onchange="Ninko._wfUpdateNode('${nodeId}', 'label', this.value)">
            </div>`;

            for (const [k, v] of Object.entries(node.config)) {
                if (node.type === 'agent' && k === 'agent_id') {
                    html += `<div class="form-row"><label class="form-label">Agent</label>
                        <select id="wf-inspect-agent_id" class="form-select"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'agent_id', this.value)">
                            <option value="">– Laden… –</option>
                        </select>
                    </div>`;
                } else if (k === 'mode' && node.type === 'trigger') {
                    html += `<div class="form-row"><label class="form-label">Modus</label>
                        <select class="form-select" onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'mode', this.value); Ninko._wfShowInspector('${nodeId}')">
                            <option value="manual" ${v === 'manual' ? 'selected' : ''}>Manuell</option>
                            <option value="cron" ${v === 'cron' ? 'selected' : ''}>Zeitplan (Cron)</option>
                            <option value="webhook" ${v === 'webhook' ? 'selected' : ''}>Webhook</option>
                            <option value="event" ${v === 'event' ? 'selected' : ''}>Event</option>
                        </select>
                    </div>`;
                    if (v === 'cron') {
                        html += `<div class="form-row"><label class="form-label">Cron-Ausdruck</label>
                            <input type="text" class="form-input" value="${this._escapeHtml(String(node.config.cron ?? ''))}"
                                placeholder="0 8 * * *"
                                onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'cron', this.value)">
                            <small style="color:var(--text-muted)">Beim Speichern wird automatisch eine geplante Automatisierung angelegt</small>
                        </div>`;
                    }
                } else if (k === 'status' && node.type === 'end') {
                    html += `<div class="form-row"><label class="form-label">Status</label>
                        <select class="form-select" onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'status', this.value)">
                            <option value="succeeded" ${v === 'succeeded' ? 'selected' : ''}>Erfolgreich</option>
                            <option value="failed" ${v === 'failed' ? 'selected' : ''}>Fehlgeschlagen</option>
                        </select>
                    </div>`;
                } else if (k === 'mode' && node.type === 'loop') {
                    html += `<div class="form-row"><label class="form-label">Modus</label>
                        <select class="form-select" onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'mode', this.value)">
                            <option value="foreach" ${v === 'foreach' ? 'selected' : ''}>Foreach (Liste)</option>
                            <option value="while" ${v === 'while' ? 'selected' : ''}>While (Bedingung)</option>
                        </select>
                    </div>`;
                } else if (k === 'prompt' && (node.type === 'loop' || node.type === 'agent')) {
                    html += `<div class="form-row"><label class="form-label">Prompt</label>
                        <textarea class="form-input" rows="3" style="resize:vertical"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'prompt', this.value)">${this._escapeHtml(String(v ?? ''))}</textarea>
                    </div>`;
                } else if (k === 'prompts' && node.type === 'parallel') {
                    const promptsArr = Array.isArray(v) ? v : ['Task 1', 'Task 2'];
                    html += `<div class="form-row"><label class="form-label">Prompts (JSON Array)</label>
                        <textarea class="form-input" rows="4" style="resize:vertical;font-family:monospace"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'prompts', this.value)">${this._escapeHtml(JSON.stringify(promptsArr, null, 2))}</textarea>
                        <small style="color:var(--text-muted)">Array von Prompts für parallele Ausführung</small>
                    </div>`;
                } else if (k === 'workflow_id' && node.type === 'subflow') {
                    html += `<div class="form-row"><label class="form-label">Workflow</label>
                        <select id="wf-inspect-workflow_id" class="form-select"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'workflow_id', this.value)">
                            <option value="">– Laden… –</option>
                        </select>
                    </div>`;
                } else if (node.type === 'script' && k === 'script_id') {
                    html += `<div class="form-row"><label class="form-label">Script</label>
                        <select id="wf-inspect-script_id" class="form-select"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'script_id', this.value)">
                            <option value="">– Laden… –</option>
                        </select>
                    </div>`;
                } else if (node.type === 'script' && k === 'input_var') {
                    html += `<div class="form-row"><label class="form-label">Input Variable (optional)</label>
                        <input type="text" class="form-input" value="${this._escapeHtml(String(v ?? ''))}"
                            placeholder="Variablenname für Script-Input"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'input_var', this.value)">
                        <small style="color:var(--text-muted)">Variable wird als {script_input} verfügbar</small>
                    </div>`;
                } else if (node.type === 'script' && k === 'timeout') {
                    html += `<div class="form-row"><label class="form-label">Timeout (Sekunden)</label>
                        <input type="number" class="form-input" min="1" max="300" value="${this._escapeHtml(String(v ?? '30'))}"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', 'timeout', this.value)">
                        <small style="color:var(--text-muted)">1-300 Sekunden (Default: 30)</small>
                    </div>`;
                } else {
                    html += `<div class="form-row"><label class="form-label">${this._escapeHtml(k)}</label>
                        <input type="text" class="form-input" value="${this._escapeHtml(String(v ?? ''))}"
                            onchange="Ninko._wfUpdateNodeConfig('${nodeId}', '${k}', this.value)">
                    </div>`;
                }
            }

            const outEdges = this._wfEdges.filter(e => e.source_id === nodeId);
            const inEdges = this._wfEdges.filter(e => e.target_id === nodeId);
            if (outEdges.length || inEdges.length) {
                html += `<div class="form-row" style="margin-top:1rem;border-top:1px solid var(--border-color);padding-top:0.75rem">
                    <label class="form-label" style="font-weight:600">Verbindungen</label>`;
                inEdges.forEach(e => {
                    const src = this._wfNodes.find(n => n.id === e.source_id);
                    html += `<div style="font-size:0.8rem;display:flex;align-items:center;justify-content:space-between;margin-bottom:0.3rem">
                        <span>↩ ${this._escapeHtml(src?.label || e.source_id)}</span>
                        <button class="btn-icon btn-icon-sm" style="color:var(--error-color)" onclick="Ninko._wfDeleteEdge('${this._escapeHtml(e.id)}')" title="Entfernen">✕</button>
                    </div>`;
                });
                outEdges.forEach(e => {
                    const tgt = this._wfNodes.find(n => n.id === e.target_id);
                    html += `<div style="font-size:0.8rem;display:flex;align-items:center;justify-content:space-between;margin-bottom:0.3rem">
                        <span>↪ ${this._escapeHtml(tgt?.label || e.target_id)}</span>
                        <button class="btn-icon btn-icon-sm" style="color:var(--error-color)" onclick="Ninko._wfDeleteEdge('${this._escapeHtml(e.id)}')" title="Entfernen">✕</button>
                    </div>`;
                });
                html += `</div>`;
            }

            content.innerHTML = html;

            if (node.type === 'agent') {
                try {
                    const res = await fetch('/api/agents/');
                    const data = await res.json();
                    const sel = document.getElementById('wf-inspect-agent_id');
                    if (sel) {
                        sel.innerHTML = '<option value="">– Agenten wählen –</option>' +
                            (data.agents || []).map(a =>
                                `<option value="${this._escapeHtml(a.id)}" ${a.id === node.config.agent_id ? 'selected' : ''}>${this._escapeHtml(a.name)}</option>`
                            ).join('');
                        if (node.config.agent_id) sel.value = node.config.agent_id;
                    }
                } catch { }
            }

            if (node.type === 'subflow') {
                try {
                    const res = await fetch('/api/workflows/');
                    const data = await res.json();
                    const sel = document.getElementById('wf-inspect-workflow_id');
                    if (sel) {
                        sel.innerHTML = '<option value="">– Workflow wählen –</option>' +
                            (data.workflows || []).map(wf =>
                                `<option value="${this._escapeHtml(wf.id)}" ${wf.id === node.config.workflow_id ? 'selected' : ''}>${this._escapeHtml(wf.name)}</option>`
                            ).join('');
                        if (node.config.workflow_id) sel.value = node.config.workflow_id;
                    }
                } catch { }
            }

            if (node.type === 'script') {
                try {
                    const res = await fetch('/api/scripting/scripts');
                    const data = await res.json();
                    const sel = document.getElementById('wf-inspect-script_id');
                    if (sel) {
                        sel.innerHTML = '<option value="">– Script wählen –</option>' +
                            (data.scripts || []).map(s =>
                                `<option value="${this._escapeHtml(s.id)}" ${s.id === node.config.script_id ? 'selected' : ''}>${this._escapeHtml(s.name)}</option>`
                            ).join('');
                        if (node.config.script_id) sel.value = node.config.script_id;
                    }
                } catch { }
            }
        },

        _wfUpdateNode(nodeId, field, value) {
            const node = this._wfNodes.find(n => n.id === nodeId);
            if (node) {
                node[field] = value;
                this._wfRenderCanvas();
                this._wfPushHistory();
                if (field === 'label' && this._wfSelectedNode === nodeId) {
                    const titleEl = document.getElementById('wf-inspector-title');
                    if (titleEl) titleEl.innerHTML = `${this._wfNodeIcon(node.type)} ${this._escapeHtml(value)}`;
                }
            }
        },

        _wfUpdateNodeConfig(nodeId, key, value) {
            const node = this._wfNodes.find(n => n.id === nodeId);
            if (node) {
                if (node.type === 'parallel' && key === 'prompts') {
                    try { node.config[key] = JSON.parse(value); }
                    catch { node.config[key] = value; }
                } else {
                    node.config[key] = value;
                }
                this._wfPushHistory();
            }
        },

        _wfDeleteEdge(edgeId) {
            this._wfEdges = this._wfEdges.filter(e => e.id !== edgeId);
            this._wfUpdateSvgEdges();
            this._wfPushHistory();
            if (this._wfSelectedNode) this._wfShowInspector(this._wfSelectedNode);
        },

        wfCloseInspector() {
            document.getElementById('wf-node-inspector')?.classList.add('hidden');
            this._wfSelectedNode = null;
            document.querySelectorAll('.wf-node').forEach(n => n.classList.remove('wf-node-selected'));
        },

        async wfDeleteSelectedNode() {
            if (!this._wfSelectedNode) return;
            if (!await this.confirm('Möchtest du diesen Node wirklich löschen?')) return;

            this._wfNodes = this._wfNodes.filter(n => n.id !== this._wfSelectedNode);
            this._wfEdges = this._wfEdges.filter(e => e.source_id !== this._wfSelectedNode && e.target_id !== this._wfSelectedNode);
            this._wfSelectedNode = null;
            document.getElementById('wf-node-inspector')?.classList.add('hidden');
            this._wfRenderCanvas();
            this._wfPushHistory();
        },

        async saveWorkflow() {
            const name = document.getElementById('wf-name-input').value.trim();
            if (!name) { showNotification('Name ist Pflichtfeld', 'error'); return; }
            const saveBtn = document.querySelector('.wf-editor-toolbar .btn-primary');
            if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Speichern…'; }
            const wfId = document.getElementById('wf-edit-id').value;
            const description = document.getElementById('wf-desc-input')?.value.trim() || '';
            const body = { name, description, nodes: this._wfNodes, edges: this._wfEdges, variables: [], enabled: true };
            try {
                const url = wfId ? `/api/workflows/${wfId}` : '/api/workflows/';
                const method = wfId ? 'PUT' : 'POST';
                const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
                if (res.ok) { showNotification(`Workflow "${name}" gespeichert`, 'success'); this.closeWorkflowEditor(); }
                else showNotification('Fehler beim Speichern', 'error');
            } catch { showNotification('Verbindungsfehler', 'error'); }
            finally { if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Speichern'; } }
        },

        async deleteWorkflow(id, name) {
            const displayName = name || 'Workflow';
            if (!await this.confirm(`Workflow "${displayName}" wirklich unwiderruflich löschen?`)) return;
            try {
                const res = await fetch(`/api/workflows/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    showNotification(`Workflow "${displayName}" gelöscht`, 'info');
                    this.loadWorkflows();
                } else {
                    const err = await res.json().catch(() => ({}));
                    showNotification(`Fehler beim Löschen: ${err.detail || 'Unbekannter Fehler'}`, 'error');
                }
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async runWorkflow(id, name) {
            try {
                const res = await fetch(`/api/workflows/${id}/run`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    showNotification(`Workflow "${name}" gestartet`, 'success');
                    this.openRunDashboard(id, name, data.run_id);
                } else showNotification('Fehler beim Starten', 'error');
            } catch { showNotification('Verbindungsfehler', 'error'); }
        },

        async openRunHistory(wfId, name) {
            this._wfCurrentWorkflowId = wfId;
            this._wfCurrentRunId = null;
            this._wfRunNodes = [];
            this._wfRunEdges = [];
            document.getElementById('workflows-overview').classList.add('hidden');
            document.getElementById('workflow-run-dashboard').classList.remove('hidden');
            document.getElementById('run-dashboard-title').textContent = name;
            document.getElementById('run-dashboard-status').textContent = 'Historie';
            document.getElementById('run-dashboard-status').className = 'run-status-badge run-idle';
            document.getElementById('run-progress-fill').style.width = '0%';
            document.getElementById('run-progress-text').textContent = '';
            document.getElementById('wf-node-inspector')?.classList.add('hidden');
            try {
                const res = await fetch(`/api/workflows/${wfId}`);
                const wf = await res.json();
                this._wfRunNodes = wf.nodes || [];
                this._wfRunEdges = wf.edges || [];
                this._wfRunRenderCanvas([]);
                this._wfRunScrollToCentroid();
            } catch {}
            await this._loadRunHistory(wfId);
        },

        openRunDashboard(wfId, name, runId) {
            this._wfCurrentWorkflowId = wfId;
            this._wfCurrentRunId = runId;
            this._wfRunNodes = [];
            this._wfRunEdges = [];
            document.getElementById('workflows-overview').classList.add('hidden');
            document.getElementById('workflow-editor').classList.add('hidden');
            document.getElementById('workflow-run-dashboard').classList.remove('hidden');
            document.getElementById('run-dashboard-title').textContent = name;
            document.getElementById('run-dashboard-status').textContent = 'gestartet';
            document.getElementById('run-dashboard-status').className = 'run-status-badge run-running';
            document.getElementById('wf-node-inspector')?.classList.add('hidden');
            fetch(`/api/workflows/${wfId}`)
                .then(r => r.json())
                .then(wf => {
                    this._wfRunNodes = wf.nodes || [];
                    this._wfRunEdges = wf.edges || [];
                    this._wfRunRenderCanvas([]);
                    this._wfRunScrollToCentroid();
                }).catch(() => {});
            clearInterval(this._wfRunRefreshTimer);
            this._wfRunRefreshTimer = setInterval(() => this._refreshRunStatus(), 3000);
            this._refreshRunStatus();
        },

        closeRunDashboard() {
            clearInterval(this._wfRunRefreshTimer);
            document.getElementById('workflow-run-dashboard').classList.add('hidden');
            document.getElementById('workflows-overview').classList.remove('hidden');
            this.loadWorkflows();
        },

        async _refreshRunStatus() {
            if (!this._wfCurrentWorkflowId) return;
            await this._loadRunHistory(this._wfCurrentWorkflowId);
            const statusEl = document.getElementById('run-dashboard-status');
            if (statusEl && (statusEl.textContent === 'succeeded' || statusEl.textContent === 'failed')) {
                clearInterval(this._wfRunRefreshTimer);
            }
        },

        async _loadRunHistory(wfId) {
            try {
                const res = await fetch(`/api/workflows/${wfId}/runs`);
                if (!res.ok) throw new Error(res.statusText);
                const data = await res.json();
                const runs = data.runs || [];
                const historyEl = document.getElementById('run-history-list');
                if (historyEl) {
                    historyEl.innerHTML = runs.map(r => `
                        <div class="run-history-item" onclick="Ninko._showRunDetail('${this._escapeHtml(wfId)}', '${this._escapeHtml(r.id)}')">
                            <span class="run-status-badge run-${this._escapeHtml(r.status)}">${this._escapeHtml(r.status)}</span>
                            <span>${r.started_at ? new Date(r.started_at).toLocaleString('de') : '–'}</span>
                            <span>${r.duration_ms ? (r.duration_ms / 1000).toFixed(1) + 's' : '–'}</span>
                        </div>
                    `).join('') || '<p class="text-muted">Noch keine Runs.</p>';
                }
                if (this._wfCurrentRunId && runs.length) {
                    const activeRun = runs.find(r => r.id === this._wfCurrentRunId) || runs[0];
                    this._renderRunSteps(activeRun);
                }
            } catch { }
        },

        _wfRunRenderCanvas(steps = []) {
            const canvas = document.getElementById('wf-run-canvas');
            const svg = document.getElementById('wf-run-edges-svg');
            if (!canvas || !svg) return;
            const stepMap = {};
            steps.forEach((s, idx) => { stepMap[s.node_id] = { ...s, _stepIndex: idx }; });
            canvas.innerHTML = '';
            this._wfRunNodes.forEach(node => {
                const step = stepMap[node.id] || {};
                const status = step.status || 'pending';
                const el = document.createElement('div');
                el.className = `wf-node wf-node-${node.type} wf-run-node wf-run-node-${status}`;
                el.id = `wf-run-node-${node.id}`;
                el.style.left = `${node.position.x}px`;
                el.style.top = `${node.position.y}px`;
                const durHtml = step.duration_ms != null
                    ? `<span class="wf-run-node-dur">${step.duration_ms}ms</span>` : '';
                el.innerHTML = `
                    <div class="wf-node-header">
                        <span class="wf-node-icon">${this._wfNodeIcon(node.type)}</span>
                        <span class="wf-node-label">${this._escapeHtml(node.label)}</span>
                        <span class="wf-run-status-pip wf-run-pip-${status}"></span>
                    </div>
                    ${durHtml}
                `;
                if (step.status) {
                    el.style.cursor = 'pointer';
                    el.addEventListener('click', () => this._wfRunShowStepDetail(step, node, steps));
                }
                canvas.appendChild(el);
            });
            this._wfRunUpdateEdges();
        },

        _wfRunGetPortPos(nodeId, side) {
            const el = document.getElementById(`wf-run-node-${nodeId}`);
            const canvas = document.getElementById('wf-run-canvas');
            if (!el || !canvas) return null;
            const x = canvas.offsetLeft + el.offsetLeft + el.offsetWidth / 2;
            if (side === 'in') return { x, y: canvas.offsetTop + el.offsetTop };
            return { x, y: canvas.offsetTop + el.offsetTop + el.offsetHeight };
        },

        _wfRunUpdateEdges() {
            const svg = document.getElementById('wf-run-edges-svg');
            if (!svg) return;
            svg.innerHTML = `<defs>
                <marker id="wf-run-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
                    <path d="M0,0 L10,5 L0,10 Z" fill="#3b82f6" />
                </marker>
            </defs>`;
            this._wfRunEdges.forEach(edge => {
                const src = this._wfRunGetPortPos(edge.source_id, 'out');
                const tgt = this._wfRunGetPortPos(edge.target_id, 'in');
                if (!src || !tgt) return;
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', `M${src.x},${src.y} L${tgt.x},${tgt.y}`);
                path.setAttribute('stroke', '#3b82f6');
                path.setAttribute('stroke-width', '2.5');
                path.setAttribute('fill', 'none');
                path.setAttribute('marker-end', 'url(#wf-run-arrow)');
                path.style.pointerEvents = 'none';
                svg.appendChild(path);
            });
        },

        _wfRunScrollToCentroid() {
            setTimeout(() => {
                const container = document.getElementById('wf-run-canvas-container');
                if (!container || !this._wfRunNodes.length) return;
                const xs = this._wfRunNodes.map(n => n.position.x);
                const ys = this._wfRunNodes.map(n => n.position.y);
                const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
                const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
                container.scrollLeft = cx - container.clientWidth / 2 + 75;
                container.scrollTop  = cy - container.clientHeight / 2 + 40;
            }, 60);
        },

        _wfRunShowStepDetail(step, node, allSteps) {
            const inspector = document.getElementById('wf-run-inspector');
            const content = document.getElementById('wf-run-inspector-content');
            if (!inspector || !content) return;
            inspector.classList.remove('hidden');
            document.getElementById('wf-run-inspector-title').innerHTML =
                `${this._wfNodeIcon(node.type)} ${this._escapeHtml(node.label)}`;
            const outputHtml = step.output
                ? `<pre class="wf-run-output">${this._escapeHtml(step.output)}</pre>`
                : '<p style="font-size:0.85rem;color:var(--text-muted);margin:0;">Keine Ausgabe.</p>';
            const stepIndex = step._stepIndex !== undefined ? step._stepIndex : (allSteps ? allSteps.indexOf(step) : -1);
            const retryBtn = (step.status === 'failed' && this._wfCurrentRunId && stepIndex >= 0)
                ? `<div class="form-row"><button class="btn btn-sm btn-primary" onclick="Ninko._retryWorkflowStep(${stepIndex})">🔄 Step neu ausführen</button></div>`
                : '';
            content.innerHTML = `
                <div class="form-row">
                    <label class="form-label">Status</label>
                    <span class="run-status-badge run-${this._escapeHtml(step.status)}">${this._escapeHtml(step.status)}</span>
                </div>
                <div class="form-row">
                    <label class="form-label">Dauer</label>
                    <span style="font-size:0.85rem;">${step.duration_ms != null ? step.duration_ms + ' ms' : '–'}</span>
                </div>
                ${step.error ? `<div class="form-row"><label class="form-label" style="color:var(--error-color);">Fehler</label><div class="wf-run-error">${this._escapeHtml(step.error)}</div></div>` : ''}
                ${retryBtn}
                <div class="form-row" style="flex:1;display:flex;flex-direction:column;min-height:0;">
                    <label class="form-label">Ausgabe</label>
                    ${outputHtml}
                </div>
            `;
        },

        async _retryWorkflowStep(stepIndex) {
            if (!this._wfCurrentRunId) return;
            try {
                const res = await fetch(`/api/workflows/runs/${this._wfCurrentRunId}/steps/${stepIndex}/retry`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                showNotification('Step wird neu ausgeführt...', 'info');
                // Poll für Update
                setTimeout(() => this._refreshRunStatus(), 2000);
            } catch (e) {
                showNotification(`Retry fehlgeschlagen: ${e.message}`, 'error');
            }
        },

        _wfRunCloseInspector() {
            document.getElementById('wf-run-inspector')?.classList.add('hidden');
        },

        _showRunDetail(wfId, runId) {
            this._wfCurrentRunId = runId;
            this._loadRunHistory(wfId);
        },

        _renderRunSteps(run) {
            const statusEl = document.getElementById('run-dashboard-status');
            const progressFill = document.getElementById('run-progress-fill');
            const progressText = document.getElementById('run-progress-text');
            if (statusEl) {
                statusEl.textContent = run.status;
                statusEl.className = `run-status-badge run-${run.status}`;
            }
            const steps = run.steps || [];
            const done = steps.filter(s => ['succeeded', 'failed', 'skipped'].includes(s.status)).length;
            if (progressFill) progressFill.style.width = steps.length ? `${(done / steps.length) * 100}%` : '0%';
            if (progressText) progressText.textContent = steps.length ? `${done} / ${steps.length} Schritte` : '';
            this._wfRunRenderCanvas(steps);
        },

        _showRunStepDetail(step) {
            const inspector = document.getElementById('wf-node-inspector');
            const content = document.getElementById('wf-inspector-content');
            const deleteBtn = document.getElementById('wf-node-delete-btn');
            if (!inspector || !content) return;

            document.getElementById('wf-inspector-title').textContent = `Node: ${step.node_label || step.node_type}`;
            inspector.classList.remove('hidden');
            if (deleteBtn) deleteBtn.style.display = 'none';

            let outputHtml = step.output ? this._formatOutput(step.output) : '<p class="text-muted">Keine Ausgabe vorhanden.</p>';
            if (step.error) {
                outputHtml += `<div class="error-box" style="margin-top:1rem; color:var(--error-color);"><strong>Fehler:</strong><br>${this._escapeHtml(step.error)}</div>`;
            }

            const statusClass = this._escapeHtml(String(step.status || ''));
            const safeStatus = this._escapeHtml(step.status);
            const safeDuration = (typeof step.duration_ms === 'number' && Number.isFinite(step.duration_ms))
                ? step.duration_ms + 'ms' : '–';
            content.innerHTML = `
                <div class="setting-group">
                    <label class="form-label">Status</label>
                    <div class="run-status-badge run-${statusClass}">${safeStatus}</div>
                </div>
                <div class="setting-group">
                    <label class="form-label">Dauer</label>
                    <span>${safeDuration}</span>
                </div>
                <div class="setting-group" style="flex:1; display:flex; flex-direction:column; min-height:0;">
                    <label class="form-label">Ausgabe</label>
                    <div class="node-output-container" style="background:rgba(0,0,0,0.2); padding:1rem; border-radius:8px; font-family:monospace; font-size:0.9rem; white-space:pre-wrap; overflow-y:auto; flex:1;">${outputHtml}</div>
                </div>
            `;
        },

        async openWorkflowTemplateSelector() {
            const modal = document.getElementById('wf-template-modal');
            const list = document.getElementById('wf-template-list');
            modal.classList.remove('hidden');
            
            try {
                const res = await fetch('/api/workflows/templates');
                const data = await res.json();
                const templates = data.templates || [];
                
                if (!templates.length) {
                    list.innerHTML = '<p class="text-muted">Keine Templates verfügbar.</p>';
                    return;
                }
                
                list.innerHTML = templates.map(t => `
                    <div class="template-card" data-template-id="${this._escapeHtml(t.id)}" style="border:1px solid var(--border-color);border-radius:8px;padding:1rem;cursor:pointer;transition:all 0.2s;" onmouseover="this.style.borderColor='var(--accent-blue)'" onmouseout="this.style.borderColor='var(--border-color)'">
                        <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem;">
                            <span style="font-size:1.5rem;">${t.icon || '📋'}</span>
                            <div>
                                <h4 style="margin:0;font-size:1rem;">${this._escapeHtml(t.name)}</h4>
                                <span style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">${this._escapeHtml(t.category || 'basic')}</span>
                            </div>
                        </div>
                        <p style="margin:0;font-size:0.9rem;color:var(--text-muted);line-height:1.4;">${this._escapeHtml(t.description)}</p>
                        <div style="margin-top:0.75rem;display:flex;gap:0.5rem;flex-wrap:wrap;">
                            ${(t.tags || []).map(tag => `<span style="font-size:0.75rem;padding:0.2rem 0.5rem;background:var(--bg-secondary);border-radius:4px;">${this._escapeHtml(tag)}</span>`).join('')}
                        </div>
                    </div>
                `).join('');
                
                list.querySelectorAll('.template-card').forEach(card => {
                    card.addEventListener('click', () => {
                        const templateId = card.dataset.templateId;
                        this.instantiateWorkflowTemplate(templateId);
                    });
                });
            } catch (err) {
                list.innerHTML = `<p class="text-muted">Fehler beim Laden: ${this._escapeHtml(err.message)}</p>`;
            }
        },

        closeWorkflowTemplateSelector() {
            document.getElementById('wf-template-modal').classList.add('hidden');
        },

        async instantiateWorkflowTemplate(templateId) {
            try {
                const res = await fetch(`/api/workflows/templates/${templateId}/instantiate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();
                
                if (res.ok) {
                    this.closeWorkflowTemplateSelector();
                    this.loadWorkflows();
                    this.openWorkflowEditor(data.id);
                } else {
                    alert('Fehler: ' + (data.detail || 'Unbekannter Fehler'));
                }
            } catch (err) {
                alert('Fehler beim Erstellen: ' + err.message);
            }
        },

        _formatOutput(text) {
            if (!text) return '';
            return this.formatText(text);
        },
    };

    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, WorkflowsFeature);
    } else {
        window.WorkflowsFeature = WorkflowsFeature;
    }
})();
