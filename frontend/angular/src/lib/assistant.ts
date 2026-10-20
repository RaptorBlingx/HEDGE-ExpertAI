import { Component, computed, effect, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import { CdkTrapFocus } from '@angular/cdk/a11y';
import { Conversation } from './conversation';
import { ExpertApi } from './expert-api';
import { identity } from './contracts';
import type { StoreApp } from './contracts';
import { AppCard } from './app-card';
import { Icon } from './icon';
import { Answer } from './answer';

@Component({ selector: 'hedge-expert-assistant', imports: [Icon, AppCard, CdkTrapFocus, Answer], providers: [Conversation],
  templateUrl: './assistant.html', styleUrl: './assistant.css',
})
export class ExpertAssistant {
  readonly presentation = input<'workspace' | 'pane'>('workspace');
  readonly expand = output<void>(); readonly close = output<void>();
  readonly chat = inject(Conversation);
  private api = inject(ExpertApi);
  readonly catalogue = signal<StoreApp[]>([]);
  readonly total = signal<number | null>(null);
  readonly nextOffset = signal<number | null>(null);
  readonly loading = signal(true);
  readonly catalogueError = signal('');
  readonly source = signal('');
  readonly draft = signal('');
  readonly selected = signal<string[]>([]);
  readonly detail = signal<StoreApp | null>(null);
  readonly evidence = signal(false);
  readonly clearConfirm = signal(false);
  readonly mobileView = signal<'chat' | 'apps'>('chat');
  readonly copied = signal<number | null>(null);
  readonly copyError = signal('');
  private focusBefore?: HTMLElement;
  private followScroll = true;
  private readonly log = viewChild<ElementRef<HTMLElement>>('log');
  private readonly discovery = viewChild<ElementRef<HTMLElement>>('discovery');
  private readonly composer = viewChild<ElementRef<HTMLTextAreaElement>>('composer');
  readonly cards = computed(() => {
    const known = this.chat.knownApps();
    const current = this.chat.apps().map(result => result.app);
    const currentIds = new Set(current.map(identity));
    // Preserve the service's current result order, including results beyond the
    // loaded catalogue page. Remaining catalogue entries are browsing options.
    return [...current, ...this.catalogue().filter(app => !currentIds.has(identity(app)))]
      .map(app => known[identity(app)] || app);
  });
  readonly activeDetail = computed(() => {
    const app = this.detail(); return app ? this.chat.knownApps()[identity(app)] || app : null;
  });
  readonly resultNames = computed(() => this.chat.apps().map(r => r.app.name).join(', '));
  readonly selectedApps = computed(() => this.cards().filter(a => this.selected().includes(identity(a))));
  readonly suggestions = [
    { icon: 'search' as const, title: 'Explore the catalogue', action: 'browse' as const },
    { icon: 'spark' as const, title: 'Find an App for your needs', action: 'need' as const },
    { icon: 'compare' as const, title: 'Understand the differences', action: 'compare' as const },
  ];
  constructor() {
    void this.load(); void this.chat.restore();
    effect(() => {
      this.chat.messages(); this.chat.stage();
      if (this.followScroll) requestAnimationFrame(() => this.log()?.nativeElement.scrollTo({ top: this.log()!.nativeElement.scrollHeight }));
    });
  }
  async load(more = false): Promise<void> {
    this.loading.set(true); this.catalogueError.set('');
    try {
      const data = await this.api.catalogue(more ? this.nextOffset() || 0 : 0);
      this.catalogue.set(more ? [...this.catalogue(), ...data.apps] : data.apps);
      this.total.set(data.total); this.nextOffset.set(data.next_offset);
    } catch (error) { this.catalogueError.set(error instanceof Error ? error.message : 'The catalogue could not be loaded.'); }
    finally { this.loading.set(false); }
    if (!more) {
      try { this.source.set((await this.api.status()).catalogue); }
      catch { this.source.set('Source status unavailable'); }
    }
  }
  start(action: 'browse' | 'need' | 'compare'): void {
    if (action === 'browse') void this.send('List the Apps and explain what they do.');
    if (action === 'need') { if (!this.draft()) this.draft.set('I need an App to '); this.describeNeed(); }
    if (action === 'compare') {
      if (this.total() === 2 && this.cards().length === 2) { this.selected.set(this.cards().map(identity)); void this.compare(); }
      else this.showApps();
    }
  }
  async send(text = this.draft()): Promise<void> {
    if (!text.trim() || this.chat.busy() || this.chat.error()) return;
    this.draft.set(''); this.mobileView.set('chat'); this.followScroll = true;
    if (this.composer()) this.composer()!.nativeElement.style.height = 'auto';
    await this.chat.send(text); this.focusComposer();
  }
  async inspect(app: StoreApp, open = false): Promise<void> {
    if (this.chat.busy()) return;
    if (open) { this.captureFocus(); this.detail.set(app); this.evidence.set(false); }
    else this.mobileView.set('chat');
    this.followScroll = true;
    await this.chat.inspect(app);
    if (!open) this.focusComposer();
  }
  select(app: StoreApp): void {
    const key = identity(app);
    this.selected.update(all => all.includes(key) ? all.filter(k => k !== key) : all.length < 2 ? [...all, key] : [all[1], key]);
  }
  async compare(): Promise<void> {
    const apps = this.selectedApps();
    if (apps.length !== 2) return;
    await this.send(`Compare ${apps[0].name} and ${apps[1].name}.`);
  }
  showEvidence(): void { this.evidence.set(true); }
  showApps(): void {
    this.mobileView.set('apps');
    requestAnimationFrame(() => this.discovery()?.nativeElement.focus({ preventScroll: false }));
  }
  async clear(): Promise<void> {
    if (await this.chat.clear()) { this.selected.set([]); this.detail.set(null); this.draft.set(''); this.mobileView.set('chat'); }
    this.clearConfirm.set(false); this.restoreFocus();
  }
  openClear(): void { this.captureFocus(); this.clearConfirm.set(true); }
  closeDialog(): void { this.detail.set(null); this.clearConfirm.set(false); this.restoreFocus(); }
  private captureFocus(): void { this.focusBefore = document.activeElement as HTMLElement; }
  private restoreFocus(): void { requestAnimationFrame(() => this.focusBefore?.isConnected ? this.focusBefore.focus() : this.focusComposer()); }
  private focusComposer(): void { if (!this.detail()) this.composer()?.nativeElement.focus({ preventScroll: true }); }
  describeNeed(): void { this.mobileView.set('chat'); requestAnimationFrame(() => this.focusComposer()); }
  keydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); void this.send(); }
  }
  input(event: Event): void {
    const field = event.target as HTMLTextAreaElement;
    this.draft.set(field.value); field.style.height = 'auto'; field.style.height = `${Math.min(field.scrollHeight, 132)}px`;
  }
  scroll(event: Event): void { const el = event.target as HTMLElement; this.followScroll = el.scrollHeight - el.scrollTop - el.clientHeight < 90; }
  entries(app: StoreApp): [string, string][] { return Object.entries(app.source_evidence || {}); }
  id(app: StoreApp): string { return identity(app); }
  recommended(app: StoreApp): boolean { return this.chat.recommended() && this.chat.apps().some(r => identity(r.app) === identity(app) && r.suitability?.status === 'source_supported'); }
  seconds(value: number | undefined): string { return (value || 0).toFixed(1); }
  async copy(id: number, text: string): Promise<void> {
    try { await navigator.clipboard.writeText(text); this.copied.set(id); this.copyError.set(''); }
    catch { this.copyError.set('Copy is unavailable in this browser. You can select and copy the answer.'); }
  }
}
