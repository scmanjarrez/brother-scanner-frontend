"use strict";

const printForm = document.getElementById("print-form");
const scanForm = document.getElementById("scan-form");
const printResult = document.getElementById("print-result");
const scanResult = document.getElementById("scan-result");
const scanPreview = document.getElementById("scan-preview");
const scanPreviewWrap = document.getElementById("scan-preview-wrap");
const continuousPagesWrap = document.getElementById("continuous-pages-wrap");
const continuousPageCount = document.getElementById("continuous-page-count");
const continuousPages = document.getElementById("continuous-pages");
const scanButton = document.getElementById("scan-button");
const finishScanButton = document.getElementById("finish-scan-button");
const printFileInput = document.getElementById("print-file");
const printPreviewToggle = document.getElementById("print-preview-toggle");
const workflowSelect = document.getElementById("workflow");
const outputFormatSelect = document.getElementById("output-format");
const workflowHint = document.getElementById("workflow-hint");
const printProfileSelect = document.getElementById("print-profile");
const languageSelect = document.getElementById("language-select");
const watermarkTextInput = document.getElementById("watermark-text");
const scanTab = document.getElementById("scan-tab");
const printTab = document.getElementById("print-tab");
const scanPanel = document.getElementById("scan-panel");
const printPanel = document.getElementById("print-panel");
const operationTabs = [scanTab, printTab];
const printProfileFields = [
  "paper_size",
  "orientation",
  "copies",
  "collate",
  "media_type",
  "resolution",
  "print_quality",
  "pages_per_sheet",
  "page_order",
  "page_border",
  "scale_mode",
  "scale_percent",
  "reverse_order",
  "toner_save",
  "watermark",
  "watermark_text",
  "header_footer",
];

const LOCALIZED_ATTRIBUTES = [
  ["aria-label", "data-i18n-aria-label"],
  ["alt", "data-i18n-alt"],
  ["content", "data-i18n-content"],
  ["title", "data-i18n-title"],
];
const localizedMessages = new WeakMap();
const LANGUAGE_STORAGE_KEY = "brother-document-language";
const DEFAULT_LANGUAGE = "es";
const languageOptions = new Set(
  Array.from(languageSelect.options, (option) => option.value),
);
const localeCatalogs = new Map();
let languageRequestId = 0;
let watermarkIsDefault = true;

function readSavedLanguage() {
  try {
    const savedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return savedLanguage && languageOptions.has(savedLanguage)
      ? savedLanguage
      : DEFAULT_LANGUAGE;
  } catch (_error) {
    return DEFAULT_LANGUAGE;
  }
}

async function loadLocaleCatalog(language) {
  const cachedCatalog = localeCatalogs.get(language);
  if (cachedCatalog) {
    return cachedCatalog;
  }

  const response = await fetch("/static/locales/" + language + ".json");
  if (!response.ok) {
    throw new Error("locale_load_failed");
  }

  const catalog = await response.json();
  if (!catalog || catalog.code !== language) {
    throw new Error("locale_format_invalid");
  }
  localeCatalogs.set(language, catalog);
  return catalog;
}

const defaultLocale = await loadLocaleCatalog(DEFAULT_LANGUAGE);
let currentLanguage = readSavedLanguage();
let currentLocale = defaultLocale;
if (currentLanguage !== DEFAULT_LANGUAGE) {
  try {
    currentLocale = await loadLocaleCatalog(currentLanguage);
  } catch (error) {
    console.error(error);
    currentLanguage = DEFAULT_LANGUAGE;
    languageSelect.value = DEFAULT_LANGUAGE;
  }
}

function formatTemplate(template, values) {
  return template.replace(/\{(\w+)\}/g, (_match, name) => String(values[name] ?? ""));
}

function t(key, values = {}) {
  const template = currentLocale.dynamic[key]
    || defaultLocale.dynamic[key]
    || "";
  return formatTemplate(template, values);
}

function tStatic(key) {
  const template = currentLocale.static[key]
    || defaultLocale.static[key]
    || "";
  return formatTemplate(template, {});
}

