/**
 * HEDGE-ExpertAI Chat Widget v2.0
 * Embeddable, self-contained chat widget for the HEDGE-IoT App Store.
 * Zero external dependencies — vanilla JS only.
 */
(function () {
  "use strict";

  // Capture script src at load time (null inside DOMContentLoaded callbacks)
  var _scriptSrc = (document.currentScript && document.currentScript.src) || "";

  /* ------------------------------------------------------------------ */
  /*  Constants                                                          */
  /* ------------------------------------------------------------------ */

  const DEFAULTS = {
    apiUrl: "",
    position: "bottom-right",
    title: "HEDGE-ExpertAI",
    subtitle: "IoT App Discovery Assistant",
    primaryColor: "#0ea5e9",
    width: "400px",
    height: "580px",
  };

  const SUGGESTIONS = [
    "Find apps for energy monitoring",
    "Show me smart irrigation solutions",
    "Recommend building comfort apps",
  ];

  const THINKING_STEPS = {
    search: [
      "Interpreting your request and extracting domain intent…",
      "Scanning indexed applications across semantic and keyword signals…",
      "Prioritizing strongest matches based on metadata relevance…",
      "Drafting a concise, evidence-based recommendation…",
    ],
    detail: [
      "Resolving the referenced app and loading full metadata…",
      "Cross-checking domain, tags, and dataset signals…",
      "Building a focused explanation around your request…",
    ],
    help: [
      "Detecting assistance intent and preparing guidance…",
      "Selecting the most useful interaction examples…",
      "Formatting quick-start instructions…",
    ],
    greeting: [
      "Detecting conversational greeting intent…",
      "Preparing a compact onboarding response…",
      "Finalizing a friendly welcome message…",
    ],
    unknown: [
      "Clarifying ambiguous intent from your prompt…",
      "Applying fallback retrieval strategy on catalog metadata…",
      "Preparing the most likely helpful response…",
    ],
  };

  const DOMAIN_COLORS = {
    energy:      { bg: "#0c4a6e", fg: "#7dd3fc", bar: "#0ea5e9" },
    building:    { bg: "#14532d", fg: "#86efac", bar: "#22c55e" },
    environment: { bg: "#7c2d12", fg: "#fdba74", bar: "#f97316" },
    agriculture: { bg: "#14532d", fg: "#86efac", bar: "#22c55e" },
    water:       { bg: "#164e63", fg: "#67e8f9", bar: "#06b6d4" },
    transport:   { bg: "#581c87", fg: "#d8b4fe", bar: "#a855f7" },
    industrial:  { bg: "#78350f", fg: "#fcd34d", bar: "#f59e0b" },
    health:      { bg: "#881337", fg: "#fda4af", bar: "#f43f5e" },
    default:     { bg: "#1e293b", fg: "#94a3b8", bar: "#64748b" },
  };

  const ICON_BOT =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>';

  const ICON_USER =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';

  const ICON_COPY =
    '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';

  const ICON_CLEAR =
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>';

  const ICON_SEND =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';

  /* ------------------------------------------------------------------ */
  /*  Utility functions                                                  */
  /* ------------------------------------------------------------------ */

  function inferIntent(message) {
    var t = (message || "").trim().toLowerCase();
    if (!t) return "unknown";
    if (/^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening))[\s!.,?]*$/.test(t)) return "greeting";
    if (/\b(help|how\s+do\s+i|what\s+can\s+you\s+do|usage|guide|instructions)\b/.test(t)) return "help";
    if (/\b(tell\s+me\s+(more\s+)?about|details?\s+(of|about|for)|explain|describe|app[-\s]?\d{3})\b/.test(t)) return "detail";
    if (/\b(find|search|looking\s+for|show\s+me|recommend|suggest|discover|monitor|manage|detect|optimi[sz]e)\b/.test(t)) return "search";
    return "unknown";
  }

  function formatDuration(ms) {
    return (ms / 1000).toFixed(1) + "s";
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function domainColor(domainRaw) {
    var d = (domainRaw || "").toLowerCase().replace(/^saref4/, "");
    return DOMAIN_COLORS[d] || DOMAIN_COLORS.default;
  }

  /** Lightweight markdown → HTML (no external library). */
  function renderMarkdown(raw) {
    var html = escapeHtml(raw);

    // Code blocks ``` … ```
    html = html.replace(/```([\s\S]*?)```/g, '<pre class="he-code-block">$1</pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code class="he-code-inline">$1</code>');
    // Headings (### … )
    html = html.replace(/^#{3,}\s+(.+)$/gm, '<strong class="he-heading">$1</strong>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Italic
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    // Blockquotes
    html = html.replace(/^&gt;\s?(.+)$/gm, '<div class="he-blockquote">$1</div>');
    // Links — sanitise href (only http/https)
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="he-link">$1</a>');
    // Unordered lists (lines starting with "- ")
    html = html.replace(/(?:^|\n)((?:- .+(?:\n|$))+)/g, function (_, block) {
      var items = block.trim().split("\n").map(function (l) {
        return "<li>" + l.replace(/^- /, "") + "</li>";
      }).join("");
      return '<ul class="he-list">' + items + "</ul>";
    });
    // Ordered lists (lines starting with "1. ", "2. " etc.)
    html = html.replace(/(?:^|\n)((?:\d+\. .+(?:\n|$))+)/g, function (_, block) {
      var items = block.trim().split("\n").map(function (l) {
        return "<li>" + l.replace(/^\d+\.\s/, "") + "</li>";
      }).join("");
      return '<ol class="he-list">' + items + "</ol>";
    });
    // Line breaks (but not inside lists / pre)
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  /* ------------------------------------------------------------------ */
  /*  Widget class                                                       */
  /* ------------------------------------------------------------------ */

  class HedgeExpertWidget {
    constructor(config) {
      config = config || {};
      this.config = Object.assign({}, DEFAULTS, config);
      if (!this.config.apiUrl) {
        this.config.apiUrl = window.location.origin;
      }

      this.sessionId = this._loadSession();
      this.isOpen = false;
      this.isStreaming = false;
      this.pendingNotification = false;
      this.thinkingInterval = null;
      this.timerInterval = null;
      this.responseStartMs = null;

      this._inject();
    }

    /* ---------- session persistence ---------- */

    _loadSession() {
      try { return sessionStorage.getItem("hedge_session_id") || null; }
      catch (_) { return null; }
    }

    _saveSession(id) {
      this.sessionId = id;
      try { sessionStorage.setItem("hedge_session_id", id); }
      catch (_) { /* no-op */ }
      this._updateSessionBadge();
    }

    /* ---------- CSS injection ---------- */

    _inject() {
      if (!document.getElementById("hedge-expert-css")) {
        var link = document.createElement("link");
        link.id = "hedge-expert-css";
        link.rel = "stylesheet";
        link.href =
          this.config.cssUrl ||
          new URL("hedge-expert-widget.css", _scriptSrc || window.location.href).href;
        document.head.appendChild(link);
      }
      this._createDOM();
      this._bindEvents();
    }

    /* ---------- DOM construction ---------- */

    _createDOM() {
      var c = document.createElement("div");
      c.className = "he-container";
      c.setAttribute("data-position", this.config.position);

      // Bubble
      var bubble = document.createElement("button");
      bubble.className = "he-bubble";
      bubble.setAttribute("aria-label", "Open HEDGE-ExpertAI assistant");
      bubble.innerHTML =
        '<span class="he-bubble-icon">' + ICON_BOT + '</span>' +
        '<span class="he-bubble-badge"></span>';

      // Panel
      var panel = document.createElement("div");
      panel.className = "he-panel";

      var sessionLabel = this.sessionId
        ? "Session: " + this.sessionId.slice(0, 8) + "…"
        : "Session: new";

      panel.innerHTML =
        '<div class="he-panel-main">' +
          '<div class="he-header">' +
            '<div class="he-header-left">' +
              '<div class="he-header-title">' + escapeHtml(this.config.title) + '</div>' +
              '<div class="he-header-session">' + sessionLabel + '</div>' +
            '</div>' +
            '<div class="he-header-actions">' +
              '<button class="he-header-btn he-clear-btn" aria-label="Clear conversation" title="Clear conversation">' + ICON_CLEAR + '</button>' +
              '<button class="he-header-btn he-close-btn" aria-label="Close">&times;</button>' +
            '</div>' +
          '</div>' +
          '<div class="he-messages"></div>' +
          '<div class="he-input-area">' +
            '<textarea class="he-input" placeholder="Ask about IoT apps…" rows="1" maxlength="500"></textarea>' +
            '<button class="he-send-btn" aria-label="Send message">' +
              '<span class="he-send-icon">' + ICON_SEND + '</span>' +
              '<span class="he-send-text">Send</span>' +
            '</button>' +
          '</div>' +
        '</div>' +
        '<div class="he-panel-side">' +
          '<div class="he-side-header">' +
            '<span class="he-side-title">Recommended Context</span>' +
            '<button class="he-side-close" aria-label="Close pane">&times;</button>' +
          '</div>' +
          '<div class="he-side-content"></div>' +
        '</div>';

      c.appendChild(panel);
      c.appendChild(bubble);
      document.body.appendChild(c);

      this.container = c;
      this.bubble = bubble;
      this.bubbleBadge = bubble.querySelector(".he-bubble-badge");
      this.panel = panel;
      this.messagesDiv = panel.querySelector(".he-messages");
      this.textarea = panel.querySelector(".he-input");
      this.sendBtn = panel.querySelector(".he-send-btn");
      this.sendText = panel.querySelector(".he-send-text");
      this.closeBtn = panel.querySelector(".he-close-btn");
      this.clearBtn = panel.querySelector(".he-clear-btn");
      this.sessionBadge = panel.querySelector(".he-header-session");
      this.sideContent = panel.querySelector(".he-side-content");
      this.sideCloseBtn = panel.querySelector(".he-side-close");
    }

    /* ---------- event binding ---------- */

    _bindEvents() {
      var self = this;

      this.bubble.addEventListener("click", function () { self.toggle(); });
      this.closeBtn.addEventListener("click", function () { self.close(); });
      this.clearBtn.addEventListener("click", function () { self._clearChat(); });
      this.sendBtn.addEventListener("click", function () { self._send(); });
      this.sideCloseBtn.addEventListener("click", function () {
        self.panel.classList.remove("he-panel--expanded");
      });

      this.textarea.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          self._send();
        }
      });

      // Auto-grow textarea
      this.textarea.addEventListener("input", function () { self._autoGrow(); });

      // Global keyboard shortcut: Ctrl+Shift+H
      document.addEventListener("keydown", function (e) {
        if (e.ctrlKey && e.shiftKey && e.key === "H") {
          e.preventDefault();
          self.toggle();
        }
      });
    }

    /* ---------- public methods ---------- */

    toggle() {
      this.isOpen ? this.close() : this.open();
    }

    open() {
      this.isOpen = true;
      this.panel.classList.add("he-panel--open");
      this.bubble.classList.add("he-bubble--hidden");
      this.pendingNotification = false;
      this.bubbleBadge.classList.remove("he-bubble-badge--visible");
      this.textarea.focus();

      if (this.messagesDiv.children.length === 0) {
        this._showWelcome();
      }
    }

    close() {
      this.isOpen = false;
      this.panel.classList.remove("he-panel--open");
      this.bubble.classList.remove("he-bubble--hidden");
    }

    /* ---------- welcome + suggestions ---------- */

    _showWelcome() {
      var wrap = document.createElement("div");
      wrap.className = "he-welcome he-animate-in";

      wrap.innerHTML =
        '<div class="he-msg he-msg--assistant">' +
          '<span class="he-msg-icon he-msg-icon--bot">' + ICON_BOT + '</span>' +
          '<div class="he-msg-body">' +
            '<div class="he-msg-content">' +
              'Hello! I\'m <strong>HEDGE-ExpertAI</strong>. I can help you discover and compare IoT applications in the HEDGE ecosystem.<br><br>' +
              'Ask me anything — or pick a suggestion below.' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="he-suggestions" id="he-suggestions"></div>';

      this.messagesDiv.appendChild(wrap);

      var sugBox = wrap.querySelector("#he-suggestions");
      var self = this;
      SUGGESTIONS.forEach(function (text) {
        var chip = document.createElement("button");
        chip.className = "he-chip";
        chip.textContent = text;
        chip.addEventListener("click", function () {
          self.textarea.value = text;
          self._send();
        });
        sugBox.appendChild(chip);
      });
    }

    /* ---------- clear chat ---------- */

    _clearChat() {
      if (this.isStreaming) return;
      this.messagesDiv.innerHTML = "";
      this._showWelcome();
    }

    /* ---------- send message ---------- */

    _send() {
      var text = this.textarea.value.trim();
      if (!text || this.isStreaming) return;

      // Remove suggestions
      var sugEl = this.messagesDiv.querySelector(".he-suggestions");
      if (sugEl) sugEl.remove();

      this.textarea.value = "";
      this.textarea.style.height = "";
      this._addUserMessage(text);
      this._setStreamState("thinking");

      var intent = inferIntent(text);
      var steps = THINKING_STEPS[intent] || THINKING_STEPS.unknown;
      var stepIdx = 0;

      // Start response timer
      this.responseStartMs = Date.now();

      // Create the final message container immediately
      var msgWrap = document.createElement("div");
      msgWrap.className = "he-msg he-msg--assistant he-animate-in";
      msgWrap.innerHTML =
        '<span class="he-msg-icon he-msg-icon--bot">' + ICON_BOT + '</span>' +
        '<div class="he-msg-body">' +
          '<div class="he-msg-top">' +
            '<span class="he-timer">0.0s</span>' +
          '</div>' +
          '<div class="he-cot">' +
            '<button class="he-cot-toggle" aria-expanded="true" disabled>' +
              '<svg class="he-cot-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>' +
              ' <span class="he-cot-title-text">Thinking Process <span class="he-pulse-dot"></span></span>' +
      var timerEl = msgWrap.querySelector(".he-timer");

      var self = this;

      // Live timer spanning both thinking and streaming
      this.timerInterval = setInterval(function () {
        if (timerEl) timerEl.textContent = formatDuration(Date.now() - self.responseStartMs);
      }, 100);

      // Function to append a step
      var processStep = function () {
        if (stepIdx < steps.length) {
          var stepEl = document.createElement("div");
          stepEl.className = "he-cot-step he-animate-in-step";
          stepEl.innerHTML = '<svg class="he-cot-check" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' +
            escapeHtml(steps[stepIdx]);
          cotSteps.appendChild(stepEl);
          self._scrollBottom();
          stepIdx++;
        } else {
          clearInterval(self.thinkingInterval);
        }
      };

      // Start sequential thinking animation (every 1 second)
      processStep();
      this.thinkingInterval = setInterval(processStep, 1000);

      fetch(this.config.apiUrl + "/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: this.sessionId, message: text }),
      })
        .then(function (resp) {
          if (!resp.ok || !resp.body) throw new Error("HTTP " + resp.status);

          // Stop thinking sequence, append remaining instantly
          clearInterval(self.thinkingInterval);
          while (stepIdx < steps.length) {
            processStep();
          }

          // Transition to streaming state
          self._setStreamState("streaming");
          contentEl.style.display = ""; // reveal text section
          cotTitleText.textContent = "Chain of Thought";
          cotToggle.removeAttribute("disabled");
          
          // Enable CoT collapse
          cotToggle.addEventListener("click", function () {
            var expanded = cotToggle.getAttribute("aria-expanded") === "true";
            cotToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
            cotSteps.style.display = expanded ? "none" : "";
            cotToggle.querySelector(".he-cot-chevron").style.transform = expanded ? "rotate(-90deg)" : "";
          });

          // Read SSE stream
          var reader = resp.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";
          var accumulated = "";
          var appsData = null;

          function readChunk() {
            return reader.read().then(function (result) {
              if (result.done) {
                // Finalize
                self._clearTimer();
                var finalMs = Date.now() - self.responseStartMs;
                if (timerEl) timerEl.textContent = formatDuration(finalMs);
                contentEl.classList.remove("he-streaming-cursor");

                if (accumulated) {
                  contentEl.innerHTML = renderMarkdown(accumulated);
                  self._addCopyButton(msgWrap, accumulated);
                }
                // Apps already rendered when SSE event arrived; render any late-arriving ones
                if (appsData && appsData.length > 0 && !self.sideContent.querySelector(".he-cards")) {
                  self.panel.classList.add("he-panel--expanded");
                  self._addAppCards(self.sideContent, appsData);
                }
                if (!self.isOpen) self._notify();
                self._setStreamState("idle");
                self._scrollBottom();
                return;
              }

              buffer += decoder.decode(result.value, { stream: true });
              var lines = buffer.split("\n");
              buffer = lines.pop() || "";

              for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (!line.startsWith("data: ")) continue;
                var evt;
                try { evt = JSON.parse(line.slice(6)); } catch (_) { continue; }

                if (evt.type === "token") {
                  accumulated += evt.content || "";
                  contentEl.innerHTML = renderMarkdown(accumulated);
                  self._scrollBottom();
                } else if (evt.type === "apps") {
                  appsData = evt.apps || [];
                  // Render app cards immediately in the side pane
                  if (appsData.length > 0) {
                    self.panel.classList.add("he-panel--expanded");
                    self._addAppCards(self.sideContent, appsData);
                  }
                } else if (evt.type === "done") {
                  if (evt.session_id) self._saveSession(evt.session_id);
                } else if (evt.type === "error") {
                  accumulated = evt.content || "An error occurred.";
                  contentEl.innerHTML = '<span class="he-error-text">' + escapeHtml(accumulated) + '</span>';
                }
              }

              return readChunk();
            });
          }

          return readChunk();
        })
        .catch(function (err) {
          self._clearThinking();
          self._clearTimer();
          self._addErrorMessage("Unable to reach the assistant. Please check your connection and try again.");
          self._setStreamState("idle");
          self._scrollBottom();
          console.error("HEDGE-ExpertAI:", err);
        });
    }

    /* ---------- message rendering ---------- */

    _addUserMessage(text) {
      var el = document.createElement("div");
      el.className = "he-msg he-msg--user he-animate-in";
      el.innerHTML =
        '<div class="he-msg-body">' +
          '<div class="he-msg-content">' + escapeHtml(text) + '</div>' +
        '</div>' +
        '<span class="he-msg-icon he-msg-icon--user">' + ICON_USER + '</span>';
      this.messagesDiv.appendChild(el);
      this._scrollBottom();
    }

    _addErrorMessage(text) {
      var el = document.createElement("div");
      el.className = "he-msg he-msg--error he-animate-in";
      el.innerHTML =
        '<span class="he-msg-icon he-msg-icon--bot">' + ICON_BOT + '</span>' +
        '<div class="he-msg-body">' +
          '<div class="he-msg-content he-error-text">' +
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:4px">' +
              '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>' +
            '</svg>' +
            escapeHtml(text) +
          '</div>' +
        '</div>';
      this.messagesDiv.appendChild(el);
      this._scrollBottom();
    }

    /* ---------- app cards ---------- */

    _addAppCards(parentBody, apps) {
      parentBody.innerHTML = ""; // Clear previous context
      var container = document.createElement("div");
      container.className = "he-cards he-animate-in";

      for (var i = 0; i < Math.min(apps.length, 5); i++) {
        var result = apps[i];
        var app = result.app || result;
        var score = result.score || 0;
        var pct = (score * 100).toFixed(0);
        var dc = domainColor(app.saref_type || app.domain || "");
        var desc = (app.description || "").slice(0, 140);
        var version = app.version ? '<span class="he-card-version">v' + escapeHtml(app.version) + '</span>' : "";
        var publisher = app.publisher ? '<span class="he-card-publisher">' + escapeHtml(app.publisher) + '</span>' : "";
        var domainLabel = app.saref_type || app.domain || "";

        var card = document.createElement("div");
        card.className = "he-card";
        card.innerHTML =
          '<div class="he-card-top">' +
            '<div class="he-card-title">' + escapeHtml(app.title || "Unknown App") + '</div>' +
            '<span class="he-card-score">' + pct + '%</span>' +
          '</div>' +
          '<div class="he-card-score-bar"><div class="he-card-score-fill" style="width:' + pct + '%;background:' + dc.bar + '"></div></div>' +
          '<div class="he-card-desc">' + escapeHtml(desc) + (desc.length >= 140 ? "…" : "") + '</div>' +
          '<div class="he-card-footer">' +
            (domainLabel ? '<span class="he-card-domain" style="background:' + dc.bg + ';color:' + dc.fg + '">' + escapeHtml(domainLabel) + '</span>' : "") +
            publisher +
            version +
            '<span class="he-card-id">' + escapeHtml(app.id || "") + '</span>' +
          '</div>';
        container.appendChild(card);
      }

      parentBody.appendChild(container);
      this._scrollBottom();
    }

    /* ---------- copy button ---------- */

    _addCopyButton(msgWrap, rawText) {
      var btn = document.createElement("button");
      btn.className = "he-copy-btn";
      btn.setAttribute("aria-label", "Copy response");
      btn.innerHTML = ICON_COPY;
      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(rawText).then(function () {
          btn.innerHTML = '<span class="he-copied">Copied!</span>';
          setTimeout(function () { btn.innerHTML = ICON_COPY; }, 1500);
        }).catch(function () { /* silent */ });
      });
      var topEl = msgWrap.querySelector(".he-msg-top");
      if (topEl) topEl.appendChild(btn);
    }

    /* ---------- thinking / timer helpers ---------- */

    _clearThinking() {
      clearInterval(this.thinkingInterval);
      this.thinkingInterval = null;
    }

    _clearTimer() {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    /* ---------- stream state management ---------- */

    _setStreamState(state) {
      // state: "idle" | "thinking" | "streaming"
      this.isStreaming = state !== "idle";
      this.textarea.disabled = this.isStreaming;
      this.sendBtn.disabled = this.isStreaming;

      if (state === "thinking") {
        this.sendText.textContent = "Thinking…";
      } else if (state === "streaming") {
        this.sendText.textContent = "Typing…";
      } else {
        this.sendText.textContent = "Send";
      }
    }

    /* ---------- notification badge ---------- */

    _notify() {
      this.pendingNotification = true;
      this.bubbleBadge.classList.add("he-bubble-badge--visible");
    }

    /* ---------- session badge ---------- */

    _updateSessionBadge() {
      if (this.sessionBadge && this.sessionId) {
        this.sessionBadge.textContent = "Session: " + this.sessionId.slice(0, 8) + "…";
      }
    }

    /* ---------- textarea auto-grow ---------- */

    _autoGrow() {
      var ta = this.textarea;
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 100) + "px";
    }

    /* ---------- scroll ---------- */

    _scrollBottom() {
      var md = this.messagesDiv;
      md.scrollTop = md.scrollHeight;
    }
  }

  /* ------------------------------------------------------------------ */
  /*  Auto-init & global export                                          */
  /* ------------------------------------------------------------------ */

  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-hedge-expert]");
    if (script) {
      var config = {};
      if (script.dataset.apiUrl) config.apiUrl = script.dataset.apiUrl;
      if (script.dataset.primaryColor) config.primaryColor = script.dataset.primaryColor;
      if (script.dataset.title) config.title = script.dataset.title;
      new HedgeExpertWidget(config);
    }
  });

  window.HedgeExpertWidget = HedgeExpertWidget;
})();
