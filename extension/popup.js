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
      modelStatus = "Load failed";
      modelHint = "Model folder exists, but the backend could not load it.";
      modelTone = "error";
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
        `${response.href} | modes: ${modeSummary.join(", ") || "none"} | launcher ${response.launcherVisible ? "visible" : "hidden"}${injected ? " | auto-injected" : ""}`,
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

    const currentSettings = await getStoredSettings();
    renderSettings(currentSettings);
    await refreshHealth(currentSettings.brainrotApiBaseUrl);
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
  }

  document.addEventListener("DOMContentLoaded", () => {
    initialize().catch((error) => {
      setNotice(error instanceof Error ? error.message : "Popup failed to initialize.", "error");
    });
  });
})();
