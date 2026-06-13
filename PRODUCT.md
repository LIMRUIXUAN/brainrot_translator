# Brainrot Translator Product Specification

## Product Summary

Brainrot Translator is an extension-first translator for internet slang, meme-coded language, and visual meme semantics. It helps users understand "brainrot" text or images while browsing the web by translating selected text, pasted text, screenshots, and meme-like media into clear English at the moment of confusion. It also supports reverse translation from standard English into internet slang for controlled, playful rewriting.

The product is currently implemented as a local FastAPI backend plus a Chrome Manifest V3 extension. The extension is the right primary form factor because the pain happens inside webpages: comments, forums, articles, social feeds, and image-heavy meme contexts. A standalone website can exist later as a demo or fallback, but the product should be validated first as a page-native browser utility.

## Stress-Test Verdict Alignment

The business stress test produced this working verdict:

- Form factor: Chrome extension is a strong fit.
- Business readiness: wait and validate before treating this as a standalone business.
- Primary risk: "brainrot translator for everyone" is too broad and likely becomes a novelty.
- Stronger wedge: a specific group that repeatedly encounters confusing English internet culture while browsing.
- Validation threshold: at least 6 of 10 users in the first chosen segment use it unprompted twice within 7 days and can name one real confusion moment it solved.

This document therefore treats Brainrot Translator as a focused extension MVP, not a complete platform. Advanced pieces such as dashboards, local model training, review queues, and analytics are useful, but they should not distract from proving repeat usage in the extension.

## Problem

Internet language changes quickly. Slang terms, meme templates, reaction images, and ironic phrasing often carry meaning that is not obvious from the literal words or pixels. Users may see phrases such as "negative aura", "let him cook", "caught in 4K", "rizz", "mid", or visual meme reactions and need:

- A plain-English equivalent.
- The cultural or social meaning behind the phrase or image.
- A confidence signal when interpretation is uncertain.
- A way to understand content in context without leaving the page.

Standard dictionaries are too slow and literal. Generic AI chat is too heavy for a quick browser moment. Brainrot Translator should sit directly where the confusion happens.

## Target Users

### Beachhead User

- Non-native English speakers, international students, and globally distributed professionals who can read formal English but struggle with rapidly changing internet slang and meme references on English-language webpages.

This beachhead is the best initial fit for a browser extension because the user already reads web content in Chrome, the pain appears during browsing, and the translation outcome is concrete: "I understand what this phrase or meme meant."

### Secondary User Segments

- Parents and teachers trying to understand youth or online slang in articles, messages, or public posts.
- Moderators and community managers who need quick explanations of slang or meme-coded posts.
- Content creators and social media managers who need to interpret trends or rewrite plain text into internet-native phrasing.
- Students and casual web users who encounter unfamiliar slang on social media, forums, articles, and chats.

### Internal and Advanced Users

- Developers and ML experimenters training local slang translation models.
- Linguistics, culture, or media researchers tracking slang frequency and usage patterns.
- QA reviewers who need to inspect low-confidence translations and improve future datasets.

## Product Goals

- Translate brainrot text into formal, understandable English with context and confidence.
- Analyze meme-like images and GIFs when they carry internet-culture meaning.
- Keep the translation workflow lightweight and page-native.
- Prove repeat extension usage in one specific beachhead segment before expanding scope.
- Make privacy and remote-analysis controls obvious enough that users trust the extension.
- Require users to provide their own OpenRouter API key in extension settings for AI-powered features.
- Support offline and local-first behavior where possible.
- Let users customize their own slang dictionary.
- Capture lightweight history for user utility.
- Keep advanced model, cache, frequency, and review systems available for learning, but secondary to the core translation loop.

## Non-Goals

- The product is not a general-purpose language translator for all languages.
- The product is not a moderation or safety enforcement system.
- The product is not intended to identify private people, infer sensitive traits, or surveil users.
- The product is not a replacement for human cultural judgment in high-stakes contexts.
- The extension should not attempt to analyze every image or every text node automatically by default if that creates noise, cost, or privacy concerns.
- The MVP should not lead with dashboards, model training, or admin review workflows before repeat end-user value is proven.
- The MVP should not try to cover mobile-only contexts such as TikTok, Instagram, Snapchat, or YouTube Shorts apps.

## Value Proposition

Brainrot Translator turns confusing internet text and memes into readable meaning in one click or hover. Unlike a static glossary, it considers sentence context, page context, and visual meme semantics. Unlike a general chatbot, it lives inside the page and returns a structured answer without forcing the user to copy, paste, switch tabs, or explain the context manually.

The value is strongest when the user is actively browsing and needs a quick explanation. If the user is willing to leave the page and ask a chatbot, the product loses most of its advantage.

