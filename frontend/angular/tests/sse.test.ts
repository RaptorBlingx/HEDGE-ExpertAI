import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SseDecoder } from '../src/lib/sse.ts';
import { identity, isStoreApp } from '../src/lib/contracts.ts';

test('SSE remains intact with every UTF-8 byte and CRLF boundary split', () => {
  const decoder = new SseDecoder();
  const stream = ': heartbeat\r\n\r\nid: 1\r\nevent: explanation_delta\r\ndata: {"type":"explanation_delta",\r\ndata: "content":"café — energy"}\r\n\r\ndata: {"type":"complete","session_id":"test"}\n\n';
  const events = [...new TextEncoder().encode(stream)].flatMap(byte => decoder.push(Uint8Array.of(byte)));
  events.push(...decoder.push());
  assert.deepEqual(events, [{ type: 'explanation_delta', content: 'café — energy' }, { type: 'complete', session_id: 'test' }]);
});
test('truncated and malformed events are errors, never successful demo replies', () => {
  const decoder = new SseDecoder();
  decoder.push(new TextEncoder().encode('data: {"type":"complete"}'));
  assert.throws(() => decoder.push(), /interrupted/);
  assert.throws(() => new SseDecoder().push(new TextEncoder().encode('data: invalid\n\n')), /unreadable/);
});
test('Store identity does not collapse equal names or ambiguous identifier separators', () => {
  const app = { id: 'internal', name: 'Same name', store_id: 'a/b', app_id: 'c' };
  assert.notEqual(identity(app), identity({ ...app, store_id: 'a', app_id: 'b/c' }));
  assert.equal(isStoreApp(app), true);
  assert.equal(isStoreApp({ name: 'Display only' }), false);
});
