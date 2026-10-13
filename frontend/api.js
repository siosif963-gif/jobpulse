import { API_BASE_URL, SNAPSHOT_URL } from "./config.js";
import * as stats from "./static-stats.js";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request(path, params = {}, signal) {
  const url = new URL(API_BASE_URL + path);
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  url.search = search.toString();

  let response;
  try {
    response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Сервер недоступен");
  }

  if (!response.ok) {
    let code = "http_error";
    let message = `Ошибка сервера (${response.status})`;
    try {
      const body = await response.json();
      if (body && body.error) {
        code = body.error.code || code;
        message = body.error.message || message;
      }
    } catch (_) { /* тело не JSON */ }
    throw new ApiError(response.status, code, message);
  }

  try {
    return await response.json();
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    throw new ApiError(response.status, "invalid_response", "Некорректный ответ сервера");
  }
}

// --- режим статичного снимка (без бэкенда) -----------------------------------
let snapshotPromise = null;

async function loadSnapshot(signal) {
  if (!snapshotPromise) {
    snapshotPromise = (async () => {
      let response;
      try {
        response = await fetch(SNAPSHOT_URL, { signal });
      } catch (err) {
        if (err && err.name === "AbortError") throw err;
        throw new ApiError(0, "network_error", "Не удалось загрузить снимок данных");
      }
      if (!response.ok) throw new ApiError(response.status, "snapshot_missing", "Снимок данных не найден");
      return response.json();
    })();
    snapshotPromise.catch(() => { snapshotPromise = null; });
  }
  return snapshotPromise;
}

const useSnapshot = API_BASE_URL === null;

function endpoint(path, compute) {
  return async (params = {}, signal) => {
    if (!useSnapshot) return request(path(params), params, signal);
    const snapshot = await loadSnapshot(signal);
    if (signal && signal.aborted) throw new DOMException("Aborted", "AbortError");
    return compute(snapshot, params);
  };
}

export const getVacancies = endpoint(() => "/api/vacancies", stats.vacancies);
export const getVacancyById = endpoint(
  (p) => `/api/vacancies/${encodeURIComponent(p.id)}`,
  (snapshot, p) => {
    const found = stats.vacancyById(snapshot, p.id);
    if (!found) throw new ApiError(404, "not_found", `Вакансия с id=${p.id} не найдена`);
    return found;
  }
);
export const getSalaryTrend = endpoint(() => "/api/stats/salary-trend", stats.salaryTrend);
export const getTechDistribution = endpoint(() => "/api/stats/tech-distribution", stats.techDistribution);
export const getCityDistribution = endpoint(() => "/api/stats/city-distribution", stats.cityDistribution);
export const getExperienceDistribution = endpoint(() => "/api/stats/experience-distribution", stats.experienceDistribution);
export const getSummary = endpoint(() => "/api/stats/summary", stats.summary);
export const getHealth = endpoint(() => "/api/health", (snapshot) => stats.health(snapshot));
