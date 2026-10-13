// Адрес бэкенда. Для продакшена замените YOUR-BACKEND.up.railway.app на адрес вашего Railway-сервиса.
export const API_BASE_URL = (["localhost", "127.0.0.1"].includes(location.hostname))
  ? "http://localhost:8000"
  : "https://YOUR-BACKEND.up.railway.app";
