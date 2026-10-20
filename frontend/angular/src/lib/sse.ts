/** Incremental SSE: handles UTF-8, CRLF, multi-line data and split boundaries. */
export class SseDecoder {
  private buffer = '';
  private decoder = new TextDecoder();
  push(chunk?: Uint8Array): unknown[] {
    this.buffer += this.decoder.decode(chunk, { stream: chunk !== undefined });
    const events: unknown[] = [];
    let match: RegExpExecArray | null;
    while ((match = /\r?\n\r?\n/.exec(this.buffer))) {
      const frame = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + match[0].length);
      const data = frame.split(/\r?\n/).filter(l => l.startsWith('data:'))
        .map(l => l.slice(5).replace(/^ /, '')).join('\n');
      if (data) {
        try { events.push(JSON.parse(data)); }
        catch { throw new Error('The assistant returned an unreadable response. Please try again.'); }
      }
    }
    if (chunk === undefined && this.buffer.trim()) throw new Error('The response was interrupted. Please try again.');
    return events;
  }
}