function localizeMessage(code, parameters = {}) {
  const template = currentLocale.apiMessages[code]
    || currentLocale.apiPatterns[code]
    || currentLocale.dynamic[code]
    || defaultLocale.apiMessages[code]
    || defaultLocale.apiPatterns[code]
    || defaultLocale.dynamic[code];
  if (!template) {
    return t("genericError");
  }

  const values = { ...parameters };
  if (typeof values.field === "string") {
    values.field = currentLocale.apiFields[values.field]
      || defaultLocale.apiFields[values.field]
      || t("genericError");
  }
  return formatTemplate(template, values);
}

let continuousArtifactIds = [];
let cardArtifactIds = [];
let cardSide = "front";
let scanSessionId = null;
let printPreviewUrl = null;
let selectedContinuousArtifactId = null;

function localizeStaticCopy() {
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const key = element.getAttribute("data-i18n");
    if (key) {
      element.textContent = tStatic(key);
    }
  });

  LOCALIZED_ATTRIBUTES.forEach(([attribute, dataAttribute]) => {
    document.querySelectorAll(`[${dataAttribute}]`).forEach((element) => {
      const key = element.getAttribute(dataAttribute);
      if (key) {
        const translation = currentLocale.attributes[attribute]?.[key]
          || defaultLocale.attributes[attribute]?.[key]
          || "";
        element.setAttribute(attribute, translation);
      }
    });
  });
}

function updateDefaultWatermark() {
  if (watermarkIsDefault) {
    watermarkTextInput.value = t("defaultWatermark");
  }
}

function applyLoadedLanguage(language, catalog, persist) {
  currentLanguage = language;
  currentLocale = catalog;
  document.documentElement.lang = currentLanguage;
  languageSelect.value = currentLanguage;
  localizeStaticCopy();
  updateDefaultWatermark();
  refreshExistingMessages();
  refreshWorkflowCopy();
  const printButton = document.getElementById("print-button");
  printButton.textContent = printButton.disabled ? t("printSending") : t("printSubmit");
  if (continuousArtifactIds.length > 0) {
    renderContinuousPages();
  } else {
    continuousPageCount.textContent = t("pageCountMany", { count: 0 });
  }
  if (printPreviewToggle.checked) {
    updatePrintPreview();
  }
  updateStatus();
  if (persist) {
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, currentLanguage);
    } catch (_error) {
      // The selected language still applies for this page view if storage is unavailable.
    }
  }
}

async function applyLanguage(language, persist = true) {
  const requestId = ++languageRequestId;
  let selectedLanguage = languageOptions.has(language)
    ? language
    : DEFAULT_LANGUAGE;
  let catalog;
  try {
    catalog = await loadLocaleCatalog(selectedLanguage);
  } catch (error) {
    console.error(error);
    selectedLanguage = DEFAULT_LANGUAGE;
    catalog = await loadLocaleCatalog(DEFAULT_LANGUAGE);
  }
  if (requestId !== languageRequestId) {
    return;
  }
  applyLoadedLanguage(selectedLanguage, catalog, persist);
}

applyLoadedLanguage(currentLanguage, currentLocale, false);
languageSelect.addEventListener("change", () => {
  void applyLanguage(languageSelect.value);
});
watermarkTextInput.addEventListener("input", () => {
  watermarkIsDefault = false;
});

operationTabs.forEach((tab) => {
  tab.addEventListener("click", () => activateOperationTab(tab));
  tab.addEventListener("keydown", (event) => {
    let nextIndex = operationTabs.indexOf(tab);
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (nextIndex + 1) % operationTabs.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (nextIndex - 1 + operationTabs.length) % operationTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = operationTabs.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    const nextTab = operationTabs[nextIndex];
    activateOperationTab(nextTab);
    nextTab.focus();
  });
});

