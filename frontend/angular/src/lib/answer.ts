import { Component, computed, input, ViewEncapsulation } from '@angular/core';
import { Marked } from 'marked';

const markdown = new Marked({
  renderer: { html: ({ text }) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') },
});

/** Angular sanitizes the HTML binding. Never bypassSecurityTrustHtml for source/model text. */
@Component({ selector: 'expert-answer', encapsulation: ViewEncapsulation.None,
  template: '<div class="prose" [innerHTML]="html()"></div>',
  styles: `
    expert-answer { display: block; }
    expert-answer .prose { overflow-wrap: anywhere; font-size: inherit; line-height: inherit; }
    expert-answer .prose :first-child { margin-top: 0; } expert-answer .prose :last-child { margin-bottom: 0; }
    expert-answer .prose p { margin: 0 0 1em; }
    expert-answer .prose strong { color: var(--ea-ink); font-weight: 600; }
    expert-answer .prose ul, expert-answer .prose ol { padding-left: 1.4em; margin: .75em 0; } expert-answer .prose li { padding-left: .2em; margin: .4em 0; }
    expert-answer .prose a { color: var(--ea-accent); text-underline-offset: 3px; }
    expert-answer .prose code, expert-answer .prose pre { font-size: .9em; background: var(--ea-soft); border-radius: 4px; padding: 2px 4px; }
    expert-answer .prose pre { padding: 12px; overflow: auto; }
    expert-answer .prose blockquote { margin: 1em 0; border-left: 2px solid var(--ea-line-strong); padding-left: 15px; }
    expert-answer .prose h1, expert-answer .prose h2, expert-answer .prose h3, expert-answer .prose h4 { font: 600 1.08em var(--ea-heading); color: var(--ea-ink); margin: 1em 0 .6em; }
    expert-answer .prose table { border-collapse: collapse; width: 100%; } expert-answer .prose td, expert-answer .prose th { text-align: left; border: 1px solid var(--ea-line); padding: 8px; }
  `,
})
export class Answer {
  readonly text = input.required<string>();
  readonly html = computed(() => markdown.parse(this.text(), { async: false, breaks: true }));
}
