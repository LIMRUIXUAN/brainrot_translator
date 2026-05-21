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
});

chrome.runtime.onStartup.addListener(() => {
  configureSidePanelBehavior().catch(() => undefined);
});

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

  return false;
});