function activateOperationTab(selectedTab) {
  const scanActive = selectedTab === scanTab;
  scanPanel.classList.toggle("hidden", !scanActive);
  printPanel.classList.toggle("hidden", scanActive);

  operationTabs.forEach((tab) => {
    const active = tab === selectedTab;
    tab.classList.toggle("tab-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
}

function refreshWorkflowCopy() {
  const workflow = workflowSelect.value;
  if (workflow === "continuous") {
    workflowHint.textContent = continuousArtifactIds.length
      ? t("pageAddedHint", { number: continuousArtifactIds.length })
      : t("scanContinuousHint");
    if (!scanButton.classList.contains("hidden")) {
      scanButton.textContent = scanButton.disabled
        ? t("scanPageBusy")
        : continuousArtifactIds.length
          ? t("scanPageNumber", { number: continuousArtifactIds.length + 1 })
          : t("scanPage");
    }
  } else if (workflow === "card") {
    if (cardArtifactIds.length === 2) {
      workflowHint.textContent = t("cardReadyHint");
    } else if (cardSide === "back") {
      workflowHint.textContent = t("frontCapturedHint");
    } else {
      workflowHint.textContent = t("scanCardHint");
    }
    if (!scanButton.classList.contains("hidden")) {
      scanButton.textContent = scanButton.disabled
        ? cardSide === "front" ? t("scanFrontBusy") : t("scanBackBusy")
        : cardSide === "front" ? t("scanFront") : t("scanBack");
    }
  } else {
    workflowHint.textContent = t("scanSingleHint");
    if (!scanButton.classList.contains("hidden")) {
      scanButton.textContent = scanButton.disabled ? t("scanBusy") : t("scan");
    }
  }
  finishScanButton.textContent = finishScanButton.disabled ? t("finishBusy") : t("finishPdf");
}

function normalizeMessagePayload(payload) {
  if (!payload || typeof payload !== "object" || typeof payload.code !== "string") {
    return { code: "genericError", params: {} };
  }
  const params = payload.params
    && typeof payload.params === "object"
    && !Array.isArray(payload.params)
    ? payload.params
    : {};
  return { code: payload.code, params };
}

class ApiResponseError extends Error {
  constructor(message) {
    super(message.code);
    this.code = message.code;
    this.parameters = message.params;
  }
}

function messageForError(error) {
  if (error instanceof ApiResponseError) {
    return { code: error.code, params: error.parameters };
  }
  return { code: "genericError", params: {} };
}

function showMessage(
  container,
  code,
  parameters,
  kind,
  downloadUrl = null,
  onDownload = null,
) {
  const alert = document.createElement("div");
  alert.className = `alert localized-message ${kind === "error" ? "alert-error" : "alert-success"} mt-1 text-sm`;
  localizedMessages.set(alert, { code, parameters });

  const text = document.createElement("span");
  text.textContent = localizeMessage(code, parameters);
  alert.append(text);

  if (downloadUrl) {
    const link = document.createElement("a");
    link.className = "link font-semibold";
    link.href = downloadUrl;
    link.download = "";
    link.textContent = t("download");
    if (onDownload) {
      link.addEventListener("click", onDownload);
    }
    alert.append(link);
  }
  container.replaceChildren(alert);
}

function showApiMessage(container, payload, kind, downloadUrl = null, onDownload = null) {
  const message = normalizeMessagePayload(payload);
  showMessage(
    container,
    message.code,
    message.params,
    kind,
    downloadUrl,
    onDownload,
  );
}

function refreshExistingMessages() {
  document.querySelectorAll(".localized-message").forEach((alert) => {
    const message = localizedMessages.get(alert);
    const text = alert.querySelector("span");
    if (!message || !text) {
      return;
    }
    text.textContent = localizeMessage(message.code, message.parameters);
    const downloadLink = alert.querySelector("a");
    if (downloadLink) {
      downloadLink.textContent = t("download");
    }
  });
}

async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new ApiResponseError(normalizeMessagePayload(payload.error));
  }
  return payload;
}

async function updateStatus() {
  const badge = document.getElementById("connection-badge");
  try {
    const response = await fetch("/api/status");
    const status = await readJson(response);
    const ready = status.printer_ready && status.scanner_ready;
    badge.className = `connection-badge ${ready ? "is-ready" : "is-warning"}`;
    const dot = document.createElement("span");
    dot.className = "connection-dot";
    const label = document.createElement("span");
    label.textContent = ready ? t("statusReady") : t("statusCheck");
    badge.replaceChildren(dot, label);
    const printer = status.printer_ready ? t("statusReady") : t("statusCheck");
    const titleKey = status.scanner_count === 1 ? "statusTitleOne" : "statusTitle";
    badge.title = t(titleKey, { printer, count: status.scanner_count });
  } catch (_error) {
    badge.className = "connection-badge is-error";
    const dot = document.createElement("span");
    dot.className = "connection-dot";
    const label = document.createElement("span");
    label.textContent = t("statusOffline");
    badge.replaceChildren(dot, label);
  }
}

printForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("print-button");
  button.disabled = true;
  button.textContent = t("printSending");
  printResult.replaceChildren();

  try {
    const response = await fetch("/api/print", {
      method: "POST",
      body: new FormData(printForm),
    });
    const result = await readJson(response);
    showApiMessage(printResult, result.message, "success");
  } catch (error) {
    const message = messageForError(error);
    showMessage(printResult, message.code, message.params, "error");
  } finally {
    button.disabled = false;
    button.textContent = t("printSubmit");
  }
});

