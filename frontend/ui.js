let toastTimer = null;

export function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  container.replaceChildren();
  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  if (type === "error") toast.setAttribute("role", "alert");
  container.appendChild(toast);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.remove(), 5000);
}

export function setLoading(sectionEl, isLoading) {
  if (!sectionEl) return;
  sectionEl.classList.toggle("is-loading", Boolean(isLoading));
  if (isLoading) sectionEl.setAttribute("aria-busy", "true");
  else sectionEl.removeAttribute("aria-busy");
}

export function setButtonLoading(btn, isLoading) {
  if (!btn) return;
  btn.classList.toggle("is-busy", Boolean(isLoading));
  btn.disabled = Boolean(isLoading);
  if (isLoading) btn.setAttribute("aria-busy", "true");
  else btn.removeAttribute("aria-busy");
}

export function showBanner(kind, text) {
  const banner = document.getElementById("status-banner");
  if (!banner) return;
  banner.className = `banner banner--${kind === "warning" ? "warning" : "info"}`;
  banner.textContent = text;
  banner.hidden = false;
}

export function hideBanner() {
  const banner = document.getElementById("status-banner");
  if (!banner) return;
  banner.hidden = true;
  banner.textContent = "";
}

// Показывает текстовое сообщение вместо содержимого контейнера; text = null убирает его.
export function renderEmpty(container, text) {
  if (!container) return;
  let message = container.querySelector(":scope > .section-message");
  if (text === null || text === undefined) {
    container.classList.remove("has-message");
    if (message) message.remove();
    return;
  }
  if (!message) {
    message = document.createElement("p");
    message.className = "section-message";
    container.appendChild(message);
  }
  message.textContent = text;
  container.classList.add("has-message");
}
