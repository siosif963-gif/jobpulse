// Расчёт статистики в браузере по статичному снимку (режим без бэкенда).
// Формулы повторяют backend/services/stats_service.py и vacancy_service.py.

const LEVELS = ["intern", "junior", "middle", "senior", "lead"];
const LEVEL_LABELS = {
  intern: "Стажёр (Intern)",
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  not_specified: "Не указан",
};
const REMOTE_VALUE = "__remote__";
const DAY_MS = 24 * 60 * 60 * 1000;

const norm = (s) => String(s).split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const round1 = (x) => Math.round(x * 10) / 10;
const pct = (count, total) => (total ? round1((count / total) * 100) : 0);

export function salaryPoint(min, max) {
  if (min !== null && min !== undefined && max !== null && max !== undefined) return (min + max) / 2;
  if (min !== null && min !== undefined) return min;
  if (max !== null && max !== undefined) return max;
  return null;
}

function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function salaryStats(points) {
  if (!points.length) return { avg_salary: null, median_salary: null, min_salary: null, max_salary: null };
  return {
    avg_salary: Math.round(points.reduce((a, b) => a + b, 0) / points.length),
    median_salary: Math.round(median(points)),
    min_salary: Math.round(Math.min(...points)),
    max_salary: Math.round(Math.max(...points)),
  };
}

function localDate(iso, timeZone) {
  // YYYY-MM-DD в нужной таймзоне
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(iso)
  );
}

