import { appState } from "./state.js";
import * as api from "./api.js";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "./utils.js";
import { hideBanner, renderEmpty, setButtonLoading, setLoading, showBanner, showToast } from "./ui.js";
import {
  applyChartTheme,
  createCityDistributionChart,
  createExperienceDistributionChart,
  createSalaryTrendChart,
  createTechDistributionChart,
  setChartCurrency,
  updateChart,
} from "./charts.js";
import { initFilters, populateFilterOptions, setFilterValues } from "./filters.js";
import { renderPagination, renderVacancies, showTableMessage } from "./table.js";

const charts = { trend: null, tech: null, city: null, experience: null };
let refreshController = null;
let trendController = null;
let tableController = null;

const ERROR_TEXT = "Не удалось загрузить данные";
const NOTHING_FOUND = "По выбранным фильтрам ничего не найдено. Попробуйте изменить параметры.";
const GENERAL_ERROR_TOAST = "Ошибка загрузки данных. Попробуйте позже.";

const $ = (id) => document.getElementById(id);

export function getCharts() {
  return charts;
}

export function applyTheme() {
  applyChartTheme(charts);
}

function hasActiveFilters() {
  const f = appState.filters;
  return Boolean(f.tech || f.city || f.experience_level || f.keyword);
}

function isAbort(reason) {
  return reason && reason.name === "AbortError";
}

// --- параметры запросов ------------------------------------------------------
function summaryParams() {
  const f = appState.filters;
  return { tech: f.tech, city: f.city, experience_level: f.experience_level, currency: f.currency, days: f.days };
}

function trendParams() {
  return { ...summaryParams(), period: appState.trendPeriod };
}

function techParams() {
  const f = appState.filters;
  return { city: f.city, experience_level: f.experience_level, days: f.days, limit: 10 };
}

function cityParams() {
  const f = appState.filters;
  return { tech: f.tech, experience_level: f.experience_level, days: f.days, limit: 10 };
}

function experienceParams() {
  const f = appState.filters;
  return { tech: f.tech, city: f.city, days: f.days };
}

function vacancyParams() {
  const f = appState.filters;
  const t = appState.table;
  return {
    keyword: f.keyword,
    city: f.city,
    tech: f.tech,
    experience_level: f.experience_level,
    currency: f.currency,
    page: t.page,
    page_size: t.page_size,
    sort_by: t.sort_by,
    sort_order: t.sort_order,
  };
}

// --- отрисовка секций -----------------------------------------------------
function chartWrap(chartKey) {
  return charts[chartKey].canvas.closest(".chart-wrap");
}

function showChartMessage(chartKey, text) {
  renderEmpty(chartWrap(chartKey), text);
}

function renderSummary(result) {
  const { summary } = result;
  const currency = appState.filters.currency;
  $("summary-total").textContent = formatNumber(summary.total_vacancies);
  $("summary-avg").textContent = formatMoney(summary.avg_salary, currency);
  $("summary-median").textContent = formatMoney(summary.median_salary, currency);
  $("summary-top-tech").textContent = summary.top_tech || "—";
  const note = summary.vacancies_with_salary > 0 ? `по ${formatNumber(summary.vacancies_with_salary)} вакансиям с зарплатой` : "нет данных о зарплатах";
  $("summary-avg-note").textContent = note;
  $("summary-median-note").textContent = note;
  $("footer-updated").textContent = summary.last_updated_at ? formatDateTime(summary.last_updated_at) : "—";
}

function renderSummaryError() {
  for (const id of ["summary-total", "summary-avg", "summary-median", "summary-top-tech"]) $(id).textContent = "—";
  $("summary-avg-note").textContent = ERROR_TEXT;
  $("summary-median-note").textContent = ERROR_TEXT;
}

function emptyTextFor(total) {
  if (total > 0) return null;
  return hasActiveFilters() ? NOTHING_FOUND : "Нет данных";
}

function renderTrend(result) {
  const points = result.data_points;
  const currency = result.currency;
  setChartCurrency(currency);
  const message = emptyTextFor(points.length);
  showChartMessage("trend", message);
  const labels = points.map((p) => formatDate(p.date));
  updateChart(charts.trend, {
    labels,
    series: [points.map((p) => p.avg_salary), points.map((p) => p.median_salary)],
    meta: points,
  });
  const canvas = charts.trend.canvas;
  const periodName = { day: "по дням", week: "по неделям", month: "по месяцам" }[appState.trendPeriod];
  const values = points.map((p) => p.avg_salary).filter((v) => v !== null);
  if (values.length) {
    canvas.setAttribute(
      "aria-label",
      `Динамика средней зарплаты ${periodName}: ${points.length} точек, от ${formatMoney(Math.min(...values), currency)} до ${formatMoney(Math.max(...values), currency)}`
    );
  } else {
    canvas.setAttribute("aria-label", `Динамика зарплат ${periodName}: нет данных`);
  }
}

