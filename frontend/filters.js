import { DEFAULT_FILTERS } from "./state.js";

const els = {};

function cacheElements() {
  els.form = document.getElementById("filters-form");
  els.tech = document.getElementById("filter-tech");
  els.city = document.getElementById("filter-city");
  els.experience = document.getElementById("filter-experience");
  els.currency = document.getElementById("filter-currency");
  els.days = document.getElementById("filter-days");
  els.keyword = document.getElementById("filter-keyword");
  els.reset = document.getElementById("reset-filters");
  els.techOptions = document.getElementById("tech-options");
}

export function initFilters({ onApply, onReset }) {
  cacheElements();
  els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    onApply(getActiveFilters());
  });
  els.reset.addEventListener("click", () => {
    resetFilters();
    onReset({ ...DEFAULT_FILTERS });
  });
}

export function getActiveFilters() {
  return {
    tech: els.tech.value.trim(),
    city: els.city.value,
    experience_level: els.experience.value,
    currency: els.currency.value || DEFAULT_FILTERS.currency,
    days: Number(els.days.value) || DEFAULT_FILTERS.days,
    keyword: els.keyword.value.trim(),
  };
}

export function setFilterValues(filters) {
  els.tech.value = filters.tech || "";
  ensureOption(els.city, filters.city || "");
  els.city.value = filters.city || "";
  els.experience.value = filters.experience_level || "";
  els.currency.value = filters.currency || DEFAULT_FILTERS.currency;
  els.days.value = String(filters.days || DEFAULT_FILTERS.days);
  els.keyword.value = filters.keyword || "";
}

export function resetFilters() {
  setFilterValues(DEFAULT_FILTERS);
}

// Если выбранного значения нет в списке (например, город вне топа) — добавить опцию.
function ensureOption(select, value) {
  if (!value) return;
  const exists = Array.from(select.options).some((o) => o.value === value);
  if (!exists) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

export function populateFilterOptions({ cities = [], technologies = [] }) {
  const existing = new Set(Array.from(els.city.options).map((o) => o.value));
  for (const name of cities) {
    if (!name || existing.has(name)) continue;
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    els.city.appendChild(option);
    existing.add(name);
  }
  els.techOptions.replaceChildren();
  for (const name of technologies) {
    const option = document.createElement("option");
    option.value = name;
    els.techOptions.appendChild(option);
  }
}