## Current Product Surface and MVP Priority

### Chrome Extension

Core MVP:

- Persistent side panel for translation, settings, history, and glossary.
- In-page floating pet bubble that shows analysis results near selected text or media.
- Text highlight analysis through mouse selection.
- Optional confirmation before highlighted text is translated.
- Direct paste translation in the side panel.
- Hover image or GIF analysis after a 600ms hover delay.
- Custom dictionary with add, import, and export flows.
- Translation history with search, type filtering, clear, JSON export, and CSV export.
- Backend health and active page connection checks.

Useful but secondary:

- Floating launcher dock with capture, hover toggle, scale controls, drag positioning, and minimize / restore.
- Reverse translation from English to brainrot slang.
- Screenshot capture flow from the floating launcher.
- Clipboard image paste analysis.
- Context menu actions for selected text and image analysis.
- Keyboard shortcut: `Ctrl+Shift+B` or `Command+Shift+B`.
- Page scan and inline annotation support for known brainrot terms.
- Onboarding tutorial.
- Dashboard metrics and slang frequency chart.

### FastAPI Backend

- `/health`
- `/translate`
- `/api/v1/analyze-highlighted-text`
- `/api/v1/recheck-highlighted-text`
- `/api/v1/reverse-translate`
- `/api/v1/analyze-screenshot-media`
- `/api/v1/analyze-image`
- `/api/v1/telemetry/slang-detections`
- `/api/v1/public/top-slang`
- `/api/v1/admin/slang`
- `/api/v1/dashboard/word-frequency`
- `/api/v1/dashboard/stats`

### Model and Data Behavior

Core MVP behavior:

- Local slang dataset lookup from `slang_terms.json`.
- Heuristic confidence fallback when the classifier is unavailable.
- OpenRouter text fallback and manual recheck using the user's API key from extension settings.
- OpenRouter vision model for image and GIF analysis using the user's API key from extension settings.
- User-selectable OpenRouter model tiers: Free NVIDIA by default, Premium DeepSeek for text, and Premium Gemini for image understanding.
- Opt-in anonymous slang frequency sharing for the shared public leaderboard.

Advanced / learning-system behavior:

- Optional fine-tuned local FLAN-T5 text translation model.
- Optional local quality classifier.
- Monthly shared slang frequency tracking with yearly leaderboard aggregation.
- Admin moderation for hiding or banning unsafe terms from public rankings.

## Core User Journeys

### 1. Highlight Text on a Webpage

1. User selects text on a normal `http` or `https` webpage.
2. If confirmation is enabled, the floating pet asks whether to translate.
3. User confirms or the product auto-runs based on settings.
4. Backend analyzes the text using local dataset, local model, cache, or remote fallback.
5. The pet bubble displays:
   - Original brainrot text.
   - Equivalent formal English.
   - Explanation.
   - Sentiment where available.
   - Confidence.
   - Review / recheck affordance.
6. Result is saved to local history.
7. If anonymous frequency sharing is enabled, the extension sends detected term/count pairs without page text, URLs, images, or API keys.

### 2. Direct Translation in Side Panel

1. User opens the side panel.
2. User pastes text into Direct Translate.
3. User chooses direction:
   - Brainrot to English.
   - English to Brainrot.
4. Product calls the relevant backend route or fallback.
5. Result appears in the side panel and is stored in history.

### 3. Analyze Meme Image or GIF

1. User enables hover image analysis.
2. User hovers over likely meme media for at least 600ms.
3. Extension builds a media payload from the source, screenshot, frame, or visible capture.
4. Backend validates media type and size.
5. Backend checks image cache by hash.
6. On cache miss, backend calls the configured vision model.
7. Pet bubble explains the visual meme meaning and confidence.
8. Result is saved to local history.
9. Image analysis results are saved locally in browser history; shared telemetry never sends image payloads.

### 4. Capture or Paste an Image

1. User clicks Capture in the floating launcher or pastes an image from the clipboard.
2. Extension creates a screenshot or file payload.
3. Backend analyzes it through the same media route.
4. Pet bubble displays the result near the launcher.

### 5. Customize Dictionary

1. User opens History / Glossary.
2. User adds a slang term and meaning.
3. Custom term becomes available to client-side matching and page scans.
4. User can import or export dictionary data.

### 6. Review Dashboard

Dashboard is an advanced learning and demo surface, not a primary MVP workflow.

1. User opens History / Glossary.
2. User clicks Refresh.
3. Side panel loads the moderated current-month Top Slang Frequency.
4. The current-month view resets automatically every month.
5. The annual countdown aggregates archived monthly counts for the selected year.
6. Dashboard depends on database availability.

### 7. First-Week Validation Test

