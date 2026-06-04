/* ------------------------------------------------------------------ */
/* Brainrot Translator — Background Service Worker                    */
/* Phases 3, 6, 7: History, Context Menu, Keyboard Shortcut           */
/* ------------------------------------------------------------------ */

const MAX_HISTORY_ENTRIES = 200;
const tabBrainrotCounts = new Map();

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

configureSidePanelBehavior().catch(() => undefined);

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
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["pet_bubble.js", "content_script.js"] })
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
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["pet_bubble.js", "content_script.js"] })
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
