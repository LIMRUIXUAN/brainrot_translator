/* ------------------------------------------------------------------ */
/* Brainrot Translator — Background Service Worker                    */
/* Phases 3, 6, 7: History, Context Menu, Keyboard Shortcut           */
/* ------------------------------------------------------------------ */

const MAX_HISTORY_ENTRIES = 200;

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

configureSidePanelBehavior().catch(() => undefined);

chrome.runtime.onInstalled.addListener(() => {
  configureSidePanelBehavior().catch(() => undefined);

  // Phase 6: Create right-click context menu
  chrome.contextMenus.create({
    id: "brainrot-translate-selection",
    title: "Translate Brainrot",
    contexts: ["selection"]
  });
});

chrome.runtime.onStartup.addListener(() => {
  configureSidePanelBehavior().catch(() => undefined);
});

// ── Phase 6: Context Menu Handler ────────────────────────────────────
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "brainrot-translate-selection") {
    return;
  }
  if (!tab?.id) {
    return;
  }

  chrome.tabs.sendMessage(
    tab.id,
    { action: "brainrotContextMenuTranslate", text: info.selectionText || "" },
    () => {
      if (chrome.runtime.lastError) {
        // Content script not injected; try injecting first then retry
        chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["pet_shell.css"] }).catch(() => {});
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["pet_bubble.js", "content_script.js"] })
          .then(() => {
            setTimeout(() => {
              chrome.tabs.sendMessage(tab.id, { action: "brainrotContextMenuTranslate", text: info.selectionText || "" });
            }, 200);
          })
          .catch(() => {});
      }
    }
  );
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

  return false;
});
