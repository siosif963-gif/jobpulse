import { formatDate, formatSalaryRange } from "./utils.js";
import { renderEmpty } from "./ui.js";

const MAX_TECH_IN_ROW = 5;

export function handleVacancyClick(url) {
  if (url) window.open(url, "_blank", "noopener");
}

function cell(label, className) {
  const td = document.createElement("td");
  td.dataset.label = label;
  if (className) td.className = className;
  return td;
}

function buildRow(vacancy) {
  const tr = document.createElement("tr");
  tr.className = "vacancy-row";
  if (!vacancy.is_active) tr.classList.add("vacancy-row--inactive");

  const titleCell = cell("Вакансия", "vacancy-title");
  const link = document.createElement("a");
  link.href = vacancy.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = vacancy.title;
  titleCell.appendChild(link);
  const tags = [];
  if (vacancy.is_remote) tags.push("Удалёнка");
  tags.push(...(vacancy.tech_stack || []).slice(0, MAX_TECH_IN_ROW));
  if (tags.length) {
    const meta = document.createElement("div");
    meta.className = "vacancy-tags";
    meta.textContent = tags.join(" · ");
    titleCell.appendChild(meta);
  }
  tr.appendChild(titleCell);

  const company = cell("Компания");
  company.textContent = vacancy.company || "—";
  tr.appendChild(company);

  const city = cell("Город");
  const cities = vacancy.cities || [];
  if (cities.length) {
    city.textContent = cities.length > 1 ? `${cities[0]} +${cities.length - 1}` : cities[0];
    if (cities.length > 1) city.title = cities.join(", ");
  } else {
    city.textContent = vacancy.is_remote ? "Удалёнка" : "—";
  }
  tr.appendChild(city);

  const salary = cell("Зарплата", "vacancy-salary");
  salary.textContent = formatSalaryRange(vacancy.salary_min, vacancy.salary_max, vacancy.currency);
  if (vacancy.salary_min === null && vacancy.salary_max === null) salary.classList.add("muted");
  tr.appendChild(salary);

  const published = cell("Опубликована");
  published.textContent = formatDate(vacancy.published_at);
  tr.appendChild(published);

  tr.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    handleVacancyClick(vacancy.url);
  });
  return tr;
}

export function renderVacancies(vacancies, emptyText = null) {
  const body = document.getElementById("vacancies-body");
  const wrap = body.closest(".table-wrap");
  body.replaceChildren();
  if (!vacancies.length) {
    renderEmpty(wrap, emptyText || "Нет данных");
    return;
  }
  renderEmpty(wrap, null);
  const fragment = document.createDocumentFragment();
  vacancies.forEach((v) => fragment.appendChild(buildRow(v)));
  body.appendChild(fragment);
}

export function showTableMessage(text) {
  const body = document.getElementById("vacancies-body");
  body.replaceChildren();
  renderEmpty(body.closest(".table-wrap"), text);
}

function pageButton(label, page, { current = false, disabled = false, ariaLabel = null }, onPageChange) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = label;
  btn.className = "page-btn";
  if (ariaLabel) btn.setAttribute("aria-label", ariaLabel);
  if (current) {
    btn.setAttribute("aria-current", "page");
    btn.classList.add("is-current");
  }
  btn.disabled = disabled;
  if (!disabled && !current) btn.addEventListener("click", () => onPageChange(page));
  return btn;
}

export function renderPagination(total, currentPage, pageSize, onPageChange) {
  const nav = document.getElementById("pagination");
  nav.replaceChildren();
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return;

  const items = [];
  items.push(pageButton("Назад", currentPage - 1, { disabled: currentPage <= 1 }, onPageChange));

  const pages = new Set([1, totalPages]);
  for (let p = currentPage - 2; p <= currentPage + 2; p += 1) {
    if (p >= 1 && p <= totalPages) pages.add(p);
  }
  const sorted = Array.from(pages).sort((a, b) => a - b);
  let previous = 0;
  for (const p of sorted) {
    if (p - previous > 1) {
      const gap = document.createElement("span");
      gap.className = "page-gap";
      gap.textContent = "…";
      gap.setAttribute("aria-hidden", "true");
      items.push(gap);
    }
    items.push(pageButton(String(p), p, { current: p === currentPage, ariaLabel: `Страница ${p}` }, onPageChange));
    previous = p;
  }
  items.push(pageButton("Вперёд", currentPage + 1, { disabled: currentPage >= totalPages }, onPageChange));
  nav.append(...items);
}
