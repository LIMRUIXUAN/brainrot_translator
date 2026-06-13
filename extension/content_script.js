if (!window.__brainrotContentScriptLoaded) {
  window.__brainrotContentScriptLoaded = true;

  (function () {
  const Shared = window.BrainrotShared;
  const DEFAULT_API_BASE = Shared.DEFAULT_API_BASE;
  const TEXT_ENDPOINT = "/api/v1/analyze-highlighted-text";
  const RECHECK_TEXT_ENDPOINT = "/api/v1/recheck-highlighted-text";
  const MEDIA_ENDPOINT = "/api/v1/analyze-screenshot-media";
  const HOVER_DELAY_MS = 600;
  const DEFAULT_SETTINGS = Object.freeze({
    ...Shared.BASE_DEFAULT_SETTINGS,
    brainrotLauncherScale: 1,
    brainrotLauncherMinimized: false
  });
  const MIN_LAUNCHER_SCALE = 0.7;
  const MAX_LAUNCHER_SCALE = 1.5;
  const LAUNCHER_SCALE_STEP = 0.1;
  const MEME_HOSTS = [
    "tenor.com",
    "giphy.com",
    "media.giphy.com",
    "i.imgur.com",
    "i.redd.it",
    "cdn.discordapp.com"
  ];
  const BRAINROT_KEYWORDS = [
    "meme", "ratio", "sigma", "skill", "ohio", "npc", "cope",
    "skibidi", "grimace", "caught", "based", "slay", "rizz",
    "aura", "mid", "bffr", "ate"
  ];
  const BRAINROT_TERM_TRANSLATIONS = Object.freeze({
    aura: "social presence or personal energy",
    ate: "did something very well",
    based: "confident, authentic, or agreeable",
    bffr: "be serious or be realistic",
    caught: "exposed or found out",
    cope: "a weak excuse for losing or being wrong",
    grimace: "meme reference, often absurd or chaotic",
    meme: "internet joke or cultural reference",
    mid: "average or unimpressive",
    npc: "someone acting generic or unoriginal",
    ohio: "weird, cursed, or chaotic",
    ratio: "a reply getting more attention than the original post",
    rizz: "charisma or flirting ability",
    sigma: "self-styled independent or dominant person",
    skibidi: "absurd meme slang from Skibidi Toilet",
    skill: "ability, often used in 'skill issue'",
    slay: "to do something very well"
  });

  /* ── Phase 4: Retry / Rate-Limit / Dedup constants ───────────── */
  const MAX_RETRIES = 2;
  const BASE_RETRY_DELAY_MS = 1000;
  const RATE_LIMIT_COOLDOWN_MS = 3000;
  const inflightRequests = new Set();
  let lastRequestTimestamp = 0;

  const bubble = new window.BrainrotPetBubble();
  let hoverTimer = null;
  let activeElement = null;
  let launcher = null;
  let runtimeSettings = { ...DEFAULT_SETTINGS };
  let hoverRequestId = 0;
  let extensionContextInvalidated = false;
  let highlightedElements = new Set();

  /* ── Phase 8: Custom dictionary cache ────────────────────────── */
  let customDictionary = [];

  function loadCustomDictionary() {
    if (!hasLiveExtensionContext()) return;
    try {
      chrome.storage.local.get({ brainrotCustomDictionary: [] }, (result) => {
        if (getChromeLastError()) return;
        customDictionary = Array.isArray(result.brainrotCustomDictionary)
          ? result.brainrotCustomDictionary : [];
      });
    } catch (e) {
      markExtensionContextInvalidated(e);
    }
  }

  function lookupCustomDictionary(text) {
    const lowered = text.trim().toLowerCase();
    for (const entry of customDictionary) {
      if (entry.term && entry.term.toLowerCase() === lowered) {
        return entry;
      }
    }
    return null;
  }

  /* ── Offline Mode Fallback Glossary ─────────────────────────── */
  let offlineGlossary = [];

  function loadOfflineGlossary() {
    if (!hasLiveExtensionContext()) return;
    try {
      chrome.storage.local.get({ brainrotOfflineGlossary: [] }, (result) => {
        if (getChromeLastError()) return;
        offlineGlossary = Array.isArray(result.brainrotOfflineGlossary)
          ? result.brainrotOfflineGlossary : [];
      });
    } catch (e) {
      markExtensionContextInvalidated(e);
    }
  }

  function translateTextOffline(text) {
    return Shared.translateTextOffline(text, offlineGlossary);
  }

  /* ── Extension context helpers ───────────────────────────────── */
  function hasLiveExtensionContext() {
    if (extensionContextInvalidated) return false;
    try {
      return Boolean(chrome?.runtime?.id && chrome?.storage?.local);
    } catch (error) {
      extensionContextInvalidated = true;
      return false;
    }
  }

  function markExtensionContextInvalidated(error) {
    if (error instanceof Error && error.message.toLowerCase().includes("extension context invalidated")) {
      extensionContextInvalidated = true;
    }
  }

  function getChromeLastError() {
    try {
      return chrome?.runtime?.lastError || null;
    } catch (error) {
      markExtensionContextInvalidated(error);
      return null;
    }
  }

  function getDebugAnchor() {
    if (launcher && launcher.isConnected) return launcher;
    return new DOMRect(window.innerWidth / 2, 120, 1, 1);
  }

  /* ── Settings ────────────────────────────────────────────────── */
  function normalizeSettings(rawSettings) {
    return Shared.normalizeSettings(rawSettings, {
      defaults: DEFAULT_SETTINGS,
      clampLauncherScale
    });
  }

  function clampLauncherScale(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return DEFAULT_SETTINGS.brainrotLauncherScale;
    return Math.min(MAX_LAUNCHER_SCALE, Math.max(MIN_LAUNCHER_SCALE, Math.round(numeric * 10) / 10));
  }

  async function readSettings() {
    if (!hasLiveExtensionContext()) return { ...DEFAULT_SETTINGS };
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS), (result) => {
          const lastError = getChromeLastError();
          if (lastError) { markExtensionContextInvalidated(lastError); resolve({ ...DEFAULT_SETTINGS }); return; }
          resolve(normalizeSettings(result));
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        resolve({ ...DEFAULT_SETTINGS });
      }
    });
  }

  async function writeSettings(partialSettings) {
    const nextSettings = normalizeSettings({ ...runtimeSettings, ...(partialSettings || {}) });
    if (!hasLiveExtensionContext()) {
      runtimeSettings = nextSettings;
      refreshLauncherState();
      return nextSettings;
    }
    return new Promise((resolve) => {
      try {
        chrome.storage.local.set(nextSettings, () => {
          const lastError = getChromeLastError();
          if (lastError) markExtensionContextInvalidated(lastError);
          runtimeSettings = nextSettings;
          refreshLauncherState();
          resolve(nextSettings);
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        runtimeSettings = nextSettings;
        refreshLauncherState();
        resolve(nextSettings);
      }
    });
  }

  async function getApiBaseUrl() {
    return runtimeSettings.brainrotApiBaseUrl || DEFAULT_API_BASE;
  }

  function buildApiHeaders() {
    return Shared.buildApiHeaders(runtimeSettings, true);
  }

  function hasOpenRouterApiKey() {
    return Shared.hasOpenRouterApiKey(runtimeSettings);
  }

  function getApiErrorMessage(response, body) {
    return Shared.getApiErrorMessage(response, body, "Backend request failed.");
  }

  function shouldRetryApiError(error) {
    return Shared.shouldRetryApiError(error);
  }

  function sendAnonymousSlangDetections(result) {
    Shared.sendAnonymousSlangDetections(runtimeSettings, result).catch(() => undefined);
  }

  function sendRuntimeMessage(message) {
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage(message, (response) => {
          const lastError = getChromeLastError();
          if (lastError) {
            reject(new Error(lastError.message || "Extension message failed."));
            return;
          }
          resolve(response || { ok: false });
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        reject(error);
      }
    });
  }

  async function runOpenRouterTextAnalysis(payload) {
    const response = await sendRuntimeMessage({
      action: "brainrotOpenRouterTextAnalysis",
      payload,
      settings: runtimeSettings
    });
    if (!response?.ok) {
      throw new Error(response?.error || "OpenRouter text analysis failed.");
    }
    return response.result;
  }

  async function runTextAnalysisBackendFirst(payload) {
    try {
      return await postJson(TEXT_ENDPOINT, payload);
    } catch (error) {
      const message = String(error?.message || "").toLowerCase();
      const needsOpenRouter = message.includes("openrouter api key");
      if (needsOpenRouter && hasOpenRouterApiKey()) {
        return await runOpenRouterTextAnalysis(payload);
      }
      throw error;
    }
  }

  async function runOpenRouterRecheck(payload) {
    const response = await sendRuntimeMessage({
      action: "brainrotOpenRouterTextAnalysis",
      payload,
      settings: runtimeSettings
    });
    if (!response?.ok) {
      throw new Error(response?.error || "OpenRouter text recheck failed.");
    }
    return response.result;
  }

  async function runOpenRouterImageAnalysis(payload) {
    const response = await sendRuntimeMessage({
      action: "brainrotOpenRouterImageAnalysis",
      payload,
      settings: runtimeSettings
    });
    if (!response?.ok) {
      throw new Error(response?.error || "OpenRouter image analysis failed.");
    }
    return response.result;
  }

  /* ── Phase 1: Page context helpers ───────────────────────────── */
  function getPageContext() {
    return {
      page_title: document.title || null,
      page_domain: window.location.hostname || null,
      page_url: window.location.href
    };
  }

  function getNearestHeading(range) {
    if (!range) return null;
    let node = range.commonAncestorContainer;
    if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
    while (node && node !== document.body) {
      const heading = node.querySelector("h1, h2, h3, h4");
      if (heading) return heading.textContent?.trim()?.slice(0, 200) || null;
      node = node.parentElement;
    }
    const pageH1 = document.querySelector("h1");
    return pageH1 ? pageH1.textContent?.trim()?.slice(0, 200) || null : null;
  }

  /* ── Phase 4: Retry wrapper with exponential backoff ─────────── */
  async function postJsonWithRetry(path, payload) {
    // Rate limit check
    const now = Date.now();
    if (now - lastRequestTimestamp < RATE_LIMIT_COOLDOWN_MS) {
      const requestKey = JSON.stringify(payload).slice(0, 200);
      if (inflightRequests.has(requestKey)) {
        throw new Error("Duplicate request — please wait a moment.");
      }
    }
    lastRequestTimestamp = Date.now();

    // Offline check
    if (!navigator.onLine) {
      throw new Error("You appear to be offline. Check your connection and try again.");
    }

    const base = await getApiBaseUrl();
    let lastError = null;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${base}${path}`, {
          method: "POST",
          headers: buildApiHeaders(),
          body: JSON.stringify(payload)
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(getApiErrorMessage(response, body));
        }
        return body;
      } catch (error) {
        lastError = error;
        if (!shouldRetryApiError(error)) {
          throw error;
        }
        if (attempt < MAX_RETRIES) {
          const delay = BASE_RETRY_DELAY_MS * Math.pow(2, attempt);
          await new Promise(r => setTimeout(r, delay));
        }
      }
    }
    throw lastError || new Error("Request failed after retries.");
  }

  // Keep legacy postJson as alias for non-retryable calls
  async function postJson(path, payload) {
    return postJsonWithRetry(path, payload);
  }

  /* ── Phase 3: History helper ─────────────────────────────────── */
  function saveToHistory(entry) {
    if (!hasLiveExtensionContext()) return;
    try {
      chrome.runtime.sendMessage({
        action: "brainrotSaveHistory",
        entry: {
          timestamp: new Date().toISOString(),
          type: entry.type || "text",
          original: entry.original || "",
          translation: entry.translation || "",
          sentiment: entry.sentiment || "unclear",
          confidence: entry.confidence || 0,
          source_url: entry.source_url || "",
          page_url: window.location.href,
          page_title: document.title || "",
          model_used: entry.model_used || ""
        }
      });
    } catch (e) {
      // Ignore — extension context may be gone
    }
  }

  function incrementBrainrotBadge(amount = 1) {
    if (!hasLiveExtensionContext()) return;
    try {
      const count = Math.max(1, Math.floor(Number(amount) || 1));
      chrome.runtime.sendMessage({ action: "brainrotIncrementBadge", amount: count });
    } catch (e) {
      // Ignore badge failures so analysis output still appears.
    }
  }

  function escapeRegExp(value) {
    return Shared.escapeRegExp(value);
  }

  function buildScanTermMap() {
    const terms = new Map();
    for (const keyword of BRAINROT_KEYWORDS) {
      const normalized = keyword.toLowerCase();
      terms.set(normalized, {
        term: keyword,
        meaning: BRAINROT_TERM_TRANSLATIONS[normalized] || "Recognized brainrot slang"
      });
    }
    for (const entry of customDictionary) {
      const term = String(entry?.term || "").trim();
      const meaning = String(entry?.meaning || "").trim();
      if (term && meaning) {
        terms.set(term.toLowerCase(), { term, meaning });
      }
    }
    return terms;
  }

  function shouldScanTextNode(node) {
    if (!node?.textContent?.trim()) return false;
    const parent = node.parentElement;
    if (!parent) return false;
    if (parent.closest("#brainrot-floating-launcher, #brainrot-pet-bubble, .brainrot-inline-highlight, .brainrot-inline-annotation")) {
      return false;
    }
    if (parent.closest("script, style, noscript, textarea, input, select, option, button")) {
      return false;
    }
    if (parent.isContentEditable) return false;
    const style = window.getComputedStyle(parent);
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
  }

  function createScanRegex(termMap) {
    const terms = Array.from(termMap.keys()).sort((a, b) => b.length - a.length);
    if (terms.length === 0) return null;
    return new RegExp(`\\b(${terms.map(escapeRegExp).join("|")})\\b`, "gi");
  }

  function wrapBrainrotMatches(textNode, regex, termMap) {
    const text = textNode.textContent || "";
    let match = null;
    let lastIndex = 0;
    let count = 0;
    const fragment = document.createDocumentFragment();

    regex.lastIndex = 0;
    while ((match = regex.exec(text)) !== null) {
      const matchedText = match[0];
      const termInfo = termMap.get(matchedText.toLowerCase());
      if (!termInfo) continue;

      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }

      const span = document.createElement("span");
      span.className = "brainrot-inline-highlight";
      span.dataset.brainrotTerm = termInfo.term;
      span.dataset.brainrotMeaning = termInfo.meaning;
      span.textContent = matchedText;
      fragment.appendChild(span);
      highlightedElements.add(span);
      count += 1;
      lastIndex = match.index + matchedText.length;
    }

    if (count === 0) return 0;
    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
    textNode.parentNode?.replaceChild(fragment, textNode);
    return count;
  }

  function clearPageHighlights() {
    const spans = Array.from(document.querySelectorAll(".brainrot-inline-highlight, .brainrot-inline-annotation"));
    for (const span of spans) {
      const parent = span.parentNode;
      if (!parent) continue;
      parent.replaceChild(document.createTextNode(span.textContent || ""), span);
      parent.normalize?.();
    }
    highlightedElements.clear();
    return spans.length;
  }

  async function scanPageForBrainrot() {
    clearPageHighlights();
    const termMap = buildScanTermMap();
    const regex = createScanRegex(termMap);
    if (!regex) return 0;

    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      { acceptNode: (node) => shouldScanTextNode(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT }
    );
    const nodes = [];
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    let index = 0;
    let count = 0;
    await new Promise((resolve) => {
      const processChunk = (deadline) => {
        const startedAt = performance.now();
        while (index < nodes.length) {
          count += wrapBrainrotMatches(nodes[index], regex, termMap);
          index += 1;
          const hasIdleTime = !deadline || deadline.timeRemaining?.() > 3;
          if (!hasIdleTime || performance.now() - startedAt > 12) break;
        }
        if (index < nodes.length) {
          if ("requestIdleCallback" in window) {
            window.requestIdleCallback(processChunk, { timeout: 250 });
          } else {
            window.setTimeout(processChunk, 16);
          }
          return;
        }
        resolve();
      };

      if ("requestIdleCallback" in window) {
        window.requestIdleCallback(processChunk, { timeout: 250 });
      } else {
        window.setTimeout(processChunk, 0);
      }
    });

    if (count > 0) {
      incrementBrainrotBadge(count);
    }
    return count;
  }

  /* ── Media helpers (unchanged core logic) ────────────────────── */
  function getMediaUrl(element) {
    if (!element) return null;
    if (element.tagName === "IMG") return element.currentSrc || element.src || null;
    const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
    const match = backgroundImage.match(/url\(["']?(.*?)["']?\)/i);
    return match ? match[1] : null;
  }

  function getMediaType(url) {
    const normalized = (url || "").toLowerCase();
    if (normalized.endsWith(".gif") || normalized.includes("format=gif")) return "image/gif";
    if (normalized.endsWith(".png")) return "image/png";
    if (normalized.endsWith(".webp")) return "image/webp";
    return "image/jpeg";
  }

  function hasMemeHost(url) {
    try {
      const hostname = new URL(url, window.location.href).hostname.toLowerCase();
      return MEME_HOSTS.some((host) => hostname.includes(host));
    } catch (error) { return false; }
  }

  function hasKeywordHint(url) {
    const normalized = (url || "").toLowerCase();
    return BRAINROT_KEYWORDS.some((keyword) => normalized.includes(keyword));
  }

  function hasMemeLikeAspectRatio(element) {
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    if (rect.width < 100 || rect.height < 100) return false;
    return true;
  }

  function isMemeCandidate(element) {
    const url = getMediaUrl(element);
    if (!url) return false;
    return hasMemeHost(url) || hasKeywordHint(url) || hasMemeLikeAspectRatio(element);
  }

  function clampCaptureCoordinate(value, maxValue) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0;
    return Math.min(Math.max(numeric, 0), Math.max(0, maxValue));
  }

  function normalizeCaptureRect(startX, startY, endX, endY, viewportWidth = window.innerWidth, viewportHeight = window.innerHeight) {
    const x1 = clampCaptureCoordinate(startX, viewportWidth);
    const y1 = clampCaptureCoordinate(startY, viewportHeight);
    const x2 = clampCaptureCoordinate(endX, viewportWidth);
    const y2 = clampCaptureCoordinate(endY, viewportHeight);
    const left = Math.min(x1, x2);
    const top = Math.min(y1, y2);
    const width = Math.abs(x2 - x1);
    const height = Math.abs(y2 - y1);
    return { left, top, width, height };
  }

  function isUsableCaptureRect(rect) {
    return Boolean(rect && rect.width >= 8 && rect.height >= 8);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      normalizeSettings,
      buildApiHeaders,
      clampLauncherScale,
      isMemeCandidate,
      hasKeywordHint,
      lookupCustomDictionary,
      getMediaType,
      getGifFrameExtractionSource,
      normalizeCaptureRect,
      isUsableCaptureRect,
      translateTextOffline,
      setOfflineGlossaryForTest(entries) {
        offlineGlossary = Array.isArray(entries) ? entries : [];
      },
      setCustomDictionaryForTest(entries) {
        customDictionary = Array.isArray(entries) ? entries : [];
      }
    };
    return;
  }

  function dataUrlToBase64(dataUrl) {
    const [, payload = ""] = dataUrl.split(",", 2);
    return payload;
  }

  async function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Failed to read file."));
      reader.readAsDataURL(file);
    });
  }

  async function loadImageFromSource(src) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("Unable to decode image preview."));
      image.src = src;
    });
  }

  function getGifFrameExtractionSource(fetched, sourceUrl) {
    return fetched?.dataUrl || sourceUrl;
  }

  async function buildFirstFrameFromSource(src, fallbackWidth = 320, fallbackHeight = 180) {
    const image = await loadImageFromSource(src);
    const canvas = document.createElement("canvas");
    const width = image.naturalWidth || fallbackWidth;
    const height = image.naturalHeight || fallbackHeight;
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable for GIF fallback extraction.");
    context.drawImage(image, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    return { dataUrl, base64: dataUrlToBase64(dataUrl), mediaType: "image/jpeg" };
  }

  async function tryBuildFirstFrameFromSource(src) {
    try {
      return await buildFirstFrameFromSource(src);
    } catch (error) {
      return null;
    }
  }

  async function fetchMediaAsset(url) {
    return new Promise((resolve, reject) => {
      if (!hasLiveExtensionContext()) {
        reject(new Error("Extension was reloaded. Refresh this page before using media analysis."));
        return;
      }
      try {
        chrome.runtime.sendMessage({ action: "fetchMediaAsset", url }, (response) => {
          const lastError = getChromeLastError();
          if (lastError) { markExtensionContextInvalidated(lastError); reject(new Error(lastError.message)); return; }
          if (!response?.ok) { reject(new Error(response?.error || "Unable to fetch media asset.")); return; }
          resolve(response);
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        reject(error instanceof Error ? error : new Error("Media fetch failed."));
      }
    });
  }

  async function captureVisibleTab() {
    return new Promise((resolve, reject) => {
      if (!hasLiveExtensionContext()) {
        reject(new Error("Extension was reloaded. Refresh this page before using capture."));
        return;
      }
      try {
        chrome.runtime.sendMessage({ action: "captureVisibleTab" }, (response) => {
          const lastError = getChromeLastError();
          if (lastError) { markExtensionContextInvalidated(lastError); reject(new Error(lastError.message)); return; }
          if (!response?.ok) { reject(new Error(response?.error || "Unable to capture screenshot.")); return; }
          resolve(response.dataUrl);
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        reject(error instanceof Error ? error : new Error("Screenshot capture failed."));
      }
    });
  }

  async function cropDataUrlToRect(dataUrl, rect) {
    const image = await loadImageFromSource(dataUrl);
    const viewportWidth = Math.max(1, window.innerWidth || rect.width);
    const viewportHeight = Math.max(1, window.innerHeight || rect.height);
    const scaleX = (image.naturalWidth || viewportWidth) / viewportWidth;
    const scaleY = (image.naturalHeight || viewportHeight) / viewportHeight;
    const sourceX = Math.max(0, Math.round(rect.left * scaleX));
    const sourceY = Math.max(0, Math.round(rect.top * scaleY));
    const sourceWidth = Math.min(
      Math.max(1, Math.round(rect.width * scaleX)),
      Math.max(1, (image.naturalWidth || viewportWidth) - sourceX)
    );
    const sourceHeight = Math.min(
      Math.max(1, Math.round(rect.height * scaleY)),
      Math.max(1, (image.naturalHeight || viewportHeight) - sourceY)
    );

    const canvas = document.createElement("canvas");
    canvas.width = sourceWidth;
    canvas.height = sourceHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas is unavailable for screenshot cropping.");
    context.drawImage(
      image,
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight,
      0,
      0,
      sourceWidth,
      sourceHeight
    );
    return canvas.toDataURL("image/png");
  }

  function updateCaptureSelectionBox(selection, rect) {
    selection.style.left = `${rect.left}px`;
    selection.style.top = `${rect.top}px`;
    selection.style.width = `${rect.width}px`;
    selection.style.height = `${rect.height}px`;
  }

  async function requestCaptureRegion() {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.id = "brainrot-capture-overlay";
      overlay.innerHTML = `
        <div class="brainrot-capture-toolbar">Select area</div>
        <div class="brainrot-capture-selection" hidden></div>
      `;
      document.body.appendChild(overlay);

      const selection = overlay.querySelector(".brainrot-capture-selection");
      let start = null;
      let cleanedUp = false;

      function cleanup(result) {
        if (cleanedUp) return;
        cleanedUp = true;
        window.removeEventListener("keydown", onKeyDown, true);
        overlay.remove();
        resolve(result);
      }

      function onKeyDown(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          cleanup(null);
        }
      }

      overlay.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        start = { x: event.clientX, y: event.clientY };
        const rect = normalizeCaptureRect(start.x, start.y, event.clientX, event.clientY);
        selection.hidden = false;
        updateCaptureSelectionBox(selection, rect);
        overlay.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });

      overlay.addEventListener("pointermove", (event) => {
        if (!start) return;
        updateCaptureSelectionBox(
          selection,
          normalizeCaptureRect(start.x, start.y, event.clientX, event.clientY)
        );
      });

      overlay.addEventListener("pointerup", (event) => {
        if (!start) return;
        const rect = normalizeCaptureRect(start.x, start.y, event.clientX, event.clientY);
        start = null;
        cleanup(isUsableCaptureRect(rect) ? rect : null);
      });

      overlay.addEventListener("pointercancel", () => {
        start = null;
        cleanup(null);
      });

      window.addEventListener("keydown", onKeyDown, true);
    });
  }

  async function createCroppedVisibleTabPayload(hiddenElement) {
    const previousVisibility = hiddenElement?.style?.visibility;
    if (hiddenElement?.style) {
      hiddenElement.style.visibility = "hidden";
    }

    try {
      const rect = await requestCaptureRegion();
      if (!rect) return null;
      const screenshotDataUrl = await captureVisibleTab();
      const croppedDataUrl = await cropDataUrlToRect(screenshotDataUrl, rect);
      const ctx = getPageContext();
      return {
        image_base64: dataUrlToBase64(croppedDataUrl),
        media_type: "image/png",
        source_url: window.location.href,
        frame0_base64: null,
        frame0_media_type: null,
        previewSrc: croppedDataUrl,
        page_title: ctx.page_title,
        page_domain: ctx.page_domain
      };
    } finally {
      if (hiddenElement?.style) {
        hiddenElement.style.visibility = previousVisibility || "";
      }
    }
  }

  async function createMediaUrlPayload(sourceUrl) {
    if (!sourceUrl) throw new Error("Media URL not found.");
    const mediaType = getMediaType(sourceUrl);
    const fetched = await fetchMediaAsset(sourceUrl);
    const ctx = getPageContext();
    const payload = {
      image_base64: fetched.base64, media_type: mediaType, source_url: sourceUrl,
      previewSrc: fetched.dataUrl || sourceUrl, frame0_base64: null, frame0_media_type: null,
      page_title: ctx.page_title, page_domain: ctx.page_domain
    };
    if (mediaType === "image/gif") {
      const firstFrame = await tryBuildFirstFrameFromSource(
        getGifFrameExtractionSource(fetched, sourceUrl)
      );
      if (firstFrame) {
        payload.frame0_base64 = firstFrame.base64;
        payload.frame0_media_type = firstFrame.mediaType;
        payload.previewSrc = firstFrame.dataUrl;
      }
    }
    return payload;
  }

  async function createHoverPayload(element) {
    return createMediaUrlPayload(getMediaUrl(element));
  }

  async function createFilePayload(file) {
    const dataUrl = await fileToDataUrl(file);
    const ctx = getPageContext();
    const payload = {
      image_base64: dataUrlToBase64(dataUrl), media_type: file.type || "image/jpeg",
      source_url: null, previewSrc: dataUrl, frame0_base64: null, frame0_media_type: null,
      page_title: ctx.page_title, page_domain: ctx.page_domain
    };
    if (payload.media_type === "image/gif") {
      const firstFrame = await tryBuildFirstFrameFromSource(dataUrl);
      if (firstFrame) {
        payload.frame0_base64 = firstFrame.base64;
        payload.frame0_media_type = firstFrame.mediaType;
        payload.previewSrc = firstFrame.dataUrl;
      }
    }
    return payload;
  }

  async function analyzeMediaPayload(anchor, payload) {
    if (!hasOpenRouterApiKey()) {
      throw new Error("OpenRouter API key is required for image analysis. Add your key in Settings.");
    }

    bubble.showLoadingState(anchor, "Analyzing image...");
    try {
      const result = await runOpenRouterImageAnalysis({
        image_base64: payload.image_base64, media_type: payload.media_type,
        image_model_tier: runtimeSettings.brainrotImageModelTier,
        source_url: payload.source_url, frame0_base64: payload.frame0_base64,
        frame0_media_type: payload.frame0_media_type,
        page_title: payload.page_title, page_domain: payload.page_domain
      });
      if (!result.is_brainrot) { bubble.hide(); return; }
      incrementBrainrotBadge();
      sendAnonymousSlangDetections(result);
      bubble.showImageAnalysisResult(anchor, result, payload.previewSrc);
      // Phase 3: Save image analysis to history
      saveToHistory({
        type: "image",
        original: payload.source_url || "Screenshot",
        source_url: payload.source_url || "",
        translation: result.brainrot_meaning || result.equivalent_text || "",
        sentiment: "neutral",
        confidence: result.confidence_score || 0
      });
    } catch (error) {
      const errMsg = String(error?.message || "").toLowerCase();
      const isMissingOpenRouterKey = errMsg.includes("openrouter api key");
      const isConnectionFailure =
        errMsg.includes("failed to fetch") ||
        errMsg.includes("networkerror") ||
        errMsg.includes("unreachable") ||
        errMsg.includes("timeout") ||
        errMsg.includes("connection") ||
        errMsg.includes("offline") ||
        error instanceof TypeError;

      if (isConnectionFailure) {
        throw new Error("Connection offline: image analysis requires OpenRouter access.");
      } else {
        throw error;
      }
    }
  }

  /* ── Text analysis ───────────────────────────────────────────── */
  function getSelectionData() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return null;
    const text = selection.toString().trim();
    if (!text) return null;
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    return {
      selectedText: text,
      surroundingText: range.commonAncestorContainer?.textContent?.trim()?.slice(0, 280) || null,
      nearestHeading: getNearestHeading(range),
      rect,
      range: range.cloneRange()
    };
  }

  function annotateSelectionInline(selectionData, result) {
    if (!runtimeSettings.brainrotEnableInlineAnnotation) return false;
    const translation = String(result.equivalent_text || result.formal_explanation || "").trim();
    if (!translation || !selectionData?.range) return false;

    const range = selectionData.range.cloneRange();
    if (range.collapsed) {
      return false;
    }

    const commonNode = range.commonAncestorContainer;
    const parentElement = commonNode.nodeType === Node.TEXT_NODE
      ? commonNode.parentElement
      : commonNode instanceof Element
        ? commonNode
        : commonNode.parentElement;
    if (!parentElement || parentElement.closest(".brainrot-inline-annotation, .brainrot-inline-highlight")) {
      return false;
    }

    const span = document.createElement("span");
    span.className = "brainrot-inline-annotation";
    span.dataset.translation = translation.slice(0, 280);
    span.dataset.confidence = String(Math.round((Number(result.confidence_score) || 0) * 100));

    try {
      const contents = range.extractContents();
      span.appendChild(contents);
      range.insertNode(span);
      window.getSelection()?.removeAllRanges();
      highlightedElements.add(span);
      return true;
    } catch (error) {
      span.remove();
      return false;
    }
  }

  async function runSelectionAnalysis(selectionData) {
    /* Phase 8: Check custom dictionary first */
    const customMatch = lookupCustomDictionary(selectionData.selectedText);
    if (customMatch) {
      const fakeResult = {
        is_brainrot: true,
        brainrot_text: customMatch.term,
        equivalent_text: customMatch.meaning,
        formal_explanation: "Matched from your custom dictionary.",
        sentiment_label: "neutral",
        confidence_score: 1.0,
        flagged_for_review: false,
        model_used: "custom_dictionary"
      };
      const annotated = annotateSelectionInline(selectionData, fakeResult);
      if (annotated) {
        bubble.hide();
      } else {
        bubble.showTextAnalysisResult(selectionData.rect, fakeResult, selectionData.selectedText, async () => {
          await runSelectionRecheck(selectionData);
        });
      }
      saveToHistory({
        type: "text", original: selectionData.selectedText,
        translation: customMatch.meaning, sentiment: "neutral", confidence: 1.0
      });
      incrementBrainrotBadge();
      sendAnonymousSlangDetections(fakeResult);
      return;
    }

    bubble.showLoadingState(selectionData.rect, "Translating highlighted text...");
    const ctx = getPageContext();
    try {
      const requestPayload = {
        selected_text: selectionData.selectedText,
        page_url: ctx.page_url,
        text_model_tier: runtimeSettings.brainrotTextModelTier,
        surrounding_text: selectionData.surroundingText,
        page_title: ctx.page_title,
        page_domain: ctx.page_domain,
        nearest_heading: selectionData.nearestHeading
      };
      const result = await runTextAnalysisBackendFirst(requestPayload);
      if (!result.is_brainrot) {
        bubble.showInfo(
          selectionData.rect,
          "No Brainrot Detected",
          result.formal_explanation || "The selected text does not look like slang or meme-coded internet speech.",
          "Recheck",
          async () => { await runSelectionRecheck(selectionData); }
        );
        return;
      }
      const annotated = annotateSelectionInline(selectionData, result);
      if (annotated) {
        bubble.hide();
      } else {
        bubble.showTextAnalysisResult(selectionData.rect, result, selectionData.selectedText, async () => {
          await runSelectionRecheck(selectionData);
        });
      }
      incrementBrainrotBadge();
      sendAnonymousSlangDetections(result);
      saveToHistory({
        type: "text", original: selectionData.selectedText,
        translation: result.equivalent_text || "", sentiment: result.sentiment_label || "unclear",
        confidence: result.confidence_score || 0
      });
    } catch (error) {
      const errMsg = String(error?.message || "").toLowerCase();
      const isMissingOpenRouterKey = errMsg.includes("openrouter api key");
      const isConnectionFailure =
        errMsg.includes("failed to fetch") ||
        errMsg.includes("networkerror") ||
        errMsg.includes("unreachable") ||
        errMsg.includes("timeout") ||
        errMsg.includes("connection") ||
        errMsg.includes("offline") ||
        error instanceof TypeError;

      if (isConnectionFailure || isMissingOpenRouterKey) {
        try {
          const result = translateTextOffline(selectionData.selectedText);
          if (!result.is_brainrot) {
            bubble.showInfo(
              selectionData.rect,
              "No Brainrot Detected (Offline)",
              result.formal_explanation || "The offline glossary did not match any slang terms in this text."
            );
            return;
          }

          const annotated = annotateSelectionInline(selectionData, result);
          if (annotated) {
            bubble.hide();
          } else {
            bubble.showTextAnalysisResult(selectionData.rect, result, selectionData.selectedText, null);
          }
          incrementBrainrotBadge();
          sendAnonymousSlangDetections(result);
          saveToHistory({
            type: "text", original: selectionData.selectedText,
            translation: result.equivalent_text || "", sentiment: result.sentiment_label || "unclear",
            confidence: result.confidence_score || 0,
            model_used: result.model_used || ""
          });
        } catch (offlineErr) {
          bubble.showError(selectionData.rect, Shared.getFriendlyErrorMessage(error, "Text analysis failed."));
        }
      } else {
        bubble.showError(selectionData.rect, Shared.getFriendlyErrorMessage(error, "Text analysis failed."));
      }
    }
  }

  async function runSelectionRecheck(selectionData) {
    if (!hasOpenRouterApiKey()) {
      bubble.showError(selectionData.rect, "OpenRouter API key is required for recheck. Add your key in Settings.");
      return;
    }

    bubble.showLoadingState(selectionData.rect, "Rechecking highlighted text...");
    const ctx = getPageContext();
    try {
      const result = await runOpenRouterRecheck({
        selected_text: selectionData.selectedText,
        page_url: ctx.page_url,
        text_model_tier: runtimeSettings.brainrotTextModelTier,
        surrounding_text: selectionData.surroundingText,
        page_title: ctx.page_title,
        page_domain: ctx.page_domain,
        nearest_heading: selectionData.nearestHeading
      });
      if (!result.is_brainrot) {
        const usedFallback = String(result.model_used || "").includes("fallback") || result.confidence_score <= 0.35;
        bubble.showInfo(
          selectionData.rect,
          usedFallback ? "Recheck Unavailable" : "Recheck Complete",
          result.formal_explanation || result.equivalent_text || "The selected model did not classify the text as brainrot.",
          "Recheck Again",
          async () => { await runSelectionRecheck(selectionData); }
        );
        return;
      }
      bubble.showTextAnalysisResult(selectionData.rect, result, selectionData.selectedText, async () => {
        await runSelectionRecheck(selectionData);
      });
      sendAnonymousSlangDetections(result);
    } catch (error) {
      const errMsg = String(error?.message || "").toLowerCase();
      const isConnectionFailure =
        errMsg.includes("failed to fetch") ||
        errMsg.includes("networkerror") ||
        errMsg.includes("unreachable") ||
        errMsg.includes("timeout") ||
        errMsg.includes("connection") ||
        errMsg.includes("offline") ||
        error instanceof TypeError;

      if (isConnectionFailure) {
        bubble.showError(selectionData.rect, "Recheck unavailable: OpenRouter connection required.");
      } else {
        bubble.showError(selectionData.rect, Shared.getFriendlyErrorMessage(error, "Text recheck failed."));
      }
    }
  }

  function promptSelectionAnalysis(selectionData) {
    const preview = selectionData.selectedText.length > 96
      ? `${selectionData.selectedText.slice(0, 93)}...`
      : selectionData.selectedText;
    bubble.showConfirmation(
      selectionData.rect, "Translate highlighted text?", `"${preview}"`,
      "Translate", "Not now",
      async () => { await runSelectionAnalysis(selectionData); },
      () => { bubble.hide(); }
    );
  }

  async function analyzeSelection(forceDirectTranslate) {
    if (!runtimeSettings.brainrotEnableTextSelection && !forceDirectTranslate) return;
    const selectionData = getSelectionData();
    if (!selectionData) return;
    if (!forceDirectTranslate && runtimeSettings.brainrotConfirmTextSelection) {
      promptSelectionAnalysis(selectionData);
      return;
    }
    await runSelectionAnalysis(selectionData);
  }

  async function analyzeElement(element, requestId) {
    bubble.showLoadingState(element, "Analyzing meme signal...");
    try {
      const payload = await createHoverPayload(element);
      if (requestId !== hoverRequestId) return;
      await analyzeMediaPayload(element, payload);
    } catch (error) {
      if (requestId !== hoverRequestId) return;
      bubble.showError(element, Shared.getFriendlyErrorMessage(error, "Unexpected image analysis error."));
    }
  }

  function cancelHoverAnalysis() {
    clearTimeout(hoverTimer);
    activeElement = null;
    hoverRequestId += 1;
    if (bubble.isLoading()) bubble.hide();
  }

  /* ── Launcher ────────────────────────────────────────────────── */
  function refreshLauncherState() {
    const dock = createLauncher();
    dock.style.display = runtimeSettings.brainrotEnableLauncher ? "block" : "none";
    dock.style.setProperty("--pet-scale", String(runtimeSettings.brainrotLauncherScale));
    dock.classList.toggle("is-minimized", runtimeSettings.brainrotLauncherMinimized);
    applyLauncherPosition(dock);

    const status = dock.querySelector("[data-brainrot-status]");
    if (status) {
      const activeModes = [];
      if (runtimeSettings.brainrotEnableTextSelection) activeModes.push("text");
      if (runtimeSettings.brainrotEnableHoverDetection) activeModes.push("hover");
      if (runtimeSettings.brainrotEnableClipboardPaste) activeModes.push("paste");
      status.textContent = activeModes.length > 0
        ? `Ready for ${activeModes.join(" + ")} analysis`
        : "All frontend listeners are paused";
    }

    const hoverToggle = dock.querySelector("[data-brainrot-toggle-hover]");
    if (hoverToggle instanceof HTMLButtonElement) {
      const paused = !runtimeSettings.brainrotEnableHoverDetection;
      hoverToggle.textContent = paused ? "Hover Off" : "Hover On";
      hoverToggle.setAttribute("aria-pressed", paused ? "true" : "false");
    }

    const scaleLabel = dock.querySelector("[data-brainrot-scale-label]");
    if (scaleLabel) {
      scaleLabel.textContent = `${Math.round(runtimeSettings.brainrotLauncherScale * 100)}%`;
    }

    const scaleDown = dock.querySelector("[data-brainrot-scale-down]");
    const scaleUp = dock.querySelector("[data-brainrot-scale-up]");
    if (scaleDown instanceof HTMLButtonElement) {
      scaleDown.disabled = runtimeSettings.brainrotLauncherScale <= MIN_LAUNCHER_SCALE;
    }
    if (scaleUp instanceof HTMLButtonElement) {
      scaleUp.disabled = runtimeSettings.brainrotLauncherScale >= MAX_LAUNCHER_SCALE;
    }
  }

  async function adjustLauncherScale(direction) {
    const nextScale = runtimeSettings.brainrotLauncherScale + direction * LAUNCHER_SCALE_STEP;
    await writeSettings({ brainrotLauncherScale: nextScale });
  }

  function clampLauncherPosition(top, dock) {
    const height = dock.offsetHeight || 120;
    return Math.min(Math.max(80, top), Math.max(80, window.innerHeight - height - 80));
  }

  function applyLauncherPosition(dock) {
    const height = dock.offsetHeight || 120;
    let topPos = Math.round(window.innerHeight / 2 - height / 2);
    const position = runtimeSettings.brainrotLauncherPosition;
    if (position && Number.isFinite(position.top)) topPos = position.top;
    topPos = clampLauncherPosition(topPos, dock);
    dock.style.top = `${topPos}px`;
    dock.style.bottom = "auto";
    dock.style.left = "auto";
    dock.style.right = runtimeSettings.brainrotLauncherMinimized ? "0px" : "18px";
  }

  function makeLauncherDraggable(dock, handle) {
    if (!(handle instanceof HTMLElement)) return;
    let dragState = null;

    function finishDrag() {
      if (!dragState) return;
      handle.classList.remove("is-dragging");
      const finalTop = clampLauncherPosition(dragState.top, dock);
      dock.style.left = "auto"; dock.style.top = `${finalTop}px`;
      dock.style.right = "18px"; dock.style.bottom = "auto";
      dragState = null;
      writeSettings({ brainrotLauncherPosition: { top: finalTop } }).catch(() => undefined);
    }

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      if (runtimeSettings.brainrotLauncherMinimized) return;
      const rect = dock.getBoundingClientRect();
      dragState = { offsetY: event.clientY - rect.top, top: rect.top };
      handle.classList.add("is-dragging");
      dock.style.left = "auto"; dock.style.top = `${rect.top}px`;
      dock.style.right = "18px"; dock.style.bottom = "auto";
      handle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    handle.addEventListener("pointermove", (event) => {
      if (!dragState) return;
      const nextTop = event.clientY - dragState.offsetY;
      const clampedTop = clampLauncherPosition(nextTop, dock);
      dragState.top = clampedTop;
      dock.style.left = "auto"; dock.style.top = `${clampedTop}px`;
      dock.style.right = "18px"; dock.style.bottom = "auto";
    });

    handle.addEventListener("pointerup", finishDrag);
    handle.addEventListener("pointercancel", finishDrag);
  }

  function createLauncher() {
    if (launcher) return launcher;
    const dock = document.createElement("div");
    dock.id = "brainrot-floating-launcher";
    dock.innerHTML = `
      <button type="button" class="brainrot-launcher-edge-toggle" data-brainrot-minimize aria-label="Minimize floating pet">&gt;</button>
      <button type="button" class="brainrot-launcher-minibar" data-brainrot-restore aria-label="Restore floating pet">
        <span class="brainrot-launcher-minibar-mark">&lt;</span>
        <span class="brainrot-launcher-minibar-text">Brainrot</span>
      </button>
      <div class="brainrot-launcher-shell">
        <div class="brainrot-launcher-brand">
          <div class="brainrot-launcher-orb">🧠</div>
          <div class="brainrot-launcher-copy">
            <div class="brainrot-launcher-eyebrow">Floating Pet</div>
            <div class="brainrot-launcher-title">Brainrot Scout</div>
            <div class="brainrot-launcher-status" data-brainrot-status></div>
          </div>
        </div>
        <div class="brainrot-launcher-actions">
          <button type="button" class="brainrot-launcher-button brainrot-launcher-button--secondary" data-brainrot-capture>Capture</button>
          <button type="button" class="brainrot-launcher-button brainrot-launcher-button--toggle" data-brainrot-toggle-hover></button>
        </div>
        <div class="brainrot-launcher-scale-row">
          <button type="button" class="brainrot-launcher-scale-btn" data-brainrot-scale-down aria-label="Scale floating pet down">−</button>
          <span class="brainrot-launcher-scale-value" data-brainrot-scale-label>100%</span>
          <button type="button" class="brainrot-launcher-scale-btn" data-brainrot-scale-up aria-label="Scale floating pet up">+</button>
        </div>
      </div>
    `;

    const captureButton = dock.querySelector("[data-brainrot-capture]");
    const hoverToggle = dock.querySelector("[data-brainrot-toggle-hover]");
    const scaleDownButton = dock.querySelector("[data-brainrot-scale-down]");
    const scaleUpButton = dock.querySelector("[data-brainrot-scale-up]");
    const minimizeButton = dock.querySelector("[data-brainrot-minimize]");
    const restoreBar = dock.querySelector("[data-brainrot-restore]");
    const dragHandle = dock.querySelector(".brainrot-launcher-brand");

    captureButton.addEventListener("click", async () => {
      try {
        bubble.hide();
        const payload = await createCroppedVisibleTabPayload(dock);
        if (!payload) {
          bubble.showTimedInfo(dock, "Capture Cancelled", "No screenshot area selected.", 2);
          return;
        }
        await analyzeMediaPayload(dock, payload);
      } catch (error) {
        bubble.showError(dock, Shared.getFriendlyErrorMessage(error, "Screenshot capture failed."));
      }
    });
    hoverToggle.addEventListener("click", async () => {
      await writeSettings({ brainrotEnableHoverDetection: !runtimeSettings.brainrotEnableHoverDetection });
    });
    scaleDownButton.addEventListener("click", async () => { await adjustLauncherScale(-1); });
    scaleUpButton.addEventListener("click", async () => { await adjustLauncherScale(1); });
    minimizeButton.addEventListener("click", async () => { await writeSettings({ brainrotLauncherMinimized: true }); });
    restoreBar.addEventListener("click", async () => { await writeSettings({ brainrotLauncherMinimized: false }); });

    document.body.appendChild(dock);
    makeLauncherDraggable(dock, dragHandle);
    applyLauncherPosition(dock);
    launcher = dock;
    return dock;
  }

  /* ── Event listeners ─────────────────────────────────────────── */
  document.addEventListener("mouseup", (event) => {
    const target = event.target;
    if (target instanceof Element && target.closest("#brainrot-pet-bubble, #brainrot-floating-launcher")) return;
    window.setTimeout(() => { analyzeSelection(false).catch(() => undefined); }, 20);
  });

  let lastMouseX = 0, lastMouseY = 0, lastAnalyzedElement = null, lastMoveTime = 0, lastCheckedX = 0, lastCheckedY = 0;

  document.addEventListener("mousemove", (event) => {
    if (!runtimeSettings.brainrotEnableHoverDetection) return;
    const now = Date.now();
    const deltaX = Math.abs(event.clientX - lastCheckedX);
    const deltaY = Math.abs(event.clientY - lastCheckedY);
    if (now - lastMoveTime < 100 && deltaX < 8 && deltaY < 8) return;
    lastMoveTime = now; lastCheckedX = event.clientX; lastCheckedY = event.clientY;
    lastMouseX = event.clientX; lastMouseY = event.clientY;

    if (activeElement) {
      const elements = document.elementsFromPoint(lastMouseX, lastMouseY) || [];
      const overUI = elements.some(el => el.id === "brainrot-pet-bubble" || el.id === "brainrot-floating-launcher");
      const overActive = elements.includes(activeElement);
      if (!overUI && !overActive) cancelHoverAnalysis();
    }

    clearTimeout(hoverTimer);
    hoverTimer = window.setTimeout(() => {
      if (!runtimeSettings.brainrotEnableHoverDetection) return;
      const elements = document.elementsFromPoint(lastMouseX, lastMouseY) || [];
      const overUI = elements.some(el => el.id === "brainrot-pet-bubble" || el.id === "brainrot-floating-launcher");
      if (overUI) return;

      let mediaElement = null;
      for (const el of elements) {
        if (el.tagName === "IMG" || el.tagName === "VIDEO") { mediaElement = el; break; }
        if (el.hasAttribute("style") && el.getAttribute("style").includes("background-image")) { mediaElement = el; break; }
        const style = window.getComputedStyle(el);
        if (style.backgroundImage && style.backgroundImage !== "none") { mediaElement = el; break; }
      }

      if (mediaElement) {
        if (mediaElement !== lastAnalyzedElement || bubble.state === "hidden") {
          lastAnalyzedElement = mediaElement;
          activeElement = mediaElement;
          const requestId = ++hoverRequestId;
          if (isMemeCandidate(mediaElement)) analyzeElement(mediaElement, requestId);
        }
      } else {
        cancelHoverAnalysis();
      }
    }, HOVER_DELAY_MS);
  });

  document.addEventListener("paste", async (event) => {
    if (!runtimeSettings.brainrotEnableClipboardPaste) return;
    const items = Array.from(event.clipboardData?.items || []);
    const imageItem = items.find((item) => item.type.startsWith("image/"));
    if (!imageItem) return;
    const file = imageItem.getAsFile();
    if (!file) return;
    try {
      const payload = await createFilePayload(file);
      await analyzeMediaPayload(createLauncher(), payload);
    } catch (error) {
      bubble.showError(createLauncher(), Shared.getFriendlyErrorMessage(error, "Clipboard image analysis failed."));
    }
  });

  /* ── Storage sync ────────────────────────────────────────────── */
  if (hasLiveExtensionContext()) {
    try {
      chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName !== "local") return;
        const updated = { ...runtimeSettings };
        let changed = false;
        for (const key of Object.keys(DEFAULT_SETTINGS)) {
          if (Object.prototype.hasOwnProperty.call(changes, key)) {
            updated[key] = changes[key].newValue;
            changed = true;
          }
        }
        if (changed) {
          runtimeSettings = normalizeSettings(updated);
          refreshLauncherState();
        }

        // Phase 8: Reload custom dictionary if it changed
        if (changes.brainrotCustomDictionary) {
          customDictionary = Array.isArray(changes.brainrotCustomDictionary.newValue)
            ? changes.brainrotCustomDictionary.newValue : [];
        }
        if (changes.brainrotOfflineGlossary) {
          offlineGlossary = Array.isArray(changes.brainrotOfflineGlossary.newValue)
            ? changes.brainrotOfflineGlossary.newValue : [];
        }
      });
    } catch (error) {
      markExtensionContextInvalidated(error);
    }
  }

  /* ── Initialization ──────────────────────────────────────────── */
  async function initialize() {
    runtimeSettings = await readSettings();
    loadCustomDictionary();
    loadOfflineGlossary();
    createLauncher();
    refreshLauncherState();
  }

  /* ── Phase 6 & 7: Message handlers for context menu / keyboard ── */
  if (hasLiveExtensionContext()) {
    try {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message?.action === "brainrotPing") {
          sendResponse({
            ok: true, href: window.location.href,
            launcherVisible: Boolean(launcher && launcher.isConnected && launcher.style.display !== "none"),
            settings: runtimeSettings
          });
          return false;
        }

        if (message?.action === "brainrotShowTestBubble") {
          bubble.showTimedInfo(getDebugAnchor(), "Page Connection Ready", "The content script is injected on this page.", 3);
          sendResponse({ ok: true });
          return false;
        }

        // Phase 6: Context menu translate
        if (message?.action === "brainrotContextMenuTranslate") {
          const selectionData = getSelectionData();
          if (selectionData) {
            runSelectionAnalysis(selectionData).catch(() => undefined);
          } else if (message.text) {
            // Fallback: use the text from the context menu info
            const fakeRect = new DOMRect(window.innerWidth / 2, window.innerHeight / 3, 1, 1);
            const fakeData = {
              selectedText: message.text,
              surroundingText: null,
              nearestHeading: null,
              rect: fakeRect
            };
            runSelectionAnalysis(fakeData).catch(() => undefined);
          }
          sendResponse({ ok: true });
          return false;
        }

        // Phase 6: Context menu image analysis
        if (message?.action === "brainrotContextMenuImage") {
          const sourceUrl = typeof message.srcUrl === "string" ? message.srcUrl.trim() : "";
          const anchor = getDebugAnchor();
          if (!sourceUrl) {
            bubble.showError(anchor, "Image URL not found.");
            sendResponse({ ok: false, error: "Image URL not found." });
            return false;
          }

          createMediaUrlPayload(sourceUrl)
            .then((payload) => analyzeMediaPayload(anchor, payload))
            .catch((error) => {
              bubble.showError(anchor, Shared.getFriendlyErrorMessage(error, "Image analysis failed."));
            });
          sendResponse({ ok: true });
          return false;
        }

        if (message?.action === "brainrotScanPage") {
          const anchor = getDebugAnchor();
          scanPageForBrainrot()
            .then((count) => {
              bubble.showTimedInfo(
                anchor,
                count > 0 ? "Page Scan Complete" : "No Terms Found",
                count > 0 ? `Highlighted ${count} brainrot term${count === 1 ? "" : "s"} on this page.` : "No recognized brainrot terms were visible on this page.",
                4
              );
            })
            .catch((error) => {
              bubble.showError(anchor, error instanceof Error ? error.message : "Page scan failed.");
            });
          sendResponse({ ok: true });
          return false;
        }

        if (message?.action === "brainrotClearPageHighlights") {
          const count = clearPageHighlights();
          sendResponse({ ok: true, count });
          return false;
        }

        // Phase 7: Keyboard shortcut translate (skip confirmation)
        if (message?.action === "brainrotKeyboardTranslate") {
          analyzeSelection(true).catch(() => undefined);
          sendResponse({ ok: true });
          return false;
        }

        return false;
      });
    } catch (error) {
      markExtensionContextInvalidated(error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { initialize().catch(() => undefined); }, { once: true });
  } else {
    initialize().catch(() => undefined);
  }
  })();
}