1. Recruit 10 users from the beachhead segment.
2. Install the extension with the minimal core features enabled.
3. Ask users to browse normally for 7 days.
4. Measure whether at least 6 users use it unprompted twice.
5. Interview each user for one real moment where the extension helped or failed.
6. Continue building only if repeat usage and specific pain stories appear.

## Functional Requirements

### Text Analysis

- The system must accept non-empty highlighted text.
- The system must include page URL, page title, page domain, nearest heading, and surrounding text when available.
- The system must classify whether selected text is brainrot, slang, or meme-coded.
- The system must return the full formal equivalent, not only definitions for isolated keywords.
- The system must return a concise cultural explanation.
- The system must include a confidence score from `0.0` to `1.0`.
- The system must flag outputs for review when confidence is below the configured threshold.
- The system must support manual recheck that bypasses stale low-confidence local or cached results.
- The system must preserve the original text when no brainrot is detected.

### Reverse Translation

- The system must convert normal English into natural internet slang.
- The system must preserve the original meaning and avoid unrelated additions.
- The result must be visibly different from the source when possible.
- The system must return confidence and model attribution.

### Image and GIF Analysis

- The system must support `image/gif`, `image/jpeg`, `image/png`, and `image/webp`.
- The system must reject empty or invalid base64 payloads.
- The system must reject payloads larger than the configured maximum size.
- The system must identify when an image or GIF functions as brainrot or meme-coded visual language.
- The system must ignore ordinary photos, generic decorative assets, and non-meme imagery when no brainrot meaning exists.
- The system must return formal visual meaning, explanation, confidence, model attribution, and fallback-frame status.
- Hover image analysis must be user-controlled and should default to a clearly explained opt-in in production.

### Browser Extension

- The extension must run on normal `http` and `https` pages.
- The extension must not rely on content scripts on protected Chrome pages.
- Users must be able to enable or disable text selection analysis, hover analysis, launcher, clipboard paste, inline annotation, and confirmation prompts.
- The side panel must persist settings in `chrome.storage.local`.
- The side panel must save text and image model tiers and apply them across active Chrome pages through storage change listeners.
- The first-run experience must default anonymous shared frequency to off.
- The floating launcher must support drag positioning, scaling, minimizing, and restoring.
- The pet bubble must show loading, confirmation, success, non-brainrot, error, and retry states.
- History must be searchable and filterable by type.
- History must export as JSON and CSV.
- Dictionary must import and export custom terms.
- The first-run experience must explain what page context and media data may be processed locally, sent to OpenRouter for AI features, or sent to the backend as anonymous term/count telemetry.

### Backend and Persistence

- The backend must expose a health check with database, local model, quality classifier, and API base status.
- The backend must expose public model-tier configuration so the extension can call OpenRouter directly without sending keys to the backend.
- The backend must apply rate limits to analysis and dashboard routes.
- The backend must support SQLite for local development and PostgreSQL-style schema concepts for production.
- Shared slang frequency must be stored by calendar month.
- The public leaderboard must exclude terms marked `hidden` or `banned`.
- Annual countdown rankings must aggregate monthly rows for the selected year.
- Dashboard stats must degrade gracefully when database is unavailable.
- The product must remain useful without shared telemetry enabled.

## Non-Functional Requirements

### Privacy

- The product should collect the minimum page context required for interpretation.
- User-provided OpenRouter API keys must stay in extension storage and be sent only from the extension background service worker directly to OpenRouter. The production default remembers the key in `chrome.storage.local` for this browser profile; privacy mode stores it only in `chrome.storage.session` until Chrome closes.
- The backend must not use a shared `OPENROUTER_API_KEY` from `.env`.
- Shared telemetry must not include OpenRouter API keys, raw page text, page URLs, domains, image payloads, or surrounding context.
- The extension should send anonymous telemetry and public/admin dashboard traffic through the configured backend, while AI model calls go directly to OpenRouter from the browser.
- Image analysis should be explicitly controllable because image payloads can contain sensitive content.
- History and custom dictionaries should remain local unless the user exports them.
- First-run onboarding should make clear that selected text, surrounding context, and image payloads may be processed by a local backend and optionally by configured remote models.
- Production builds should prefer opt-in controls for hover image analysis and clipboard image analysis.

### Performance

- Text selection should feel immediate for local glossary or cache hits.
- Hover image analysis must debounce accidental mouse movement.
- Duplicate or rapid repeated requests should be deduplicated or cooled down.
- Backend route timeouts should produce graceful fallback responses.
- Local model loading can be lazy but health should disclose availability.

### Reliability

