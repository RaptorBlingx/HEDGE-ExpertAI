/**
 * HEDGE-ExpertAI Chat Widget
 * Embeddable, self-contained chat widget for the HEDGE-IoT App Store.
 * No framework dependencies.
 */
(function () {
  "use strict";

  const DEFAULTS = {
    apiUrl: "http://localhost:8000",
    position: "bottom-right",
    title: "HEDGE-ExpertAI",
    subtitle: "IoT App Discovery Assistant",
    primaryColor: "#2563eb",
    width: "380px",
    height: "520px",
  };

  class HedgeExpertWidget {
    constructor(config = {}) {
      this.config = { ...DEFAULTS, ...config };
      this.sessionId = this._loadSession();
      this.isOpen = false;
      this._inject();
    }

    _loadSession() {
      try {
        return sessionStorage.getItem("hedge_session_id") || null;
      } catch {
        return null;
      }
    }

    _saveSession(id) {
      this.sessionId = id;
      try {
        sessionStorage.setItem("hedge_session_id", id);
      } catch {
        /* ignore */
      }
    }

    _inject() {
      // Inject CSS
      if (!document.getElementById("hedge-expert-css")) {
        const link = document.createElement("link");
        link.id = "hedge-expert-css";
        link.rel = "stylesheet";
        link.href =
          this.config.cssUrl ||
          new URL("hedge-expert-widget.css", document.currentScript?.src || window.location.href).href;
        document.head.appendChild(link);
      }

      // Create widget DOM
      this._createDOM();
      this._bindEvents();
    }

    _createDOM() {
      // Container
      const container = document.createElement("div");
      container.className = "hedge-expert-container";
      container.setAttribute("data-position", this.config.position);

      // Chat bubble button
      const bubble = document.createElement("button");
      bubble.className = "hedge-expert-bubble";
      bubble.setAttribute("aria-label", "Open chat assistant");
      bubble.style.backgroundColor = this.config.primaryColor;
      bubble.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;

      // Chat panel
      const panel = document.createElement("div");
      panel.className = "hedge-expert-panel";
      panel.style.width = this.config.width;
      panel.style.height = this.config.height;
      panel.innerHTML = `
        <div class="hedge-expert-header" style="background-color:${this.config.primaryColor}">
          <div class="hedge-expert-header-text">
            <div class="hedge-expert-title">${this._escapeHtml(this.config.title)}</div>
            <div class="hedge-expert-subtitle">${this._escapeHtml(this.config.subtitle)}</div>
          </div>
          <button class="hedge-expert-close" aria-label="Close chat">&times;</button>
        </div>
        <div class="hedge-expert-messages"></div>
        <div class="hedge-expert-input-area">
          <input type="text" class="hedge-expert-input" placeholder="Ask about IoT apps..." maxlength="500" />
          <button class="hedge-expert-send" style="background-color:${this.config.primaryColor}" aria-label="Send message">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
      `;

      container.appendChild(panel);
      container.appendChild(bubble);
      document.body.appendChild(container);

      this.container = container;
      this.bubble = bubble;
      this.panel = panel;
      this.messagesDiv = panel.querySelector(".hedge-expert-messages");
      this.input = panel.querySelector(".hedge-expert-input");
      this.sendBtn = panel.querySelector(".hedge-expert-send");
      this.closeBtn = panel.querySelector(".hedge-expert-close");
    }

    _bindEvents() {
      this.bubble.addEventListener("click", () => this.toggle());
      this.closeBtn.addEventListener("click", () => this.close());
      this.sendBtn.addEventListener("click", () => this._send());
      this.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this._send();
        }
      });
    }

    toggle() {
      this.isOpen ? this.close() : this.open();
    }

    open() {
      this.isOpen = true;
      this.panel.classList.add("hedge-expert-panel--open");
      this.bubble.classList.add("hedge-expert-bubble--hidden");
      this.input.focus();

      // Welcome message if empty
      if (this.messagesDiv.children.length === 0) {
        this._addMessage(
          "assistant",
          "Hello! I'm HEDGE-ExpertAI. I can help you discover IoT applications. Try asking something like <em>\"Find apps for energy monitoring\"</em>."
        );
      }
    }

    close() {
      this.isOpen = false;
      this.panel.classList.remove("hedge-expert-panel--open");
      this.bubble.classList.remove("hedge-expert-bubble--hidden");
    }

    async _send() {
      const text = this.input.value.trim();
      if (!text) return;

      this.input.value = "";
      this._addMessage("user", this._escapeHtml(text));
      this._setLoading(true);

      try {
        const resp = await fetch(`${this.config.apiUrl}/api/v1/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: this.sessionId,
            message: text,
          }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const data = await resp.json();
        this._saveSession(data.session_id);

        // Add text response
        this._addMessage("assistant", this._formatMarkdown(data.message));

        // Add app cards if any
        if (data.apps && data.apps.length > 0) {
          this._addAppCards(data.apps);
        }
      } catch (err) {
        this._addMessage(
          "assistant",
          "Sorry, I'm having trouble connecting. Please try again in a moment."
        );
        console.error("HEDGE-ExpertAI error:", err);
      } finally {
        this._setLoading(false);
      }
    }

    _addMessage(role, html) {
      const msg = document.createElement("div");
      msg.className = `hedge-expert-msg hedge-expert-msg--${role}`;
      msg.innerHTML = html;
      this.messagesDiv.appendChild(msg);
      this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
    }

    _addAppCards(apps) {
      const cardsContainer = document.createElement("div");
      cardsContainer.className = "hedge-expert-cards";

      for (const result of apps.slice(0, 5)) {
        const app = result.app || result;
        const card = document.createElement("div");
        card.className = "hedge-expert-card";

        const sarefBadge = app.saref_type
          ? `<span class="hedge-expert-badge">${this._escapeHtml(app.saref_type)}</span>`
          : "";

        const desc = (app.description || "").slice(0, 120);
        card.innerHTML = `
          <div class="hedge-expert-card-header">
            <strong>${this._escapeHtml(app.title || "Unknown App")}</strong>
            ${sarefBadge}
          </div>
          <p class="hedge-expert-card-desc">${this._escapeHtml(desc)}${desc.length >= 120 ? "..." : ""}</p>
          ${result.score ? `<span class="hedge-expert-score">Relevance: ${(result.score * 100).toFixed(0)}%</span>` : ""}
        `;
        cardsContainer.appendChild(card);
      }

      this.messagesDiv.appendChild(cardsContainer);
      this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
    }

    _setLoading(on) {
      if (on) {
        const loader = document.createElement("div");
        loader.className = "hedge-expert-loading";
        loader.innerHTML = '<div class="hedge-expert-dots"><span></span><span></span><span></span></div>';
        this.messagesDiv.appendChild(loader);
        this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
        this.sendBtn.disabled = true;
      } else {
        const loader = this.messagesDiv.querySelector(".hedge-expert-loading");
        if (loader) loader.remove();
        this.sendBtn.disabled = false;
      }
    }

    _escapeHtml(str) {
      const div = document.createElement("div");
      div.textContent = str;
      return div.innerHTML;
    }

    _formatMarkdown(text) {
      // Basic markdown: bold, italic, line breaks
      return this._escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/g, "<em>$1</em>")
        .replace(/\n/g, "<br>");
    }
  }

  // Auto-initialize if data attributes present
  document.addEventListener("DOMContentLoaded", () => {
    const script = document.querySelector("script[data-hedge-expert]");
    if (script) {
      const config = {};
      if (script.dataset.apiUrl) config.apiUrl = script.dataset.apiUrl;
      if (script.dataset.primaryColor) config.primaryColor = script.dataset.primaryColor;
      if (script.dataset.title) config.title = script.dataset.title;
      new HedgeExpertWidget(config);
    }
  });

  // Expose globally
  window.HedgeExpertWidget = HedgeExpertWidget;
})();
