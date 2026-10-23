import { Component, signal, viewChild } from '@angular/core';
import { ExpertAssistant } from '../lib/assistant';
import { Icon } from '../lib/icon';

@Component({ selector: 'expert-demo', imports: [ExpertAssistant, Icon], templateUrl: './app.html', styleUrl: './app.css' })
export class DemoApp {
  readonly mode = signal<'workspace' | 'pane'>(new URLSearchParams(location.search).get('view') === 'pane' ? 'pane' : 'workspace');
  readonly paneOpen = signal(true);
  readonly about = signal(false);
  readonly dark = signal(false);
  readonly assistant = viewChild(ExpertAssistant);
  constructor() {
    try { this.dark.set(localStorage.getItem('expertai-theme') === 'dark' || (!localStorage.getItem('expertai-theme') && matchMedia('(prefers-color-scheme: dark)').matches)); } catch { /* system defaults */ }
  }
  switchMode(mode: 'workspace' | 'pane'): void { this.mode.set(mode); this.paneOpen.set(true); this.about.set(false); history.replaceState(null, '', mode === 'pane' ? '?view=pane' : location.pathname); }
  theme(): void { this.dark.update(v => !v); try { localStorage.setItem('expertai-theme', this.dark() ? 'dark' : 'light'); } catch { /* optional preference */ } }
}