printFileInput.addEventListener("change", updatePrintPreview);
printPreviewToggle.addEventListener("change", updatePrintPreview);
printProfileSelect.addEventListener("change", applyPrintProfile);
document.getElementById("save-profile-button").addEventListener("click", savePrintProfile);

scanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const workflow = workflowSelect.value;
  const side = cardSide;
  if (workflow === "single" && scanSessionId) {
    requestScanSessionCleanup(scanSessionId);
    scanSessionId = null;
  }
  scanButton.disabled = true;
  finishScanButton.disabled = true;
  scanResult.replaceChildren();

  if (workflow === "card") {
    scanButton.textContent = side === "front" ? t("scanFrontBusy") : t("scanBackBusy");
  } else if (workflow === "continuous") {
    scanButton.textContent = t("scanPageBusy");
  } else {
    scanButton.textContent = t("scanBusy");
  }

  try {
    const formData = new FormData(scanForm);
    formData.set("workflow", workflow);
    formData.set("card_side", side);
    if (workflow !== "single" && scanSessionId) {
      formData.set("scan_session_id", scanSessionId);
    }
    const response = await fetch("/api/scan", { method: "POST", body: formData });
    const result = await readJson(response);
    scanSessionId = result.scan_session_id;
    displayPreview(result.preview_url);

    if (workflow === "continuous") {
      continuousArtifactIds.push(result.artifact_id);
      selectedContinuousArtifactId = result.artifact_id;
      renderContinuousPages();
      finishScanButton.classList.remove("hidden");
      refreshWorkflowCopy();
      showApiMessage(scanResult, result.message, "success");
    } else if (workflow === "card") {
      cardArtifactIds.push(result.artifact_id);
      if (side === "front") {
        cardSide = "back";
        refreshWorkflowCopy();
        showMessage(scanResult, "frontCaptured", {}, "success");
      } else {
        finishScanButton.classList.remove("hidden");
        scanButton.classList.add("hidden");
        refreshWorkflowCopy();
        showMessage(scanResult, "bothSidesCaptured", {}, "success");
      }
    } else {
      showApiMessage(
        scanResult,
        result.message,
        "success",
        result.download_url,
        resetScanAfterDownload,
      );
    }
  } catch (error) {
    const message = messageForError(error);
    showMessage(scanResult, message.code, message.params, "error");
  } finally {
    scanButton.disabled = false;
    finishScanButton.disabled = false;
    refreshWorkflowCopy();
  }
});

finishScanButton.addEventListener("click", async () => {
  const workflow = workflowSelect.value;
  const artifactIds = workflow === "card" ? cardArtifactIds : continuousArtifactIds;
  if (workflow === "card" && artifactIds.length !== 2) {
    showMessage(scanResult, "scanFrontAndBack", {}, "error");
    return;
  }
  if (workflow === "continuous" && artifactIds.length === 0) {
    showMessage(scanResult, "scanAtLeastOnePage", {}, "error");
    return;
  }
  if (!scanSessionId) {
    showMessage(scanResult, "expiredSession", {}, "error");
    return;
  }

  finishScanButton.disabled = true;
  finishScanButton.textContent = t("finishBusy");
  try {
    const formData = new FormData();
    formData.set("workflow", workflow);
    formData.set("resolution", scanForm.elements.namedItem("resolution").value);
    formData.set("scan_session_id", scanSessionId);
    artifactIds.forEach((artifactId) => formData.append("artifact_ids", artifactId));
    const response = await fetch("/api/scans/compose", { method: "POST", body: formData });
    const result = await readJson(response);
    showApiMessage(
      scanResult,
      result.message,
      "success",
      result.download_url,
      resetScanAfterDownload,
    );
    if (workflow === "card") {
      displayPreview(
        `/api/preview/${scanSessionId}/${cardArtifactIds[1]}`,
      );
    }
  } catch (error) {
    const message = messageForError(error);
    showMessage(scanResult, message.code, message.params, "error");
  } finally {
    finishScanButton.disabled = false;
    finishScanButton.textContent = t("finishPdf");
  }
});

