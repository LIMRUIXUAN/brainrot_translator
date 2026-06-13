const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

function loadContentScriptApi() {
  const sharedSource = fs.readFileSync("extension/shared.js", "utf8");
  const source = fs.readFileSync("extension/content_script.js", "utf8");
  const module = { exports: {} };
  const window = {
    __brainrotContentScriptLoaded: false,
    BrainrotPetBubble: class BrainrotPetBubble {},
    getComputedStyle(element) {
      return element.__computedStyle || { backgroundImage: "none" };
    },
    location: { href: "https://example.test/articles/post" }
  };
  const document = {};

  vm.runInNewContext(
    sharedSource,
    {
      module: { exports: {} },
      window,
      globalThis: window
    },
    { filename: "extension/shared.js" }
  );

  vm.runInNewContext(
    source,
    {
      module,
      window,
      document,
      URL
    },
    { filename: "extension/content_script.js" }
  );

  return module.exports;
}

function imageElement(src, rect = { width: 320, height: 180 }) {
  return {
    tagName: "IMG",
    currentSrc: src,
    src,
    getBoundingClientRect() {
      return rect;
    }
  };
}

test("normalizeSettings trims values and preserves boolean edge cases", () => {
  const api = loadContentScriptApi();
  const normalized = api.normalizeSettings({
    brainrotApiBaseUrl: " http://localhost:9000/// ",
    brainrotApiAuthToken: " secret-token ",
    brainrotEnableTextSelection: false,
    brainrotEnableHoverDetection: "false",
    brainrotEnableInlineAnnotation: true,
    brainrotTextModelSpeed: "slow",
    brainrotLauncherPosition: { left: 14.4, top: 92.6 },
    brainrotLauncherScale: 2.2,
    brainrotLauncherMinimized: true
  });

  assert.equal(normalized.brainrotApiBaseUrl, "http://localhost:9000");
  assert.equal(normalized.brainrotApiAuthToken, "secret-token");
  assert.equal(normalized.brainrotEnableTextSelection, false);
  assert.equal(normalized.brainrotEnableHoverDetection, true);
  assert.equal(normalized.brainrotEnableInlineAnnotation, true);
  assert.equal(normalized.brainrotTextModelSpeed, "slow");
  assert.equal(normalized.brainrotLauncherPosition.left, 14);
  assert.equal(normalized.brainrotLauncherPosition.top, 93);
  assert.equal(normalized.brainrotLauncherScale, 1.5);
  assert.equal(normalized.brainrotLauncherMinimized, true);
});

test("normalizeSettings defaults invalid text model speed to fast", () => {
  const api = loadContentScriptApi();
  const normalized = api.normalizeSettings({ brainrotTextModelSpeed: "turbo" });

  assert.equal(normalized.brainrotTextModelSpeed, "fast");
});

test("clampLauncherScale clamps and rounds boundary values", () => {
  const api = loadContentScriptApi();

  assert.equal(api.clampLauncherScale(0.1), 0.7);
  assert.equal(api.clampLauncherScale(1.26), 1.3);
  assert.equal(api.clampLauncherScale(5), 1.5);
  assert.equal(api.clampLauncherScale("bad"), 1);
});

test("isMemeCandidate detects meme hosts, keyword hints, and meme-sized media", () => {
  const api = loadContentScriptApi();

  assert.equal(api.isMemeCandidate(imageElement("https://media.giphy.com/media/example.gif")), true);
  assert.equal(api.isMemeCandidate(imageElement("https://cdn.example.test/sigma-edit.jpg")), true);
  assert.equal(api.isMemeCandidate(imageElement("https://cdn.example.test/plain-photo.jpg")), true);
  assert.equal(
    api.isMemeCandidate(imageElement("https://cdn.example.test/icon.jpg", { width: 48, height: 48 })),
    false
  );
});

test("hasKeywordHint matches brainrot keywords in URLs", () => {
  const api = loadContentScriptApi();

  assert.equal(api.hasKeywordHint("https://example.test/posts/skibidi-rizz.png"), true);
  assert.equal(api.hasKeywordHint("https://example.test/posts/quarterly-report.png"), false);
});

test("lookupCustomDictionary returns exact case-insensitive matches", () => {
  const api = loadContentScriptApi();
  api.setCustomDictionaryForTest([
    { term: "Gyatt", meaning: "exclamation of surprise" },
    { term: "NPC", meaning: "unoriginal person" }
  ]);

  assert.deepEqual(api.lookupCustomDictionary("gyatt"), {
    term: "Gyatt",
    meaning: "exclamation of surprise"
  });
  assert.equal(api.lookupCustomDictionary("npc behavior"), null);
});

test("getMediaType infers image content types from URL patterns", () => {
  const api = loadContentScriptApi();

  assert.equal(api.getMediaType("https://example.test/a.gif"), "image/gif");
  assert.equal(api.getMediaType("https://example.test/a?format=gif"), "image/gif");
  assert.equal(api.getMediaType("https://example.test/a.png"), "image/png");
  assert.equal(api.getMediaType("https://example.test/a.webp"), "image/webp");
  assert.equal(api.getMediaType("https://example.test/a.jpeg"), "image/jpeg");
});

test("GIF frame extraction prefers fetched data URL over remote source URL", () => {
  const api = loadContentScriptApi();
  const remoteUrl = "https://media.giphy.com/media/example.gif";
  const dataUrl = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

  assert.equal(api.getGifFrameExtractionSource({ dataUrl }, remoteUrl), dataUrl);
  assert.equal(api.getGifFrameExtractionSource({}, remoteUrl), remoteUrl);
});

test("normalizeCaptureRect clamps and supports reverse drag direction", () => {
  const api = loadContentScriptApi();

  assert.equal(
    JSON.stringify(api.normalizeCaptureRect(420, 260, 120, 80, 500, 300)),
    JSON.stringify({ left: 120, top: 80, width: 300, height: 180 })
  );
  assert.equal(
    JSON.stringify(api.normalizeCaptureRect(-20, 20, 700, 340, 500, 300)),
    JSON.stringify({ left: 0, top: 20, width: 500, height: 280 })
  );
  assert.equal(api.isUsableCaptureRect({ left: 10, top: 10, width: 7, height: 40 }), false);
  assert.equal(api.isUsableCaptureRect({ left: 10, top: 10, width: 80, height: 40 }), true);
});