function renderTech(result) {
  const items = result.technologies;
  showChartMessage("tech", emptyTextFor(items.length));
  updateChart(charts.tech, {
    labels: items.map((i) => i.name),
    series: [items.map((i) => i.count)],
    meta: items,
  });
  charts.tech.canvas.setAttribute(
    "aria-label",
    items.length
      ? `Топ технологий: ${items.length} позиций, лидер — ${items[0].name} (${formatNumber(items[0].count)} вакансий)`
      : "Топ технологий: нет данных"
  );
}

function renderCity(result) {
  const items = result.cities;
  showChartMessage("city", emptyTextFor(items.length));
  updateChart(charts.city, {
    labels: items.map((i) => i.name),
    series: [items.map((i) => i.count)],
    meta: items,
  });
  charts.city.canvas.setAttribute(
    "aria-label",
    items.length
      ? `Распределение по городам: ${items.length} позиций, лидер — ${items[0].name} (${formatNumber(items[0].count)} вакансий)`
      : "Распределение по городам: нет данных"
  );
}

function renderExperience(result) {
  const items = result.experience_levels;
  showChartMessage("experience", emptyTextFor(result.total_vacancies));
  updateChart(charts.experience, {
    labels: items.map((i) => i.label),
    series: [items.map((i) => i.count)],
    meta: items,
  });
  const parts = items.filter((i) => i.count > 0).map((i) => `${i.label} — ${formatNumber(i.count)}`);
  charts.experience.canvas.setAttribute(
    "aria-label",
    parts.length ? `Распределение по уровню опыта: ${parts.join(", ")}` : "Распределение по уровню опыта: нет данных"
  );
}

function renderTable(result) {
  const { vacancies, pagination } = result;
  if (!vacancies.length && appState.table.page > 1 && pagination.total_pages > 0) {
    appState.table.page = pagination.total_pages;
    refreshTable();
    return;
  }
  renderVacancies(vacancies, emptyTextFor(pagination.total));
  renderPagination(pagination.total, pagination.page, pagination.page_size, (page) => {
    appState.table.page = page;
    refreshTable();
  });
}

function renderSectionError(chartKey) {
  const key = chartKey;
  updateChart(charts[key], { labels: [], series: key === "trend" ? [[], []] : [[]], meta: [] });
  showChartMessage(key, ERROR_TEXT);
}

// --- загрузка -----------------------------------------------------------------
const sections = {
  summary: () => $("summary"),
  trend: () => chartWrap("trend"),
  tech: () => chartWrap("tech"),
  city: () => chartWrap("city"),
  experience: () => chartWrap("experience"),
  table: () => document.querySelector("#vacancies-section .table-wrap"),
};

export async function refreshAll() {
  if (refreshController) refreshController.abort();
  if (trendController) trendController.abort();
  if (tableController) tableController.abort();
  refreshController = new AbortController();
  const { signal } = refreshController;
  const applyBtn = $("apply-filters");

  Object.values(sections).forEach((get) => setLoading(get(), true));
  setButtonLoading(applyBtn, true);
  setChartCurrency(appState.filters.currency);

  const tasks = {
    summary: api.getSummary(summaryParams(), signal),
    trend: api.getSalaryTrend(trendParams(), signal),
    tech: api.getTechDistribution(techParams(), signal),
    city: api.getCityDistribution(cityParams(), signal),
    experience: api.getExperienceDistribution(experienceParams(), signal),
    table: api.getVacancies(vacancyParams(), signal),
  };
  const names = Object.keys(tasks);
  const results = await Promise.allSettled(Object.values(tasks));

  if (signal.aborted) return; // запущен более новый refreshAll — он сам снимет индикаторы

  const renderers = {
    summary: [renderSummary, renderSummaryError],
    trend: [renderTrend, () => renderSectionError("trend")],
    tech: [renderTech, () => renderSectionError("tech")],
    city: [renderCity, () => renderSectionError("city")],
    experience: [renderExperience, () => renderSectionError("experience")],
    table: [renderTable, () => showTableMessage(ERROR_TEXT)],
  };

  let failed = false;
  results.forEach((result, i) => {
    const name = names[i];
    setLoading(sections[name](), false);
    if (result.status === "fulfilled") {
      try {
        renderers[name][0](result.value);
      } catch (err) {
        console.error(err);
        failed = true;
        renderers[name][1]();
      }
    } else if (!isAbort(result.reason)) {
      failed = true;
      renderers[name][1]();
    }
  });
  setButtonLoading(applyBtn, false);
  if (failed) showToast(GENERAL_ERROR_TOAST, "error");
}

