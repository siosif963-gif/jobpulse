import { applyTheme, initDashboard } from "./dashboard.js";

const THEME_KEY = "jobpulse-theme";

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function renderThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  const dark = currentTheme() === "dark";
  btn.setAttribute("aria-pressed", String(dark));
  btn.setAttribute("aria-label", dark ? "Включить светлую тему" : "Включить тёмную тему");
  btn.textContent = dark ? "Светлая тема" : "Тёмная тема";
}

function initTheme() {
  renderThemeToggle();
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch (_) { /* localStorage недоступен */ }
    renderThemeToggle();
    applyTheme();
  });
}

function start() {
  initTheme();
  if (typeof Chart === "undefined") {
    const banner = document.getElementById("status-banner");
    banner.className = "banner banner--warning";
    banner.textContent = "Не удалось загрузить библиотеку графиков (Chart.js). Проверьте подключение к интернету.";
    banner.hidden = false;
    return;
  }
  initDashboard();
}

// Chart.js подключён с defer: к DOMContentLoaded скрипт уже выполнен.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
