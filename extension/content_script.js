if (!window.__brainrotContentScriptLoaded) {
  window.__brainrotContentScriptLoaded = true;

  (function () {
  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const TEXT_ENDPOINT = "/api/v1/analyze-highlighted-text";
  const RECHECK_TEXT_ENDPOINT = "/api/v1/recheck-highlighted-text";
  const MEDIA_ENDPOINT = "/api/v1/analyze-screenshot-media";
  const HOVER_DELAY_MS = 600;
  const DEFAULT_SETTINGS = Object.freeze({
    brainrotApiBaseUrl: DEFAULT_API_BASE,
    brainrotEnableTextSelection: true,
    brainrotConfirmTextSelection: true,
    brainrotEnableHoverDetection: true,
    brainrotEnableLauncher: true,
    brainrotEnableClipboardPaste: true,
    brainrotLauncherPosition: null,
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
    "meme",
    "ratio",
    "sigma",
    "skill",
    "ohio",
    "npc",
    "cope",
    "skibidi",
    "grimace",
    "caught",
    "based",
    "slay",
    "rizz",
    "aura",
    "mid",
    "bffr",
    "ate"
  ];

  const bubble = new window.BrainrotPetBubble();
  let hoverTimer = null;
  let activeElement = null;
  let launcher = null;
  let runtimeSettings = { ...DEFAULT_SETTINGS };
  let hoverRequestId = 0;
  let extensionContextInvalidated = false;

  function hasLiveExtensionContext() {
    if (extensionContextInvalidated) {
      return false;
    }
    try {
      return Boolean(chrome?.runtime?.id && chrome?.storage?.local);
    } catch (error) {
      extensionContextInvalidated = true;
      return false;
    }
  }

  function markExtensionContextInvalidated(error) {
    if (
      error instanceof Error &&
      error.message.toLowerCase().includes("extension context invalidated")
    ) {
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
    if (launcher && launcher.isConnected) {
      return launcher;
    }
    return new DOMRect(window.innerWidth / 2, 120, 1, 1);
  }

  function normalizeSettings(rawSettings) {
    const raw = rawSettings || {};
    const apiBaseUrl =
      typeof raw.brainrotApiBaseUrl === "string" && raw.brainrotApiBaseUrl.trim()
        ? raw.brainrotApiBaseUrl.trim()
        : DEFAULT_API_BASE;

    return {
      brainrotApiBaseUrl: apiBaseUrl.replace(/\/+$/, ""),
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
          : DEFAULT_SETTINGS.brainrotLauncherPosition,
      brainrotLauncherScale: clampLauncherScale(raw.brainrotLauncherScale),
      brainrotLauncherMinimized:
        typeof raw.brainrotLauncherMinimized === "boolean"
          ? raw.brainrotLauncherMinimized
          : DEFAULT_SETTINGS.brainrotLauncherMinimized
    };
  }

  function clampLauncherScale(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return DEFAULT_SETTINGS.brainrotLauncherScale;
    }
    return Math.min(
      MAX_LAUNCHER_SCALE,
      Math.max(MIN_LAUNCHER_SCALE, Math.round(numeric * 10) / 10)
    );
  }

  async function readSettings() {
    if (!hasLiveExtensionContext()) {
      return { ...DEFAULT_SETTINGS };
    }

    return new Promise((resolve) => {
      try {
        chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS), (result) => {
          const lastError = getChromeLastError();
          if (lastError) {
            markExtensionContextInvalidated(lastError);
            resolve({ ...DEFAULT_SETTINGS });
            return;
          }
          resolve(normalizeSettings(result));
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        resolve({ ...DEFAULT_SETTINGS });
      }
    });
  }

  async function writeSettings(partialSettings) {
    const nextSettings = normalizeSettings({
      ...runtimeSettings,
      ...(partialSettings || {})
    });

    if (!hasLiveExtensionContext()) {
      runtimeSettings = nextSettings;
      refreshLauncherState();
      return nextSettings;
    }

    return new Promise((resolve) => {
      try {
        chrome.storage.local.set(nextSettings, () => {
          const lastError = getChromeLastError();
          if (lastError) {
            markExtensionContextInvalidated(lastError);
            runtimeSettings = nextSettings;
            refreshLauncherState();
            resolve(nextSettings);
            return;
          }
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

  async function postJson(path, payload) {
    const base = await getApiBaseUrl();
    const response = await fetch(`${base}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || body.error || "Backend request failed.");
    }
    return body;
  }

  function getMediaUrl(element) {
    if (!element) {
      return null;
    }

    if (element.tagName === "IMG") {
      return element.currentSrc || element.src || null;
    }

    const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
    const match = backgroundImage.match(/url\(["']?(.*?)["']?\)/i);
    return match ? match[1] : null;
  }

  function getMediaType(url) {
    const normalized = (url || "").toLowerCase();
    if (normalized.endsWith(".gif") || normalized.includes("format=gif")) {
      return "image/gif";
    }
    if (normalized.endsWith(".png")) {
      return "image/png";
    }
    if (normalized.endsWith(".webp")) {
      return "image/webp";
    }
    return "image/jpeg";
  }

  function hasMemeHost(url) {
    try {
      const hostname = new URL(url, window.location.href).hostname.toLowerCase();
      return MEME_HOSTS.some((host) => hostname.includes(host));
    } catch (error) {
      return false;
    }
  }

  function hasKeywordHint(url) {
    const normalized = (url || "").toLowerCase();
    return BRAINROT_KEYWORDS.some((keyword) => normalized.includes(keyword));
  }

  function hasMemeLikeAspectRatio(element) {
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return false;
    }

    // Reject tiny icons or 1px trackers
    if (rect.width < 100 || rect.height < 100) {
      return false;
    }
    return true;
  }

  function isMemeCandidate(element) {
    const url = getMediaUrl(element);
    if (!url) {
      return false;
    }

    return hasMemeHost(url) || hasKeywordHint(url) || hasMemeLikeAspectRatio(element);
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

  async function buildFirstFrameFromSource(src, fallbackWidth = 320, fallbackHeight = 180) {
    const image = await loadImageFromSource(src);
    const canvas = document.createElement("canvas");
    const width = image.naturalWidth || fallbackWidth;
    const height = image.naturalHeight || fallbackHeight;
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("Canvas is unavailable for GIF fallback extraction.");
    }

    context.drawImage(image, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    return {
      dataUrl,
      base64: dataUrlToBase64(dataUrl),
      mediaType: "image/jpeg"
    };
  }

  async function fetchMediaAsset(url) {
    return new Promise((resolve, reject) => {
      if (!hasLiveExtensionContext()) {
        reject(new Error("Extension was reloaded. Refresh this page before using media analysis."));
        return;
      }

      try {
        chrome.runtime.sendMessage(
          { action: "fetchMediaAsset", url },
          (response) => {
            const lastError = getChromeLastError();
            if (lastError) {
              markExtensionContextInvalidated(lastError);
              reject(new Error(lastError.message));
              return;
            }
            if (!response?.ok) {
              reject(new Error(response?.error || "Unable to fetch media asset."));
              return;
            }
            resolve(response);
          }
        );
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
          if (lastError) {
            markExtensionContextInvalidated(lastError);
            reject(new Error(lastError.message));
            return;
          }
          if (!response?.ok) {
            reject(new Error(response?.error || "Unable to capture screenshot."));
            return;
          }
          resolve(response.dataUrl);
        });
      } catch (error) {
        markExtensionContextInvalidated(error);
        reject(error instanceof Error ? error : new Error("Screenshot capture failed."));
      }
    });
  }

  async function createHoverPayload(element) {
    const sourceUrl = getMediaUrl(element);
    if (!sourceUrl) {
      throw new Error("Media URL not found.");
    }

    const mediaType = getMediaType(sourceUrl);
    const fetched = await fetchMediaAsset(sourceUrl);
    const payload = {
      image_base64: fetched.base64,
      media_type: mediaType,
      source_url: sourceUrl,
      previewSrc: fetched.dataUrl || sourceUrl,
      frame0_base64: null,
      frame0_media_type: null
    };

    if (mediaType === "image/gif") {
      const firstFrame = await buildFirstFrameFromSource(sourceUrl);
      payload.frame0_base64 = firstFrame.base64;
      payload.frame0_media_type = firstFrame.mediaType;
      payload.previewSrc = firstFrame.dataUrl;
    }

    return payload;
  }

  async function createFilePayload(file) {
    const dataUrl = await fileToDataUrl(file);
    const payload = {
      image_base64: dataUrlToBase64(dataUrl),
      media_type: file.type || "image/jpeg",
      source_url: null,
      previewSrc: dataUrl,
      frame0_base64: null,
      frame0_media_type: null
    };

    if (payload.media_type === "image/gif") {
      const firstFrame = await buildFirstFrameFromSource(dataUrl);
      payload.frame0_base64 = firstFrame.base64;
      payload.frame0_media_type = firstFrame.mediaType;
      payload.previewSrc = firstFrame.dataUrl;
    }

    return payload;
  }

  async function analyzeMediaPayload(anchor, payload) {
    bubble.showLoadingState(anchor, "Analyzing screenshot or GIF...");
    const result = await postJson(MEDIA_ENDPOINT, {
      image_base64: payload.image_base64,
      media_type: payload.media_type,
      source_url: payload.source_url,
      frame0_base64: payload.frame0_base64,
      frame0_media_type: payload.frame0_media_type
    });

    if (!result.is_brainrot) {
      bubble.hide();
      return;
    }

    bubble.showImageAnalysisResult(anchor, result, payload.previewSrc);
  }

  function getSelectionData() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      return null;
    }

    const text = selection.toString().trim();
    if (!text) {
      return null;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    return {
      selectedText: text,
      surroundingText: range.commonAncestorContainer?.textContent?.trim()?.slice(0, 280) || null,
      rect
    };
  }

  async function runSelectionAnalysis(selectionData) {
    bubble.showLoadingState(selectionData.rect, "Translating highlighted text...");
    try {
      const result = await postJson(TEXT_ENDPOINT, {
        selected_text: selectionData.selectedText,
        page_url: window.location.href,
        surrounding_text: selectionData.surroundingText
      });
      if (!result.is_brainrot) {
        bubble.showInfo(
          selectionData.rect,
          "No Brainrot Detected",
          result.formal_explanation || "The selected text does not look like slang or meme-coded internet speech.",
          "Recheck",
          async () => {
            await runSelectionRecheck(selectionData);
          }
        );
        return;
      }
      bubble.showTextAnalysisResult(
        selectionData.rect,
        result,
        selectionData.selectedText,
        async () => {
          await runSelectionRecheck(selectionData);
        }
      );
    } catch (error) {
      bubble.showError(
        selectionData.rect,
        error instanceof Error ? error.message : "Text analysis failed."
      );
    }
  }

  async function runSelectionRecheck(selectionData) {
    bubble.showLoadingState(selectionData.rect, "Rechecking highlighted text with DeepSeek...");
    try {
      const result = await postJson(RECHECK_TEXT_ENDPOINT, {
        selected_text: selectionData.selectedText,
        page_url: window.location.href,
        surrounding_text: selectionData.surroundingText
      });
      if (!result.is_brainrot) {
        const usedFallback =
          String(result.model_used || "").includes("fallback") ||
          result.confidence_score <= 0.35;
        bubble.showInfo(
          selectionData.rect,
          usedFallback ? "Recheck Unavailable" : "Recheck Complete",
          result.formal_explanation || result.equivalent_text || "DeepSeek did not classify the text as brainrot.",
          "Recheck Again",
          async () => {
            await runSelectionRecheck(selectionData);
          }
        );
        return;
      }
      bubble.showTextAnalysisResult(
        selectionData.rect,
        result,
        selectionData.selectedText,
        async () => {
          await runSelectionRecheck(selectionData);
        }
      );
    } catch (error) {
      bubble.showError(
        selectionData.rect,
        error instanceof Error ? error.message : "Text recheck failed."
      );
    }
  }

  function promptSelectionAnalysis(selectionData) {
    const preview =
      selectionData.selectedText.length > 96
        ? `${selectionData.selectedText.slice(0, 93)}...`
        : selectionData.selectedText;

    bubble.showConfirmation(
      selectionData.rect,
      "Translate highlighted text?",
      `"${preview}"`,
      "Translate",
      "Not now",
      async () => {
        await runSelectionAnalysis(selectionData);
      },
      () => {
        bubble.hide();
      }
    );
  }

  async function analyzeSelection() {
    if (!runtimeSettings.brainrotEnableTextSelection) {
      return;
    }

    const selectionData = getSelectionData();
    if (!selectionData) {
      return;
    }

    if (runtimeSettings.brainrotConfirmTextSelection) {
      promptSelectionAnalysis(selectionData);
      return;
    }

    await runSelectionAnalysis(selectionData);
  }

  async function analyzeElement(element, requestId) {
    bubble.showLoadingState(element, "Analyzing meme signal...");
    try {
      const payload = await createHoverPayload(element);
      if (requestId !== hoverRequestId) {
        return;
      }
      await analyzeMediaPayload(element, payload);
    } catch (error) {
      if (requestId !== hoverRequestId) {
        return;
      }
      bubble.showError(
        element,
        error instanceof Error ? error.message : "Unexpected image analysis error."
      );
    }
  }


  function cancelHoverAnalysis() {
    clearTimeout(hoverTimer);
    activeElement = null;
    hoverRequestId += 1;
    if (bubble.isLoading()) {
      bubble.hide();
    }
  }

  function refreshLauncherState() {
    const dock = createLauncher();
    dock.style.display = runtimeSettings.brainrotEnableLauncher ? "block" : "none";
    dock.style.setProperty("--pet-scale", String(runtimeSettings.brainrotLauncherScale));
    dock.classList.toggle("is-minimized", runtimeSettings.brainrotLauncherMinimized);
    applyLauncherPosition(dock);

    const status = dock.querySelector("[data-brainrot-status]");
    if (status) {
      const activeModes = [];
      if (runtimeSettings.brainrotEnableTextSelection) {
        activeModes.push("text");
      }
      if (runtimeSettings.brainrotEnableHoverDetection) {
        activeModes.push("hover");
      }
      if (runtimeSettings.brainrotEnableClipboardPaste) {
        activeModes.push("paste");
      }
      status.textContent =
        activeModes.length > 0
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

  function clampLauncherPosition(top, dock) {
    const height = dock.offsetHeight || 120;
    // Enforce 80px padding from top and bottom to avoid Chrome navigation and bottom bars
    return Math.min(Math.max(80, top), Math.max(80, window.innerHeight - height - 80));
  }

  function applyLauncherPosition(dock) {
    const height = dock.offsetHeight || 120;
    let topPos = Math.round(window.innerHeight / 2 - height / 2);

    const position = runtimeSettings.brainrotLauncherPosition;
    if (position && Number.isFinite(position.top)) {
      topPos = position.top;
    }

    topPos = clampLauncherPosition(topPos, dock);

    dock.style.top = `${topPos}px`;
    dock.style.bottom = "auto";
    dock.style.left = "auto";

    if (runtimeSettings.brainrotLauncherMinimized) {
      dock.style.right = "0px";
    } else {
      dock.style.right = "18px";
    }
  }

  function makeLauncherDraggable(dock, handle) {
    if (!(handle instanceof HTMLElement)) {
      return;
    }

    let dragState = null;

    function finishDrag() {
      if (!dragState) {
        return;
      }

      handle.classList.remove("is-dragging");
      const finalTop = clampLauncherPosition(dragState.top, dock);
      dock.style.left = "auto";
      dock.style.top = `${finalTop}px`;
      dock.style.right = "18px";
      dock.style.bottom = "auto";
      dragState = null;
      writeSettings({ brainrotLauncherPosition: { top: finalTop } }).catch(() => undefined);
    }

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) {
        return;
      }
      if (runtimeSettings.brainrotLauncherMinimized) {
        return;
      }

      const rect = dock.getBoundingClientRect();
      dragState = {
        offsetY: event.clientY - rect.top,
        top: rect.top
      };
      handle.classList.add("is-dragging");
      dock.style.left = "auto";
      dock.style.top = `${rect.top}px`;
      dock.style.right = "18px";
      dock.style.bottom = "auto";
      handle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    handle.addEventListener("pointermove", (event) => {
      if (!dragState) {
        return;
      }

      const nextTop = event.clientY - dragState.offsetY;
      const clampedTop = clampLauncherPosition(nextTop, dock);
      dragState.top = clampedTop;
      dock.style.left = "auto";
      dock.style.top = `${clampedTop}px`;
      dock.style.right = "18px";
      dock.style.bottom = "auto";
    });

    handle.addEventListener("pointerup", finishDrag);
    handle.addEventListener("pointercancel", finishDrag);
  }

  async function adjustLauncherScale(direction) {
    const nextScale = clampLauncherScale(
      runtimeSettings.brainrotLauncherScale + direction * LAUNCHER_SCALE_STEP
    );
    await writeSettings({ brainrotLauncherScale: nextScale });
  }

  function createLauncher() {
    if (launcher) {
      return launcher;
    }

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
        const dataUrl = await captureVisibleTab();
        const payload = {
          image_base64: dataUrlToBase64(dataUrl),
          media_type: "image/png",
          source_url: window.location.href,
          frame0_base64: null,
          frame0_media_type: null,
          previewSrc: dataUrl
        };
        await analyzeMediaPayload(dock, payload);
      } catch (error) {
        bubble.showError(
          dock,
          error instanceof Error ? error.message : "Screenshot capture failed."
        );
      }
    });
    hoverToggle.addEventListener("click", async () => {
      await writeSettings({
        brainrotEnableHoverDetection: !runtimeSettings.brainrotEnableHoverDetection
      });
    });
    scaleDownButton.addEventListener("click", async () => {
      await adjustLauncherScale(-1);
    });
    scaleUpButton.addEventListener("click", async () => {
      await adjustLauncherScale(1);
    });
    minimizeButton.addEventListener("click", async () => {
      await writeSettings({ brainrotLauncherMinimized: true });
    });
    restoreBar.addEventListener("click", async () => {
      await writeSettings({ brainrotLauncherMinimized: false });
    });


    document.body.appendChild(dock);
    makeLauncherDraggable(dock, dragHandle);
    applyLauncherPosition(dock);
    launcher = dock;
    return dock;
  }

  document.addEventListener("mouseup", (event) => {
    const target = event.target;
    if (
      target instanceof Element &&
      target.closest("#brainrot-pet-bubble, #brainrot-floating-launcher")
    ) {
      return;
    }

    window.setTimeout(() => {
      analyzeSelection().catch(() => undefined);
    }, 20);
  });

  let lastMouseX = 0;
  let lastMouseY = 0;
  let lastAnalyzedElement = null;
  let lastMoveTime = 0;
  let lastCheckedX = 0;
  let lastCheckedY = 0;

  document.addEventListener("mousemove", (event) => {
    if (!runtimeSettings.brainrotEnableHoverDetection) {
      return;
    }

    const now = Date.now();
    const deltaX = Math.abs(event.clientX - lastCheckedX);
    const deltaY = Math.abs(event.clientY - lastCheckedY);

    // Throttle checks to 100ms and minimum 8px displacement
    if (now - lastMoveTime < 100 && deltaX < 8 && deltaY < 8) {
      return;
    }
    lastMoveTime = now;
    lastCheckedX = event.clientX;
    lastCheckedY = event.clientY;

    lastMouseX = event.clientX;
    lastMouseY = event.clientY;

    if (activeElement) {
      const elements = document.elementsFromPoint(lastMouseX, lastMouseY) || [];
      const overUI = elements.some(el => el.id === "brainrot-pet-bubble" || el.id === "brainrot-floating-launcher");
      const overActive = elements.includes(activeElement);
      
      if (!overUI && !overActive) {
        cancelHoverAnalysis();
      }
    }

    clearTimeout(hoverTimer);
    
    hoverTimer = window.setTimeout(() => {
      if (!runtimeSettings.brainrotEnableHoverDetection) return;

      const elements = document.elementsFromPoint(lastMouseX, lastMouseY) || [];
      
      const overUI = elements.some(el => el.id === "brainrot-pet-bubble" || el.id === "brainrot-floating-launcher");
      if (overUI) {
        return;
      }

      let mediaElement = null;
      for (const el of elements) {
        if (el.tagName === "IMG" || el.tagName === "VIDEO") {
          mediaElement = el;
          break;
        }
        if (el.hasAttribute("style") && el.getAttribute("style").includes("background-image")) {
          mediaElement = el;
          break;
        }
        const style = window.getComputedStyle(el);
        if (style.backgroundImage && style.backgroundImage !== "none") {
          mediaElement = el;
          break;
        }
      }

      if (mediaElement) {
        if (mediaElement !== lastAnalyzedElement || bubble.state === "hidden") {
          lastAnalyzedElement = mediaElement;
          activeElement = mediaElement;
          const requestId = ++hoverRequestId;
          if (isMemeCandidate(mediaElement)) {
            analyzeElement(mediaElement, requestId);
          }
        }
      } else {
        cancelHoverAnalysis();
      }
    }, HOVER_DELAY_MS);
  });

  document.addEventListener("paste", async (event) => {
    if (!runtimeSettings.brainrotEnableClipboardPaste) {
      return;
    }

    const items = Array.from(event.clipboardData?.items || []);
    const imageItem = items.find((item) => item.type.startsWith("image/"));
    if (!imageItem) {
      return;
    }
    const file = imageItem.getAsFile();
    if (!file) {
      return;
    }
    try {
      const payload = await createFilePayload(file);
      await analyzeMediaPayload(createLauncher(), payload);
    } catch (error) {
      bubble.showError(
        createLauncher(),
        error instanceof Error ? error.message : "Clipboard image analysis failed."
      );
    }
  });

  if (hasLiveExtensionContext()) {
    try {
      chrome.storage.onChanged.addListener((changes, areaName) => {
        if (areaName !== "local") {
          return;
        }

        const updated = { ...runtimeSettings };
        let changed = false;
        for (const key of Object.keys(DEFAULT_SETTINGS)) {
          if (Object.prototype.hasOwnProperty.call(changes, key)) {
            updated[key] = changes[key].newValue;
            changed = true;
          }
        }
        if (!changed) {
          return;
        }

        runtimeSettings = normalizeSettings(updated);
        refreshLauncherState();
      });
    } catch (error) {
      markExtensionContextInvalidated(error);
    }
  }

  async function initialize() {
    runtimeSettings = await readSettings();
    createLauncher();
    refreshLauncherState();
  }

  if (hasLiveExtensionContext()) {
    try {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message?.action === "brainrotPing") {
          sendResponse({
            ok: true,
            href: window.location.href,
            launcherVisible: Boolean(
              launcher &&
              launcher.isConnected &&
              launcher.style.display !== "none"
            ),
            settings: runtimeSettings
          });
          return false;
        }

        if (message?.action === "brainrotShowTestBubble") {
          bubble.showTimedInfo(
            getDebugAnchor(),
            "Page Connection Ready",
            "The content script is injected on this page.",
            3
          );
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
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        initialize().catch(() => undefined);
      },
      { once: true }
    );
  } else {
    initialize().catch(() => undefined);
  }
  })();
}
