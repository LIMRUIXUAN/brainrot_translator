(function () {
  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const DEFAULT_SETTINGS = Object.freeze({
    brainrotApiBaseUrl: DEFAULT_API_BASE,
    brainrotEnableTextSelection: true,
    brainrotConfirmTextSelection: true,
    brainrotEnableHoverDetection: true,
    brainrotEnableLauncher: true,
    brainrotEnableClipboardPaste: true,
    brainrotLauncherPosition: null
  });

  const elements = {};

  function normalizeSettings(rawSettings) {
    const raw = rawSettings || {};
    const apiBase =
      typeof raw.brainrotApiBaseUrl === "string" && raw.brainrotApiBaseUrl.trim()
        ? raw.brainrotApiBaseUrl.trim()
        : DEFAULT_API_BASE;

    return {
      brainrotApiBaseUrl: apiBase.replace(/\/+$/, ""),
      brainrotEnableTextSelection:
        typeof raw.brainrotEnableTextSelection === "boolean"
          ? raw.brainrotEnableTextSelection
          : DEFAULT_SETTINGS.brainrotEnableTextSelection,
      brainrotConfirmTextSelection:
        typeof raw.brainrotConfirmTextSelection === "boolean"
          ? raw.brainrotConfirmTextSelection
          : DEFAULT_SETTINGS.brainrotConfirmTextSelection,
      brainrotEnableHoverDetection:
        typeof raw.brainrotEnableHoverDetection === "boolean"
          ? raw.brainrotEnableHoverDetection
          : DEFAULT_SETTINGS.brainrotEnableHoverDetection,
      brainrotEnableLauncher:
        typeof raw.brainrotEnableLauncher === "boolean"
          ? raw.brainrotEnableLauncher
          : DEFAULT_SETTINGS.brainrotEnableLauncher,
      brainrotEnableClipboardPaste:
        typeof raw.brainrotEnableClipboardPaste === "boolean"
          ? raw.brainrotEnableClipboardPaste
          : DEFAULT_SETTINGS.brainrotEnableClipboardPaste,
      brainrotLauncherPosition:
        raw.brainrotLauncherPosition &&
        Number.isFinite(raw.brainrotLauncherPosition.left) &&
        Number.isFinite(raw.brainrotLauncherPosition.top)
          ? {
              left: Math.round(raw.brainrotLauncherPosition.left),
              top: Math.round(raw.brainrotLauncherPosition.top)
            }
          : DEFAULT_SETTINGS.brainrotLauncherPosition
    };
  }

  function setNotice(message, tone) {
    elements.notice.textContent = message || "";
    elements.notice.className = "notice";
    if (tone) {
      elements.notice.classList.add(`is-${tone}`);
    }
  }

  function isValidApiBaseUrl(value) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch (error) {
      return false;
    }
  }

  function getStoredSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS), (result) => {
        resolve(normalizeSettings(result));
      });
    });
  }

  function setStoredSettings(nextSettings) {
    return new Promise((resolve) => {
      chrome.storage.local.set(nextSettings, () => resolve());
    });
  }

  function readFormSettings() {
    return normalizeSettings({
      brainrotApiBaseUrl: elements.apiBaseUrl.value,
      brainrotEnableTextSelection: elements.enableTextSelection.checked,
      brainrotConfirmTextSelection: elements.confirmTextSelection.checked,
      brainrotEnableHoverDetection: elements.enableHoverDetection.checked,
      brainrotEnableLauncher: elements.enableLauncher.checked,
      brainrotEnableClipboardPaste: elements.enableClipboardPaste.checked
    });
  }

  function renderSettings(settings) {
    elements.apiBaseUrl.value = settings.brainrotApiBaseUrl;
    elements.enableTextSelection.checked = settings.brainrotEnableTextSelection;
    elements.confirmTextSelection.checked = settings.brainrotConfirmTextSelection;
    elements.enableHoverDetection.checked = settings.brainrotEnableHoverDetection;
    elements.enableLauncher.checked = settings.brainrotEnableLauncher;
    elements.enableClipboardPaste.checked = settings.brainrotEnableClipboardPaste;
  }

  function setHealthCard(card, valueNode, hintNode, status, hint, tone) {
    card.className = "health-card";
    if (tone) {
      card.classList.add(`is-${tone}`);
    }
    valueNode.textContent = status;
    hintNode.textContent = hint;
  }

  function renderHealthSuccess(baseUrl, payload) {
    const localModelLoaded = Boolean(payload.local_text_model_loaded);
    const localModelAvailable = Boolean(payload.local_text_model_available);
    const qualityClassifierLoaded = Boolean(payload.local_quality_classifier_loaded);
    const qualityClassifierAvailable = Boolean(payload.local_quality_classifier_available);
    let modelStatus = "Fallback";
    let modelHint = "Text uses glossary fallback; image/GIF still requires OpenRouter.";
    let modelTone = "warn";

    if (localModelLoaded) {
      modelStatus = "Local model";
      modelHint = qualityClassifierLoaded
        ? "Text uses local FLAN-T5 plus the local confidence classifier."
        : "Text uses local FLAN-T5 with heuristic confidence.";
      modelTone = "ok";
      if (qualityClassifierAvailable && !qualityClassifierLoaded) {
        modelStatus = "Partial local";
        modelHint = "FLAN-T5 loaded, but the confidence classifier folder could not load.";
        modelTone = "warn";
      }
    } else if (localModelAvailable) {
      modelStatus = "Available";
      modelHint = "Local model folder found. It will load dynamically on first request.";
      modelTone = "ok";
    } else if (payload.openrouter_configured) {
      modelStatus = "OpenRouter";
      modelHint = "Text fallback and image/GIF analysis can use OpenRouter.";
      modelTone = "ok";
    }

    setHealthCard(
      elements.backendStatusCard,
      elements.backendStatusValue,
      elements.backendStatusHint,
      payload.status === "ok" ? "Reachable" : "Unexpected",
      `Target ${baseUrl}`,
      payload.status === "ok" ? "ok" : "warn"
    );
    setHealthCard(
      elements.modelStatusCard,
      elements.modelStatusValue,
      elements.modelStatusHint,
      modelStatus,
      modelHint,
      modelTone
    );
    setHealthCard(
      elements.databaseStatusCard,
      elements.databaseStatusValue,
      elements.databaseStatusHint,
      payload.database_configured ? "Connected" : "Unavailable",
      payload.database_configured
        ? "Review staging is ready for low-confidence corrections."
        : "Active learning writes are currently blocked.",
      payload.database_configured ? "ok" : "error"
    );
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeHistoryText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function truncateHistoryText(value, maxLength) {
    const text = normalizeHistoryText(value);
    if (text.length <= maxLength) return text;
    return `${text.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
  }

  function summarizeHistoryOriginal(entry, isImage) {
    const sourceUrl = normalizeHistoryText(entry?.source_url || "");
    const original = normalizeHistoryText(entry?.original || "");
    const displaySource = sourceUrl || original;
    if (!isImage) return truncateHistoryText(original, 90);
    if (!displaySource || displaySource === "Screenshot") return "Screenshot / captured image";
    if (displaySource.startsWith("data:")) return "Captured or pasted image data";

    try {
      const url = new URL(displaySource);
      const path = url.pathname && url.pathname !== "/" ? url.pathname : "";
      return `Image: ${truncateHistoryText(`${url.hostname}${path}`, 83)}`;
    } catch {
      return `Image: ${truncateHistoryText(displaySource, 83)}`;
    }
  }

  function setFrequencyStatus(message, tone) {
    const statusEl = document.getElementById("frequencyStatus");
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = "frequency-status";
    if (tone) {
      statusEl.classList.add(`is-${tone}`);
    }
  }

  function renderFrequencyBarChart(items) {
    const container = document.getElementById("barChartContainer");
    if (!container) return;

    if (!Array.isArray(items) || items.length === 0) {
      container.innerHTML = `<p style="text-align: center; color: #94a3b8; font-size: 13px; margin: 12px 0;">No slang terms recorded yet.</p>`;
      setFrequencyStatus("No terms logged.", null);
      return;
    }

    const maxCount = Math.max(...items.map(item => Number(item.count) || 1));
    
    container.innerHTML = items.map(item => {
      const term = escapeHtml(item.term || "Unknown");
      const count = Number(item.count) || 0;
      const percentage = Math.max(5, Math.round((count / maxCount) * 100));

      return `
        <div class="bar-chart-row">
          <span class="bar-chart-label" title="${term}">${term}</span>
          <div class="bar-chart-bar-outer">
            <div class="bar-chart-bar-inner" style="width: ${percentage}%"></div>
          </div>
          <span class="bar-chart-count">${count}</span>
        </div>
      `;
    }).join("");

    setFrequencyStatus(`Showing top ${items.length} slang terms.`, null);
  }

  async function refreshDashboardStats(baseUrl) {
    try {
      const response = await fetch(`${baseUrl}/api/v1/dashboard/stats`, { method: "GET" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || payload.error || "Failed to fetch dashboard stats.");

      const totalTextEl = document.getElementById("statTotalText");
      const totalImageEl = document.getElementById("statTotalImage");
      const uniqueTermsEl = document.getElementById("statUniqueTerms");

      if (totalTextEl) totalTextEl.textContent = payload.total_text_analyses ?? 0;
      if (totalImageEl) totalImageEl.textContent = payload.total_image_analyses ?? 0;
      if (uniqueTermsEl) uniqueTermsEl.textContent = payload.unique_terms ?? 0;

      const banner = document.getElementById("statTopTermBanner");
      if (banner) {
        if (payload.top_term) {
          const nameEl = document.getElementById("statTopTermName");
          const countEl = document.getElementById("statTopTermCount");
          if (nameEl) nameEl.textContent = payload.top_term;
          if (countEl) countEl.textContent = payload.top_term_count ?? 0;
          banner.style.display = "block";
        } else {
          banner.style.display = "none";
        }
      }
    } catch (error) {
      const totalTextEl = document.getElementById("statTotalText");
      const totalImageEl = document.getElementById("statTotalImage");
      const uniqueTermsEl = document.getElementById("statUniqueTerms");

      if (totalTextEl) totalTextEl.textContent = "-";
      if (totalImageEl) totalImageEl.textContent = "-";
      if (uniqueTermsEl) uniqueTermsEl.textContent = "-";
      const banner = document.getElementById("statTopTermBanner");
      if (banner) banner.style.display = "none";
    }
  }

  async function refreshFrequency(baseUrl) {
    setFrequencyStatus("Refreshing dashboard...", null);
    await refreshDashboardStats(baseUrl);

    try {
      const response = await fetch(`${baseUrl}/api/v1/dashboard/word-frequency?limit=10`, {
        method: "GET"
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || "Dashboard request failed.");
      }
      renderFrequencyBarChart(payload.items || []);
    } catch (error) {
      const container = document.getElementById("barChartContainer");
      if (container) {
        container.innerHTML = "";
      }
      setFrequencyStatus(error instanceof Error ? error.message : "Unable to load dashboard data.", "error");
    }
  }

  /* ── Phase 3: Translation History Manager ───────────────────── */
  async function renderHistory() {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotHistory: [] }, resolve);
    });
    const history = Array.isArray(result.brainrotHistory) ? result.brainrotHistory : [];
    const container = document.getElementById("historyListContainer");
    if (!container) return;

    if (history.length === 0) {
      container.innerHTML = `<p class="history-empty" style="text-align: center; color: #94a3b8; font-size: 13px; margin: 12px 0;">No history entries found.</p>`;
      return;
    }

    container.innerHTML = history.map((entry) => {
      const isImage = entry.type === "image";
      const date = entry.timestamp ? new Date(entry.timestamp) : new Date();
      const dateStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const fullOriginal = normalizeHistoryText(entry.original || "");
      const fullSourceUrl = normalizeHistoryText(entry.source_url || "");
      const fullTranslation = normalizeHistoryText(entry.translation || "");
      const original = escapeHtml(summarizeHistoryOriginal(entry, isImage));
      const translation = escapeHtml(truncateHistoryText(fullTranslation, 160));
      const sentiment = escapeHtml(entry.sentiment || "unclear");
      const confidence = Math.round((entry.confidence || 0) * 100);
      const originalTitle = escapeHtml(isImage && fullSourceUrl ? fullSourceUrl : fullOriginal);
      const translationTitle = escapeHtml(fullTranslation);
      
      const badgeClass = isImage ? "history-type-badge is-image" : "history-type-badge";
      const typeLabel = isImage ? "Image" : "Text";

      return `
        <div class="history-entry">
          <div class="history-header">
            <span class="history-time">${dateStr}</span>
            <span class="${badgeClass}">${typeLabel}</span>
          </div>
          <div class="history-content">
            <div class="history-original" title="${originalTitle}">"${original}"</div>
            <div class="history-arrow">⟶</div>
            <div class="history-translation" title="${translationTitle}">${translation}</div>
          </div>
          <div class="history-meta">
            <span class="history-chip">Sentiment: ${sentiment}</span>
            <span class="history-chip">Confidence: ${confidence}%</span>
          </div>
        </div>
      `;
    }).join("");
  }

  async function clearHistory() {
    if (!confirm("Are you sure you want to clear your translation log history?")) {
      return;
    }
    await new Promise((resolve) => {
      chrome.storage.local.set({ brainrotHistory: [] }, resolve);
    });
    await renderHistory();
  }

  /* ── Phase 9: Export & Share ────────────────────────────────── */
  function triggerDownload(content, filename, contentType) {
    const blob = new Blob([content], { type: contentType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function exportHistoryJson() {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotHistory: [] }, resolve);
    });
    const history = Array.isArray(result.brainrotHistory) ? result.brainrotHistory : [];
    if (history.length === 0) {
      alert("No history entries to export.");
      return;
    }
    const jsonStr = JSON.stringify(history, null, 2);
    triggerDownload(jsonStr, "brainrot_history.json", "application/json");
  }

  async function exportHistoryCsv() {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotHistory: [] }, resolve);
    });
    const history = Array.isArray(result.brainrotHistory) ? result.brainrotHistory : [];
    if (history.length === 0) {
      alert("No history entries to export.");
      return;
    }
    const headers = ["Timestamp", "Type", "Original", "Source URL", "Translation", "Sentiment", "Confidence", "Page URL", "Page Title"];
    const rows = history.map(entry => [
      entry.timestamp || "",
      entry.type || "text",
      entry.original || "",
      entry.source_url || "",
      entry.translation || "",
      entry.sentiment || "unclear",
      entry.confidence || 0,
      entry.page_url || "",
      entry.page_title || ""
    ]);
    const csvContent = [headers, ...rows]
      .map(row => row.map(val => `"${String(val).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    triggerDownload(csvContent, "brainrot_history.csv", "text/csv");
  }

  /* ── Phase 8: Custom dictionary / User glossary ────────────── */
  async function renderDictionary() {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotCustomDictionary: [] }, resolve);
    });
    const list = Array.isArray(result.brainrotCustomDictionary) ? result.brainrotCustomDictionary : [];
    const container = document.getElementById("dictionaryList");
    if (!container) return;

    if (list.length === 0) {
      container.innerHTML = `<li style="text-align: center; color: #94a3b8; font-size: 12px; padding: 12px 0;">No custom slang terms added yet.</li>`;
      return;
    }

    container.innerHTML = list.map((item, idx) => {
      const term = escapeHtml(item.term || "");
      const meaning = escapeHtml(item.meaning || "");
      return `
        <li class="dictionary-item" data-index="${idx}">
          <div class="dictionary-info">
            <div class="dictionary-term">${term}</div>
            <div class="dictionary-meaning">${meaning}</div>
          </div>
          <button type="button" class="dictionary-delete-btn" data-action="delete" title="Delete term">×</button>
        </li>
      `;
    }).join("");

    // Bind delete events
    container.querySelectorAll(".dictionary-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const itemEl = e.target.closest(".dictionary-item");
        if (!itemEl) return;
        const index = parseInt(itemEl.dataset.index, 10);
        await deleteDictionaryItem(index);
      });
    });
  }

  async function deleteDictionaryItem(index) {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotCustomDictionary: [] }, resolve);
    });
    const list = Array.isArray(result.brainrotCustomDictionary) ? result.brainrotCustomDictionary : [];
    list.splice(index, 1);
    await new Promise((resolve) => {
      chrome.storage.local.set({ brainrotCustomDictionary: list }, resolve);
    });
    await renderDictionary();
  }

  async function addDictionaryItem(term, meaning) {
    const result = await new Promise((resolve) => {
      chrome.storage.local.get({ brainrotCustomDictionary: [] }, resolve);
    });
    const list = Array.isArray(result.brainrotCustomDictionary) ? result.brainrotCustomDictionary : [];
    
    // Check for duplicate
    const lowered = term.trim().toLowerCase();
    const duplicateIdx = list.findIndex(item => item.term.toLowerCase() === lowered);
    if (duplicateIdx >= 0) {
      list[duplicateIdx].meaning = meaning.trim();
    } else {
      list.push({ term: term.trim(), meaning: meaning.trim() });
    }

    await new Promise((resolve) => {
      chrome.storage.local.set({ brainrotCustomDictionary: list }, resolve);
    });
    await renderDictionary();
  }


  function renderHealthError(baseUrl, message) {
    setHealthCard(
      elements.backendStatusCard,
      elements.backendStatusValue,
      elements.backendStatusHint,
      "Offline",
      `${baseUrl} did not answer /health.`,
      "error"
    );
    setHealthCard(
      elements.modelStatusCard,
      elements.modelStatusValue,
      elements.modelStatusHint,
      "Unknown",
      "The popup could not confirm OpenRouter availability.",
      "warn"
    );
    setHealthCard(
      elements.databaseStatusCard,
      elements.databaseStatusValue,
      elements.databaseStatusHint,
      "Unknown",
      "The popup could not confirm review staging.",
      "warn"
    );
    setNotice(message, "error");
    renderFrequencyError("Dashboard unavailable while the backend is offline.");
  }

  async function getActiveTab() {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });
    if (!tab?.id) {
      throw new Error("No active browser tab is available.");
    }
    return tab;
  }

  async function sendMessageToActiveTab(message) {
    const tab = await getActiveTab();
    return new Promise((resolve, reject) => {
      chrome.tabs.sendMessage(tab.id, message, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response);
      });
    });
  }

  function isScriptableUrl(url) {
    if (!url) {
      return false;
    }

    try {
      const parsed = new URL(url);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch (error) {
      return false;
    }
  }

  async function injectIntoActivePage() {
    const tab = await getActiveTab();
    if (!isScriptableUrl(tab.url)) {
      throw new Error("The active tab is a protected page. Use a normal http or https webpage.");
    }

    await chrome.scripting.insertCSS({
      target: { tabId: tab.id },
      files: ["pet_shell.css"]
    });
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["pet_bubble.js", "content_script.js"]
    });
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    return tab;
  }

  async function ensureActivePageConnection() {
    try {
      const response = await sendMessageToActiveTab({ action: "brainrotPing" });
      if (response?.ok) {
        return { response, injected: false };
      }
    } catch (error) {
      // Fall through to injection attempt.
    }

    await injectIntoActivePage();
    const response = await sendMessageToActiveTab({ action: "brainrotPing" });
    if (!response?.ok) {
      throw new Error("The content script still did not answer after injection.");
    }
    return { response, injected: true };
  }

  function renderPageStatus(status, hint, tone) {
    if (!elements.pageStatusCard) {
      return;
    }
    setHealthCard(
      elements.pageStatusCard,
      elements.pageStatusValue,
      elements.pageStatusHint,
      status,
      hint,
      tone
    );
  }

  async function checkActivePage() {
    renderPageStatus("Checking", "Waiting for the current tab to answer.", "warn");
    try {
      const { response, injected } = await ensureActivePageConnection();

      const modeSummary = [];
      if (response.settings?.brainrotEnableTextSelection) {
        modeSummary.push(
          response.settings?.brainrotConfirmTextSelection ? "text-confirm" : "text-auto"
        );
      }
      if (response.settings?.brainrotEnableHoverDetection) {
        modeSummary.push("hover");
      }
      if (response.settings?.brainrotEnableClipboardPaste) {
        modeSummary.push("paste");
      }
      renderPageStatus(
        "Connected",
        `Modes: ${modeSummary.join(", ") || "none"} | launcher ${response.launcherVisible ? "visible" : "hidden"}${injected ? " | auto-injected" : ""}`,
        "ok"
      );
      setNotice(
        injected
          ? "Content script was missing and has been injected into the active tab."
          : "Active tab is connected to the content script.",
        "success"
      );
    } catch (error) {
      renderPageStatus(
        "Not available",
        "Use a normal http or https webpage, then run the page check again.",
        "error"
      );
      setNotice(
        error instanceof Error ? error.message : "The active tab did not answer the content script probe.",
        "error"
      );
    }
  }

  async function showTestBubbleOnPage() {
    try {
      await ensureActivePageConnection();
      const response = await sendMessageToActiveTab({ action: "brainrotShowTestBubble" });
      if (!response?.ok) {
        throw new Error("The content script did not acknowledge the test bubble request.");
      }
      setNotice("Test bubble requested on the active page.", "success");
      renderPageStatus(
        "Connected",
        "A visible test bubble was sent to the current page.",
        "ok"
      );
    } catch (error) {
      renderPageStatus(
        "Not available",
        "Use a normal http or https webpage, then try the test bubble again.",
        "error"
      );
      setNotice(
        error instanceof Error ? error.message : "Unable to request a test bubble on the active page.",
        "error"
      );
    }
  }

  async function refreshHealth(baseUrl) {
    setNotice("Checking backend health...", null);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${baseUrl}/health`, {
        method: "GET",
        signal: controller.signal
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || "Backend health check failed.");
      }
      renderHealthSuccess(baseUrl, payload);
      await refreshFrequency(baseUrl);
      setNotice("Backend health check succeeded.", "success");
    } catch (error) {
      renderHealthError(
        baseUrl,
        error instanceof Error ? error.message : "Unable to reach the backend."
      );
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  async function saveSettings() {
    const nextSettings = normalizeSettings({
      ...(await getStoredSettings()),
      ...readFormSettings()
    });
    if (!isValidApiBaseUrl(nextSettings.brainrotApiBaseUrl)) {
      setNotice("API Base URL must be a valid http or https address.", "error");
      return;
    }

    await setStoredSettings(nextSettings);
    setNotice("Settings saved. Content scripts will pick them up immediately.", "success");
    await refreshHealth(nextSettings.brainrotApiBaseUrl);
  }

  async function resetDefaults() {
    renderSettings(DEFAULT_SETTINGS);
    await setStoredSettings({ ...DEFAULT_SETTINGS });
    setNotice("Defaults restored.", "success");
    await refreshHealth(DEFAULT_SETTINGS.brainrotApiBaseUrl);
  }

  async function saveBehaviorSettingsImmediately() {
    const currentSettings = await getStoredSettings();
    const nextSettings = normalizeSettings({
      ...currentSettings,
      brainrotEnableTextSelection: elements.enableTextSelection.checked,
      brainrotConfirmTextSelection: elements.confirmTextSelection.checked,
      brainrotEnableHoverDetection: elements.enableHoverDetection.checked,
      brainrotEnableLauncher: elements.enableLauncher.checked,
      brainrotEnableClipboardPaste: elements.enableClipboardPaste.checked
    });
    await setStoredSettings(nextSettings);
  }

  async function initialize() {
    elements.apiBaseUrl = document.getElementById("apiBaseUrl");
    elements.enableTextSelection = document.getElementById("enableTextSelection");
    elements.confirmTextSelection = document.getElementById("confirmTextSelection");
    elements.enableHoverDetection = document.getElementById("enableHoverDetection");
    elements.enableLauncher = document.getElementById("enableLauncher");
    elements.enableClipboardPaste = document.getElementById("enableClipboardPaste");
    elements.saveSettingsButton = document.getElementById("saveSettingsButton");
    elements.resetDefaultsButton = document.getElementById("resetDefaultsButton");
    elements.refreshHealthButton = document.getElementById("refreshHealthButton");
    elements.notice = document.getElementById("notice");
    elements.backendStatusCard = document.getElementById("backendStatusCard");
    elements.backendStatusValue = document.getElementById("backendStatusValue");
    elements.backendStatusHint = document.getElementById("backendStatusHint");
    elements.modelStatusCard = document.getElementById("modelStatusCard");
    elements.modelStatusValue = document.getElementById("modelStatusValue");
    elements.modelStatusHint = document.getElementById("modelStatusHint");
    elements.databaseStatusCard = document.getElementById("databaseStatusCard");
    elements.databaseStatusValue = document.getElementById("databaseStatusValue");
    elements.databaseStatusHint = document.getElementById("databaseStatusHint");
    elements.pageStatusCard = document.getElementById("pageStatusCard");
    elements.pageStatusValue = document.getElementById("pageStatusValue");
    elements.pageStatusHint = document.getElementById("pageStatusHint");
    elements.checkPageButton = document.getElementById("checkPageButton");
    elements.showTestBubbleButton = document.getElementById("showTestBubbleButton");
    elements.refreshFrequencyButton = document.getElementById("refreshStatsButton");
    elements.frequencyStatus = document.getElementById("frequencyStatus");
    
    elements.clearHistoryButton = document.getElementById("clearHistoryButton");
    elements.exportJsonButton = document.getElementById("exportJsonButton");
    elements.exportCsvButton = document.getElementById("exportCsvButton");
    elements.dictionaryForm = document.getElementById("dictionaryForm");
    elements.dictTermInput = document.getElementById("dictTermInput");
    elements.dictMeaningInput = document.getElementById("dictMeaningInput");

    const currentSettings = await getStoredSettings();
    renderSettings(currentSettings);
    await refreshHealth(currentSettings.brainrotApiBaseUrl);
    
    // Render History & Dictionary
    await renderHistory();
    await renderDictionary();

    if (elements.pageStatusCard) {
      await checkActivePage();
    }

    elements.saveSettingsButton.addEventListener("click", () => {
      saveSettings().catch((error) => {
        setNotice(error instanceof Error ? error.message : "Failed to save settings.", "error");
      });
    });
    elements.resetDefaultsButton.addEventListener("click", () => {
      resetDefaults().catch((error) => {
        setNotice(error instanceof Error ? error.message : "Failed to reset defaults.", "error");
      });
    });
    elements.refreshHealthButton.addEventListener("click", () => {
      const baseUrl = readFormSettings().brainrotApiBaseUrl;
      if (!isValidApiBaseUrl(baseUrl)) {
        setNotice("Enter a valid API Base URL before running a health check.", "error");
        return;
      }
      refreshHealth(baseUrl).catch(() => undefined);
    });
    elements.refreshFrequencyButton?.addEventListener("click", () => {
      const baseUrl = readFormSettings().brainrotApiBaseUrl;
      if (!isValidApiBaseUrl(baseUrl)) {
        setNotice("Enter a valid API Base URL before refreshing the dashboard.", "error");
        return;
      }
      refreshFrequency(baseUrl).catch(() => undefined);
    });
    elements.checkPageButton?.addEventListener("click", () => {
      checkActivePage().catch((error) => {
        setNotice(error instanceof Error ? error.message : "Failed to probe the active page.", "error");
      });
    });
    elements.showTestBubbleButton?.addEventListener("click", () => {
      showTestBubbleOnPage().catch((error) => {
        setNotice(error instanceof Error ? error.message : "Failed to show the test bubble.", "error");
      });
    });

    elements.clearHistoryButton?.addEventListener("click", () => {
      clearHistory().catch(() => undefined);
    });
    elements.exportJsonButton?.addEventListener("click", () => {
      exportHistoryJson().catch(() => undefined);
    });
    elements.exportCsvButton?.addEventListener("click", () => {
      exportHistoryCsv().catch(() => undefined);
    });
    
    elements.dictionaryForm?.addEventListener("submit", (e) => {
      e.preventDefault();
      const term = elements.dictTermInput.value;
      const meaning = elements.dictMeaningInput.value;
      if (term && meaning) {
        addDictionaryItem(term, meaning).then(() => {
          elements.dictTermInput.value = "";
          elements.dictMeaningInput.value = "";
        }).catch(() => undefined);
      }
    });

    [
      elements.enableTextSelection,
      elements.confirmTextSelection,
      elements.enableHoverDetection,
      elements.enableLauncher,
      elements.enableClipboardPaste
    ].forEach((checkbox) => {
      checkbox?.addEventListener("change", () => {
        saveBehaviorSettingsImmediately().catch((error) => {
          setNotice(
            error instanceof Error ? error.message : "Failed to update behavior setting.",
            "error"
          );
        });
      });
    });

    chrome.storage.onChanged?.addListener((changes, areaName) => {
      if (areaName !== "local") {
        return;
      }

      // Check settings changes
      const updated = {};
      let hasSettingsChange = false;
      for (const key of Object.keys(DEFAULT_SETTINGS)) {
        if (Object.prototype.hasOwnProperty.call(changes, key)) {
          updated[key] = changes[key].newValue;
          hasSettingsChange = true;
        }
      }

      if (hasSettingsChange) {
        getStoredSettings()
          .then((storedSettings) => {
            renderSettings({
              ...storedSettings,
              ...updated
            });
          })
          .catch(() => undefined);
      }

      // Live updates to History & Dictionary views if they change under us
      if (changes.brainrotHistory) {
        renderHistory().catch(() => undefined);
      }
      if (changes.brainrotCustomDictionary) {
        renderDictionary().catch(() => undefined);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initialize().catch((error) => {
      setNotice(error instanceof Error ? error.message : "Popup failed to initialize.", "error");
    });
  });
})();