- If the backend is unreachable, the extension should show an actionable error and use client offline glossary where available.
- If OpenRouter is unavailable or no user key is present, local/offline text routes should still work when possible while AI-only features show a clear missing-key error.
- If the extension context is invalidated, users should be guided to reload the extension and page.
- Invalid media and invalid JSON requests must return clear validation errors.

### Accessibility

- Side panel tabs must expose appropriate tab semantics.
- Buttons and controls must have accessible labels where needed.
- Result messages should be readable without relying only on color.
- Keyboard shortcut and context menu flows should remain available for users who avoid pointer-heavy workflows.

## Success Metrics

### Validation Metrics

- First-week repeat usage: at least 6 of 10 beachhead users use the extension unprompted twice within 7 days.
- Pain-story capture: at least 6 of 10 users can name one specific moment where the extension resolved confusion.
- Activation: percentage of installed users who complete first successful highlighted-text translation.
- Core loop retention: percentage of users who translate text or media again within 7 days.
- Extension-fit proof: percentage of users who say the value would be meaningfully worse as a copy/paste website.

### Product Quality Metrics

- Text translation success rate: percentage of highlighted slang selections returning a useful equivalent.
- Low-confidence rate: percentage of results below `BRAINROT_LOW_CONFIDENCE_THRESHOLD`.
- Recheck improvement rate: percentage of rechecked results that produce higher confidence or clearer explanation.
- Cache hit rate for text and image analysis.
- Average response time by route and model path.
- Number of custom dictionary terms added.
- History reuse: percentage of users who search, export, or revisit prior translations.
- Dashboard top-term counts and unique slang coverage, treated as learning-system metrics after core retention is proven.
- Manual QA acceptance rate for low-confidence review items, treated as model-improvement metrics after core retention is proven.

## Risks and Mitigations

- Novelty risk: users may try it once, laugh, and never return.
  - Mitigation: validate repeat usage with one beachhead segment before adding broad platform features.
- Segment risk: "everyone confused by brainrot" is too broad to sell or design for.
  - Mitigation: start with non-native English speakers and international students/professionals, then compare secondary segments.
- Channel limitation: much brainrot lives in mobile apps where Chrome extensions cannot operate.
  - Mitigation: focus on web-native contexts first and do not claim mobile app coverage in the MVP.
- Thin-wrapper risk: generic AI tools and major browsers may add similar translation or explanation features.
  - Mitigation: differentiate through page-native UX, visual meme analysis, custom dictionary, local history, and fast contextual workflows.
- Fast-changing slang can make outputs stale.
  - Mitigation: custom dictionary, import/export, model-tier choice, manual recheck, and admin moderation for shared rankings.
- Meme images can be ambiguous or context dependent.
  - Mitigation: include page title/domain/source URL and confidence flags.
- Remote model cost or latency can grow with image analysis.
  - Mitigation: hover debounce, cache, media size limits, and user-controlled toggles.
- Privacy concerns around page context and screenshots.
  - Mitigation: local backend proxy, explicit settings, minimal payloads, and clear controls.
- False positives may annoy users.
  - Mitigation: confirmation mode, inline annotation toggle, glossary-first detection, and non-brainrot fallback.

## Release Scope

### Validation MVP

- Chrome extension with side panel and floating pet UI.
- Text selection analysis.
- Direct text translation.
- Image hover analysis with explicit user control.
- Offline glossary fallback.
- Custom dictionary.
- History and export.
- Backend health and basic caching.
- First-run privacy explanation.

### Already Implemented but Not Launch-Critical

- Reverse translation.
- Screenshot capture.
- Clipboard image paste.
- Page scan and inline annotation.
- Local FLAN-T5 model loading.
- Local quality classifier loading.
- Review staging.
- Dashboard stats and frequency chart.

### Recommended Next Iteration

- Run the 10-user, 7-day validation test with the beachhead segment.
- Use interview quotes to decide whether to continue with the same segment, pivot segments, or stop.
- Add user controls for history retention and clearing all local data.
- Add model-path indicators directly in result cards.
- Add a safer permission mode that only enables image hover per-site.
- Add automated screenshot regression checks for the extension UI.
- Add a dedicated review admin page only after the product has repeat users.
- Add dataset update workflow from verified review rows back into training data.

## Open Questions

- Should image hover analysis be opt-in per domain rather than global?
- Should history sync across browsers, or remain strictly local?
- What confidence threshold best balances helpfulness and noise for casual users?
- Should custom dictionary terms affect backend analysis, client-only analysis, or both?
- Should the product provide educational explanations in multiple languages?
- Should production deployments default to remote models, local models, or hybrid routing?
- Which beachhead segment retains best: non-native English speakers, parents/teachers, moderators, or creators?
- Would users still choose this if Chrome, Google Lens, or a general AI assistant added native meme/slang explanation?
