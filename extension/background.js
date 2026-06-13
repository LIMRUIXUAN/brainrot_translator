/* ------------------------------------------------------------------ */
/* Brainrot Translator — Background Service Worker                    */
/* Phases 3, 6, 7: History, Context Menu, Keyboard Shortcut           */
/* ------------------------------------------------------------------ */

const MAX_HISTORY_ENTRIES = 200;
const tabBrainrotCounts = new Map();
const OPENROUTER_STORAGE_KEY = "brainrotOpenRouterApiKey";
const OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions";
const DEFAULT_MODEL_CONFIG = Object.freeze({
  text: {
    free: "nvidia/nemotron-3-super-120b-a12b:free",
    premium: "deepseek/deepseek-v4-flash"
  },
  image: {
    free: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    premium: "google/gemini-3.1-flash-lite",
    fallbacks: ["google/gemini-3.1-flash-lite"]
  }
});

const TEXT_RESPONSE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "is_brainrot",
    "brainrot_text",
    "equivalent_text",
    "formal_explanation",
    "sentiment_label",
    "sentiment_rationale",
    "confidence_score",
    "flagged_for_review",
    "model_used"
  ],
  properties: {
    is_brainrot: { type: "boolean" },
    brainrot_text: { anyOf: [{ type: "string" }, { type: "null" }] },
    equivalent_text: { anyOf: [{ type: "string" }, { type: "null" }] },
    formal_explanation: { anyOf: [{ type: "string" }, { type: "null" }] },
    sentiment_label: { enum: ["positive", "negative", "neutral", "mixed", "unclear"] },
    sentiment_rationale: { anyOf: [{ type: "string" }, { type: "null" }] },
    confidence_score: { type: "number", minimum: 0, maximum: 1 },
    flagged_for_review: { type: "boolean" },
    model_used: { anyOf: [{ type: "string" }, { type: "null" }] }
  }
};

const REVERSE_RESPONSE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["reverse_text", "confidence_score", "model_used"],
  properties: {
    reverse_text: { type: "string" },
    confidence_score: { type: "number", minimum: 0, maximum: 1 },
    model_used: { type: "string" }
  }
};

const IMAGE_RESPONSE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "is_brainrot",
    "brainrot_meaning",
    "equivalent_text",
    "formal_explanation",
    "confidence_score",
    "flagged_for_review",
    "model_used",
    "used_frame_fallback"
  ],
  properties: {
    is_brainrot: { type: "boolean" },
    brainrot_meaning: { anyOf: [{ type: "string" }, { type: "null" }] },
    equivalent_text: { anyOf: [{ type: "string" }, { type: "null" }] },
    formal_explanation: { anyOf: [{ type: "string" }, { type: "null" }] },
    confidence_score: { type: "number", minimum: 0, maximum: 1 },
    flagged_for_review: { type: "boolean" },
    model_used: { anyOf: [{ type: "string" }, { type: "null" }] },
    used_frame_fallback: { type: "boolean" }
  }
};

function clampConfidence(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(1, numeric));
}

function trimText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isAbortLikeError(error) {
  const name = String(error?.name || "");
  const message = String(error?.message || "").toLowerCase();
  return name === "AbortError" ||
    message.includes("user aborted") ||
    message.includes("operation was aborted");
}

async function getOpenRouterKeyStatus() {
  const [localResult, sessionResult] = await Promise.all([
    chrome.storage.local.get({
      [OPENROUTER_STORAGE_KEY]: "",
      brainrotRememberOpenRouterKey: true
    }),
    chrome.storage.session.get({ [OPENROUTER_STORAGE_KEY]: "" })
  ]);
  const localKey = String(localResult[OPENROUTER_STORAGE_KEY] || "").trim();
  const sessionKey = String(sessionResult[OPENROUTER_STORAGE_KEY] || "").trim();
  const rememberOnDevice = localResult.brainrotRememberOpenRouterKey !== false;

  if (rememberOnDevice && localKey) {
    return { present: true, storage: "local", rememberOnDevice, key: localKey };
  }
  if (sessionKey) {
    return { present: true, storage: "session", rememberOnDevice, key: sessionKey };
  }
  if (localKey) {
    return { present: true, storage: "local", rememberOnDevice: true, key: localKey };
  }
  return { present: false, storage: "none", rememberOnDevice, key: "" };
}

