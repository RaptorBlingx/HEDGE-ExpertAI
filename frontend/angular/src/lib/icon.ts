import { Component, input } from '@angular/core';
import { LucideDynamicIcon, LucideArrowUp, LucideArrowRight, LucidePlus,
  LucideX, LucideMoon, LucideSun, LucidePanelRight, LucideMaximize2, LucideLayers,
  LucideMessageCircle, LucideCheck, LucideBookOpen, LucideGitCompareArrows,
  LucideSparkles, LucideShieldCheck, LucideRotateCcw, LucideSquare, LucideCopy, LucideSearch,
  LucideCircleHelp } from '@lucide/angular';

const icons = { up: LucideArrowUp, arrow: LucideArrowRight,
  plus: LucidePlus, close: LucideX, moon: LucideMoon, sun: LucideSun, panel: LucidePanelRight,
  expand: LucideMaximize2, layers: LucideLayers, chat: LucideMessageCircle, check: LucideCheck,
  book: LucideBookOpen, compare: LucideGitCompareArrows, spark: LucideSparkles,
  shield: LucideShieldCheck, retry: LucideRotateCcw, stop: LucideSquare, copy: LucideCopy,
  search: LucideSearch, help: LucideCircleHelp };
export type IconName = keyof typeof icons;
@Component({ selector: 'expert-icon', imports: [LucideDynamicIcon],
  template: '<svg [lucideIcon]="icons[name()]" [size]="size()" [strokeWidth]="1.7" aria-hidden="true"></svg>',
  styles: ':host { display: inline-flex; flex: 0 0 auto; vertical-align: middle; }',
})
export class Icon { readonly name = input.required<IconName>(); readonly size = input(18); readonly icons = icons; }
