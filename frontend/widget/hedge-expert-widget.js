/**
 * HEDGE-ExpertAI Chat Widget v3.0
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
    locale: "en",
    getAccessToken: null,
  };

  const SUGGESTIONS = [
    "Find apps for energy monitoring",
    "Show me smart irrigation solutions",
    "Recommend building comfort apps",
  ];

  const SUPPORTED_LOCALES = ["en", "de", "fr", "es", "it", "nl", "pt", "tr"];

  const STAGE_LABELS = {
    intent: "Understanding the request…",
    retrieval: "Searching the application catalogue…",
    ranking: "Ranking evidence-backed matches…",
    explanation: "Preparing a grounded explanation…",
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

  function localized(value, locale) {
    if (value && typeof value === "object") return value[locale] || value.en || "";
    return value || "";
  }

  function eventKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return "evt-" + window.crypto.randomUUID();
    }
    return "evt-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
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
      if (SUPPORTED_LOCALES.indexOf(this.config.locale) === -1) {
        var browserLocale = (navigator.language || "en").split("-")[0];
        this.config.locale = SUPPORTED_LOCALES.indexOf(browserLocale) >= 0 ? browserLocale : "en";
      }

      this.sessionId = this._loadSession();
      this.isOpen = false;
      this.isStreaming = false;
      this.pendingNotification = false;
      this.timerInterval = null;
      this.responseStartMs = null;
      this.activeController = null;
      this.previouslyFocused = null;
      this.lastMessage = "";

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

    _forgetSession() {
      this.sessionId = null;
      try { sessionStorage.removeItem("hedge_session_id"); }
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
          new URL("hedge-expert-widget.css?v=3.0.0", _scriptSrc || window.location.href).href;
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
      panel.setAttribute("role", "dialog");
      panel.setAttribute("aria-modal", "true");
      panel.setAttribute("aria-labelledby", "he-dialog-title");
      panel.setAttribute("aria-hidden", "true");

      var sessionLabel = this.sessionId
        ? "Session: " + this.sessionId.slice(0, 8) + "…"
        : "Session: new";

      panel.innerHTML =
        '<div class="he-panel-main">' +
          '<div class="he-header">' +
            '<div class="he-header-left">' +
              '<div class="he-header-title" id="he-dialog-title">' + escapeHtml(this.config.title) + '</div>' +
              (this.config.subtitle
                ? '<div class="he-header-subtitle">' + escapeHtml(this.config.subtitle) + '</div>'
                : '') +
              '<div class="he-header-session">' + sessionLabel + '</div>' +
            '</div>' +
            '<div class="he-header-actions">' +
              '<label class="he-locale-label"><span class="he-sr-only">Language</span>' +
                '<select class="he-locale" aria-label="Language"></select>' +
              '</label>' +
              '<button class="he-header-btn he-clear-btn" aria-label="Clear conversation" title="Clear conversation">' + ICON_CLEAR + '</button>' +
              '<button class="he-header-btn he-close-btn" aria-label="Close">&times;</button>' +
            '</div>' +
          '</div>' +
          '<div class="he-messages" role="log" aria-live="polite" aria-relevant="additions text"></div>' +
          '<div class="he-input-area">' +
            '<label class="he-sr-only" for="he-chat-input">Ask about IoT applications</label>' +
            '<textarea id="he-chat-input" class="he-input" placeholder="Ask about IoT apps…" rows="1" maxlength="2000"></textarea>' +
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
      this.container.setAttribute("lang", this.config.locale);
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
      this.localeSelect = panel.querySelector(".he-locale");
      SUPPORTED_LOCALES.forEach(function (locale) {
        var option = document.createElement("option");
        option.value = locale;
        option.textContent = locale.toUpperCase();
        if (locale === this.config.locale) option.selected = true;
        this.localeSelect.appendChild(option);
      }, this);

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
      this.localeSelect.addEventListener("change", function () {
        self.config.locale = this.value;
        self.container.setAttribute("lang", this.value);
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
        if (e.key === "Escape" && self.isOpen) {
          e.preventDefault();
          self.close();
        }
        if (e.key === "Tab" && self.isOpen) self._trapFocus(e);
      });
    }

    /* ---------- public methods ---------- */

    toggle() {
      this.isOpen ? this.close() : this.open();
    }

    open() {
      this.isOpen = true;
      this.previouslyFocused = document.activeElement;
      this.panel.classList.add("he-panel--open");
      this.panel.setAttribute("aria-hidden", "false");
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
      this.panel.setAttribute("aria-hidden", "true");
      this.bubble.classList.remove("he-bubble--hidden");
      if (this.previouslyFocused && typeof this.previouslyFocused.focus === "function") {
        this.previouslyFocused.focus();
      }
    }

    _trapFocus(event) {
      var focusable = this.panel.querySelectorAll(
        'button:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href]'
      );
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
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
      this._cancelActive();
      var sessionId = this.sessionId;
      if (sessionId) {
        var self = this;
        this._authHeaders().then(function (headers) {
          return fetch(
            self.config.apiUrl + "/api/v2/sessions/" + encodeURIComponent(sessionId),
            { method: "DELETE", headers: headers }
          );
        }).catch(function () { /* session TTL remains the fallback */ });
      }
      this._forgetSession();
      this.messagesDiv.innerHTML = "";
      this._clearSidePane();
      this._showWelcome();
    }

    _cancelActive() {
      if (this.activeController) this.activeController.abort();
      this.activeController = null;
      this._clearTimer();
      this._setStreamState("idle");
    }

    _authHeaders() {
      var provider = this.config.getAccessToken;
      return Promise.resolve(typeof provider === "function" ? provider() : null).then(function (token) {
        var headers = { "Content-Type": "application/json" };
        if (token) headers.Authorization = "Bearer " + token;
        return headers;
      });
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
      if (this.isStreaming) {
        this._cancelActive();
        return;
      }
      if (!text) return;
      this._clearTimer();
      this.lastMessage = text;

      // Remove suggestions
      var sugEl = this.messagesDiv.querySelector(".he-suggestions");
      if (sugEl) sugEl.remove();

      this.textarea.value = "";
      this.textarea.style.height = "";
      this.textarea.style.overflowY = "hidden";
      this._clearSidePane();
      this._addUserMessage(text);
      this._setStreamState("thinking");

      // Start response timer
      this.responseStartMs = Date.now();
      this.activeController = new AbortController();

      // Create the final message container immediately
      var msgWrap = document.createElement("div");
      msgWrap.className = "he-msg he-msg--assistant he-animate-in";
      msgWrap.innerHTML =
        '<span class="he-msg-icon he-msg-icon--bot">' + ICON_BOT + '</span>' +
        '<div class="he-msg-body">' +
          '<div class="he-msg-top">' +
            '<span class="he-timer">0.0s</span>' +
          '</div>' +
          '<div class="he-stage" role="status" aria-live="polite">Connecting to the catalogue…</div>' +
          '<div class="he-msg-content he-streaming-cursor" style="display: none;"></div>' +
        '</div>';
      this.messagesDiv.appendChild(msgWrap);
      this._scrollBottom();

      var stageEl = msgWrap.querySelector(".he-stage");
      var contentEl = msgWrap.querySelector(".he-msg-content");
      var timerEl = msgWrap.querySelector(".he-timer");
      var self = this;

      // Live timer spanning both thinking and streaming
      this.timerInterval = setInterval(function () {
        if (timerEl) timerEl.textContent = formatDuration(Date.now() - self.responseStartMs);
      }, 100);

      this._authHeaders().then(function (headers) {
        return fetch(self.config.apiUrl + "/api/v2/chat/stream", {
          method: "POST",
          headers: headers,
          signal: self.activeController.signal,
          body: JSON.stringify({
            session_id: self.sessionId,
            message: text,
            locale: self.config.locale,
            filters: {},
          }),
        });
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
          var appsData = [];
          var finalSessionId = null;
          var impressionId = null;
          var finalized = false;

          function finalizeStream() {
            if (finalized) return;
            finalized = true;
            self._clearTimer();
            var finalMs = Date.now() - self.responseStartMs;
            if (timerEl) timerEl.textContent = formatDuration(finalMs);
            stageEl.textContent = "Complete";
            stageEl.classList.add("he-stage--complete");
            contentEl.classList.remove("he-streaming-cursor");

            if (accumulated) {
              contentEl.innerHTML = renderMarkdown(accumulated);
              self._addCopyButton(msgWrap, accumulated);
            }
            if (appsData.length > 0 && !self.sideContent.querySelector(".he-cards")) {
              self.panel.classList.add("he-panel--expanded");
              self._addAppCards(self.sideContent, appsData, impressionId);
            }
            if (appsData.length > 0 && impressionId) {
              self._addFeedbackButtons(msgWrap, impressionId);
            }
            if (finalSessionId) self._saveSession(finalSessionId);
            if (!self.isOpen) self._notify();
            self._setStreamState("idle");
            self.activeController = null;
            self._scrollBottom();
          }

          function readChunk() {
            return reader.read().then(function (result) {
              if (result.done) {
                finalizeStream();
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

                if (evt.type === "stage") {
                  stageEl.textContent = STAGE_LABELS[evt.stage] || "Working…";
                } else if (evt.type === "explanation_delta") {
                  accumulated += evt.content || "";
                  contentEl.style.display = "";
                  contentEl.innerHTML = renderMarkdown(accumulated);
                  self._setStreamState("streaming");
                  self._scrollBottom();
                } else if (evt.type === "recommendations") {
                  appsData = evt.apps || [];
                  impressionId = evt.impression_id || impressionId;
                  // Render app cards immediately in the side pane
                  if (appsData.length > 0) {
                    self.panel.classList.add("he-panel--expanded");
                    self._addAppCards(self.sideContent, appsData, impressionId);
                  }
                } else if (evt.type === "complete") {
                  if (evt.session_id) finalSessionId = evt.session_id;
                  impressionId = evt.impression_id || impressionId;
                } else if (evt.type === "problem") {
                  accumulated = evt.detail || evt.title || "An error occurred.";
                  contentEl.innerHTML = '<span class="he-error-text">' + escapeHtml(accumulated) + '</span>';
                }
              }

              return readChunk();
            });
          }

          return readChunk();
        })
        .catch(function (err) {
          self._clearTimer();
          stageEl.textContent = err && err.name === "AbortError" ? "Cancelled" : "Request failed";
          if (!err || err.name !== "AbortError") {
            contentEl.style.display = "";
            contentEl.innerHTML = '<span class="he-error-text">Unable to reach the assistant. Please check your connection and try again.</span>';
          }
          self._setStreamState("idle");
          self.activeController = null;
          self._scrollBottom();
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

    _addAppCards(parentBody, apps, impressionId) {
      parentBody.innerHTML = ""; // Clear previous context
      var container = document.createElement("div");
      container.className = "he-cards he-animate-in";

      for (var i = 0; i < Math.min(apps.length, 5); i++) {
        var result = apps[i];
        var app = result.app || result;
        var relevance = result.relevance || "medium";
        var domainLabel = (app.domains && app.domains[0]) || app.saref_type || app.domain || "";
        var dc = domainColor(domainLabel);
        var desc = (app.description || "").slice(0, 140);
        var appTitle = localized(app.title, this.config.locale) || "Unknown App";
        var versionValue = (app.lifecycle && app.lifecycle.version) || app.version || "";
        var publisherValue = (app.publisher && app.publisher.name) || app.publisher || "";
        var version = versionValue ? '<span class="he-card-version">v' + escapeHtml(versionValue) + '</span>' : "";
        var publisher = publisherValue ? '<span class="he-card-publisher">' + escapeHtml(publisherValue) + '</span>' : "";

        var card = document.createElement(app.app_url ? "a" : "div");
        card.className = "he-card";
        if (app.app_url) {
          card.href = app.app_url;
          card.target = "_blank";
          card.rel = "noopener noreferrer";
          card.setAttribute("aria-label", "Open " + appTitle);
        }
        card.innerHTML =
          '<div class="he-card-top">' +
            '<div class="he-card-title">' + escapeHtml(appTitle) + '</div>' +
            '<span class="he-card-score">' + escapeHtml(relevance) + '</span>' +
          '</div>' +
          '<div class="he-card-desc">' + escapeHtml(desc) + (desc.length >= 140 ? "…" : "") + '</div>' +
          '<div class="he-card-footer">' +
            (domainLabel ? '<span class="he-card-domain" style="background:' + dc.bg + ';color:' + dc.fg + '">' + escapeHtml(domainLabel) + '</span>' : "") +
            publisher +
            version +
            '<span class="he-card-id">' + escapeHtml(app.id || "") + '</span>' +
          '</div>';
        if (app.app_url && impressionId) {
          var self = this;
          (function (appId) {
            card.addEventListener("click", function () {
              self._sendRecommendationEvent(impressionId, "app_opened", appId);
            });
          })(app.id);
        }
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

    _addFeedbackButtons(msgWrap, impressionId) {
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
        self._sendRecommendationEvent(
          impressionId,
          action === "accept" ? "recommendation_accepted" : "recommendation_dismissed"
        );
      }

      acceptBtn.addEventListener("click", function () { handleFeedback("accept"); });
      dismissBtn.addEventListener("click", function () { handleFeedback("dismiss"); });

      var bodyEl = msgWrap.querySelector(".he-msg-body");
      if (bodyEl) bodyEl.appendChild(bar);
    }

    _sendRecommendationEvent(impressionId, eventType, appId) {
      var self = this;
      this._authHeaders().then(function (headers) {
          return fetch(self.config.apiUrl + "/api/v2/recommendation-events", {
            method: "POST",
            headers: headers,
            body: JSON.stringify({
              impression_id: impressionId,
              idempotency_key: eventKey(),
              event_type: eventType,
              app_id: appId || undefined,
            }),
          });
      }).catch(function () { /* best-effort telemetry */ });
    }

    /* ---------- thinking / timer helpers ---------- */

    _clearTimer() {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }

    /* ---------- stream state management ---------- */

    _setStreamState(state) {
      // state: "idle" | "thinking" | "streaming"
      this.isStreaming = state !== "idle";
      this.textarea.disabled = this.isStreaming;
      this.sendBtn.disabled = false;

      if (state === "thinking") {
        this.sendText.textContent = "Stop";
      } else if (state === "streaming") {
        this.sendText.textContent = "Stop";
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
      if (this.sessionBadge) {
        this.sessionBadge.textContent = this.sessionId
          ? "Session: " + this.sessionId.slice(0, 8) + "…"
          : "Session: new";
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
      if (script.dataset.locale) config.locale = script.dataset.locale;
      new HedgeExpertWidget(config);
    }
  });

  window.HedgeExpertWidget = HedgeExpertWidget;
})();
