const DEFAULT_API_BASE = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";

async function getState() {
  const state = await chrome.storage.local.get([
    "bill_teaching_assistant_session_id",
    "bill_teaching_assistant_api_base",
    "bill_teaching_assistant_enabled",
    "bill_teaching_assistant_last_sync",
    "bill_teaching_assistant_last_error",
    "bill_teaching_assistant_last_event_type",
    "bill_teaching_assistant_last_event_http_status",
    "bill_teaching_assistant_last_event_outcome",
  ]);
  return {
    sessionId: String(state.bill_teaching_assistant_session_id || "").trim(),
    apiBase: String(state.bill_teaching_assistant_api_base || DEFAULT_API_BASE).trim() || DEFAULT_API_BASE,
    enabled: state.bill_teaching_assistant_enabled !== false,
    lastSync: state.bill_teaching_assistant_last_sync || null,
    lastError: state.bill_teaching_assistant_last_error || null,
    lastEventType: state.bill_teaching_assistant_last_event_type || null,
    lastEventHttpStatus: state.bill_teaching_assistant_last_event_http_status ?? null,
    lastEventOutcome: state.bill_teaching_assistant_last_event_outcome || null,
  };
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tabs[0] || null;
}

async function getTabDiagnostics() {
  const tab = await getActiveTab();
  if (!tab) {
    return { tabUrl: null, tabId: null, contentScriptActive: false, reason: "no_active_tab" };
  }

  let ping = null;
  let contentScriptActive = false;
  try {
    ping = await chrome.tabs.sendMessage(tab.id, { type: "BTA_PING" });
    contentScriptActive = Boolean(ping?.active);
  } catch {
    contentScriptActive = false;
  }

  return {
    tabUrl: tab.url || null,
    tabId: tab.id,
    contentScriptActive,
    ping: ping || null,
  };
}

async function setBadgeFromState() {
  const state = await getState();
  const text = state.enabled && state.sessionId ? "ON" : "--";
  await chrome.action.setBadgeText({ text });
  await chrome.action.setBadgeBackgroundColor({ color: state.enabled && state.sessionId ? "#0ea5e9" : "#64748b" });
}

async function sendEventToBillCore(payload) {
  const state = await getState();
  if (!state.enabled || !state.sessionId) {
    await chrome.storage.local.set({
      bill_teaching_assistant_last_event_outcome: "skipped",
      bill_teaching_assistant_last_event_type: payload?.event_type || null,
      bill_teaching_assistant_last_event_http_status: null,
    });
    return { ok: false, skipped: true, reason: "not_paired" };
  }

  const url = `${state.apiBase}/api/teaching/session/${encodeURIComponent(state.sessionId)}/extension-events`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error("BILL_TEACHING_EXTENSION_EVENT_FAILED", {
      session_id: state.sessionId,
      event_type: payload?.event_type || "unknown",
      status: response.status,
      url,
    });
    throw new Error(body?.detail || `Extension event rejected (${response.status})`);
  }

  console.info("BILL_TEACHING_EXTENSION_EVENT_SENT", {
    session_id: state.sessionId,
    event_type: payload?.event_type || "unknown",
    status: response.status,
    url,
  });

  await chrome.storage.local.set({
    bill_teaching_assistant_last_sync: new Date().toISOString(),
    bill_teaching_assistant_last_error: null,
    bill_teaching_assistant_last_event_type: payload?.event_type || null,
    bill_teaching_assistant_last_event_http_status: response.status,
    bill_teaching_assistant_last_event_outcome: "ok",
  });
  await setBadgeFromState();
  return { ok: true, body };
}

chrome.runtime.onInstalled.addListener(() => {
  void setBadgeFromState();
});

chrome.runtime.onStartup.addListener(() => {
  void setBadgeFromState();
});

chrome.storage.onChanged.addListener(() => {
  void setBadgeFromState();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return false;
  }

  if (message.type === "BTA_GET_STATE") {
    void (async () => {
      sendResponse({ ok: true, ...(await getState()) });
    })();
    return true;
  }

  if (message.type === "BTA_SET_PAIRING") {
    void (async () => {
      const sessionId = String(message.sessionId || "").trim();
      const apiBase = String(message.apiBase || DEFAULT_API_BASE).trim() || DEFAULT_API_BASE;
      await chrome.storage.local.set({
        bill_teaching_assistant_session_id: sessionId,
        bill_teaching_assistant_api_base: apiBase,
        bill_teaching_assistant_enabled: Boolean(sessionId),
        bill_teaching_assistant_last_error: null,
        bill_teaching_assistant_last_event_outcome: null,
        bill_teaching_assistant_last_event_http_status: null,
        bill_teaching_assistant_last_event_type: null,
      });
      await setBadgeFromState();
      sendResponse({ ok: true, sessionId, apiBase });
    })();
    return true;
  }

  if (message.type === "BTA_CLEAR_PAIRING") {
    void (async () => {
      await chrome.storage.local.set({
        bill_teaching_assistant_session_id: "",
        bill_teaching_assistant_enabled: false,
        bill_teaching_assistant_last_error: null,
        bill_teaching_assistant_last_event_outcome: null,
        bill_teaching_assistant_last_event_http_status: null,
        bill_teaching_assistant_last_event_type: null,
      });
      await setBadgeFromState();
      sendResponse({ ok: true });
    })();
    return true;
  }

  if (message.type === "BTA_SEND_EVENT") {
    void (async () => {
      try {
        const result = await sendEventToBillCore(message.payload);
        sendResponse({ ok: true, ...result });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        console.error("BILL_TEACHING_EXTENSION_EVENT_FAILED", {
          session_id: (await getState()).sessionId,
          event_type: message.payload?.event_type || "unknown",
          error: errorMessage,
        });
        await chrome.storage.local.set({
          bill_teaching_assistant_last_error: errorMessage,
          bill_teaching_assistant_last_event_type: message.payload?.event_type || null,
          bill_teaching_assistant_last_event_outcome: "failed",
        });
        await setBadgeFromState();
        sendResponse({ ok: false, error: errorMessage });
      }
    })();
    return true;
  }

  if (message.type === "BTA_GET_TAB_DIAGNOSTICS") {
    void (async () => {
      const diag = await getTabDiagnostics();
      sendResponse({ ok: true, ...diag });
    })();
    return true;
  }

  if (message.type === "BTA_TEST_SEND_CONTEXT") {
    void (async () => {
      try {
        const tab = await getActiveTab();
        if (!tab?.id) {
          sendResponse({ ok: false, error: "No active tab found." });
          return;
        }

        const contextResponse = await chrome.tabs.sendMessage(tab.id, { type: "BTA_GET_CONTEXT" });
        if (!contextResponse?.ok || !contextResponse?.context) {
          sendResponse({ ok: false, error: "Content script is not active on this tab." });
          return;
        }

        const payload = {
          event_type: "context",
          ...contextResponse.context,
          reason: "popup-manual-test",
          source: "extension",
        };
        const result = await sendEventToBillCore(payload);
        sendResponse({ ok: true, result });
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        await chrome.storage.local.set({
          bill_teaching_assistant_last_error: errorMessage,
          bill_teaching_assistant_last_event_outcome: "failed",
          bill_teaching_assistant_last_event_type: "context",
        });
        sendResponse({ ok: false, error: errorMessage });
      }
    })();
    return true;
  }

  return false;
});