import { Component, computed, input, output } from '@angular/core';
import type { StoreApp } from './contracts';
import { Icon } from './icon';

@Component({ selector: 'expert-app-card', imports: [Icon], template: `
  <article class="app-card" [class.selected]="selected()" [class.recommended]="recommended()">
    @if (recommended()) { <div class="recommendation-label"><expert-icon name="check" [size]="14" /> Documented match</div> }
    <div class="card-top"><span class="app-monogram">{{ initials() }}</span>
      <button type="button" class="select-app" [attr.aria-label]="'Select ' + app().name + ' for comparison'"
        [attr.aria-pressed]="selected()" [disabled]="disabled()" (click)="select.emit(app())">
        <expert-icon [name]="selected() ? 'check' : 'plus'" [size]="16" />
      </button>
    </div>
    <button type="button" class="card-name" [disabled]="disabled()" (click)="open.emit(app())">{{ app().name }} <expert-icon name="arrow" [size]="17" /></button>
    <p class="provider">{{ app().provider || 'Provider not listed' }}</p>
    @if (app().description) { <p class="card-description">{{ app().description }}</p> }
    <div class="card-bottom"><span><span class="tiny-dot"></span> Store application</span>
      <div class="card-actions">
      @if (app().source_evidence) { <button type="button" class="source-button" [attr.aria-label]="'View source for ' + app().name" title="View Store source" (click)="source.emit(app())"><expert-icon name="book" [size]="16" /></button> }
      <button type="button" class="text-button" [disabled]="disabled()" (click)="explain.emit(app())">Explain <expert-icon name="arrow" [size]="15" /></button></div>
    </div>
  </article>`, styleUrl: './app-card.css',
})
export class AppCard {
  readonly app = input.required<StoreApp>(); readonly selected = input(false); readonly disabled = input(false);
  readonly recommended = input(false);
  readonly source = output<StoreApp>(); readonly open = output<StoreApp>(); readonly explain = output<StoreApp>(); readonly select = output<StoreApp>();
  readonly initials = computed(() => this.app().name.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase());
}
