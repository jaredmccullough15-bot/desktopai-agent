const DEFAULT_API_BASE = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com";
const OVERLAY_ID = "bill-teaching-assistant-overlay";
const PAUSED_COLOR = "#64748b";

let overlayRoot = null;
let pairState = { enabled: false, sessionId: "", apiBase: DEFAULT_API_BASE };
let contextTimer = null;
let lastContextSignature = "";

try {
  document.documentElement?.setAttribute("data-bill-teaching-extension-active", "true");
  console.info("BILL_TEACHING_EXTENSION_CONTENT_ACTIVE", { url: window.location.href });
} catch {
  // no-op for pages that block DOM mutation very early
}

function safeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function isVisibleElement(element) {
  if (!element || !(element instanceof Element)) return false;
  const style = window.getComputedStyle(element);
  if (!style || style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function redactSensitiveValue(element, value) {
  const labelText = [
    element.getAttribute("aria-label"),
    element.getAttribute("placeholder"),
    element.getAttribute("name"),
    element.id,
    element.type,
  ].map((item) => safeText(item).toLowerCase()).join(" ");
  if (element.type === "password" || /password|passcode|otp|mfa|token|secret|code/.test(labelText)) {
    return "[redacted]";
  }
  return "[redacted]";
}

function getNearbyLabelText(element) {
  if (!element || !(element instanceof Element)) return "";
  const ariaLabelledBy = safeText(element.getAttribute("aria-labelledby"));
  if (ariaLabelledBy) {
    const labelledElement = document.getElementById(ariaLabelledBy);
    if (labelledElement) return safeText(labelledElement.textContent);
  }
  const parentLabel = element.closest("label");
  if (parentLabel) return safeText(parentLabel.textContent);
  const id = safeText(element.getAttribute("id"));
  if (id) {
    const directLabel = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    if (directLabel) return safeText(directLabel.textContent);
  }
  return "";
}

function getBoundingBox(element) {
  const rect = element.getBoundingClientRect();
  return {
    x: Math.round(rect.x),
    y: Math.round(rect.y),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  };
}

function buildSelectorCandidates(element) {
  const selectors = [];
  const tag = element.tagName.toLowerCase();
  const labelText = safeText(
    element.getAttribute("aria-label") ||
      element.getAttribute("placeholder") ||
      getNearbyLabelText(element) ||
      element.textContent ||
      element.id ||
      element.name ||
      "",
  );
  const escaped = labelText.replace(/"/g, '\\"');
  if (element.id) selectors.push(`#${CSS.escape(element.id)}`);
  if (element.name) selectors.push(`${tag}[name="${CSS.escape(element.name)}"]`);
  if (element.getAttribute("aria-label")) selectors.push(`${tag}[aria-label="${escaped}"]`);
  if (element.getAttribute("placeholder")) selectors.push(`${tag}[placeholder="${escaped}"]`);
  if (labelText) {
    selectors.push(`${tag}:has-text("${escaped}")`);
    selectors.push(`text=/^\\s*${labelText.replace(/\s+/g, "\\s+").replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$/i`);
  }
  if (element.getAttribute("role")) selectors.push(`[role="${CSS.escape(element.getAttribute("role"))}"]`);
  return Array.from(new Set(selectors)).slice(0, 8);
}

function getVisibleInteractiveElements(selector) {
  return Array.from(document.querySelectorAll(selector)).filter((element) => isVisibleElement(element)).slice(0, 20);
}

function describeElement(element) {
  const role = safeText(element.getAttribute("role") || element.role || "");
  const targetType = element.tagName.toLowerCase() === "a" ? "link" : element.tagName.toLowerCase() === "button" ? "button" : ["input", "textarea", "select"].includes(element.tagName.toLowerCase()) ? "field" : role || element.tagName.toLowerCase();
  const visibleText = safeText(element.textContent || "");
  const ariaLabel = safeText(element.getAttribute("aria-label") || "");
  const placeholder = safeText(element.getAttribute("placeholder") || "");
  const name = safeText(element.getAttribute("name") || "");
  const elementId = safeText(element.id || "");
  const nearbyLabelText = getNearbyLabelText(element);
  const targetLabel = safeText(ariaLabel || placeholder || nearbyLabelText || visibleText || name || elementId || "");
  const isSensitive = /password|passcode|otp|mfa|token|secret|code/.test([ariaLabel, placeholder, nearbyLabelText, visibleText, name, elementId].join(" ").toLowerCase()) || element.type === "password";

  return {
    target_type: targetType,
    target_label: targetLabel,
    visible_text: visibleText || null,
    role: role || null,
    aria_label: ariaLabel || null,
    placeholder: placeholder || null,
    name: name || null,
    element_id: elementId || null,
    nearby_label_text: nearbyLabelText || null,
    bounding_box: getBoundingBox(element),
    selector_candidates: buildSelectorCandidates(element),
    selectors: buildSelectorCandidates(element),
    is_sensitive: Boolean(isSensitive),
    value_redacted: isSensitive ? "[redacted]" : "[redacted]",
  };
}

function getInteractiveTarget(target) {
  if (!target || !(target instanceof Element)) return null;
  const selector = [
    "button",
    "a[href]",
    "input",
    "textarea",
    "select",
    "[role='button']",
    "[role='link']",
    "[tabindex]:not([tabindex='-1'])",
  ].join(", ");
  return target.closest(selector) || null;
}

function capturePageContext() {
  const visibleButtons = getVisibleInteractiveElements("button, [role='button'], input[type='button'], input[type='submit']").map((element) => ({
    text: safeText(element.textContent || element.getAttribute("value") || ""),
    aria_label: safeText(element.getAttribute("aria-label") || "") || null,
    role: safeText(element.getAttribute("role") || (element.tagName.toLowerCase() === "button" ? "button" : "")) || null,
    selector_hint: buildSelectorCandidates(element)[0] || null,
  }));

  const visibleFields = getVisibleInteractiveElements("input:not([type='hidden']), textarea, select").map((element) => ({
    label: safeText(getNearbyLabelText(element) || element.getAttribute("aria-label") || ""),
    placeholder: safeText(element.getAttribute("placeholder") || "") || null,
    type: safeText(element.getAttribute("type") || element.tagName.toLowerCase()),
    name: safeText(element.getAttribute("name") || "") || null,
    selector_hint: buildSelectorCandidates(element)[0] || null,
    sensitive: Boolean(element.type === "password" || /password|passcode|otp|mfa|token|secret|code/.test([element.getAttribute("aria-label"), element.getAttribute("placeholder"), element.getAttribute("name"), element.id].join(" ").toLowerCase())),
  }));

  const visibleLinks = getVisibleInteractiveElements("a[href]").map((element) => ({
    text: safeText(element.textContent || element.getAttribute("aria-label") || ""),
    href: safeText(element.getAttribute("href") || "") || null,
  }));

  const visibleHeadings = getVisibleInteractiveElements("h1, h2, h3, h4, h5, h6").map((element) => ({
    text: safeText(element.textContent || ""),
    level: Number(element.tagName.slice(1)) || null,
  }));

  const currentUrl = String(window.location.href || "");
  return {
    current_url: currentUrl,
    page_title: safeText(document.title || ""),
    domain: safeText(window.location.hostname || ""),
    visible_buttons: visibleButtons,
    visible_fields: visibleFields,
    visible_links: visibleLinks,
    visible_headings: visibleHeadings,
    active_element: document.activeElement
      ? {
          type: safeText(document.activeElement.tagName || "").toLowerCase(),
          label: safeText(document.activeElement.getAttribute?.("aria-label") || document.activeElement.textContent || ""),
        }
      : null,
    page_changed: false,
    captured_at: new Date().toISOString(),
    source: "extension",
  };
}

function ensureOverlay() {
  if (overlayRoot) return overlayRoot;
  overlayRoot = document.createElement("div");
  overlayRoot.id = OVERLAY_ID;
  overlayRoot.style.cssText = [
    "position:fixed",
    "z-index:2147483647",
    "right:16px",
    "bottom:16px",
    "max-width:320px",
    "padding:10px 12px",
    "border-radius:14px",
    "background:rgba(7,10,17,0.96)",
    "color:#e2e8f0",
    "border:1px solid rgba(34,211,238,0.35)",
    "box-shadow:0 16px 40px rgba(0,0,0,0.35)",
    "font:12px/1.4 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif",
  ].join(";");
  document.documentElement.appendChild(overlayRoot);
  return overlayRoot;
}

function renderOverlay() {
  const overlay = ensureOverlay();
  const paired = pairState.enabled && pairState.sessionId;
  overlay.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
      <div>
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.18em;color:${paired ? "#67e8f9" : PAUSED_COLOR}">Bill Teaching Assistant</div>
        <div style="margin-top:4px;font-weight:600">${paired ? "Bill Teaching Helper is watching" : "Bill Teaching Helper is waiting to pair"}</div>
      </div>
      <div style="width:10px;height:10px;border-radius:999px;background:${paired ? "#22c55e" : PAUSED_COLOR}"></div>
    </div>
    <div style="margin-top:6px;color:#94a3b8">${safeText(window.location.hostname || "")}</div>
    ${paired ? `<div style="margin-top:4px;color:#cbd5e1">Session ${safeText(pairState.sessionId).slice(0, 8)}…</div>` : ""}
  `;
}

async function refreshPairingState() {
  const state = await chrome.storage.local.get([
    "bill_teaching_assistant_session_id",
    "bill_teaching_assistant_api_base",
    "bill_teaching_assistant_enabled",
  ]);
  pairState = {
    sessionId: String(state.bill_teaching_assistant_session_id || "").trim(),
    apiBase: String(state.bill_teaching_assistant_api_base || DEFAULT_API_BASE).trim() || DEFAULT_API_BASE,
    enabled: state.bill_teaching_assistant_enabled !== false,
  };
  renderOverlay();
}

function scheduleContextCapture(reason) {
  if (!pairState.enabled || !pairState.sessionId) {
    renderOverlay();
    return;
  }
  clearTimeout(contextTimer);
  contextTimer = setTimeout(() => {
    const context = capturePageContext();
    const signature = JSON.stringify({
      url: context.current_url,
      title: context.page_title,
      domain: context.domain,
      buttons: context.visible_buttons.map((item) => item.text || item.aria_label || "").slice(0, 5),
      fields: context.visible_fields.map((item) => item.label || item.placeholder || item.name || "").slice(0, 5),
      reason,
    });
    if (signature === lastContextSignature) {
      return;
    }
    lastContextSignature = signature;
    void chrome.runtime.sendMessage({ type: "BTA_SEND_EVENT", payload: { event_type: "context", ...context, reason } });
  }, 250);
}

function sendInteractionEvent(eventType, element) {
  if (!pairState.enabled || !pairState.sessionId) return;
  const target = describeElement(element);
  const context = capturePageContext();
  const payload = {
    event_type: eventType,
    ...context,
    target: {
      ...target,
      value_redacted: target.is_sensitive ? "[redacted]" : "[redacted]",
    },
    input_metadata: eventType === "input" || eventType === "change"
      ? {
          value_redacted: "[redacted]",
        }
      : null,
  };
  void chrome.runtime.sendMessage({ type: "BTA_SEND_EVENT", payload });
}

document.addEventListener("click", (event) => {
  const target = getInteractiveTarget(event.target);
  if (!target || overlayRoot?.contains(target)) return;
  sendInteractionEvent("click", target);
}, true);

document.addEventListener("focusin", (event) => {
  const target = getInteractiveTarget(event.target);
  if (!target || overlayRoot?.contains(target)) return;
  sendInteractionEvent("focus", target);
}, true);

document.addEventListener("input", (event) => {
  const target = getInteractiveTarget(event.target);
  if (!target || overlayRoot?.contains(target)) return;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement)) return;
  sendInteractionEvent("input", target);
}, true);

document.addEventListener("change", (event) => {
  const target = getInteractiveTarget(event.target);
  if (!target || overlayRoot?.contains(target)) return;
  sendInteractionEvent("change", target);
}, true);

window.addEventListener("hashchange", () => scheduleContextCapture("hashchange"));
window.addEventListener("popstate", () => scheduleContextCapture("popstate"));
window.addEventListener("load", () => scheduleContextCapture("load"));

chrome.storage.onChanged.addListener((changes) => {
  if (
    changes.bill_teaching_assistant_session_id ||
    changes.bill_teaching_assistant_api_base ||
    changes.bill_teaching_assistant_enabled
  ) {
    void refreshPairingState().then(() => scheduleContextCapture("pairing-changed"));
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return false;
  }

  if (message.type === "BTA_PING") {
    sendResponse({
      ok: true,
      active: true,
      url: window.location.href,
      paired: Boolean(pairState.enabled && pairState.sessionId),
      sessionId: pairState.sessionId || null,
    });
    return false;
  }

  if (message.type === "BTA_GET_CONTEXT") {
    sendResponse({
      ok: true,
      active: true,
      url: window.location.href,
      paired: Boolean(pairState.enabled && pairState.sessionId),
      sessionId: pairState.sessionId || null,
      context: capturePageContext(),
    });
    return false;
  }

  return false;
});

void refreshPairingState().then(() => scheduleContextCapture("initial"));