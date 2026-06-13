(function (root) {
  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const BASE_DEFAULT_SETTINGS = Object.freeze({
    brainrotApiBaseUrl: DEFAULT_API_BASE,
    brainrotApiAuthToken: "",
    brainrotEnableTextSelection: true,
    brainrotConfirmTextSelection: true,
    brainrotEnableHoverDetection: true,
    brainrotEnableLauncher: true,
    brainrotEnableClipboardPaste: true,
    brainrotEnableInlineAnnotation: false,
    brainrotTextModelSpeed: "fast",
    brainrotLauncherPosition: null
  });

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function normalizeSettings(rawSettings, options = {}) {
    const defaults = {
      ...BASE_DEFAULT_SETTINGS,
      ...(options.defaults || {})
    };
    const raw = rawSettings || {};
    const apiBase =
      typeof raw.brainrotApiBaseUrl === "string" && raw.brainrotApiBaseUrl.trim()
        ? raw.brainrotApiBaseUrl.trim()
        : DEFAULT_API_BASE;

    const normalized = {
      brainrotApiBaseUrl: apiBase.replace(/\/+$/, ""),
      brainrotApiAuthToken:
        typeof raw.brainrotApiAuthToken === "string"
          ? raw.brainrotApiAuthToken.trim()
          : defaults.brainrotApiAuthToken,
      brainrotEnableTextSelection:
        typeof raw.brainrotEnableTextSelection === "boolean"
          ? raw.brainrotEnableTextSelection
          : defaults.brainrotEnableTextSelection,
      brainrotConfirmTextSelection:
        typeof raw.brainrotConfirmTextSelection === "boolean"
          ? raw.brainrotConfirmTextSelection
          : defaults.brainrotConfirmTextSelection,
      brainrotEnableHoverDetection:
        typeof raw.brainrotEnableHoverDetection === "boolean"
          ? raw.brainrotEnableHoverDetection
          : defaults.brainrotEnableHoverDetection,
      brainrotEnableLauncher:
        typeof raw.brainrotEnableLauncher === "boolean"
          ? raw.brainrotEnableLauncher
          : defaults.brainrotEnableLauncher,
      brainrotEnableClipboardPaste:
        typeof raw.brainrotEnableClipboardPaste === "boolean"
          ? raw.brainrotEnableClipboardPaste
          : defaults.brainrotEnableClipboardPaste,
      brainrotEnableInlineAnnotation:
        typeof raw.brainrotEnableInlineAnnotation === "boolean"
          ? raw.brainrotEnableInlineAnnotation
          : defaults.brainrotEnableInlineAnnotation,
      brainrotTextModelSpeed:
        raw.brainrotTextModelSpeed === "slow"
          ? "slow"
          : defaults.brainrotTextModelSpeed,
      brainrotLauncherPosition:
        raw.brainrotLauncherPosition &&
        Number.isFinite(raw.brainrotLauncherPosition.left) &&
        Number.isFinite(raw.brainrotLauncherPosition.top)
          ? {
              left: Math.round(raw.brainrotLauncherPosition.left),
              top: Math.round(raw.brainrotLauncherPosition.top)
            }
          : defaults.brainrotLauncherPosition
    };

    if (typeof options.clampLauncherScale === "function") {
      normalized.brainrotLauncherScale = options.clampLauncherScale(raw.brainrotLauncherScale);
    } else if (Object.prototype.hasOwnProperty.call(defaults, "brainrotLauncherScale")) {
      normalized.brainrotLauncherScale = defaults.brainrotLauncherScale;
    }

    if (Object.prototype.hasOwnProperty.call(defaults, "brainrotLauncherMinimized")) {
      normalized.brainrotLauncherMinimized =
        typeof raw.brainrotLauncherMinimized === "boolean"
          ? raw.brainrotLauncherMinimized
          : defaults.brainrotLauncherMinimized;
    }

    return normalized;
  }

  function translateTextOffline(text, glossary) {
    const cleaned = String(text || "").trim();
    const offlineGlossary = Array.isArray(glossary) ? glossary : [];
    if (!cleaned) {
      return {
        is_brainrot: false,
        brainrot_text: null,
        equivalent_text: "",
        formal_explanation: "Empty text.",
        sentiment_label: "unclear",
        confidence_score: 0.0,
        flagged_for_review: false,
        model_used: "client_offline_glossary"
      };
    }

    const lowered = cleaned.toLowerCase();
    const exactMatches = offlineGlossary.filter(
      (entry) => String(entry.term || "").toLowerCase().trim() === lowered
    );
    if (exactMatches.length > 0) {
      const match = exactMatches[0];
      return {
        is_brainrot: true,
        brainrot_text: match.term,
        equivalent_text: match.meaning,
        formal_explanation: `Matched exact term "${match.term}" offline.`,
        sentiment_label: "neutral",
        confidence_score: 0.8,
        flagged_for_review: false,
        model_used: "client_offline_glossary"
      };
    }

    const matched = [];
    const sortedGlossary = [...offlineGlossary].sort((a, b) => {
      return String(b.term || "").length - String(a.term || "").length;
    });

    for (const entry of sortedGlossary) {
      const term = String(entry.term || "").trim();
      const meaning = String(entry.meaning || "").trim();
      if (!term || !meaning) continue;
      const normalizedTerm = term.toLowerCase();
      if (normalizedTerm.length < 2) continue;

      try {
        const pattern = new RegExp(`(?<!\\w)${escapeRegExp(normalizedTerm)}(?!\\w)`, "i");
        if (pattern.test(lowered)) matched.push({ term, meaning });
      } catch (error) {
        const pattern = new RegExp(`\\b${escapeRegExp(normalizedTerm)}\\b`, "i");
        if (pattern.test(lowered)) matched.push({ term, meaning });
      }
    }

    if (matched.length > 0) {
      let normal = cleaned;
      if (matched.length === 1 && matched[0].term.toLowerCase().trim() === lowered) {
        normal = matched[0].meaning;
      } else {
        let substituted = cleaned;
        const termsExplained = [];
        for (const entry of sortedGlossary) {
          const term = String(entry.term || "").trim();
          const meaning = String(entry.meaning || "").trim();
          if (!term || !meaning) continue;
          const normalizedTerm = term.toLowerCase();
          if (normalizedTerm.length < 2) continue;

          const pattern = new RegExp(`\\b${escapeRegExp(normalizedTerm)}\\b`, "gi");
          if (pattern.test(substituted)) {
            pattern.lastIndex = 0;
            const cleanMeaning = meaning.trim().replace(/\.+$/, "");
            substituted = substituted.replace(pattern, `[${cleanMeaning}]`);
            termsExplained.push(`${term}: ${cleanMeaning}`);
          }
        }
        normal = termsExplained.length > 0
          ? substituted.replace(/\s+/g, " ").trim()
          : "Possible meaning: " + matched.slice(0, 4).map((m) => `${m.term}: ${m.meaning}`).join(" | ");
      }

      return {
        is_brainrot: true,
        brainrot_text: matched.map((m) => m.term).join(", "),
        equivalent_text: normal,
        formal_explanation: "Offline translation (glossary lookup).",
        sentiment_label: "neutral",
        confidence_score: 0.8,
        flagged_for_review: false,
        model_used: "client_offline_glossary"
      };
    }

    return {
      is_brainrot: false,
      brainrot_text: null,
      equivalent_text: cleaned,
      formal_explanation: "No brainrot detected (Offline glossary check).",
      sentiment_label: "unclear",
      confidence_score: 0.8,
      flagged_for_review: false,
      model_used: "client_offline_glossary"
    };
  }

  function buildApiHeaders(settings, includeJson = false) {
    const headers = {};
    if (includeJson) headers["Content-Type"] = "application/json";
    const token = String(settings?.brainrotApiAuthToken || "").trim();
    if (token) headers["X-OpenRouter-API-Key"] = token;
    return headers;
  }

  function hasOpenRouterApiKey(settings) {
    return Boolean(String(settings?.brainrotApiAuthToken || "").trim());
  }

  function getApiErrorMessage(response, payload, fallback = "Backend request failed.") {
    if (response.status === 429) {
      return "Please wait before trying again. The backend rate limit was reached.";
    }
    if (response.status === 401) {
      return "OpenRouter API key is missing or invalid. Add your key in Settings.";
    }
    return payload?.detail || payload?.error || fallback;
  }

  function shouldRetryApiError(error) {
    const message = String(error?.message || "");
    return !message.startsWith("Please wait") && !message.startsWith("OpenRouter API key");
  }

  const api = {
    DEFAULT_API_BASE,
    BASE_DEFAULT_SETTINGS,
    escapeRegExp,
    normalizeSettings,
    translateTextOffline,
    buildApiHeaders,
    hasOpenRouterApiKey,
    getApiErrorMessage,
    shouldRetryApiError
  };

  root.BrainrotShared = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
