'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function loadApp({ documentOverrides = {}, fetchImpl = async () => ({ ok: false }) } = {}) {
  const storage = {
    getItem: () => null,
    setItem() {},
    removeItem() {},
  };
  const document = {
    readyState: 'loading',
    addEventListener() {},
    querySelectorAll: () => [],
    getElementById: () => null,
    querySelector: () => null,
    createElement: () => ({}),
    documentElement: { setAttribute() {}, style: {} },
    body: { classList: { add() {}, remove() {}, toggle() {} }, dataset: {} },
    ...documentOverrides,
  };
  const context = {
    console,
    document,
    localStorage: storage,
    sessionStorage: storage,
    fetch: fetchImpl,
    AbortController,
    URLSearchParams,
    TextDecoder,
    TextEncoder,
    DOMException,
    setTimeout,
    clearTimeout,
    EventSource: function EventSource() {
      this.close = () => {};
    },
    navigator: { language: 'de' },
    location: {},
    history: {},
    confirm: () => true,
    alert() {},
  };
  context.window = context;
  context.globalThis = context;
  context.window.addEventListener = () => {};
  context.window.matchMedia = () => ({ matches: false, addEventListener() {} });
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf8'),
    context,
  );
  return context;
}

test('sendMessage keeps its request controller across timeline handshake cancellation', async () => {
  const input = { value: 'hello' };
  const errors = [];
  let releaseHandshake;
  let fetchCalls = 0;
  const context = loadApp({
    documentOverrides: {
      getElementById: (id) => (id === 'chat-input' ? input : null),
    },
    fetchImpl: async (_url, options) => {
      fetchCalls += 1;
      if (options.signal.aborted) throw new DOMException('Aborted', 'AbortError');
      return { ok: false };
    },
  });
  const { Ninko } = context.window;
  Object.assign(Ninko, {
    currentHistoryId: 'history-1',
    sessionId: 'default:session-1',
    addChatMessage: (role, text) => {
      if (role === 'ai') errors.push(text);
    },
    showTyping() {},
    hideTyping() {},
    _setChatBusy() {},
    _ensureHistoryEntry() {},
    _stopAgentEventTimeline() {},
    _startAgentEventTimeline: () => new Promise((resolve) => {
      releaseHandshake = resolve;
    }),
  });

  const sending = Ninko.sendMessage();
  await Promise.resolve();
  Ninko._abortController.abort();
  Ninko._abortController = null;
  releaseHandshake(false);
  await sending;

  assert.equal(fetchCalls, 1);
  assert.deepEqual(errors, []);
});

test('timeline auto-opens only on first reveal and announces the latest event', () => {
  const shell = { hidden: true };
  const wrapper = { open: false };
  const announcer = { textContent: '' };
  const status = { dataset: {}, textContent: '' };
  const nodes = {
    replaceChildren() {},
    appendChild() {},
  };
  const chat = {
    scrollHeight: 100,
    scrollTop: 0,
    clientHeight: 100,
  };
  const context = loadApp({
    documentOverrides: {
      getElementById(id) {
        return {
          'execution-timeline': shell,
          'execution-timeline-nodes': nodes,
          'execution-timeline-announcer': announcer,
          'execution-timeline-status': status,
          'chat-messages': chat,
        }[id] || null;
      },
      querySelector: () => wrapper,
      createElement: () => ({
        className: '',
        style: { setProperty() {} },
        dataset: {},
        setAttribute() {},
        append() {},
      }),
    },
  });
  const { Ninko } = context.window;
  const node = {
    runId: 'run-1',
    kind: 'agent',
    state: 'running',
    depth: 0,
    label: 'Kubernetes',
  };
  Ninko._executionTimeline = {
    apply: () => true,
    snapshot: () => [node],
    latestTerminalRoot: () => null,
  };

  Ninko._handleAgentExecutionEvent({ run_id: 'run-1' });
  assert.equal(wrapper.open, true);
  assert.equal(announcer.textContent, 'Kubernetes: läuft');

  wrapper.open = false;
  Ninko._handleAgentExecutionEvent({ run_id: 'run-1' });
  assert.equal(wrapper.open, false);
});
