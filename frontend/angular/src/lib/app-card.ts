import { Component, computed, input, output } from '@angular/core';
import type { StoreApp } from './contracts';
import { Icon } from './icon';

@Component({ selector: 'expert-app-card', imports: [Icon], template: `
  <article class="app-card" [class.selected]="selected()">
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
      <button type="button" class="text-button" [disabled]="disabled()" (click)="explain.emit(app())">Explain <expert-icon name="arrow" [size]="15" /></button>
    </div>
    @if (recommended()) { <div class="recommendation-label"><expert-icon name="check" [size]="13" /> Documented match for this request</div> }
  </article>`, styleUrl: './app-card.css',
})
export class AppCard {
  readonly app = input.required<StoreApp>(); readonly selected = input(false); readonly disabled = input(false);
  readonly recommended = input(false);
  readonly open = output<StoreApp>(); readonly explain = output<StoreApp>(); readonly select = output<StoreApp>();
  readonly initials = computed(() => this.app().name.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase());
}
