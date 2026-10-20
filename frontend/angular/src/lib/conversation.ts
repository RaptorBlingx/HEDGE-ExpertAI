import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { ExpertApi } from './expert-api';
import { identity } from './contracts';
import type { AppResult, InspectAction, StoreApp } from './contracts';

export interface Message {
  id: number; role: 'user' | 'assistant'; text: string;
  elapsed?: number; path?: 'prepared' | 'assisted'; error?: string; stopped?: boolean;
  apps?: AppResult[]; recommended?: boolean;
}

/** One instance per assistant. Presentation switches share the same session. */
@Injectable()
export class Conversation {
  private api = inject(ExpertApi);
  readonly messages = signal<Message[]>([]);
  readonly apps = signal<AppResult[]>([]);
  readonly knownApps = signal<Record<string, StoreApp>>({});
  readonly busy = signal(false);
  readonly restoring = signal(false);
  readonly stage = signal('');
  readonly elapsed = signal(0);
  readonly error = signal('');
  readonly recommended = signal(false);
  readonly last = computed(() => this.messages().at(-1));
  private session: string | null = null;
  private controller?: AbortController;
  private timer?: ReturnType<typeof setInterval>;
  private serial = 0;
  private readonly requests = new Map<number, { text: string; action?: InspectAction }>();

  constructor() { inject(DestroyRef).onDestroy(() => { this.stop(); clearInterval(this.timer); }); }

  async restore(): Promise<void> {
    this.restoring.set(true);
    try {
      this.session = sessionStorage.getItem(this.api.config.sessionKey);
      if (this.session) {
        const history = await this.api.history(this.session);
        if (!history) this.save(null);
        else {
          this.messages.set(history.messages.filter(m => m.role === 'user' || m.role === 'assistant')
            .map(m => ({ id: ++this.serial, role: m.role as 'user' | 'assistant', text: m.content })));
          this.setApps(history.apps || []);
        }
      }
    } catch { this.error.set('Your conversation could not be restored. Try reloading before continuing, or start a new conversation.'); }
    finally { this.restoring.set(false); }
  }
  private save(id: string | null): void {
    this.session = id;
    try {
      if (id) sessionStorage.setItem(this.api.config.sessionKey, id);
      else sessionStorage.removeItem(this.api.config.sessionKey);
    } catch { /* in-memory sessions still work in storage-restricted hosts */ }
  }
  private setApps(rows: AppResult[]): void {
    this.apps.set(rows);
    this.knownApps.update(old => ({ ...old, ...Object.fromEntries(rows.map(r => [identity(r.app), r.app])) }));
  }
  async send(text: string, action?: InspectAction): Promise<void> {
    text = text.trim();
    if (!text || text.length > 2000 || this.busy() || this.restoring() || this.error()) return;
    const replyId = ++this.serial;
    this.requests.set(replyId, { text, action });
    this.messages.update(all => [...all, { id: ++this.serial, role: 'user', text }, { id: replyId, role: 'assistant', text: '' }]);
    this.apps.set([]);
    this.recommended.set(false);
    this.busy.set(true); this.stage.set('Finding the right information'); this.elapsed.set(0);
    const controller = new AbortController(); this.controller = controller;
    const started = performance.now();
    this.timer = setInterval(() => this.elapsed.set((performance.now() - started) / 1000), 200);
    const patch = (update: Partial<Message>) => this.messages.update(all => all.map(m => m.id === replyId ? { ...m, ...update } : m));
    let content = '';
    try {
      for await (const event of this.api.chat({ message: text, session_id: this.session, locale: 'en', filters: {}, ...(action ? { app_action: action } : {}) }, controller.signal)) {
        if (event.type === 'recommendations') this.setApps(event.apps || []);
        if (event.type === 'explanation_delta') { content += event.content || ''; patch({ text: content }); }
        if (event.type === 'stage') this.stage.set(event.stage === 'retrieval' ? 'Exploring the Store catalogue' : 'Preparing your answer');
        if (event.type === 'complete') {
          if (event.session_id) this.save(event.session_id);
          this.recommended.set(event.decision?.outcome === 'recommended');
          patch({ path: event.generation?.model_completed ? 'assisted' : 'prepared',
            apps: this.apps(), recommended: this.recommended() });
        }
      }
    } catch (error) {
      this.apps.set([]); this.recommended.set(false);
      patch(controller.signal.aborted ? { stopped: true } : { error: error instanceof Error ? error.message : 'Connection lost. Please try again.' });
    } finally {
      patch({ elapsed: (performance.now() - started) / 1000 });
      clearInterval(this.timer); this.busy.set(false); this.controller = undefined;
    }
  }
  inspect(app: StoreApp): Promise<void> {
    return this.send(`Tell me about ${app.name}`, { type: 'inspect', store_id: app.store_id, app_id: app.app_id });
  }
  retry(id: number): void { const request = this.requests.get(id); if (request) void this.send(request.text, request.action); }
  stop(): void { this.controller?.abort(); }
  async clear(): Promise<boolean> {
    if (this.busy()) return false;
    try {
      if (this.session) await this.api.clear(this.session);
      this.save(null); this.messages.set([]); this.apps.set([]); this.knownApps.set({}); this.error.set(''); this.recommended.set(false); this.requests.clear();
      return true;
    } catch { this.error.set('The conversation could not be cleared. Please try again.'); return false; }
  }
}
