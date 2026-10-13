import { API_BASE_URL } from "./config.js";

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

export const getVacancies = (params, signal) => request("/api/vacancies", params, signal);
export const getVacancyById = (params, signal) => request(`/api/vacancies/${encodeURIComponent(params.id)}`, {}, signal);
export const getSalaryTrend = (params, signal) => request("/api/stats/salary-trend", params, signal);
export const getTechDistribution = (params, signal) => request("/api/stats/tech-distribution", params, signal);
export const getCityDistribution = (params, signal) => request("/api/stats/city-distribution", params, signal);
export const getExperienceDistribution = (params, signal) => request("/api/stats/experience-distribution", params, signal);
export const getSummary = (params, signal) => request("/api/stats/summary", params, signal);
export const getHealth = (params, signal) => request("/api/health", params, signal);
