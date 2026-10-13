export const DEFAULT_FILTERS = {
  tech: "",
  city: "",
  experience_level: "",
  currency: "RUR",
  days: 30,
  keyword: "",
};

export const appState = {
  filters: { ...DEFAULT_FILTERS },
  trendPeriod: "week",
  table: { page: 1, page_size: 20, sort_by: "published_at", sort_order: "desc" },
};