export async function refreshTrend() {
  if (trendController) trendController.abort();
  trendController = new AbortController();
  const { signal } = trendController;
  const target = sections.trend();
  setLoading(target, true);
  try {
    renderTrend(await api.getSalaryTrend(trendParams(), signal));
  } catch (err) {
    if (isAbort(err)) return;
    renderSectionError("trend");
    showToast(GENERAL_ERROR_TOAST, "error");
  }
  setLoading(target, false);
}

export async function refreshTable() {
  if (tableController) tableController.abort();
  tableController = new AbortController();
  const { signal } = tableController;
  const target = sections.table();
  setLoading(target, true);
  try {
    renderTable(await api.getVacancies(vacancyParams(), signal));
  } catch (err) {
    if (isAbort(err)) return;
    showTableMessage(ERROR_TEXT);
    showToast(GENERAL_ERROR_TOAST, "error");
  }
  setLoading(target, false);
}

export function applyFilterFromChart(key, value) {
  if (value === null || value === undefined || value === "" || value === "not_specified") return;
  appState.filters = { ...appState.filters, [key]: value };
  appState.table.page = 1;
  setFilterValues(appState.filters);
  refreshAll();
}

// --- инициализация ----------------------------------------------------------
function applyHealth(health) {
  if (health.snapshot) {
    showBanner("info", `Демонстрационный режим: статичный снимок данных Habr Career на ${formatDate(health.last_parsing_at)}.`);
  } else if (health.status === "no_data") {
    showBanner("info", "Данные ещё не собраны. Запустите парсер вручную или дождитесь автоматического запуска.");
  } else if (["failed", "blocked"].includes(health.last_run_status)) {
    showBanner("warning", `Источник временно недоступен. Показаны данные на ${formatDate(health.last_parsing_at)}.`);
  } else {
    hideBanner();
  }
}

function setupControls() {
  const periodGroup = $("trend-period");
  periodGroup.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-period]");
    if (!btn || btn.dataset.period === appState.trendPeriod) return;
    appState.trendPeriod = btn.dataset.period;
    periodGroup.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    refreshTrend();
  });

  $("table-sort").addEventListener("change", (event) => {
    const [sortBy, sortOrder] = event.target.value.split(":");
    appState.table.sort_by = sortBy;
    appState.table.sort_order = sortOrder;
    appState.table.page = 1;
    refreshTable();
  });

  $("page-size").addEventListener("change", (event) => {
    appState.table.page_size = Number(event.target.value);
    appState.table.page = 1;
    refreshTable();
  });
}

export async function initDashboard() {
  charts.trend = createSalaryTrendChart($("chart-trend"));
  charts.tech = createTechDistributionChart($("chart-tech"), (name) => applyFilterFromChart("tech", name));
  charts.city = createCityDistributionChart($("chart-city"), (value) => applyFilterFromChart("city", value));
  charts.experience = createExperienceDistributionChart($("chart-experience"), (level) =>
    applyFilterFromChart("experience_level", level)
  );

  initFilters({
    onApply(filters) {
      appState.filters = filters;
      appState.table.page = 1;
      refreshAll();
    },
    onReset(filters) {
      appState.filters = { ...filters };
      appState.table.page = 1;
      refreshAll();
    },
  });
  setupControls();
  setFilterValues(appState.filters);

  const [healthResult, citiesResult, techResult] = await Promise.allSettled([
    api.getHealth({}),
    api.getCityDistribution({ days: 365, limit: 50 }),
    api.getTechDistribution({ days: 365, limit: 50 }),
  ]);

  populateFilterOptions({
    cities: citiesResult.status === "fulfilled"
      ? citiesResult.value.cities.filter((c) => c.value && c.value !== "__remote__").map((c) => c.value)
      : [],
    technologies: techResult.status === "fulfilled" ? techResult.value.technologies.map((t) => t.name) : [],
  });

  if (healthResult.status === "fulfilled") {
    applyHealth(healthResult.value);
  } else {
    showToast("Не удалось получить статус сервера.", "error");
  }

  await refreshAll();
}
