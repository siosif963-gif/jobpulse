// Режимы работы:
//  - локально (localhost) — живой бэкенд на http://localhost:8000;
//  - на GitHub Pages — статичный снимок данных (data/snapshot.json), бэкенд не нужен;
//  - ?static=1 в адресе принудительно включает режим снимка (проверка локально).
// Если развернёте бэкенд, замените null ниже на его адрес, например "https://my-backend.up.railway.app".
const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
const forceStatic = new URLSearchParams(location.search).has("static");

export const API_BASE_URL = forceStatic ? null : isLocal ? "http://localhost:8000" : null;
export const SNAPSHOT_URL = "data/snapshot.json";