workflowSelect.addEventListener("change", () => {
  if (scanSessionId) {
    requestScanSessionCleanup(scanSessionId);
    scanSessionId = null;
  }
  continuousArtifactIds = [];
  cardArtifactIds = [];
  cardSide = "front";
  selectedContinuousArtifactId = null;
  finishScanButton.classList.add("hidden");
  scanButton.classList.remove("hidden");
  scanResult.replaceChildren();
  scanPreviewWrap.classList.add("hidden");
  continuousPagesWrap.classList.add("hidden");
  continuousPages.replaceChildren();
  continuousPageCount.textContent = t("pageCountMany", { count: 0 });

  const workflow = workflowSelect.value;
  const isSingle = workflow === "single";
  outputFormatSelect.disabled = !isSingle;
  if (!isSingle) {
    outputFormatSelect.value = "pdf";
  }

  refreshWorkflowCopy();
});

workflowSelect.dispatchEvent(new Event("change"));

document.getElementById("scale-mode").addEventListener("change", (event) => {
  document.getElementById("scale-percent-wrap").classList.toggle("hidden", event.target.value !== "custom");
});

outputFormatSelect.addEventListener("change", () => {
  document.getElementById("jpeg-quality-wrap").classList.toggle("hidden", outputFormatSelect.value !== "jpeg");
});

scanForm.addEventListener("input", (event) => {
  if (event.target.name === "brightness") {
    document.getElementById("brightness-value").textContent = event.target.value;
  }
  if (event.target.name === "contrast") {
    document.getElementById("contrast-value").textContent = event.target.value;
  }
});

function displayPreview(url) {
  scanPreview.src = url;
  scanPreviewWrap.classList.remove("hidden");
}

function requestScanSessionCleanup(sessionId) {
  fetch(`/api/scans/sessions/${sessionId}`, {
    method: "DELETE",
    keepalive: true,
  }).catch((error) => {
    console.error(error);
  });
}

function resetScanAfterDownload() {
  scanSessionId = null;
  workflowSelect.dispatchEvent(new Event("change"));
}

function renderContinuousPages() {
  const countKey = continuousArtifactIds.length === 1 ? "pageCountOne" : "pageCountMany";
  continuousPageCount.textContent = t(countKey, { count: continuousArtifactIds.length });
  continuousPagesWrap.classList.remove("hidden");
  continuousPages.replaceChildren();

  continuousArtifactIds.forEach((artifactId, index) => {
    const pageNumber = index + 1;
    const isSelected = artifactId === selectedContinuousArtifactId;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `relative rounded-lg border p-1 text-left transition ${isSelected ? "border-blue-600 ring-2 ring-blue-100" : "border-slate-200 hover:border-slate-400"}`;
    button.setAttribute("aria-label", t("viewPage", { number: pageNumber }));
    button.setAttribute("aria-pressed", String(isSelected));

    const image = document.createElement("img");
    image.src = `/api/preview/${scanSessionId}/${artifactId}`;
    image.alt = t("pagePreview", { number: pageNumber });
    image.loading = "lazy";
    image.className = "aspect-[3/4] w-full rounded-md bg-slate-50 object-contain";

    const label = document.createElement("span");
    label.className = "block px-1 py-1 text-xs font-medium text-slate-700";
    label.textContent = t("pageLabel", { number: pageNumber });

    button.append(image, label);
    button.addEventListener("click", () => {
      selectedContinuousArtifactId = artifactId;
      displayPreview(image.src);
      renderContinuousPages();
    });
    continuousPages.append(button);
  });
}