export function bucketDate(iso, period, timeZone) {
  const day = localDate(iso, timeZone);
  if (period === "day") return day;
  const [y, m, d] = day.split("-").map(Number);
  if (period === "month") return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-01`;
  const dt = new Date(Date.UTC(y, m - 1, d));
  const weekday = (dt.getUTCDay() + 6) % 7; // понедельник = 0
  dt.setUTCDate(dt.getUTCDate() - weekday);
  return dt.toISOString().slice(0, 10);
}

function prepare(snapshot) {
  if (!snapshot._prepared) {
    snapshot._prepared = snapshot.vacancies.map((v) => ({
      v,
      ts: Date.parse(v.published_at),
      techs: new Set(v.tech_stack.map(norm)),
      cityNorm: new Set(v.cities.map(norm)),
    }));
  }
  return snapshot._prepared;
}

function select(snapshot, { tech, city, experience_level, days, onlyActive = false } = {}) {
  const now = Date.parse(snapshot.generated_at);
  const techN = tech ? norm(tech) : null;
  const cityN = city && city !== REMOTE_VALUE ? city.trim().toLowerCase() : null;
  return prepare(snapshot)
    .filter((row) => {
      const v = row.v;
      if (onlyActive && !v.is_active) return false;
      if (techN && !row.techs.has(techN)) return false;
      if (city === REMOTE_VALUE && !v.is_remote) return false;
      if (cityN && !row.cityNorm.has(cityN)) return false;
      if (experience_level && v.experience_level !== experience_level) return false;
      if (days && row.ts < now - days * DAY_MS) return false;
      return true;
    })
    .map((row) => row.v);
}

function cityCounts(vacancies) {
  const totals = new Map(); // norm -> count
  const spellings = new Map(); // norm -> Map(spelling -> count)
  for (const v of vacancies) {
    const seen = new Set();
    for (const c of v.cities) {
      const n = c.trim().toLowerCase();
      if (!n || seen.has(n)) continue;
      seen.add(n);
      totals.set(n, (totals.get(n) || 0) + 1);
      const sp = spellings.get(n) || new Map();
      sp.set(c, (sp.get(c) || 0) + 1);
      spellings.set(n, sp);
    }
  }
  return [...totals].map(([n, count]) => {
    const best = [...spellings.get(n)].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0][0];
    return { name: best, value: best, count };
  });
}

const byCountThenName = (a, b) => b.count - a.count || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);

function techCounts(vacancies) {
  const counts = new Map(); // norm -> {name, count}
  for (const v of vacancies) {
    const seen = new Set();
    for (const t of v.tech_stack) {
      const n = norm(t);
      if (seen.has(n)) continue;
      seen.add(n);
      const cur = counts.get(n);
      if (cur) cur.count += 1;
      else counts.set(n, { name: t, count: 1 });
    }
  }
  return [...counts.values()].sort(byCountThenName);
}

// --- публичные функции ------------------------------------------------------
export function vacancies(snapshot, p) {
  let items = select(snapshot, { tech: p.tech, city: p.city, experience_level: p.experience_level });
  if (p.only_active !== "false" && p.only_active !== false) items = items.filter((v) => v.is_active);
  const kw = p.keyword ? String(p.keyword).trim().toLowerCase() : "";
  if (kw) items = items.filter((v) => `${v.title} ${v.company || ""}`.toLowerCase().includes(kw));
  const cur = p.currency || "RUR";
  if (p.salary_min !== undefined && p.salary_min !== "" && p.salary_min !== null) {
    items = items.filter((v) => v.currency === cur && (v.salary_max ?? v.salary_min) !== null && (v.salary_max ?? v.salary_min) >= Number(p.salary_min));
  }
  if (p.salary_max !== undefined && p.salary_max !== "" && p.salary_max !== null) {
    items = items.filter((v) => v.currency === cur && (v.salary_min ?? v.salary_max) !== null && (v.salary_min ?? v.salary_max) <= Number(p.salary_max));
  }

  const sortBy = p.sort_by || "published_at";
  const dir = (p.sort_order || "desc") === "asc" ? 1 : -1;
  const key = (v) => (sortBy === "published_at" ? Date.parse(v.published_at) : v[sortBy]);
  items = [...items].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    const na = ka === null || ka === undefined;
    const nb = kb === null || kb === undefined;
    if (na !== nb) return na ? 1 : -1; // NULL всегда в конце
    if (!na && ka !== kb) return (ka - kb) * dir;
    return b.id - a.id;
  });

  const page = Math.max(1, Number(p.page) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(p.page_size) || 20));
  const total = items.length;
  return {
    vacancies: items.slice((page - 1) * pageSize, page * pageSize),
    pagination: { total, page, page_size: pageSize, total_pages: total ? Math.ceil(total / pageSize) : 0 },
  };
}

export function salaryTrend(snapshot, p) {
  const days = Number(p.days) || 30;
  const currency = p.currency || "RUR";
  const period = p.period || "week";
  const tz = snapshot.timezone || "Europe/Moscow";
  const buckets = new Map();
  for (const v of select(snapshot, { tech: p.tech, city: p.city, experience_level: p.experience_level, days })) {
    const key = bucketDate(v.published_at, period, tz);
    const b = buckets.get(key) || { count: 0, points: [] };
    b.count += 1;
    if (v.currency === currency) {
      const point = salaryPoint(v.salary_min, v.salary_max);
      if (point !== null) b.points.push(point);
    }
    buckets.set(key, b);
  }
  const data_points = [...buckets.keys()].sort().map((date) => {
    const b = buckets.get(date);
    return { date, ...salaryStats(b.points), vacancy_count: b.count, salary_count: b.points.length };
  });
  return {
    data_points,
    currency,
    filters: { tech: p.tech || null, city: p.city || null, experience_level: p.experience_level || null, period, days },
  };
}

export function techDistribution(snapshot, p) {
  const days = Number(p.days) || 30;
  const limit = Number(p.limit) || 10;
  const items = select(snapshot, { city: p.city, experience_level: p.experience_level, days });
  const total = items.length;
  return {
    technologies: techCounts(items)
      .slice(0, limit)
      .map((t) => ({ name: t.name, count: t.count, percentage: pct(t.count, total) })),
    total_vacancies: total,
    filters: { city: p.city || null, experience_level: p.experience_level || null, days, limit },
  };
}

export function cityDistribution(snapshot, p) {
  const days = Number(p.days) || 30;
  const limit = Number(p.limit) || 10;
  const items = select(snapshot, { tech: p.tech, experience_level: p.experience_level, days });
  const total = items.length;
  let rows = cityCounts(items);
  const remote = items.filter((v) => v.is_remote).length;
  if (remote) rows.push({ name: "Удалёнка", value: REMOTE_VALUE, count: remote });
  const unspecified = items.filter((v) => !v.is_remote && v.cities.length === 0).length;
  if (unspecified) rows.push({ name: "Не указан", value: null, count: unspecified });
  rows = rows.sort(byCountThenName).slice(0, limit);
  return {
    cities: rows.map((r) => ({ ...r, percentage: pct(r.count, total) })),
    total_vacancies: total,
    filters: { tech: p.tech || null, experience_level: p.experience_level || null, days, limit },
  };
}

export function experienceDistribution(snapshot, p) {
  const days = Number(p.days) || 30;
  const items = select(snapshot, { tech: p.tech, city: p.city, days });
  const total = items.length;
  const counts = new Map();
  for (const v of items) counts.set(v.experience_level, (counts.get(v.experience_level) || 0) + 1);
  const rows = LEVELS.map((level) => ({
    level,
    label: LEVEL_LABELS[level],
    count: counts.get(level) || 0,
    percentage: pct(counts.get(level) || 0, total),
  }));
  const unspecified = counts.get(null) || 0;
  if (unspecified > 0) {
    rows.push({ level: "not_specified", label: LEVEL_LABELS.not_specified, count: unspecified, percentage: pct(unspecified, total) });
  }
  return {
    experience_levels: rows,
    total_vacancies: total,
    filters: { tech: p.tech || null, city: p.city || null, days },
  };
}

export function summary(snapshot, p) {
  const days = Number(p.days) || 30;
  const currency = p.currency || "RUR";
  const items = select(snapshot, { tech: p.tech, city: p.city, experience_level: p.experience_level, days });
  const points = items
    .filter((v) => v.currency === currency)
    .map((v) => salaryPoint(v.salary_min, v.salary_max))
    .filter((x) => x !== null);

  const cities = cityCounts(items).sort(byCountThenName);
  const techs = techCounts(items);
  const levels = new Map();
  for (const v of items) if (v.experience_level) levels.set(v.experience_level, (levels.get(v.experience_level) || 0) + 1);
  let common = null;
  for (const level of LEVELS) {
    if (levels.has(level) && (common === null || levels.get(level) > levels.get(common))) common = level;
  }
  return {
    summary: {
      total_vacancies: items.length,
      vacancies_with_salary: points.length,
      ...salaryStats(points),
      currency,
      top_city: cities.length ? cities[0].name : null,
      top_tech: techs.length ? techs[0].name : null,
      most_common_experience: common,
      most_common_experience_label: common ? LEVEL_LABELS[common] : null,
      last_updated_at: snapshot.last_parsing_at || snapshot.generated_at,
    },
    filters: { tech: p.tech || null, city: p.city || null, experience_level: p.experience_level || null, days },
  };
}

export function health(snapshot) {
  const total = snapshot.vacancies.length;
  return {
    status: total ? "ok" : "no_data",
    last_parsing_at: snapshot.last_parsing_at || snapshot.generated_at,
    last_run_status: "success",
    total_vacancies: total,
    active_vacancies: snapshot.vacancies.filter((v) => v.is_active).length,
    is_parsing_now: false,
    scheduler_running: false,
    next_run_at: null,
    snapshot: true,
  };
}

export function vacancyById(snapshot, id) {
  return snapshot.vacancies.find((v) => v.id === Number(id)) || null;
}
