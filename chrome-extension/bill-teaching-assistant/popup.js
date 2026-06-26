const DEFAULT_API_BASE = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";

const sessionIdInput = document.getElementById("sessionId");
const apiBaseInput = document.getElementById("apiBase");
const statusValue = document.getElementById("statusValue");
const metaValue = document.getElementById("metaValue");
const connectButton = document.getElementById("connect");
const disconnectButton = document.getElementById("disconnect");
const contentStateValue = document.getElementById("contentStateValue");
const pairedSessionValue = document.getElementById("pairedSessionValue");
const tabUrlValue = document.getElementById("tabUrlValue");
const lastEventValue = document.getElementById("lastEventValue");
const testContextButton = document.getElementById("testContext");
const diagNote = document.getElementById("diagNote");

function formatTime(value) {
  if (!value) return "n/a";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "n/a";
  return d.toLocaleTimeString();
}

async function askBackground(message) {
  try {
    return await chrome.runtime.sendMessage(message);
  } catch {
    return null;
  }
}

async function loadState() {
  const stateResponse = await askBackground({ type: "BTA_GET_STATE" });
  const state = stateResponse?.ok ? stateResponse : {
    sessionId: "",
    apiBase: DEFAULT_API_BASE,
    enabled: false,
    lastSync: null,
    lastError: null,
    lastEventType: null,
    lastEventOutcome: null,
    lastEventHttpStatus: null,
  };
  const diagnostics = await askBackground({ type: "BTA_GET_TAB_DIAGNOSTICS" });

  sessionIdInput.value = state.sessionId || "";
  apiBaseInput.value = state.apiBase || DEFAULT_API_BASE;

  const paired = Boolean(state.enabled && state.sessionId);
  statusValue.textContent = paired ? "Paired" : "Waiting";
  metaValue.textContent = paired
    ? `Session ${state.sessionId}${state.lastSync ? ` • synced ${formatTime(state.lastSync)}` : ""}${state.lastError ? ` • last error: ${state.lastError}` : ""}`
    : "No session paired yet.";

  pairedSessionValue.textContent = `Paired session: ${state.sessionId || "n/a"}`;

  const tabUrl = diagnostics?.tabUrl || "n/a";
  tabUrlValue.textContent = `Active tab: ${tabUrl}`;

  const contentActive = Boolean(diagnostics?.contentScriptActive);
  contentStateValue.textContent = contentActive ? "Content active" : "Content inactive";
  contentStateValue.className = contentActive ? "ok" : "warn";

  const outcome = state.lastEventOutcome || "n/a";
  const type = state.lastEventType || "n/a";
  const status = state.lastEventHttpStatus ?? "n/a";
  lastEventValue.textContent = `Last event: ${type} • ${outcome} • HTTP ${status}`;

  diagNote.textContent = contentActive
    ? "Content script is active on this tab. You can run a manual context send test."
    : "Content script is not active on this tab/profile. Load the extension in the same Chrome profile as the teaching tab.";
}

async function savePairing(enabled) {
  const sessionId = String(sessionIdInput.value || "").trim();
  const apiBase = String(apiBaseInput.value || DEFAULT_API_BASE).trim() || DEFAULT_API_BASE;
  await chrome.runtime.sendMessage({
    type: enabled ? "BTA_SET_PAIRING" : "BTA_CLEAR_PAIRING",
    sessionId,
    apiBase,
  });
  await loadState();
}

connectButton.addEventListener("click", () => {
  void savePairing(true);
});

disconnectButton.addEventListener("click", () => {
  void savePairing(false);
});

testContextButton.addEventListener("click", () => {
  void (async () => {
    testContextButton.disabled = true;
    const result = await askBackground({ type: "BTA_TEST_SEND_CONTEXT" });
    if (!result?.ok) {
      diagNote.textContent = `Manual test failed: ${result?.error || "unknown error"}`;
    } else {
      diagNote.textContent = "Manual context event sent successfully.";
    }
    await loadState();
    testContextButton.disabled = false;
  })();
});

void loadState();