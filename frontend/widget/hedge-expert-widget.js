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

  const THINKING_STOPWORDS = {
    a: true, about: true, an: true, and: true, app: true, apps: true, details: true,
    detail: true, explain: true, find: true, for: true, i: true, me: true, of: true,
    on: true, please: true, recommend: true, show: true, suggest: true, tell: true,
    the: true, to: true, what: true, with: true,
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

  const THINKING_STEP_MS = 2300;

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

  function extractThinkingFocus(message) {
    var tokens = ((message || "").toLowerCase().match(/[a-z0-9-]+/g) || []);
    var picked = [];
    for (var i = 0; i < tokens.length; i++) {
      var token = tokens[i];
      if (THINKING_STOPWORDS[token]) continue;
      if (picked.indexOf(token) !== -1) continue;
      picked.push(token);
      if (picked.length >= 3) break;
    }
    return picked.length ? picked.join(" ") : "your request";
  }

  function buildThinkingSteps(message, intent) {
    var base = (THINKING_STEPS[intent] || THINKING_STEPS.unknown).slice();
    var focus = extractThinkingFocus(message);
    var focusPhrase = focus === "your request" ? focus : '"' + focus + '"';

    base.unshift("Framing " + focusPhrase + " against the HEDGE app catalog…");

    if (intent === "search") {
      base.push("Cross-checking ranked matches for confidence and relevance…");
      base.push("Tightening the final recommendation so it is easy to compare…");
    } else if (intent === "detail") {
      base.push("Verifying the explanation against the app metadata and datasets…");
      base.push("Refining the answer so the most useful details land first…");
    } else if (intent === "help" || intent === "greeting") {
      base.push("Shaping a compact response with the clearest next step…");
    } else {
      base.push("Rechecking the safest and most useful response framing…");
    }

    return base;
  }

  function splitStreamText(text) {
    if (!text) return [];
    return text.replace(/\r\n/g, "\n").match(/\s+|[^\s]+\s*/g) || [];
  }

  function formatDuration(ms) {
    return (ms / 1000).toFixed(1) + "s";
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function normalizeHexColor(value) {
    var raw = String(value || "").trim();
    if (!/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(raw)) {
      return DEFAULTS.primaryColor;
    }
    if (raw.length === 4) {
      return (
        "#" +
        raw[1] + raw[1] +
        raw[2] + raw[2] +
        raw[3] + raw[3]
      ).toLowerCase();
    }
    return raw.toLowerCase();
  }

  function hexToRgb(hex) {
    var normalized = normalizeHexColor(hex);
    return {
      r: parseInt(normalized.slice(1, 3), 16),
      g: parseInt(normalized.slice(3, 5), 16),
      b: parseInt(normalized.slice(5, 7), 16),
    };
  }

  function clampChannel(value) {
    return Math.max(0, Math.min(255, Math.round(value)));
  }

  function rgbToHex(rgb) {
    function part(value) {
      return clampChannel(value).toString(16).padStart(2, "0");
    }
    return "#" + part(rgb.r) + part(rgb.g) + part(rgb.b);
  }

  function blendHex(baseHex, targetHex, ratio) {
    var safeRatio = Math.max(0, Math.min(1, ratio));
    var base = hexToRgb(baseHex);
    var target = hexToRgb(targetHex);
    return rgbToHex({
      r: base.r + (target.r - base.r) * safeRatio,
      g: base.g + (target.g - base.g) * safeRatio,
      b: base.b + (target.b - base.b) * safeRatio,
    });
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
          new URL("hedge-expert-widget.css?v=" + Date.now(), _scriptSrc || window.location.href).href;
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
              (this.config.subtitle
                ? '<div class="he-header-subtitle">' + escapeHtml(this.config.subtitle) + '</div>'
                : '') +
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

      this._applyThemeConfig();
    }

    _applyThemeConfig() {
      var primary = normalizeHexColor(this.config.primaryColor);
      var primaryDark = blendHex(primary, "#0f172a", 0.35);
      var primarySoft = blendHex(primary, "#ffffff", 0.2);
      var primaryRgb = hexToRgb(primary);

      this.container.style.setProperty("--he-primary", primary);
      this.container.style.setProperty("--he-primary-dark", primaryDark);
      this.container.style.setProperty("--he-primary-soft", primarySoft);
      this.container.style.setProperty(
        "--he-primary-rgb",
        primaryRgb.r + ", " + primaryRgb.g + ", " + primaryRgb.b
      );
      this.container.style.setProperty("--he-panel-width", this.config.width || DEFAULTS.width);
      this.container.style.setProperty("--he-panel-height", this.config.height || DEFAULTS.height);
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
      this._clearSidePane();
      this._showWelcome();
    }

    _clearSidePane() {
      if (this.sideContent) {
        this.sideContent.innerHTML = "";
      }
      this.panel.classList.remove("he-panel--expanded");
    }

    /* ---------- send message ---------- */

    _send() {
      var text = this.textarea.value.trim();
      if (!text || this.isStreaming) return;
      this._clearThinking();
      this._clearTimer();

      // Remove suggestions
      var sugEl = this.messagesDiv.querySelector(".he-suggestions");
      if (sugEl) sugEl.remove();

      this.textarea.value = "";
      this.textarea.style.height = "";
      this.textarea.style.overflowY = "hidden";
      this._clearSidePane();
      this._addUserMessage(text);
      this._setStreamState("thinking");

      var intent = inferIntent(text);
      var steps = buildThinkingSteps(text, intent);
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
            '<div class="he-cot-live" aria-live="polite" aria-atomic="true"></div>' +
          '</div>' +
          '<div class="he-msg-content he-streaming-cursor" style="display: none;"></div>' +
        '</div>';
      this.messagesDiv.appendChild(msgWrap);
      this._scrollBottom();

      var cotEl = msgWrap.querySelector(".he-cot");
      var cotLive = msgWrap.querySelector(".he-cot-live");
      var contentEl = msgWrap.querySelector(".he-msg-content");
      var timerEl = msgWrap.querySelector(".he-timer");
      var self = this;

      // Live timer spanning both thinking and streaming
      this.timerInterval = setInterval(function () {
        if (timerEl) timerEl.textContent = formatDuration(Date.now() - self.responseStartMs);
      }, 100);

      function showThought(nextText) {
        var activeThoughts = cotLive.querySelectorAll(".he-cot-live-text");
        for (var idx = 0; idx < activeThoughts.length; idx++) {
          activeThoughts[idx].classList.remove("he-cot-live-text--current");
          activeThoughts[idx].classList.add("he-cot-live-text--exit");
          (function (node) {
            setTimeout(function () {
              if (node.parentNode) node.parentNode.removeChild(node);
            }, 280);
          })(activeThoughts[idx]);
        }

        var nextThought = document.createElement("span");
        nextThought.className = "he-cot-live-text";
        nextThought.textContent = nextText;
        nextThought.setAttribute("data-text", nextText);
        cotLive.appendChild(nextThought);

        window.requestAnimationFrame(function () {
          nextThought.classList.add("he-cot-live-text--current");
        });

        self._scrollBottom();
      }

      // Function to swap the live thought line
      var processStep = function () {
        if (steps.length) {
          showThought(steps[stepIdx % steps.length]);
          stepIdx++;
        }
      };

      // Start sequential thinking animation.
      processStep();
      this.thinkingInterval = setInterval(processStep, THINKING_STEP_MS);

      fetch(this.config.apiUrl + "/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: this.sessionId, message: text }),
      })
        .then(function (resp) {
          if (!resp.ok || !resp.body) throw new Error("HTTP " + resp.status);

          // Transition to streaming state
          self._setStreamState("streaming");
          contentEl.style.display = ""; // reveal text section

          // Read SSE stream
          var reader = resp.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";
          var accumulated = "";
          var appsData = null;
          var renderQueue = [];
          var renderInterval = null;
          var streamComplete = false;
          var finalSessionId = null;
          var finalized = false;
          var thoughtCycleStopped = false;

          function stopThinkingCycle() {
            if (thoughtCycleStopped) return;
            thoughtCycleStopped = true;
            self._clearThinking();
          }

          function stopRenderPump() {
            clearInterval(renderInterval);
            renderInterval = null;
          }

          function finalizeStream() {
            if (finalized) return;
            finalized = true;
            stopRenderPump();
            self._clearThinking();
            cotEl.classList.add("he-cot--complete");
            self._clearTimer();
            var finalMs = Date.now() - self.responseStartMs;
            if (timerEl) timerEl.textContent = formatDuration(finalMs);
            contentEl.classList.remove("he-streaming-cursor");

            if (accumulated) {
              contentEl.innerHTML = renderMarkdown(accumulated);
              self._addCopyButton(msgWrap, accumulated);
            }
            if (appsData && appsData.length > 0 && !self.sideContent.querySelector(".he-cards")) {
              self.panel.classList.add("he-panel--expanded");
              self._addAppCards(self.sideContent, appsData);
            }
            // Add feedback buttons when apps were recommended
            if (appsData && appsData.length > 0) {
              var feedbackAppIds = appsData.map(function (r) {
                var a = r.app || r;
                return a.id || "";
              }).filter(Boolean);
              if (feedbackAppIds.length > 0) {
                self._addFeedbackButtons(msgWrap, feedbackAppIds);
              }
            }
            if (finalSessionId) self._saveSession(finalSessionId);
            if (!self.isOpen) self._notify();
            self._setStreamState("idle");
            self._scrollBottom();
          }

          function startRenderPump() {
            if (renderInterval) return;
            renderInterval = setInterval(function () {
              if (!renderQueue.length) {
                if (streamComplete) finalizeStream();
                return;
              }

              stopThinkingCycle();
              accumulated += renderQueue.shift();
              contentEl.innerHTML = renderMarkdown(accumulated);
              self._scrollBottom();

              if (!renderQueue.length && streamComplete) {
                finalizeStream();
              }
            }, 36);
          }

          function readChunk() {
            return reader.read().then(function (result) {
              if (result.done) {
                streamComplete = true;
                if (!renderQueue.length) finalizeStream();
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
                  renderQueue = renderQueue.concat(splitStreamText(evt.content || ""));
                  startRenderPump();
                } else if (evt.type === "apps") {
                  appsData = evt.apps || [];
                  // Render app cards immediately in the side pane
                  if (appsData.length > 0) {
                    self.panel.classList.add("he-panel--expanded");
                    self._addAppCards(self.sideContent, appsData);
                  }
                } else if (evt.type === "done") {
                  if (evt.session_id) finalSessionId = evt.session_id;
                } else if (evt.type === "error") {
                  accumulated = evt.content || "An error occurred.";
                  renderQueue = [];
                  stopRenderPump();
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
          cotEl.classList.add("he-cot--complete");
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

    /* ---------- feedback buttons ---------- */

    _addFeedbackButtons(msgWrap, appIds) {
      var self = this;
      var bar = document.createElement("div");
      bar.className = "he-feedback-bar";
      bar.innerHTML =
        '<span class="he-feedback-label">Was this helpful?</span>' +
        '<button class="he-feedback-btn he-feedback-accept" aria-label="Helpful">' +
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"/>' +
          '</svg> Yes' +
        '</button>' +
        '<button class="he-feedback-btn he-feedback-dismiss" aria-label="Not helpful">' +
          '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M17 14V2"/><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"/>' +
          '</svg> No' +
        '</button>';

      var acceptBtn = bar.querySelector(".he-feedback-accept");
      var dismissBtn = bar.querySelector(".he-feedback-dismiss");

      function handleFeedback(action) {
        acceptBtn.disabled = true;
        dismissBtn.disabled = true;
        if (action === "accept") {
          acceptBtn.classList.add("he-feedback-btn--active-accept");
          acceptBtn.innerHTML = '&#10003; Thanks!';
        } else {
          dismissBtn.classList.add("he-feedback-btn--active-dismiss");
          dismissBtn.innerHTML = '&#10003; Noted';
        }
        self._sendFeedback(appIds, action);
      }

      acceptBtn.addEventListener("click", function () { handleFeedback("accept"); });
      dismissBtn.addEventListener("click", function () { handleFeedback("dismiss"); });

      var bodyEl = msgWrap.querySelector(".he-msg-body");
      if (bodyEl) bodyEl.appendChild(bar);
    }

    _sendFeedback(appIds, action) {
      var self = this;
      for (var i = 0; i < Math.min(appIds.length, 5); i++) {
        (function (appId) {
          fetch(self.config.apiUrl + "/api/v1/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: self.sessionId || "",
              app_id: appId,
              action: action,
            }),
          }).catch(function () { /* best-effort */ });
        })(appIds[i]);
      }
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
      var maxHeight = 100;
      ta.style.height = "auto";
      ta.style.height = Math.max(Math.min(ta.scrollHeight, maxHeight), 36) + "px";
      ta.style.overflowY = ta.scrollHeight > maxHeight ? "auto" : "hidden";
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
      if (script.dataset.position) config.position = script.dataset.position;
      if (script.dataset.subtitle) config.subtitle = script.dataset.subtitle;
      if (script.dataset.primaryColor) config.primaryColor = script.dataset.primaryColor;
      if (script.dataset.title) config.title = script.dataset.title;
      if (script.dataset.width) config.width = script.dataset.width;
      if (script.dataset.height) config.height = script.dataset.height;
      if (script.dataset.cssUrl) config.cssUrl = script.dataset.cssUrl;
      new HedgeExpertWidget(config);
    }
  });

  window.HedgeExpertWidget = HedgeExpertWidget;
})();
