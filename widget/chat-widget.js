(function () {
  "use strict";

  const script = document.currentScript;
  const orgId = script.getAttribute("data-org");
  const apiBase = script.getAttribute("data-api") || script.src.replace(/\/widget\/.*$/, "");

  if (!orgId) {
    console.error("TBM Chat Widget: data-org attribute is required");
    return;
  }

  // Session management
  let sessionId = sessionStorage.getItem("tbm_session_" + orgId);
  if (!sessionId) {
    sessionId = "sess_" + Math.random().toString(36).substring(2) + Date.now().toString(36);
    sessionStorage.setItem("tbm_session_" + orgId, sessionId);
  }

  let config = {
    primary_color: "#2563eb",
    text_color: "#ffffff",
    welcome_message: "Hi! How can I help you today?",
    placeholder_text: "Type your message...",
    logo_url: null,
  };
  let orgName = "";
  let isOpen = false;
  let isLoading = false;

  // Load widget config from API
  async function loadConfig() {
    try {
      const resp = await fetch(apiBase + "/api/tenants/public/" + orgId);
      if (resp.ok) {
        const data = await resp.json();
        orgName = data.name || "";
        Object.assign(config, data.widget_config || {});
        applyConfig();
      }
    } catch (e) {
      console.warn("TBM Chat Widget: Could not load config", e);
    }
  }

  // Load CSS
  function loadStyles() {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = apiBase + "/widget/chat-widget.css";
    document.head.appendChild(link);
  }

  function applyConfig() {
    const root = document.querySelector(".tbm-chat-widget");
    if (root) {
      root.style.setProperty("--tbm-primary", config.primary_color);
      root.style.setProperty("--tbm-text", config.text_color);
    }
    const headerName = document.querySelector(".tbm-chat-header-name");
    if (headerName) headerName.textContent = orgName || "Chat";
    const input = document.querySelector(".tbm-chat-input");
    if (input) input.placeholder = config.placeholder_text;
    const logo = document.querySelector(".tbm-chat-header-logo");
    if (logo) {
      if (config.logo_url) {
        logo.src = config.logo_url;
        logo.style.display = "";
      } else {
        logo.style.display = "none";
      }
    }
  }

  function createWidget() {
    const container = document.createElement("div");
    container.className = "tbm-chat-widget";
    container.innerHTML = `
      <button class="tbm-chat-bubble" aria-label="Open chat">
        <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
      </button>
      <div class="tbm-chat-window">
        <div class="tbm-chat-header">
          <div class="tbm-chat-header-info">
            <img class="tbm-chat-header-logo" src="" alt="" style="display:none">
            <span class="tbm-chat-header-name">Chat</span>
          </div>
          <button class="tbm-chat-close" aria-label="Close chat">&times;</button>
        </div>
        <div class="tbm-chat-messages">
          <div class="tbm-chat-message tbm-chat-message-assistant">${escapeHtml(config.welcome_message)}</div>
        </div>
        <div class="tbm-chat-typing">
          <div class="tbm-typing-dot"></div>
          <div class="tbm-typing-dot"></div>
          <div class="tbm-typing-dot"></div>
        </div>
        <div class="tbm-chat-input-area">
          <input type="text" class="tbm-chat-input" placeholder="${escapeHtml(config.placeholder_text)}" maxlength="4000">
          <button class="tbm-chat-send" aria-label="Send message">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
        <div class="tbm-powered-by">Powered by TBM Chatbot</div>
      </div>
    `;
    document.body.appendChild(container);

    // Event listeners
    const bubble = container.querySelector(".tbm-chat-bubble");
    const window_ = container.querySelector(".tbm-chat-window");
    const closeBtn = container.querySelector(".tbm-chat-close");
    const input = container.querySelector(".tbm-chat-input");
    const sendBtn = container.querySelector(".tbm-chat-send");

    bubble.addEventListener("click", function () {
      isOpen = !isOpen;
      window_.classList.toggle("tbm-open", isOpen);
      bubble.style.display = isOpen ? "none" : "flex";
      if (isOpen) input.focus();
    });

    closeBtn.addEventListener("click", function () {
      isOpen = false;
      window_.classList.remove("tbm-open");
      bubble.style.display = "flex";
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener("click", sendMessage);

    applyConfig();
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function addMessage(role, content, sources) {
    const messages = document.querySelector(".tbm-chat-messages");
    const msg = document.createElement("div");
    msg.className = "tbm-chat-message tbm-chat-message-" + role;
    msg.textContent = content;

    if (sources && sources.length > 0) {
      const sourcesDiv = document.createElement("div");
      sourcesDiv.className = "tbm-chat-sources";
      const validSources = sources.filter(function (s) { return s.source_url; });
      if (validSources.length > 0) {
        sourcesDiv.innerHTML = "Sources: " + validSources.map(function (s) {
          return '<a href="' + escapeHtml(s.source_url) + '" target="_blank" rel="noopener">' + escapeHtml(s.document_title) + "</a>";
        }).join(", ");
        msg.appendChild(sourcesDiv);
      }
    }

    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
  }

  function setTyping(visible) {
    const typing = document.querySelector(".tbm-chat-typing");
    typing.classList.toggle("tbm-visible", visible);
    if (visible) {
      const messages = document.querySelector(".tbm-chat-messages");
      messages.scrollTop = messages.scrollHeight;
    }
  }

  async function sendMessage() {
    if (isLoading) return;
    const input = document.querySelector(".tbm-chat-input");
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    addMessage("user", text);
    isLoading = true;
    setTyping(true);

    const sendBtn = document.querySelector(".tbm-chat-send");
    sendBtn.disabled = true;

    try {
      const resp = await fetch(apiBase + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org_id: orgId,
          message: text,
          session_id: sessionId,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(function () { return {}; });
        throw new Error(err.detail || "Request failed");
      }

      const data = await resp.json();
      addMessage("assistant", data.response, data.sources);
    } catch (e) {
      addMessage("assistant", "Sorry, something went wrong. Please try again.");
      console.error("TBM Chat Widget:", e);
    } finally {
      isLoading = false;
      setTyping(false);
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // Initialize
  loadStyles();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      createWidget();
      loadConfig();
    });
  } else {
    createWidget();
    loadConfig();
  }
})();
