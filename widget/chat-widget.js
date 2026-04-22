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
  let messageCount = 0; // Track messages for CSAT trigger

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
      messageCount = data.messageCount || 0;
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
        messageCount: messageCount,
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
  let csatEnabled = false;
  let csatTriggerAfter = 5;
  let csatSubmitted = false;
  let isOpen = false;
  let isLoading = false;
  let prechatCompleted = false;
  let visitorName = null;
  let visitorEmail = null;
  let teaserDismissed = false;
  let teaserTimeout = null;
  let typingTimeout = null;
  // Wave 3 state
  let customCss = null;
  let defaultLanguage = "en";
  let supportedLanguages = ["en"];
  let greetingVariants = [];
  let escalationTriggers = [];
  let articlesPanelOpen = false;

  // --- Feature 14: Markdown-to-HTML renderer ---
  function renderMarkdown(text) {
    // Escape HTML first
    var escaped = escapeHtml(text);

    // Bold: **text**
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // Italic: *text* (but not inside bold)
    escaped = escaped.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

    // Links: [text](url)
    escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // Auto-detect URLs (not already in an href)
    escaped = escaped.replace(/(?<!href="|">)(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>');

    // Auto-detect email addresses
    escaped = escaped.replace(/(?<!href="mailto:)([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})/g,
      '<a href="mailto:$1">$1</a>');

    // Process line by line for lists
    var lines = escaped.split("\n");
    var result = [];
    var inUl = false;
    var inOl = false;

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var ulMatch = line.match(/^\s*[-*]\s+(.*)/);
      var olMatch = line.match(/^\s*\d+\.\s+(.*)/);

      if (ulMatch) {
        if (!inUl) { result.push("<ul>"); inUl = true; }
        if (inOl) { result.push("</ol>"); inOl = false; }
        result.push("<li>" + ulMatch[1] + "</li>");
      } else if (olMatch) {
        if (!inOl) { result.push("<ol>"); inOl = true; }
        if (inUl) { result.push("</ul>"); inUl = false; }
        result.push("<li>" + olMatch[1] + "</li>");
      } else {
        if (inUl) { result.push("</ul>"); inUl = false; }
        if (inOl) { result.push("</ol>"); inOl = false; }
        result.push(line);
      }
    }
    if (inUl) result.push("</ul>");
    if (inOl) result.push("</ol>");

    // Join and convert remaining newlines to <br> (except inside lists)
    var html = result.join("\n");
    // Replace newlines that aren't inside list elements
    html = html.replace(/\n(?!<\/?[uo]l>|<\/?li>)/g, "<br>");
    // Clean up extra <br> before/after lists
    html = html.replace(/<br>\s*(<[uo]l>)/g, "$1");
    html = html.replace(/(<\/[uo]l>)\s*<br>/g, "$1");

    return html;
  }

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
        csatEnabled = data.csat_enabled || false;
        csatTriggerAfter = data.csat_trigger_after || 5;

        // Wave 3 config
        customCss = data.custom_css || null;
        defaultLanguage = data.default_language || "en";
        supportedLanguages = data.supported_languages || ["en"];
        greetingVariants = data.greeting_variants || [];
        escalationTriggers = data.escalation_triggers || [];

        // Defaults for quick replies
        if (!quickReplies || quickReplies.length === 0) {
          quickReplies = ["How do I register?", "What programs do you offer?", "Do you offer financial aid?"];
        }

        applyConfig();
        showQuickReplies();
        showAwayIndicator();
        startTeaserTimer();
        injectCustomCss();
        applyGreetingVariant();
        applyWidgetPosition();
        applyLanguage();
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
    // Update welcome message
    if (!savedMessages.length) {
      var welcomeMsg = document.querySelector(".tbm-chat-message-assistant");
      if (welcomeMsg) {
        welcomeMsg.innerHTML = renderMarkdown(config.welcome_message);
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

  // --- Feature 16: Chat export / transcript ---
  function exportTranscript() {
    var messagesEl = document.querySelector(".tbm-chat-messages");
    if (!messagesEl) return;

    var lines = [];
    lines.push("Chat Transcript — " + (orgName || orgId));
    lines.push("Date: " + new Date().toLocaleString());
    lines.push("Session: " + sessionId);
    lines.push("---");
    lines.push("");

    messagesEl.querySelectorAll(".tbm-chat-message").forEach(function (el) {
      var role = el.classList.contains("tbm-chat-message-user") ? "You" : (orgName || "Bot");
      // Get text content, stripping HTML
      var tempDiv = document.createElement("div");
      tempDiv.innerHTML = el.innerHTML;
      // Remove feedback buttons, sources, suggestions from export
      tempDiv.querySelectorAll(".tbm-feedback, .tbm-chat-sources, .tbm-suggestions, .tbm-quick-replies").forEach(function (c) { c.remove(); });
      var text = tempDiv.textContent.trim();
      var time = new Date().toLocaleTimeString();
      lines.push("[" + role + "] " + text);
      lines.push("");
    });

    var blob = new Blob([lines.join("\n")], { type: "text/plain" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "chat-transcript-" + orgId + ".txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // --- Feature 12: CSAT survey ---
  function shouldShowCSAT() {
    if (!csatEnabled) return false;
    if (csatSubmitted) return false;
    if (!conversationId) return false;
    if (messageCount < csatTriggerAfter) return false;
    return true;
  }

  function showCSATPrompt() {
    var messagesEl = document.querySelector(".tbm-chat-messages");
    if (!messagesEl) return;
    // Don't show duplicate
    if (messagesEl.querySelector(".tbm-csat-prompt")) return;

    var csatDiv = document.createElement("div");
    csatDiv.className = "tbm-csat-prompt";
    csatDiv.innerHTML =
      '<div class="tbm-csat-title">How would you rate your experience?</div>' +
      '<div class="tbm-csat-stars">' +
        '<button class="tbm-csat-star" data-rating="1" title="1 star">&#9733;</button>' +
        '<button class="tbm-csat-star" data-rating="2" title="2 stars">&#9733;</button>' +
        '<button class="tbm-csat-star" data-rating="3" title="3 stars">&#9733;</button>' +
        '<button class="tbm-csat-star" data-rating="4" title="4 stars">&#9733;</button>' +
        '<button class="tbm-csat-star" data-rating="5" title="5 stars">&#9733;</button>' +
      '</div>' +
      '<div class="tbm-csat-thanks" style="display:none">Thanks for your feedback!</div>';

    csatDiv.querySelectorAll(".tbm-csat-star").forEach(function (star) {
      star.addEventListener("mouseenter", function () {
        var rating = parseInt(this.getAttribute("data-rating"));
        highlightStars(csatDiv, rating);
      });
      star.addEventListener("mouseleave", function () {
        highlightStars(csatDiv, 0);
      });
      star.addEventListener("click", function () {
        var rating = parseInt(this.getAttribute("data-rating"));
        submitCSAT(rating, csatDiv);
      });
    });

    messagesEl.appendChild(csatDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function highlightStars(container, rating) {
    container.querySelectorAll(".tbm-csat-star").forEach(function (star) {
      var starRating = parseInt(star.getAttribute("data-rating"));
      star.classList.toggle("tbm-csat-star-active", starRating <= rating);
    });
  }

  function submitCSAT(rating, container) {
    csatSubmitted = true;
    var starsDiv = container.querySelector(".tbm-csat-stars");
    var thanksDiv = container.querySelector(".tbm-csat-thanks");
    starsDiv.style.display = "none";
    thanksDiv.style.display = "block";

    fetch(apiBase + "/api/csat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        rating: rating,
      }),
    }).catch(function (err) {
      console.warn("TBM Chat Widget: CSAT submit failed", err);
    });

    persistState();
  }

  // --- Feature 25: Custom CSS injection ---
  function injectCustomCss() {
    if (!customCss) return;
    var style = document.createElement("style");
    style.setAttribute("data-tbm-custom", "true");
    style.textContent = customCss;
    document.head.appendChild(style);
  }

  // --- Feature 27: Greeting variants ---
  function applyGreetingVariant() {
    if (!greetingVariants || greetingVariants.length === 0) return;
    if (savedMessages.length > 0) return; // Don't change if restoring
    var variant = greetingVariants[Math.floor(Math.random() * greetingVariants.length)];
    var welcomeMsg = document.querySelector(".tbm-chat-message-assistant");
    if (welcomeMsg) {
      welcomeMsg.innerHTML = renderMarkdown(variant);
    }
  }

  // --- Feature 33: Widget position customization ---
  function applyWidgetPosition() {
    var wp = config.widget_position;
    if (!wp) return;
    var widget = document.querySelector(".tbm-chat-widget");
    if (!widget) return;
    var side = wp.side || "right";
    var bottomOffset = (wp.bottom_offset != null ? wp.bottom_offset : 20) + "px";
    var sideOffset = (wp.side_offset != null ? wp.side_offset : 20) + "px";

    widget.style.position = "fixed";
    widget.style.bottom = bottomOffset;
    if (side === "left") {
      widget.style.left = sideOffset;
      widget.style.right = "auto";
      widget.classList.add("tbm-position-left");
    } else {
      widget.style.right = sideOffset;
      widget.style.left = "auto";
      widget.classList.remove("tbm-position-left");
    }
  }

  // --- Feature 26: Multi-language support ---
  function applyLanguage() {
    var widget = document.querySelector(".tbm-chat-widget");
    if (widget && defaultLanguage) {
      widget.setAttribute("lang", defaultLanguage);
    }
    // Update placeholder based on language
    var input = document.querySelector(".tbm-chat-input");
    if (input && defaultLanguage !== "en") {
      var placeholders = {
        es: "Escribe tu mensaje...",
        fr: "Tapez votre message...",
        de: "Nachricht eingeben...",
        pt: "Digite sua mensagem...",
        it: "Scrivi il tuo messaggio...",
        zh: "输入您的消息...",
        ja: "メッセージを入力...",
        ko: "메시지를 입력하세요...",
        ar: "...اكتب رسالتك",
      };
      if (placeholders[defaultLanguage]) {
        input.placeholder = placeholders[defaultLanguage];
      }
    }
  }

  // --- Feature 23: Knowledge Base Article Browser ---
  function toggleArticlesPanel() {
    var panel = document.querySelector(".tbm-articles-panel");
    var chatMain = document.querySelector(".tbm-chat-main");
    if (!panel) return;
    articlesPanelOpen = !articlesPanelOpen;
    panel.style.display = articlesPanelOpen ? "flex" : "none";
    if (chatMain) chatMain.style.display = articlesPanelOpen ? "none" : "flex";
    if (articlesPanelOpen) loadArticles();
  }

  async function loadArticles(searchQuery) {
    var listEl = document.querySelector(".tbm-articles-list");
    if (!listEl) return;
    listEl.innerHTML = '<div class="tbm-articles-loading">Loading articles...</div>';
    try {
      var url = apiBase + "/api/tenants/" + orgId + "/articles";
      if (searchQuery) url += "?search=" + encodeURIComponent(searchQuery);
      var resp = await fetch(url);
      if (!resp.ok) throw new Error("Failed to load");
      var articles = await resp.json();
      if (articles.length === 0) {
        listEl.innerHTML = '<div class="tbm-articles-empty">No articles found.</div>';
        return;
      }
      listEl.innerHTML = "";
      // Group by category
      var categories = {};
      articles.forEach(function (a) {
        var cat = a.category || "General";
        if (!categories[cat]) categories[cat] = [];
        categories[cat].push(a);
      });
      Object.keys(categories).sort().forEach(function (cat) {
        var catHeader = document.createElement("div");
        catHeader.className = "tbm-articles-category";
        catHeader.textContent = cat;
        listEl.appendChild(catHeader);
        categories[cat].forEach(function (article) {
          var item = document.createElement("div");
          item.className = "tbm-articles-item";
          item.innerHTML =
            '<div class="tbm-articles-title">' + escapeHtml(article.title) + '</div>' +
            '<div class="tbm-articles-snippet">' + escapeHtml(article.snippet.substring(0, 120)) + '</div>';
          item.addEventListener("click", function () {
            if (article.source_url) {
              window.open(article.source_url, "_blank", "noopener");
            } else {
              // Insert as chat query
              toggleArticlesPanel();
              var inputEl = document.querySelector(".tbm-chat-input");
              if (inputEl) inputEl.value = "Tell me about: " + article.title;
              sendMessage();
            }
          });
          listEl.appendChild(item);
        });
      });
    } catch (e) {
      listEl.innerHTML = '<div class="tbm-articles-empty">Could not load articles.</div>';
    }
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
          '<div class="tbm-chat-header-actions">' +
            '<button class="tbm-chat-articles-btn" aria-label="Browse articles" title="Help articles"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg></button>' +
            '<button class="tbm-chat-export" aria-label="Download transcript" title="Download transcript">' +
              '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
            '</button>' +
            '<button class="tbm-chat-close" aria-label="Close chat">&times;</button>' +
          '</div>' +
        '</div>' +
        '<div class="tbm-away-indicator" style="display:none"></div>' +
        '<div class="tbm-articles-panel" style="display:none">' +
          '<div class="tbm-articles-header">' +
            '<input type="text" class="tbm-articles-search" placeholder="Search articles..." maxlength="200">' +
            '<button class="tbm-articles-back" aria-label="Back to chat">&larr; Chat</button>' +
          '</div>' +
          '<div class="tbm-articles-list"></div>' +
        '</div>' +
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
          '<div class="tbm-powered-by">AI support can make mistakes · Powered by TBM</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(container);

    // Event listeners
    var bubble = container.querySelector(".tbm-chat-bubble");
    var chatWindow = container.querySelector(".tbm-chat-window");
    var closeBtn = container.querySelector(".tbm-chat-close");
    var exportBtn = container.querySelector(".tbm-chat-export");
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

    // Feature 16: Export button
    exportBtn.addEventListener("click", exportTranscript);

    // Feature 23: Articles panel
    var articlesBtn = container.querySelector(".tbm-chat-articles-btn");
    if (articlesBtn) articlesBtn.addEventListener("click", toggleArticlesPanel);
    var articlesBack = container.querySelector(".tbm-articles-back");
    if (articlesBack) articlesBack.addEventListener("click", toggleArticlesPanel);
    var articlesSearch = container.querySelector(".tbm-articles-search");
    if (articlesSearch) {
      var searchTimeout = null;
      articlesSearch.addEventListener("input", function () {
        clearTimeout(searchTimeout);
        var q = articlesSearch.value.trim();
        searchTimeout = setTimeout(function () { loadArticles(q || undefined); }, 300);
      });
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    sendBtn.addEventListener("click", sendMessage);

    if (prechatSubmit) {
      prechatSubmit.addEventListener("click", handlePrechatSubmit);
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
    // Re-attach suggestion chip listeners
    messagesEl.querySelectorAll(".tbm-suggestion-chip").forEach(function (chip) {
      chip.addEventListener("click", handleSuggestionClick);
    });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // --- Feature 5: Quick reply buttons ---
  function showQuickReplies() {
    if (!quickReplies || quickReplies.length === 0) return;
    if (savedMessages.length > 0) return;

    var messagesEl = document.querySelector(".tbm-chat-messages");
    if (!messagesEl) return;

    var welcomeMsg = messagesEl.querySelector(".tbm-chat-message-assistant");
    if (!welcomeMsg) return;

    if (welcomeMsg.querySelector(".tbm-quick-replies")) return;

    var qrDiv = document.createElement("div");
    qrDiv.className = "tbm-quick-replies";
    quickReplies.forEach(function (text) {
      var btn = document.createElement("button");
      btn.className = "tbm-quick-reply-btn";
      btn.textContent = text;
      btn.addEventListener("click", function () {
        var allQr = document.querySelectorAll(".tbm-quick-replies");
        allQr.forEach(function (el) { el.remove(); });
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

    var fbDiv = btn.parentElement;
    fbDiv.querySelectorAll(".tbm-feedback-btn").forEach(function (b) {
      b.disabled = true;
      b.classList.remove("tbm-feedback-active");
    });
    btn.classList.add("tbm-feedback-active");

    fetch(apiBase + "/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, rating: rating }),
    }).catch(function (err) {
      console.warn("TBM Chat Widget: feedback failed", err);
    });

    persistState();
  }

  // --- Feature 13: Suggestion chips ---
  function addSuggestions(messageEl, suggestions) {
    if (!suggestions || suggestions.length === 0) return;
    var sugDiv = document.createElement("div");
    sugDiv.className = "tbm-suggestions";
    suggestions.forEach(function (text) {
      var chip = document.createElement("button");
      chip.className = "tbm-suggestion-chip";
      chip.textContent = text;
      chip.addEventListener("click", handleSuggestionClick);
      sugDiv.appendChild(chip);
    });
    messageEl.appendChild(sugDiv);
  }

  function handleSuggestionClick(e) {
    var text = e.currentTarget.textContent;
    // Remove all suggestion chips
    document.querySelectorAll(".tbm-suggestions").forEach(function (el) { el.remove(); });
    var inputEl = document.querySelector(".tbm-chat-input");
    if (inputEl) inputEl.value = text;
    sendMessage();
  }

  // --- Message handling ---
  function addMessage(role, content, sources, messageId, suggestions) {
    var messagesEl = document.querySelector(".tbm-chat-messages");
    var msg = document.createElement("div");
    msg.className = "tbm-chat-message tbm-chat-message-" + role;
    if (messageId) msg.setAttribute("data-message-id", messageId);

    // Feature 14: Rich message formatting for bot messages
    if (role === "assistant") {
      msg.innerHTML = renderMarkdown(content);
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

    // Feature 13: Add suggestion chips
    if (role === "assistant" && suggestions && suggestions.length > 0) {
      addSuggestions(msg, suggestions);
    }

    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    // Feature 4: Persist after each message
    persistState();
  }

  // --- Feature 15: Typing indicator (robust) ---
  function setTyping(visible) {
    var typing = document.querySelector(".tbm-chat-typing");
    if (!typing) return;

    // Clear any existing timeout
    if (typingTimeout) {
      clearTimeout(typingTimeout);
      typingTimeout = null;
    }

    typing.classList.toggle("tbm-visible", visible);
    if (visible) {
      var messagesEl = document.querySelector(".tbm-chat-messages");
      if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
      // Auto-hide after 30s safety timeout
      typingTimeout = setTimeout(function () {
        typing.classList.remove("tbm-visible");
      }, 30000);
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

    // Remove any existing suggestion chips when user sends a new message
    document.querySelectorAll(".tbm-suggestions").forEach(function (el) { el.remove(); });

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
      messageCount++;
      addMessage("assistant", data.response, data.sources, data.message_id, data.suggestions || []);

      // Feature 12: Check if we should show CSAT prompt
      if (shouldShowCSAT()) {
        setTimeout(function () { showCSATPrompt(); }, 1000);
      }
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
