'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  AgentEventSseParser,
  AgentExecutionTimelineModel,
  AgentEventStreamClient,
} = require('../core/agent_event_timeline.js');

function event(type, runId, parentRunId = null, extra = {}) {
  return {
    event_id: `${type}-${runId}`,
    type,
    timestamp: '2026-07-29T18:00:00Z',
    tenant_id: 'default',
    session_id: 'default:session-1',
    run_id: runId,
    parent_run_id: parentRunId,
    agent_id: extra.agent_id || 'kubernetes',
    data: extra.data || {},
  };
}

test('SSE parser preserves partial frames and multiline data', () => {
  const parser = new AgentEventSseParser();

  assert.deepEqual(parser.push('id: 1-0\nevent: started\ndata: {"type":'), []);
  assert.deepEqual(parser.push('"started"}\n\n: keepalive\n\n'), [
    {
      id: '1-0',
      event: 'started',
      data: '{"type":"started"}',
    },
  ]);
});

test('SSE parser normalizes CRLF split across chunks without corrupting cursor', () => {
  const parser = new AgentEventSseParser();

  assert.deepEqual(parser.push('id: 1-0\r'), []);
  assert.deepEqual(parser.push('\nevent: started\r\ndata: {"type":"started"}\r\n\r\n'), [
    {
      id: '1-0',
      event: 'started',
      data: '{"type":"started"}',
    },
  ]);
});

test('timeline builds pipeline, step and tool hierarchy', () => {
  const model = new AgentExecutionTimelineModel();
  model.apply(event('started', 'pipeline', null, { agent_id: 'pipeline' }));
  model.apply(event('started', 'pipeline:step-1', 'pipeline'));
  model.apply(event('tool_call', 'tool-1', 'pipeline:step-1', {
    data: { tool_name: 'list_pods' },
  }));
  model.apply({
    ...event('tool_result', 'tool-1', 'pipeline:step-1', {
      data: { tool_name: 'list_pods', duration_ms: 42 },
    }),
    event_id: 'tool-result-1',
  });

  const nodes = model.snapshot();
  assert.deepEqual(nodes.map((node) => node.kind), ['pipeline', 'step', 'tool']);
  assert.deepEqual(nodes.map((node) => node.depth), [0, 1, 2]);
  assert.equal(nodes[2].state, 'done');
  assert.equal(nodes[2].durationMs, 42);
});

test('timeline deduplicates replayed event IDs', () => {
  const model = new AgentExecutionTimelineModel();
  const started = event('started', 'run-1');

  assert.equal(model.apply(started), true);
  assert.equal(model.apply(started), false);
  assert.equal(model.snapshot().length, 1);
});

test('standalone tool result does not complete the overall execution', () => {
  const model = new AgentExecutionTimelineModel();
  model.apply(event('tool_call', 'tool-1', null, {
    data: { tool_name: 'list_pods' },
  }));
  model.apply({
    ...event('tool_result', 'tool-1', null, {
      data: { tool_name: 'list_pods', duration_ms: 42 },
    }),
    event_id: 'tool-result-standalone',
  });

  assert.equal(model.snapshot()[0].state, 'done');
  assert.equal(model.latestTerminalRoot(), null);
});

test('stream retries an owner race and sends cursor on reconnect', async () => {
  const requests = [];
  const fetchImpl = async (url) => {
    requests.push(url);
    if (requests.length === 1) {
      return { status: 404, ok: false, body: null };
    }
    return { status: 204, ok: true, body: null };
  };
  const client = new AgentEventStreamClient({
    sessionId: 'session-1',
    initialCursor: '7-0',
    fetchImpl,
    retryDelays: [0],
    onEvent: () => {},
  });

  await client.start();

  assert.equal(requests.length, 2);
  assert.match(requests[0], /session_id=session-1/);
  assert.match(requests[0], /after=7-0/);
});

test('stream starts at server tail and reconnects after delivered cursor', async () => {
  const requests = [];
  const delivered = [];
  const encoder = new TextEncoder();
  let readCount = 0;
  const body = {
    getReader() {
      return {
        async read() {
          if (readCount++ === 0) {
            return {
              done: false,
              value: encoder.encode(
                'id: 12-0\nevent: started\ndata: {"event_id":"evt-1","run_id":"run-1","type":"started"}\n\n',
              ),
            };
          }
          return { done: true, value: undefined };
        },
        async cancel() {},
      };
    },
  };
  const fetchImpl = async (url) => {
    requests.push(url);
    if (requests.length === 1) {
      return {
        status: 200,
        ok: true,
        headers: { get: () => '11-0' },
        body,
      };
    }
    return { status: 204, ok: true, headers: { get: () => null }, body: null };
  };
  const client = new AgentEventStreamClient({
    sessionId: 'session-1',
    fetchImpl,
    retryDelays: [0],
    onEvent: (event) => delivered.push(event),
  });

  await client.start();

  assert.match(requests[0], /tail=true/);
  assert.match(requests[1], /after=12-0/);
  assert.deepEqual(delivered.map((item) => item.event_id), ['evt-1']);
});

test('owner retry keeps tail mode until the server establishes a baseline', async () => {
  const requests = [];
  const encoder = new TextEncoder();
  let readCount = 0;
  const body = {
    getReader() {
      return {
        async read() {
          if (readCount++ === 0) {
            return {
              done: false,
              value: encoder.encode(
                'id: 4-0\nevent: started\ndata: {"event_id":"evt-4","run_id":"run-1","type":"started"}\n\n',
              ),
            };
          }
          return { done: true, value: undefined };
        },
        async cancel() {},
      };
    },
  };
  const fetchImpl = async (url) => {
    requests.push(url);
    if (requests.length === 1) {
      return { status: 404, ok: false, headers: { get: () => null }, body: null };
    }
    if (requests.length === 2) {
      return {
        status: 200,
        ok: true,
        headers: { get: () => '3-0' },
        body,
      };
    }
    return { status: 204, ok: true, headers: { get: () => null }, body: null };
  };
  const client = new AgentEventStreamClient({
    sessionId: 'session-1',
    fetchImpl,
    retryDelays: [0],
    onEvent: () => {},
  });

  await client.start();

  assert.match(requests[0], /tail=true/);
  assert.match(requests[1], /tail=true/);
  assert.match(requests[2], /after=4-0/);
});

test('stream does not retry permanent HTTP errors', async () => {
  let requests = 0;
  const states = [];
  const client = new AgentEventStreamClient({
    sessionId: 'session-1',
    fetchImpl: async () => {
      requests += 1;
      return { status: 403, ok: false, headers: { get: () => null }, body: null };
    },
    onEvent: () => {},
    onState: (state) => states.push(state),
  });

  await client.start();

  assert.equal(requests, 1);
  assert.deepEqual(states, ['unavailable', 'closed']);
});

test('already aborted request signal prevents opening a stream', async () => {
  const external = new AbortController();
  external.abort();
  let requests = 0;
  const client = new AgentEventStreamClient({
    sessionId: 'session-1',
    fetchImpl: async () => {
      requests += 1;
      return { status: 204, ok: true, headers: { get: () => null }, body: null };
    },
    onEvent: () => {},
  });

  await client.start(external.signal);

  assert.equal(requests, 0);
});
