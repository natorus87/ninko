/**
 * Resumable AgentEvent SSE client and pure execution-tree reducer.
 */
(function registerAgentEventTimeline(globalScope) {
  'use strict';

  const TERMINAL_TYPES = new Set([
    'completed',
    'failed',
    'cancelled',
    'approval_required',
  ]);

  class AgentEventSseParser {
    constructor() {
      this.buffer = '';
      this.pendingCarriageReturn = false;
    }

    push(chunk) {
      let input = String(chunk || '');
      if (this.pendingCarriageReturn) {
        input = `\r${input}`;
        this.pendingCarriageReturn = false;
      }
      if (input.endsWith('\r')) {
        this.pendingCarriageReturn = true;
        input = input.slice(0, -1);
      }
      this.buffer += input.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      const blocks = this.buffer.split('\n\n');
      this.buffer = blocks.pop() || '';
      return blocks.map((block) => this.parseBlock(block)).filter(Boolean);
    }

    parseBlock(block) {
      let id = '';
      let event = 'message';
      const dataLines = [];
      for (const line of block.split('\n')) {
        if (!line || line.startsWith(':')) continue;
        const separator = line.indexOf(':');
        const field = separator === -1 ? line : line.slice(0, separator);
        let value = separator === -1 ? '' : line.slice(separator + 1);
        if (value.startsWith(' ')) value = value.slice(1);
        if (field === 'id' && !value.includes('\0')) id = value;
        if (field === 'event') event = value || 'message';
        if (field === 'data') dataLines.push(value);
      }
      if (!dataLines.length) return null;
      return { id, event, data: dataLines.join('\n') };
    }
  }

  class AgentExecutionTimelineModel {
    constructor({ maxNodes = 40 } = {}) {
      this.maxNodes = maxNodes;
      this.nodes = new Map();
      this.eventIds = new Set();
      this.order = 0;
    }

    apply(event) {
      if (!event || !event.event_id || !event.run_id || !event.type) return false;
      if (this.eventIds.has(event.event_id)) return false;
      this.eventIds.add(event.event_id);
      if (this.eventIds.size > 1000) {
        const oldest = this.eventIds.values().next().value;
        this.eventIds.delete(oldest);
      }

      const data = event.data && typeof event.data === 'object' ? event.data : {};
      const existing = this.nodes.get(event.run_id);
      const node = existing || {
        runId: event.run_id,
        parentRunId: event.parent_run_id || null,
        agentId: event.agent_id || 'agent',
        kind: this.kindFor(event),
        label: this.labelFor(event),
        state: 'running',
        order: this.order++,
        startedAt: event.timestamp || null,
        data: {},
      };

      node.parentRunId = event.parent_run_id || node.parentRunId;
      node.agentId = event.agent_id || node.agentId;
      node.kind = this.kindFor(event, node.kind);
      node.label = this.labelFor(event, node.label);
      node.state = this.stateFor(event);
      node.durationMs = data.duration_ms ?? node.durationMs ?? null;
      node.status = data.status || node.status || '';
      node.preview = data.error || data.preview || node.preview || '';
      node.data = { ...node.data, ...data };
      node.terminal = TERMINAL_TYPES.has(event.type) || event.type === 'tool_result';
      this.nodes.set(node.runId, node);

      while (this.nodes.size > this.maxNodes) {
        const oldest = [...this.nodes.values()].sort((a, b) => a.order - b.order)[0];
        this.nodes.delete(oldest.runId);
      }
      return true;
    }

    kindFor(event, fallback = 'agent') {
      if (event.type === 'tool_call' || event.type === 'tool_result') return 'tool';
      if (event.agent_id === 'pipeline') return 'pipeline';
      if (
        event.parent_run_id
        && String(event.run_id).startsWith(`${event.parent_run_id}:`)
      ) return 'step';
      return fallback;
    }

    labelFor(event, fallback = '') {
      const data = event.data && typeof event.data === 'object' ? event.data : {};
      if (data.tool_name) return String(data.tool_name);
      if (event.agent_id === 'pipeline') return 'Pipeline';
      return String(event.agent_id || fallback || 'Agent');
    }

    stateFor(event) {
      if (event.type === 'failed') return 'error';
      if (event.type === 'cancelled') return 'cancelled';
      if (event.type === 'approval_required') return 'waiting';
      if (event.type === 'tool_result') return event.data?.error ? 'error' : 'done';
      if (event.type === 'completed') return 'done';
      return 'running';
    }

    snapshot() {
      const depthFor = (node, visited = new Set()) => {
        if (!node.parentRunId || visited.has(node.runId)) return 0;
        const parent = this.nodes.get(node.parentRunId);
        if (!parent) return 1;
        visited.add(node.runId);
        return Math.min(4, 1 + depthFor(parent, visited));
      };
      return [...this.nodes.values()]
        .sort((a, b) => a.order - b.order)
        .map((node) => ({ ...node, depth: depthFor(node) }));
    }

    latestTerminalRoot() {
      return this.snapshot().reverse().find(
        (node) => node.depth === 0 && node.kind !== 'tool' && node.terminal,
      ) || null;
    }
  }

  class AgentEventStreamClient {
    constructor({
      sessionId,
      onEvent,
      onState = () => {},
      fetchImpl = globalScope.fetch?.bind(globalScope),
      retryDelays = [100, 250, 500, 1000, 1500],
      initialCursor = null,
    }) {
      this.sessionId = sessionId;
      this.onEvent = onEvent;
      this.onState = onState;
      this.fetchImpl = fetchImpl;
      this.retryDelays = retryDelays;
      this.cursor = initialCursor;
      this.controller = null;
      this.running = false;
    }

    stop() {
      this.running = false;
      this.controller?.abort();
      this.controller = null;
    }

    async start(externalSignal = null) {
      if (this.running || !this.fetchImpl || !this.sessionId) return;
      this.running = true;
      this.controller = new AbortController();
      const stopFromExternal = () => this.stop();
      if (externalSignal?.aborted) {
        this.stop();
        return;
      }
      externalSignal?.addEventListener('abort', stopFromExternal, { once: true });
      let retryIndex = 0;

      try {
        while (this.running && !this.controller.signal.aborted) {
          const query = new URLSearchParams({ session_id: this.sessionId });
          if (this.cursor) {
            query.set('after', this.cursor);
          } else {
            query.set('tail', 'true');
          }
          try {
            const response = await this.fetchImpl(
              `/api/agents/events/stream?${query}`,
              {
                headers: { Accept: 'text/event-stream' },
                signal: this.controller.signal,
              },
            );
            if (response.status === 204 || response.status === 410) return;
            if (response.status === 404) {
              if (retryIndex < this.retryDelays.length) {
                await this.wait(this.retryDelays[retryIndex++]);
                continue;
              }
              this.onState('unavailable');
              return;
            }
            if (
              response.status >= 400
              && response.status < 500
              && response.status !== 429
            ) {
              this.onState('unavailable');
              return;
            }
            if (!response.ok || !response.body) {
              throw new Error(`AgentEvent stream HTTP ${response.status}`);
            }
            const initialCursor = response.headers?.get?.('X-Agent-Event-Cursor');
            if (initialCursor) this.cursor = initialCursor;
            retryIndex = 0;
            this.onState('connected');
            await this.consume(response.body);
            if (this.running) await this.wait(200);
          } catch (error) {
            if (error?.name === 'AbortError' || !this.running) return;
            this.onState('reconnecting');
            const delay = this.retryDelays[
              Math.min(retryIndex++, this.retryDelays.length - 1)
            ] || 1000;
            await this.wait(delay);
          }
        }
      } finally {
        externalSignal?.removeEventListener('abort', stopFromExternal);
        this.running = false;
        this.onState('closed');
      }
    }

    async consume(body) {
      const reader = body.getReader();
      const decoder = new TextDecoder();
      const parser = new AgentEventSseParser();
      try {
        while (this.running) {
          const { done, value } = await reader.read();
          if (done) return;
          for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
            if (frame.id) this.cursor = frame.id;
            try {
              this.onEvent(JSON.parse(frame.data), frame);
            } catch {
              // Malformed application frames are skipped; the cursor still advances.
            }
          }
        }
      } finally {
        try {
          await reader.cancel();
        } catch {
          // Reader is already closed.
        }
      }
    }

    wait(milliseconds) {
      return new Promise((resolve, reject) => {
        const signal = this.controller.signal;
        const onAbort = () => {
          clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        };
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', onAbort);
          resolve();
        }, milliseconds);
        signal.addEventListener('abort', onAbort, { once: true });
      });
    }
  }

  globalScope.AgentEventSseParser = AgentEventSseParser;
  globalScope.AgentExecutionTimelineModel = AgentExecutionTimelineModel;
  globalScope.AgentEventStreamClient = AgentEventStreamClient;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      AgentEventSseParser,
      AgentExecutionTimelineModel,
      AgentEventStreamClient,
    };
  }
}(typeof window !== 'undefined' ? window : globalThis));
