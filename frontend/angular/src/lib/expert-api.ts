import { inject, Injectable, InjectionToken } from '@angular/core';
import { isStoreApp } from './contracts';
import type { Catalogue, ChatRequest, ExpertConfig, History, ServiceStatus, StreamEvent } from './contracts';
import { SseDecoder } from './sse';

export const EXPERT_CONFIG = new InjectionToken<ExpertConfig>('EXPERT_CONFIG', {
  factory: () => ({ apiBase: '', sessionKey: 'hedge-expertai-angular-session' }),
});

@Injectable({ providedIn: 'root' })
export class ExpertApi {
  readonly config = inject(EXPERT_CONFIG);
  private async request(path: string, init: RequestInit = {}): Promise<Response> {
    const token = await this.config.getAccessToken?.();
    const headers = new Headers(init.headers);
    headers.set('Content-Type', 'application/json');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(this.config.apiBase.replace(/\/$/, '') + path, { ...init, headers });
    if (!response.ok) {
      if (response.status === 401) throw new Error('Your Store session has expired. Sign in again and retry.');
      if (response.status === 403) throw new Error('Access to this request was denied. Check your Store access or contact the preview owner.');
      if (response.status === 429) throw new Error('A few too many requests. Wait a moment, then try again.');
      throw new Error(`The service could not complete this request (${response.status}). Please try again.`);
    }
    return response;
  }
  async catalogue(offset = 0): Promise<Catalogue> {
    const data: Catalogue = await (await this.request(`/api/v2/catalogue?offset=${offset}&limit=25`)).json();
    if (!Array.isArray(data.apps) || !data.apps.every(isStoreApp)) throw new Error('The Store returned an unreadable catalogue.');
    return data;
  }
  async status(): Promise<ServiceStatus> { return (await this.request('/api/v2/status')).json(); }
  async history(id: string): Promise<History | null> {
    try { return await (await this.request(`/api/v2/sessions/${encodeURIComponent(id)}`)).json(); }
    catch (error) {
      if (error instanceof Error && error.message.includes('(404)')) return null;
      throw error;
    }
  }
  async clear(id: string): Promise<void> { await this.request(`/api/v2/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
  async *chat(body: ChatRequest, signal: AbortSignal): AsyncGenerator<StreamEvent> {
    const response = await this.request('/api/v2/chat/stream', { method: 'POST', body: JSON.stringify(body), signal });
    if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('The assistant did not return a conversation stream.');
    const reader = response.body.getReader();
    const decoder = new SseDecoder();
    let complete = false;
    try {
      while (true) {
        const { value, done } = await reader.read();
        for (const raw of decoder.push(done ? undefined : value)) {
          if (!raw || typeof raw !== 'object' || !('type' in raw)) throw new Error('The assistant returned an unreadable event.');
          const event = raw as StreamEvent;
          if (event.type === 'problem') throw new Error(event.detail || event.title || 'The assistant could not complete this request.');
          if (event.type === 'recommendations' && (!Array.isArray(event.apps) || !event.apps.every(r => isStoreApp(r.app)))) throw new Error('The assistant returned unreadable App results.');
          if (event.type === 'complete') complete = true;
          yield event;
        }
        if (done) break;
      }
      if (!complete) throw new Error('The response was interrupted. Please try again.');
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  }
}