function updatePrintPreview() {
  const previewWrap = document.getElementById("print-preview-wrap");
  const pdfPreview = document.getElementById("print-pdf-preview");
  const imagePreview = document.getElementById("print-image-preview");
  const previewNote = document.getElementById("print-preview-note");
  const file = printFileInput.files[0];

  if (printPreviewUrl) {
    URL.revokeObjectURL(printPreviewUrl);
    printPreviewUrl = null;
  }
  pdfPreview.classList.add("hidden");
  imagePreview.classList.add("hidden");
  previewNote.classList.add("hidden");

  if (!printPreviewToggle.checked || !file) {
    previewWrap.classList.add("hidden");
    return;
  }

  previewWrap.classList.remove("hidden");
  printPreviewUrl = URL.createObjectURL(file);
  const extension = file.name.split(".").pop().toLowerCase();
  if (file.type === "application/pdf" || extension === "pdf") {
    pdfPreview.src = printPreviewUrl;
    pdfPreview.classList.remove("hidden");
  } else if (["png", "jpg", "jpeg"].includes(extension)) {
    imagePreview.src = printPreviewUrl;
    imagePreview.classList.remove("hidden");
  } else {
    previewNote.textContent = t("tiffPreview");
    previewNote.classList.remove("hidden");
  }
}

function loadSavedProfiles() {
  try {
    const profiles = JSON.parse(localStorage.getItem("brother-print-profiles") || "{}");
    return profiles && typeof profiles === "object" && !Array.isArray(profiles) ? profiles : {};
  } catch (_error) {
    return {};
  }
}

function renderSavedProfiles() {
  [...printProfileSelect.options]
    .filter((option) => option.value.startsWith("saved:"))
    .forEach((option) => option.remove());
  Object.keys(loadSavedProfiles())
    .sort((first, second) => first.localeCompare(second))
    .forEach((name) => {
      const option = document.createElement("option");
      option.value = `saved:${name}`;
      option.textContent = name;
      printProfileSelect.append(option);
    });
}

function readPrintProfile() {
  return Object.fromEntries(
    printProfileFields.map((name) => {
      const field = printForm.elements.namedItem(name);
      if (field instanceof HTMLInputElement && field.type === "checkbox") {
        return [name, field.checked];
      }
      if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
        return [name, field.value];
      }
      return [name, ""];
    }),
  );
}

function setPrintProfile(profile) {
  const watermarkValue = profile.watermark_text;
  if (typeof watermarkValue === "string") {
    watermarkIsDefault = Array.from(localeCatalogs.values()).some(
      (catalog) => catalog.dynamic.defaultWatermark === watermarkValue,
    );
  }
  Object.entries(profile).forEach(([name, value]) => {
    const field = printForm.elements.namedItem(name);
    if (field instanceof HTMLInputElement && field.type === "checkbox") {
      field.checked = Boolean(value);
    } else if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement) {
      field.value = String(value);
    }
  });
  document.getElementById("scale-mode").dispatchEvent(new Event("change"));
}

function applyPrintProfile() {
  const selected = printProfileSelect.value;
  if (selected === "default") {
    setPrintProfile({
      paper_size: "A4",
      orientation: "portrait",
      copies: "1",
      collate: false,
      media_type: "Plain",
      resolution: "600",
      print_quality: "Graphics",
      pages_per_sheet: "1",
      page_order: "rltb",
      page_border: "none",
      scale_mode: "off",
      scale_percent: "100",
      reverse_order: false,
      toner_save: false,
      watermark: false,
      watermark_text: t("defaultWatermark"),
      header_footer: false,
    });
  } else if (selected === "graphics") {
    setPrintProfile({ resolution: "600", print_quality: "Graphics", toner_save: false });
  } else if (selected === "draft") {
    setPrintProfile({ resolution: "300", print_quality: "Text", toner_save: true });
  } else if (selected.startsWith("saved:")) {
    const name = selected.slice("saved:".length);
    const profile = loadSavedProfiles()[name];
    if (profile && typeof profile === "object") {
      setPrintProfile(profile);
    }
  }
}

function savePrintProfile() {
  const enteredName = window.prompt(t("profileNamePrompt"));
  if (!enteredName || !enteredName.trim()) {
    return;
  }
  const name = enteredName.trim().slice(0, 40);
  try {
    const profiles = loadSavedProfiles();
    profiles[name] = readPrintProfile();
    localStorage.setItem("brother-print-profiles", JSON.stringify(profiles));
    renderSavedProfiles();
    printProfileSelect.value = `saved:${name}`;
    showMessage(printResult, "profileSaved", { name }, "success");
  } catch (_error) {
    showMessage(printResult, "profileSaveError", {}, "error");
  }
}

renderSavedProfiles();
window.setInterval(updateStatus, 30000);
window.addEventListener("pagehide", () => {
  if (scanSessionId) {
    requestScanSessionCleanup(scanSessionId);
  }
});