async function syncOpenRouterKeyStatus() {
  const status = await getOpenRouterKeyStatus();
  await chrome.storage.local.set({
    brainrotOpenRouterKeyPresent: status.present,
    brainrotOpenRouterKeyStorage: status.storage,
    brainrotRememberOpenRouterKey: status.rememberOnDevice
  });
  return status;
}

async function getOpenRouterKey() {
  const status = await getOpenRouterKeyStatus();
  return status.key;
}

async function clearOpenRouterKey() {
  await Promise.all([
    chrome.storage.local.remove([OPENROUTER_STORAGE_KEY, "brainrotApiAuthToken"]),
    chrome.storage.session.remove(OPENROUTER_STORAGE_KEY)
  ]);
  await chrome.storage.local.set({
    brainrotOpenRouterKeyPresent: false,
    brainrotOpenRouterKeyStorage: "none"
  });
  return { present: false, storage: "none" };
}

async function setOpenRouterKey(value, rememberOnDevice = true) {
  const apiKey = String(value || "").trim();
  if (!apiKey) {
    await clearOpenRouterKey();
    await chrome.storage.local.set({ brainrotRememberOpenRouterKey: rememberOnDevice !== false });
    return { present: false, storage: "none" };
  }

  if (rememberOnDevice !== false) {
    await chrome.storage.local.set({
      [OPENROUTER_STORAGE_KEY]: apiKey,
      brainrotOpenRouterKeyPresent: true,
      brainrotOpenRouterKeyStorage: "local",
      brainrotRememberOpenRouterKey: true
    });
    await chrome.storage.session.remove(OPENROUTER_STORAGE_KEY);
    await chrome.storage.local.remove("brainrotApiAuthToken");
    return { present: true, storage: "local" };
  }

  await chrome.storage.session.set({ [OPENROUTER_STORAGE_KEY]: apiKey });
  await chrome.storage.local.remove([OPENROUTER_STORAGE_KEY, "brainrotApiAuthToken"]);
  await chrome.storage.local.set({
    brainrotOpenRouterKeyPresent: true,
    brainrotOpenRouterKeyStorage: "session",
    brainrotRememberOpenRouterKey: false
  });
  return { present: true, storage: "session" };
}

async function setOpenRouterKeyPersistence(rememberOnDevice = true) {
  const status = await getOpenRouterKeyStatus();
  if (!status.present) {
    await chrome.storage.local.set({
      brainrotRememberOpenRouterKey: rememberOnDevice !== false,
      brainrotOpenRouterKeyPresent: false,
      brainrotOpenRouterKeyStorage: "none"
    });
    return { present: false, storage: "none" };
  }
  return await setOpenRouterKey(status.key, rememberOnDevice);
}

async function migrateLegacyOpenRouterKey() {
  try {
    const result = await chrome.storage.local.get({ brainrotApiAuthToken: "" });
    const legacyKey = String(result.brainrotApiAuthToken || "").trim();
    if (legacyKey) {
      await setOpenRouterKey(legacyKey, true);
      return;
    }
    await syncOpenRouterKeyStatus();
    await chrome.storage.local.remove("brainrotApiAuthToken");
  } catch (error) {
    // Ignore migration failures; the user can re-enter the key.
  }
}

