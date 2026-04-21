(function () {
  "use strict";

  const script = document.currentScript;
  const orgId = script.getAttribute("data-org");
  const apiBase = script.getAttribute("data-api") || script.src.replace(/\/widget\/.*$/, "");

  if (!orgId) {
    console.error("TBM Chat Widget: data-org attribute is required");
    return;
  }

  // --- Session management ---
  const STORAGE_KEY = "tbm_chat_" + orgId;
  const EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours

  let sessionId = null;
  let conversationId = null;
  let savedMessages = [];

  function generateSessionId() {
    return "sess_" + Math.random().toString(36).substring(2) + Date.now().toString(36);
  }

  // Feature 4: localStorage persistence
  function loadPersistedState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const data = JSON.parse(raw);
      if (Date.now() - data.timestamp > EXPIRY_MS) {
        localStorage.removeItem(STORAGE_KEY);
        return false;
      }
      sessionId = data.sessionId;
      conversationId = data.conversationId || null;
      savedMessages = data.messages || [];
      return true;
    } catch (e) {
      localStorage.removeItem(STORAGE_KEY);
      return false;
    }
  }

  function persistState() {
    try {
      const messagesEl = document.querySelector(".tbm-chat-messages");
      if (!messagesEl) return;
      const msgs = [];
      messagesEl.querySelectorAll(".tbm-chat-message").forEach(function (el) {
        const role = el.classList.contains("tbm-chat-message-user") ? "user" : "assistant";
        const messageId = el.getAttribute("data-message-id") || null;
        msgs.push({ role: role, html: el.innerHTML, messageId: messageId });
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        sessionId: sessionId,
        conversationId: conversationId,
        messages: msgs,
        timestamp: Date.now(),
      }));
    } catch (e) {
      // localStorage may be full or unavailable
    }
  }

  if (!loadPersistedState()) {
    sessionId = generateSessionId();
  }

  // --- State ---
  let config = {
    primary_color: "#2563eb",
    text_color: "#ffffff",
    welcome_message: "Hi! How can I help you today?",
    placeholder_text: "Type your message...",
    logo_url: null,
    prechat_enabled: false,
    prechat_fields: [],
    launcher_teaser: null,
  };
  let orgName = "";
  let quickReplies = [];
  let supportEmail = null;
  let businessHours = null;
  let awayMessage = null;
  let isOpen = false;
  let isLoading = false;
  let prechatCompleted = false;
  let visitorName = null;
  let visitorEmail = null;
  let teaserDismissed = false;
  let teaserTimeout = null;

  // --- Load config ---
  async function loadConfig() {
    try {
      const resp = await fetch(apiBase + "/api/tenants/public/" + orgId);
      if (resp.ok) {
        const data = await resp.json();
        orgName = data.name || "";
        Object.assign(config, data.widget_config || {});
        quickReplies = data.quick_replies || [];
        supportEmail = data.support_email || null;
        businessHours = data.business_hours || null;
        awayMessage = data.away_message || null;

        // Defaults for quick replies
        if (!quickReplies || quickReplies.length === 0) {
          quickReplies = ["How do I register?", "What programs do you offer?", "Do you offer financial aid?"];
        }

        applyConfig();
        showQuickReplies();
        showAwayIndicator();
        startTeaserTimer();
      }
    } catch (e) {
      console.warn("TBM Chat Widget: Could not load config", e);
    }
  }

  // --- Load CSS ---
  function loadStyles() {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = apiBase + "/widget/chat-widget.css";
    document.head.appendChild(link);
  }

  // --- Apply config to DOM ---
  function applyConfig() {
    const root = document.querySelector(".tbm-chat-widget");
    if (root) {
      root.style.setProperty("--tbm-primary", config.primary_color);
      root.style.setProperty("--tbm-text", config.text_color);
    }
    const headerName = document.querySelector(".tbm-chat-header-name");
    if (headerName) headerName.textContent = orgName || "Chat";
    var input = document.querySelector(".tbm-chat-input");
    if (input) input.placeholder = config.placeholder_text;
    var logo = document.querySelector(".tbm-chat-header-logo");
    if (logo) {
      if (config.logo_url) {
        logo.src = config.logo_url;
        logo.style.display = "";
      } else {
        logo.style.display = "none";
      }
    }
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // --- Feature 8: Away mode indicator ---
  function isWithinBusinessHours() {
    if (!businessHours || !businessHours.hours) return true;
    try {
      var now = new Date();
      // Use simple day check (server also checks, this is UX only)
      var days = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
      var dayKey = days[now.getDay()];
      var dayHours = businessHours.hours[dayKey];
      if (!dayHours || dayHours.length < 2) return false;
      var openParts = dayHours[0].split(":");
      var closeParts = dayHours[1].split(":");
      var openMin = parseInt(openParts[0]) * 60 + parseInt(openParts[1]);
      var closeMin = parseInt(closeParts[0]) * 60 + parseInt(closeParts[1]);
      var nowMin = now.getHours() * 60 + now.getMinutes();
      return nowMin >= openMin && nowMin <= closeMin;
    } catch (e) {
      return true;
    }
  }

  function showAwayIndicator() {
    var indicator = document.querySelector(".tbm-away-indicator");
    if (!indicator) return;
    if (businessHours && !isWithinBusinessHours()) {
      indicator.textContent = awayMessage || "We are currently offline";
      indicator.style.display = "block";
    } else {
      indicator.style.display = "none";
    }
  }

  // --- Feature 6: Launcher teaser ---
  function startTeaserTimer() {
    if (!config.launcher_teaser || teaserDismissed || isOpen) return;
    teaserTimeout = setTimeout(function () {
      if (!isOpen && !teaserDismissed) {
        showTeaser();
      }
    }, 5000);
  }

  function showTeaser() {
    var teaser = document.querySelector(".tbm-teaser");
    if (teaser) {
      teaser.querySelector(".tbm-teaser-text").textContent = config.launcher_teaser;
      teaser.style.display = "flex";
    }
  }

  function dismissTeaser() {
    teaserDismissed = true;
    var teaser = document.querySelector(".tbm-teaser");
    if (teaser) teaser.style.display = "none";
    if (teaserTimeout) clearTimeout(teaserTimeout);
  }

  // --- Feature 3: Pre-chat form ---
  function shouldShowPrechat() {
    if (!config.prechat_enabled) return false;
    if (prechatCompleted) return false;
    if (visitorName || visitorEmail) return false;
    if (savedMessages.length > 0) return false;
    return true;
  }

  function showPrechat() {
    var form = document.querySelector(".tbm-prechat-form");
    var chatArea = document.querySelector(".tbm-chat-main");
    if (form && chatArea) {
      form.style.display = "flex";
      chatArea.style.display = "none";
    }
  }

  function hidePrechat() {
    var form = document.querySelector(".tbm-prechat-form");
    var chatArea = document.querySelector(".tbm-chat-main");
    if (form && chatArea) {
      form.style.display = "none";
      chatArea.style.display = "flex";
    }
  }

  function handlePrechatSubmit() {
    var nameInput = document.querySelector(".tbm-prechat-name");
    var emailInput = document.querySelector(".tbm-prechat-email");
    var name = nameInput ? nameInput.value.trim() : "";
    var email = emailInput ? emailInput.value.trim() : "";

    if (!name || !email) return;

    visitorName = name;
    visitorEmail = email;
    prechatCompleted = true;
    hidePrechat();
    var input = document.querySelector(".tbm-chat-input");
    if (input) input.focus();
  }

  // --- Widget DOM ---
  function createWidget() {
    var container = document.createElement("div");
    container.className = "tbm-chat-widget";
    container.innerHTML =
      '<div class="tbm-teaser" style="display:none">' +
        '<span class="tbm-teaser-text"></span>' +
        '<button class="tbm-teaser-close" aria-label="Dismiss">&times;</button>' +
      '</div>' +
      '<button class="tbm-chat-bubble" aria-label="Open chat">' +
        '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>' +
      '</button>' +
      '<div class="tbm-chat-window">' +
        '<div class="tbm-chat-header">' +
          '<div class="tbm-chat-header-info">' +
            '<img class="tbm-chat-header-logo" src="" alt="" style="display:none">' +
            '<span class="tbm-chat-header-name">Chat</span>' +
          '</div>' +
          '<button class="tbm-chat-close" aria-label="Close chat">&times;</button>' +
        '</div>' +
        '<div class="tbm-away-indicator" style="display:none"></div>' +
        '<div class="tbm-prechat-form" style="display:none">' +
          '<div class="tbm-prechat-title">Before we start, tell us about yourself</div>' +
          '<input type="text" class="tbm-prechat-name" placeholder="Your name" maxlength="255">' +
          '<input type="email" class="tbm-prechat-email" placeholder="Your email" maxlength="255">' +
          '<button class="tbm-prechat-submit">Start Chat</button>' +
        '</div>' +
        '<div class="tbm-chat-main" style="display:flex;flex-direction:column;flex:1;min-height:0">' +
          '<div class="tbm-chat-messages">' +
            '<div class="tbm-chat-message tbm-chat-message-assistant">' + escapeHtml(config.welcome_message) + '</div>' +
          '</div>' +
          '<div class="tbm-chat-typing">' +
            '<div class="tbm-typing-dot"></div>' +
            '<div class="tbm-typing-dot"></div>' +
            '<div class="tbm-typing-dot"></div>' +
          '</div>' +
          '<div class="tbm-chat-input-area">' +
            '<input type="text" class="tbm-chat-input" placeholder="' + escapeHtml(config.placeholder_text) + '" maxlength="4000">' +
            '<button class="tbm-chat-send" aria-label="Send message">' +
              '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
            '</button>' +
          '</div>' +
          '<div class="tbm-powered-by">Powered by TBM Chatbot</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(container);

    // Event listeners
    var bubble = container.querySelector(".tbm-chat-bubble");
    var chatWindow = container.querySelector(".tbm-chat-window");
    var closeBtn = container.querySelector(".tbm-chat-close");
    var input = container.querySelector(".tbm-chat-input");
    var sendBtn = container.querySelector(".tbm-chat-send");
    var teaserClose = container.querySelector(".tbm-teaser-close");
    var teaserEl = container.querySelector(".tbm-teaser");
    var prechatSubmit = container.querySelector(".tbm-prechat-submit");

    bubble.addEventListener("click", function () {
      isOpen = true;
      chatWindow.classList.add("tbm-open");
      bubble.style.display = "none";
      dismissTeaser();
      if (shouldShowPrechat()) {
        showPrechat();
      } else {
        hidePrechat();
        input.focus();
      }
    });

    if (teaserEl) {
      teaserEl.addEventListener("click", function (e) {
        if (e.target === teaserClose) {
          dismissTeaser();
          return;
        }
        // Clicking teaser text opens chat
        isOpen = true;
        chatWindow.classList.add("tbm-open");
        bubble.style.display = "none";
        dismissTeaser();
        if (shouldShowPrechat()) {
          showPrechat();
        } else {
          hidePrechat();
          input.focus();
        }
      });
    }

    closeBtn.addEventListener("click", function () {
      isOpen = false;
      chatWindow.classList.remove("tbm-open");
      bubble.style.display = "flex";
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener("click", sendMessage);

    if (prechatSubmit) {
      prechatSubmit.addEventListener("click", handlePrechatSubmit);
      // Allow Enter in prechat form
      container.querySelector(".tbm-prechat-email").addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); handlePrechatSubmit(); }
      });
    }

    applyConfig();

    // Feature 4: Restore persisted messages
    if (savedMessages.length > 0) {
      restoreMessages();
    }
  }

  function restoreMessages() {
    var messagesEl = document.querySelector(".tbm-chat-messages");
    if (!messagesEl) return;
    // Clear the default welcome message
    messagesEl.innerHTML = "";
    savedMessages.forEach(function (msg) {
      var div = document.createElement("div");
      div.className = "tbm-chat-message tbm-chat-message-" + msg.role;
      div.innerHTML = msg.html;
      if (msg.messageId) div.setAttribute("data-message-id", msg.messageId);
      messagesEl.appendChild(div);
    });
    // Re-attach feedback listeners
    messagesEl.querySelectorAll(".tbm-feedback-btn").forEach(function (btn) {
      btn.addEventListener("click", handleFeedbackClick);
    });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // --- Feature 5: Quick reply buttons ---
  function showQuickReplies() {
    if (!quickReplies || quickReplies.length === 0) return;
    if (savedMessages.length > 0) return; // Don't show if conversation restored

    var messagesEl = document.querySelector(".tbm-chat-messages");
    if (!messagesEl) return;

    var welcomeMsg = messagesEl.querySelector(".tbm-chat-message-assistant");
    if (!welcomeMsg) return;

    // Check if quick replies already exist
    if (welcomeMsg.querySelector(".tbm-quick-replies")) return;

    var qrDiv = document.createElement("div");
    qrDiv.className = "tbm-quick-replies";
    quickReplies.forEach(function (text) {
      var btn = document.createElement("button");
      btn.className = "tbm-quick-reply-btn";
      btn.textContent = text;
      btn.addEventListener("click", function () {
        // Remove quick reply buttons
        var allQr = document.querySelectorAll(".tbm-quick-replies");
        allQr.forEach(function (el) { el.remove(); });
        // Send as regular message
        var inputEl = document.querySelector(".tbm-chat-input");
        if (inputEl) inputEl.value = text;
        sendMessage();
      });
      qrDiv.appendChild(btn);
    });
    welcomeMsg.appendChild(qrDiv);
  }

  // --- Feature 7: Feedback buttons ---
  function addFeedbackButtons(messageEl, messageId) {
    if (!messageId) return;
    var fbDiv = document.createElement("div");
    fbDiv.className = "tbm-feedback";
    fbDiv.innerHTML =
      '<button class="tbm-feedback-btn" data-rating="positive" data-message-id="' + messageId + '" title="Helpful">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>' +
      '</button>' +
      '<button class="tbm-feedback-btn" data-rating="negative" data-message-id="' + messageId + '" title="Not helpful">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm12-7h2.67A2.31 2.31 0 0 1 27 10v7a2.31 2.31 0 0 1-2.33 2H22"/></svg>' +
      '</button>';
    messageEl.appendChild(fbDiv);

    fbDiv.querySelectorAll(".tbm-feedback-btn").forEach(function (btn) {
      btn.addEventListener("click", handleFeedbackClick);
    });
  }

  function handleFeedbackClick(e) {
    var btn = e.currentTarget;
    var messageId = btn.getAttribute("data-message-id");
    var rating = btn.getAttribute("data-rating");
    if (!messageId) return;

    // Disable all feedback buttons for this message
    var fbDiv = btn.parentElement;
    fbDiv.querySelectorAll(".tbm-feedback-btn").forEach(function (b) {
      b.disabled = true;
      b.classList.remove("tbm-feedback-active");
    });
    btn.classList.add("tbm-feedback-active");

    // Submit feedback
    fetch(apiBase + "/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, rating: rating }),
    }).catch(function (err) {
      console.warn("TBM Chat Widget: feedback failed", err);
    });

    persistState();
  }

  // --- Message handling ---
  function addMessage(role, content, sources, messageId) {
    var messagesEl = document.querySelector(".tbm-chat-messages");
    var msg = document.createElement("div");
    msg.className = "tbm-chat-message tbm-chat-message-" + role;
    if (messageId) msg.setAttribute("data-message-id", messageId);

    // Render markdown-like bold and newlines for bot messages
    if (role === "assistant") {
      msg.innerHTML = escapeHtml(content)
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>");
    } else {
      msg.textContent = content;
    }

    if (sources && sources.length > 0) {
      var validSources = sources.filter(function (s) { return s.source_url; });
      if (validSources.length > 0) {
        var sourcesDiv = document.createElement("div");
        sourcesDiv.className = "tbm-chat-sources";
        sourcesDiv.innerHTML = "Sources: " + validSources.map(function (s) {
          return '<a href="' + escapeHtml(s.source_url) + '" target="_blank" rel="noopener">' + escapeHtml(s.document_title) + "</a>";
        }).join(", ");
        msg.appendChild(sourcesDiv);
      }
    }

    // Feature 7: Add feedback buttons to bot messages
    if (role === "assistant" && messageId) {
      addFeedbackButtons(msg, messageId);
    }

    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    // Feature 4: Persist after each message
    persistState();
  }

  function setTyping(visible) {
    var typing = document.querySelector(".tbm-chat-typing");
    if (!typing) return;
    typing.classList.toggle("tbm-visible", visible);
    if (visible) {
      var messagesEl = document.querySelector(".tbm-chat-messages");
      if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  async function sendMessage() {
    if (isLoading) return;
    var input = document.querySelector(".tbm-chat-input");
    var text = input.value.trim();
    if (!text) return;

    input.value = "";
    addMessage("user", text);
    isLoading = true;
    setTyping(true);

    var sendBtn = document.querySelector(".tbm-chat-send");
    sendBtn.disabled = true;

    try {
      var body = {
        org_id: orgId,
        message: text,
        session_id: sessionId,
      };
      // Feature 3: Include pre-chat data
      if (visitorName) body.visitor_name = visitorName;
      if (visitorEmail) body.visitor_email = visitorEmail;

      var resp = await fetch(apiBase + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        throw new Error(err.detail || "Request failed");
      }

      var data = await resp.json();
      conversationId = data.conversation_id;
      addMessage("assistant", data.response, data.sources, data.message_id);
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

  // --- Initialize ---
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
