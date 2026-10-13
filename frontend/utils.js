const CURRENCY_SYMBOLS = { RUR: "₽", USD: "$", EUR: "€" };
const numberFormat = new Intl.NumberFormat("ru-RU");

export function formatNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return numberFormat.format(n);
}

export function formatMoney(n, currency = "RUR") {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const symbol = CURRENCY_SYMBOLS[currency] || currency || "";
  return `${numberFormat.format(Math.round(n))} ${symbol}`.trim();
}

export function formatSalaryRange(min, max, currency = "RUR") {
  const hasMin = min !== null && min !== undefined;
  const hasMax = max !== null && max !== undefined;
  if (!hasMin && !hasMax) return "Зарплата не указана";
  const symbol = CURRENCY_SYMBOLS[currency] || currency || "";
  if (hasMin && hasMax) return `${numberFormat.format(min)} – ${numberFormat.format(max)} ${symbol}`.trim();
  if (hasMin) return `от ${numberFormat.format(min)} ${symbol}`.trim();
  return `до ${numberFormat.format(max)} ${symbol}`.trim();
}

export function formatDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date
    .toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" })
    .replace(/\s?г\.$/, "");
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const time = date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return `${formatDate(iso)}, ${time}`;
}

export function formatPercent(p) {
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(p)}%`;
}