async function fetchModelConfig(apiBaseUrl) {
  const base = String(apiBaseUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/v1/public/model-config`, {
      method: "GET",
      headers: { "Content-Type": "application/json" }
    });
    if (!response.ok) throw new Error("Model config unavailable.");
    const payload = await response.json();
    return {
      text: { ...DEFAULT_MODEL_CONFIG.text, ...(payload.text || {}) },
      image: {
        ...DEFAULT_MODEL_CONFIG.image,
        ...(payload.image || {}),
        fallbacks: Array.isArray(payload.image?.fallbacks)
          ? payload.image.fallbacks
          : DEFAULT_MODEL_CONFIG.image.fallbacks
      }
    };
  } catch (error) {
    return DEFAULT_MODEL_CONFIG;
  }
}

function resolveTier(tier) {
  return tier === "premium" ? "premium" : "free";
}

function buildTextSystemPrompt() {
  return [
    "You are a precise internet-slang and brainrot translator.",
    "Classify whether the highlighted text contains internet slang, meme-coded language, or brainrot vocabulary.",
    "When it is brainrot, return the exact slang terms in brainrot_text, a complete formal-English sentence in equivalent_text, a concise cultural explanation in formal_explanation, a sentiment_label of positive, negative, neutral, mixed, or unclear, a short sentiment_rationale, and a confidence score between 0 and 1.",
    "When it is not brainrot, set is_brainrot to false, keep equivalent_text as the original text, and set formal_explanation to a short sentence saying no brainrot or internet slang was detected.",
    "Return JSON only and follow the schema exactly."
  ].join("\n");
}

function buildTextUserPrompt(payload) {
  return [
    `Analyze the entire highlighted text selection: "${trimText(payload.selected_text)}"`,
    "1. Translate the COMPLETE sentence context smoothly into formal English.",
    "2. Identify any core brainrot/slang elements and provide a sharp, concise explanation of its cultural context and exact internet stance.",
    `Page Title: ${trimText(payload.page_title) || "unavailable"}`,
    `Page Host/Platform: ${trimText(payload.page_domain) || "unavailable"}`,
    `Page URL hint: ${trimText(payload.page_url) || "unavailable"}`,
    `Nearest heading context: ${trimText(payload.nearest_heading) || "unavailable"}`,
    `Surrounding context: ${trimText(payload.surrounding_text) || "unavailable"}`,
    "Estimate sentiment from the complete message, not from one isolated term."
  ].join("\n");
}

function buildReverseSystemPrompt() {
  return [
    "You are a structured Gen Z and internet-slang rewrite engine.",
    "Convert normal English into natural brainrot or Gen Z internet English without adding unrelated facts.",
    "Keep the user's core meaning, tone, and intent. Prefer current slang only when it fits.",
    "Always produce a meaningful rewrite that is visibly different from the source sentence while preserving meaning.",
    "Use casual internet phrasing such as bro, no cap, lowkey, highkey, cooked, aura, L, W, rizz, valid, or goated only when contextually suitable.",
    "Do not simply copy the source text, only add punctuation, or make a tiny grammar-only edit.",
    "Return JSON only with reverse_text, confidence_score, and model_used.",
    "Keep reverse_text concise and readable, not an overloaded list of slang terms."
  ].join("\n");
}

function buildImageSystemPrompt() {
  return [
    "You are a multimodal internet-culture classifier.",
    "Determine whether the attached image or GIF functions as brainrot vocabulary, not whether it is merely funny or emotional.",
    "Use the provided page host/domain and context to determine platform-specific sarcasm or humor.",
    "Translate the complete visual message into a natural, fully formed formal English sentence. Do not isolate only one meme label.",
    "Capture the visual's social stance, implied joke, and internet-culture verdict.",
    "If is_brainrot is true, provide brainrot_meaning, equivalent_text, and formal_explanation.",
    "If is_brainrot is false, set those fields to null.",
    "Return JSON only and follow the schema exactly."
  ].join("\n");
}

function buildImageUserPrompt(payload, usingFrame) {
  return [
    "Analyze the attached screenshot/media asset.",
    "1. Deconstruct the entire overarching message and translate it into a direct formal English sentence.",
    "2. Provide a brief, punchy explanation focused on the core brainrot meme meaning.",
    `Page Title: ${trimText(payload.page_title) || "unavailable"}`,
    `Page Host/Platform: ${trimText(payload.page_domain) || "unavailable"}`,
    `Source URL hint: ${trimText(payload.source_url) || "unavailable"}`,
    usingFrame
      ? "The attached image is a first-frame fallback extracted from a GIF."
      : "The attached asset is the original screenshot or raw media."
  ].join("\n");
}

async function executeOpenRouter(payload, timeoutMs = 90000) {
  const apiKey = await getOpenRouterKey();
  if (!apiKey) {
    throw new Error("OpenRouter API key is required. Add your key in Settings.");
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(OPENROUTER_CHAT_URL, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://brainrot-translator.local",
        "X-OpenRouter-Title": "Brainrot Translator"
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (response.status === 401 || response.status === 403) {
      throw new Error("OpenRouter API key is missing or invalid. Add your key in Settings.");
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body?.error?.message || body?.detail || `OpenRouter request failed (${response.status}).`);
    }
    const body = await response.json();
    const rawContent = body?.choices?.[0]?.message?.content;
    const content = Array.isArray(rawContent)
      ? rawContent.map((part) => part?.text || "").join("")
      : String(rawContent || "");
    return JSON.parse(content);
  } catch (error) {
    if (isAbortLikeError(error)) {
      const seconds = Math.round(timeoutMs / 1000);
      throw new Error(`OpenRouter request timed out after ${seconds}s. Try again, check your connection, or switch to a faster model.`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

function normalizeTextResult(result, selectedText, model) {
  const confidence = clampConfidence(result?.confidence_score);
  const isBrainrot = Boolean(result?.is_brainrot);
  if (!isBrainrot) {
    return {
      is_brainrot: false,
      brainrot_text: selectedText,
      equivalent_text: selectedText,
      formal_explanation: trimText(result?.formal_explanation) || "No brainrot or internet slang marker was detected, so the text was left unchanged.",
      sentiment_label: result?.sentiment_label || "unclear",
      sentiment_rationale: trimText(result?.sentiment_rationale) || null,
      confidence_score: confidence,
      flagged_for_review: confidence < 0.6,
      model_used: model
    };
  }
  return {
    is_brainrot: true,
    brainrot_text: trimText(result?.brainrot_text) || selectedText,
    equivalent_text: trimText(result?.equivalent_text) || selectedText,
    formal_explanation: trimText(result?.formal_explanation) || null,
    sentiment_label: result?.sentiment_label || "unclear",
    sentiment_rationale: trimText(result?.sentiment_rationale) || null,
    confidence_score: confidence,
    flagged_for_review: confidence < 0.6,
    model_used: model
  };
}

function normalizeReverseResult(result, originalText, model) {
  return {
    reverse_text: trimText(result?.reverse_text) || originalText,
    confidence_score: clampConfidence(result?.confidence_score),
    model_used: trimText(result?.model_used) || model
  };
}

function normalizeImageResult(result, model, usedFrameFallback) {
  const confidence = clampConfidence(result?.confidence_score);
  const isBrainrot = Boolean(result?.is_brainrot);
  return {
    is_brainrot: isBrainrot,
    brainrot_meaning: isBrainrot ? (trimText(result?.brainrot_meaning) || null) : null,
    equivalent_text: isBrainrot ? (trimText(result?.equivalent_text) || null) : null,
    formal_explanation: isBrainrot ? (trimText(result?.formal_explanation) || null) : null,
    confidence_score: confidence,
    flagged_for_review: confidence < 0.6,
    model_used: model,
    used_frame_fallback: Boolean(usedFrameFallback)
  };
}

async function analyzeTextWithOpenRouter(requestPayload, settings = {}) {
  const modelConfig = await fetchModelConfig(settings.brainrotApiBaseUrl);
  const tier = resolveTier(requestPayload.text_model_tier || settings.brainrotTextModelTier);
  const model = modelConfig.text[tier] || DEFAULT_MODEL_CONFIG.text[tier];
  const selectedText = trimText(requestPayload.selected_text);
  const payload = {
    model,
    messages: [
      { role: "system", content: buildTextSystemPrompt() },
      { role: "user", content: buildTextUserPrompt(requestPayload) }
    ],
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "highlighted_text_analysis_response",
        strict: true,
        schema: TEXT_RESPONSE_SCHEMA
      }
    },
    temperature: 0.1
  };
  const parsed = await executeOpenRouter(payload, tier === "premium" ? 30000 : 90000);
  return normalizeTextResult(parsed, selectedText, model);
}

async function reverseWithOpenRouter(requestPayload, settings = {}) {
  const modelConfig = await fetchModelConfig(settings.brainrotApiBaseUrl);
  const tier = resolveTier(requestPayload.text_model_tier || settings.brainrotTextModelTier);
  const model = modelConfig.text[tier] || DEFAULT_MODEL_CONFIG.text[tier];
  const text = trimText(requestPayload.text);
  const payload = {
    model,
    messages: [
      { role: "system", content: buildReverseSystemPrompt() },
      { role: "user", content: `Convert this normal English into brainrot English: "${text}"` }
    ],
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "reverse_translate_response",
        strict: true,
        schema: REVERSE_RESPONSE_SCHEMA
      }
    },
    temperature: 0.35
  };
  const parsed = await executeOpenRouter(payload, tier === "premium" ? 30000 : 90000);
  return normalizeReverseResult(parsed, text, model);
}

function buildImageDataUrl(base64, mediaType) {
  const value = String(base64 || "").trim();
  if (value.startsWith("data:")) return value;
  return `data:${mediaType || "image/png"};base64,${value}`;
}

async function analyzeImageWithOpenRouter(requestPayload, settings = {}) {
  const modelConfig = await fetchModelConfig(settings.brainrotApiBaseUrl);
  const tier = resolveTier(requestPayload.image_model_tier || settings.brainrotImageModelTier);
  const model = modelConfig.image[tier] || DEFAULT_MODEL_CONFIG.image[tier];
  const payload = {
    model,
    messages: [
      { role: "system", content: buildImageSystemPrompt() },
      {
        role: "user",
        content: [
          { type: "text", text: buildImageUserPrompt(requestPayload, false) },
          {
            type: "image_url",
            image_url: { url: buildImageDataUrl(requestPayload.image_base64, requestPayload.media_type) }
          }
        ]
      }
    ],
    response_format: {
      type: "json_schema",
      json_schema: {
        name: "image_analysis_response",
        strict: true,
        schema: IMAGE_RESPONSE_SCHEMA
      }
    },
    temperature: 0.1
  };
  const parsed = await executeOpenRouter(payload, tier === "premium" ? 45000 : 90000);
  return normalizeImageResult(parsed, model, false);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    clearOpenRouterKey,
    getOpenRouterKey,
    getOpenRouterKeyStatus,
    migrateLegacyOpenRouterKey,
    setOpenRouterKey,
    setOpenRouterKeyPersistence
  };
}

// ── Side Panel Behavior ──────────────────────────────────────────────
async function configureSidePanelBehavior() {
  if (!chrome.sidePanel?.setPanelBehavior) {
    return;
  }

  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  } catch (error) {
    // Ignore unsupported-channel failures so the rest of the extension keeps working.
  }
}

async function loadOfflineGlossary() {
  try {
    const url = chrome.runtime.getURL("slang_terms.json");
    const response = await fetch(url);
    const data = await response.json();
    if (Array.isArray(data)) {
      await chrome.storage.local.set({ brainrotOfflineGlossary: data });
    }
  } catch (error) {
    // Ignore loading failures
  }
}

if (typeof module === "undefined" || !module.exports) {
  configureSidePanelBehavior().catch(() => undefined);
  migrateLegacyOpenRouterKey().catch(() => undefined);
}

chrome.runtime.onInstalled.addListener(() => {
  configureSidePanelBehavior().catch(() => undefined);
  loadOfflineGlossary().catch(() => undefined);

  // Phase 6: Create right-click context menu
  chrome.contextMenus.create({
    id: "brainrot-translate-selection",
    title: "Translate Brainrot",
    contexts: ["selection"]
  });
  chrome.contextMenus.create({
    id: "brainrot-analyze-image",
    title: "Analyze Brainrot Meme",
    contexts: ["image"]
  });
});

chrome.runtime.onStartup.addListener(() => {
  configureSidePanelBehavior().catch(() => undefined);
  loadOfflineGlossary().catch(() => undefined);
});

function resetBadge(tabId) {
  if (!tabId) {
    return;
  }
  tabBrainrotCounts.delete(tabId);
  chrome.action.setBadgeText({ text: "", tabId }).catch(() => undefined);
}

chrome.tabs.onRemoved.addListener((tabId) => {
  tabBrainrotCounts.delete(tabId);
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    resetBadge(tabId);
  }
});

function sendContextMenuMessage(tab, message) {
  if (!tab?.id) {
    return;
  }

  chrome.tabs.sendMessage(
    tab.id,
    message,
    () => {
      if (chrome.runtime.lastError) {
        // Content script not injected; try injecting first then retry
        chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["pet_shell.css"] }).catch(() => {});
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["shared.js", "pet_bubble.js", "content_script.js"] })
          .then(() => {
            setTimeout(() => {
              chrome.tabs.sendMessage(tab.id, message);
            }, 200);
          })
          .catch(() => {});
      }
    }
  );
}

// ── Phase 6: Context Menu Handler ────────────────────────────────────
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "brainrot-translate-selection") {
    sendContextMenuMessage(
      tab,
      { action: "brainrotContextMenuTranslate", text: info.selectionText || "" }
    );
    return;
  }

  if (info.menuItemId === "brainrot-analyze-image") {
    sendContextMenuMessage(
      tab,
      { action: "brainrotContextMenuImage", srcUrl: info.srcUrl || "" }
    );
  }
});

// ── Phase 7: Keyboard Shortcut Handler ───────────────────────────────
chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "translate-selection") {
    return;
  }
  if (!tab?.id) {
    return;
  }

  chrome.tabs.sendMessage(
    tab.id,
    { action: "brainrotKeyboardTranslate" },
    () => {
      if (chrome.runtime.lastError) {
        // Content script not injected
        chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["pet_shell.css"] }).catch(() => {});
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["shared.js", "pet_bubble.js", "content_script.js"] })
          .then(() => {
            setTimeout(() => {
              chrome.tabs.sendMessage(tab.id, { action: "brainrotKeyboardTranslate" });
            }, 200);
          })
          .catch(() => {});
      }
    }
  );
});

// ── Phase 3: History Manager ─────────────────────────────────────────
async function saveHistoryEntry(entry) {
  try {
    const result = await chrome.storage.local.get({ brainrotHistory: [] });
    const history = Array.isArray(result.brainrotHistory) ? result.brainrotHistory : [];
    history.unshift(entry);
    if (history.length > MAX_HISTORY_ENTRIES) {
      history.length = MAX_HISTORY_ENTRIES;
    }
    await chrome.storage.local.set({ brainrotHistory: history });
  } catch (error) {
    // Storage write failed — ignore silently
  }
}

// ── Message Router ───────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.action === "brainrotSetOpenRouterApiKey") {
    setOpenRouterKey(message.apiKey, message.rememberOnDevice)
      .then((status) => sendResponse({ ok: true, ...status }))
      .catch(() => sendResponse({ ok: false, error: "Unable to update OpenRouter key." }));
    return true;
  }

  if (message?.action === "brainrotGetOpenRouterApiKeyStatus") {
    getOpenRouterKeyStatus()
      .then((status) => sendResponse({
        ok: true,
        present: status.present,
        storage: status.storage,
        rememberOnDevice: status.rememberOnDevice
      }))
      .catch(() => sendResponse({ ok: false, present: false }));
    return true;
  }

  if (message?.action === "brainrotSetOpenRouterKeyPersistence") {
    setOpenRouterKeyPersistence(message.rememberOnDevice)
      .then((status) => sendResponse({ ok: true, ...status }))
      .catch(() => sendResponse({ ok: false, error: "Unable to update OpenRouter key storage." }));
    return true;
  }

  if (message?.action === "brainrotOpenRouterTextAnalysis") {
    analyzeTextWithOpenRouter(message.payload || {}, message.settings || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : "OpenRouter text analysis failed."
      }));
    return true;
  }

  if (message?.action === "brainrotOpenRouterReverseTranslate") {
    reverseWithOpenRouter(message.payload || {}, message.settings || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : "OpenRouter reverse translation failed."
      }));
    return true;
  }

  if (message?.action === "brainrotOpenRouterImageAnalysis") {
    analyzeImageWithOpenRouter(message.payload || {}, message.settings || {})
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : "OpenRouter image analysis failed."
      }));
    return true;
  }

  if (message?.action === "captureVisibleTab") {
    chrome.tabs.captureVisibleTab(
      sender.tab?.windowId,
      { format: "png" },
      (dataUrl) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        sendResponse({ ok: true, dataUrl });
      }
    );
    return true;
  }

  if (message?.action === "fetchMediaAsset" && typeof message.url === "string") {
    fetch(message.url)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Asset fetch failed with status ${response.status}.`);
        }
        const blob = await response.blob();
        const buffer = await blob.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        const chunkSize = 32768;
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += chunkSize) {
          const slice = bytes.subarray(offset, offset + chunkSize);
          binary += String.fromCharCode(...slice);
        }
        const base64 = btoa(binary);
        sendResponse({
          ok: true,
          base64,
          contentType: blob.type || "application/octet-stream",
          dataUrl: `data:${blob.type || "application/octet-stream"};base64,${base64}`
        });
      })
      .catch((error) => {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Media fetch failed."
        });
      });
    return true;
  }

  // Phase 3: Save translation to history
  if (message?.action === "brainrotSaveHistory" && message.entry) {
    saveHistoryEntry(message.entry)
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message?.action === "brainrotIncrementBadge") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse({ ok: false });
      return false;
    }
    const increment = Math.max(1, Math.floor(Number(message.amount) || 1));
    const count = (tabBrainrotCounts.get(tabId) || 0) + increment;
    tabBrainrotCounts.set(tabId, count);
    chrome.action.setBadgeBackgroundColor({ color: "#7c3aed", tabId }).catch(() => undefined);
    chrome.action.setBadgeText({ text: String(count), tabId }).catch(() => undefined);
    sendResponse({ ok: true, count });
    return false;
  }

  return false;
});
