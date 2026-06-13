const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

function createStorageArea(seed = {}) {
  const data = { ...seed };
  return {
    data,
    async get(defaults = {}) {
      if (typeof defaults === "string") {
        return { [defaults]: data[defaults] };
      }
      if (Array.isArray(defaults)) {
        return Object.fromEntries(defaults.map((key) => [key, data[key]]));
      }
      const result = {};
      for (const [key, fallback] of Object.entries(defaults)) {
        result[key] = Object.prototype.hasOwnProperty.call(data, key) ? data[key] : fallback;
      }
      return result;
    },
    async set(values) {
      Object.assign(data, values || {});
    },
    async remove(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) {
        delete data[key];
      }
    }
  };
}

async function loadBackgroundApi(localSeed = {}, sessionSeed = {}) {
  const source = fs.readFileSync("extension/background.js", "utf8");
  const module = { exports: {} };
  const local = createStorageArea(localSeed);
  const session = createStorageArea(sessionSeed);
  const addListener = () => undefined;
  const chrome = {
    storage: { local, session },
    sidePanel: { setPanelBehavior: async () => undefined },
    runtime: { onInstalled: { addListener }, onStartup: { addListener }, onMessage: { addListener } },
    contextMenus: { create: () => undefined, onClicked: { addListener } },
    tabs: { onRemoved: { addListener }, onUpdated: { addListener }, sendMessage: () => undefined },
    commands: { onCommand: { addListener } },
    action: {
      setBadgeText: async () => undefined,
      setBadgeBackgroundColor: async () => undefined
    },
    scripting: {
      insertCSS: async () => undefined,
      executeScript: async () => undefined
    }
  };

  vm.runInNewContext(
    source,
    { module, chrome, fetch, setTimeout, clearTimeout, btoa },
    { filename: "extension/background.js" }
  );
  await Promise.resolve();
  await Promise.resolve();
  return { api: module.exports, local, session };
}

test("setOpenRouterKey stores persistent keys locally by default", async () => {
  const { api, local, session } = await loadBackgroundApi();

  const status = await api.setOpenRouterKey("sk-local", true);

  assert.equal(status.present, true);
  assert.equal(status.storage, "local");
  assert.equal(local.data.brainrotOpenRouterApiKey, "sk-local");
  assert.equal(local.data.brainrotOpenRouterKeyPresent, true);
  assert.equal(local.data.brainrotOpenRouterKeyStorage, "local");
  assert.equal(local.data.brainrotRememberOpenRouterKey, true);
  assert.equal(session.data.brainrotOpenRouterApiKey, undefined);
});

test("setOpenRouterKey stores privacy-mode keys in session only", async () => {
  const { api, local, session } = await loadBackgroundApi();

  const status = await api.setOpenRouterKey("sk-session", false);

  assert.equal(status.present, true);
  assert.equal(status.storage, "session");
  assert.equal(local.data.brainrotOpenRouterApiKey, undefined);
  assert.equal(local.data.brainrotOpenRouterKeyPresent, true);
  assert.equal(local.data.brainrotOpenRouterKeyStorage, "session");
  assert.equal(local.data.brainrotRememberOpenRouterKey, false);
  assert.equal(session.data.brainrotOpenRouterApiKey, "sk-session");
});

test("setOpenRouterKeyPersistence moves an existing key between stores", async () => {
  const { api, local, session } = await loadBackgroundApi();

  await api.setOpenRouterKey("sk-move", true);
  const sessionStatus = await api.setOpenRouterKeyPersistence(false);

  assert.equal(sessionStatus.present, true);
  assert.equal(sessionStatus.storage, "session");
  assert.equal(local.data.brainrotOpenRouterApiKey, undefined);
  assert.equal(session.data.brainrotOpenRouterApiKey, "sk-move");

  const localStatus = await api.setOpenRouterKeyPersistence(true);

  assert.equal(localStatus.present, true);
  assert.equal(localStatus.storage, "local");
  assert.equal(local.data.brainrotOpenRouterApiKey, "sk-move");
  assert.equal(session.data.brainrotOpenRouterApiKey, undefined);
});

test("migrateLegacyOpenRouterKey moves the old token to persistent storage", async () => {
  const { api, local, session } = await loadBackgroundApi({ brainrotApiAuthToken: "sk-legacy" });

  await api.migrateLegacyOpenRouterKey();

  assert.equal(local.data.brainrotOpenRouterApiKey, "sk-legacy");
  assert.equal(local.data.brainrotApiAuthToken, undefined);
  assert.equal(local.data.brainrotOpenRouterKeyStorage, "local");
  assert.equal(session.data.brainrotOpenRouterApiKey, undefined);
});
