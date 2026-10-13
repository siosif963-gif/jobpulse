import { formatMoney, formatNumber, formatPercent } from "./utils.js";

let currentCurrency = "RUR";

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function palette() {
  return [1, 2, 3, 4, 5, 6].map((i) => css(`--chart-${i}`));
}

function baseOptions(onClick, clickable = true) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: { legend: { display: false } },
    onHover(event, elements) {
      const target = event.native && event.native.target;
      if (target) target.style.cursor = clickable && elements.length && onClick ? "pointer" : "default";
    },
    onClick(event, elements, chart) {
      if (!onClick || !elements.length) return;
      onClick(elements[0].index, chart);
    },
  };
}

// Применяет цвета темы к графику (вызывается при создании, обновлении данных и смене темы)
function styleChart(chart) {
  const colors = palette();
  const grid = css("--grid");
  const muted = css("--text-muted");
  const surface = css("--surface");
  const kind = chart.config.type;

  if (kind === "line") {
    chart.data.datasets[0].borderColor = colors[0];
    chart.data.datasets[0].backgroundColor = colors[0];
    chart.data.datasets[1].borderColor = colors[1];
    chart.data.datasets[1].backgroundColor = colors[1];
  } else if (kind === "doughnut") {
    chart.data.datasets[0].backgroundColor = colors;
    chart.data.datasets[0].borderColor = surface;
  } else {
    chart.data.datasets[0].backgroundColor = colors[0];
  }

  const { scales, plugins } = chart.options;
  if (scales) {
    for (const scale of Object.values(scales)) {
      scale.ticks = { ...(scale.ticks || {}), color: muted };
      scale.grid = { ...(scale.grid || {}), color: grid };
      if (scale.border) scale.border.color = grid;
    }
  }
  if (plugins.legend && plugins.legend.display) {
    plugins.legend.labels = { ...(plugins.legend.labels || {}), color: muted };
  }
}

function currencyNow() {
  return currentCurrency;
}

export function createSalaryTrendChart(canvas) {
  const options = baseOptions(null, false);
  options.interaction = { mode: "index", intersect: false };
  options.plugins.legend = { display: true, position: "bottom" };
  options.plugins.tooltip = {
    callbacks: {
      title: (items) => items[0].label,
      label: (item) => `${item.dataset.label}: ${formatMoney(item.parsed.y, currencyNow())}`,
      afterBody(items) {
        const meta = items[0].chart.$meta || [];
        const point = meta[items[0].dataIndex];
        return point ? `вакансий: ${point.vacancy_count}, с зарплатой: ${point.salary_count}` : "";
      },
    },
  };
  options.scales = {
    x: { ticks: { maxRotation: 0, autoSkip: true } },
    y: { beginAtZero: false, ticks: { callback: (v) => formatMoney(v, currencyNow()) } },
  };
  const chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Средняя", data: [], tension: 0.25, spanGaps: true, pointRadius: 3 },
        { label: "Медианная", data: [], tension: 0.25, spanGaps: true, borderDash: [6, 4], pointRadius: 2 },
      ],
    },
    options,
  });
  styleChart(chart);
  chart.update("none");
  return chart;
}

export function createTechDistributionChart(canvas, onClick) {
  const options = baseOptions((index, chart) => onClick && onClick(chart.data.labels[index]));
  options.plugins.tooltip = {
    callbacks: {
      label(item) {
        const meta = item.chart.$meta || [];
        const p = meta[item.dataIndex];
        return p ? `${formatNumber(p.count)} вакансий (${formatPercent(p.percentage)})` : String(item.parsed.y);
      },
    },
  };
  options.scales = { x: { ticks: { maxRotation: 45 } }, y: { beginAtZero: true, ticks: { precision: 0 } } };
  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Вакансий", data: [] }] },
    options,
  });
  styleChart(chart);
  chart.update("none");
  return chart;
}

export function createCityDistributionChart(canvas, onClick) {
  const options = baseOptions((index, chart) => {
    const meta = chart.$meta || [];
    if (meta[index]) onClick && onClick(meta[index].value);
  });
  options.indexAxis = "y";
  options.plugins.tooltip = {
    callbacks: {
      label(item) {
        const meta = item.chart.$meta || [];
        const p = meta[item.dataIndex];
        return p ? `${formatNumber(p.count)} вакансий (${formatPercent(p.percentage)})` : String(item.parsed.x);
      },
    },
  };
  options.scales = { x: { beginAtZero: true, ticks: { precision: 0 } }, y: {} };
  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Вакансий", data: [] }] },
    options,
  });
  styleChart(chart);
  chart.update("none");
  return chart;
}

export function createExperienceDistributionChart(canvas, onClick) {
  const options = baseOptions((index, chart) => {
    const meta = chart.$meta || [];
    if (meta[index]) onClick && onClick(meta[index].level);
  });
  options.plugins.legend = { display: true, position: "bottom" };
  options.plugins.tooltip = {
    callbacks: {
      label(item) {
        const meta = item.chart.$meta || [];
        const p = meta[item.dataIndex];
        return p ? `${item.label}: ${formatNumber(p.count)} (${formatPercent(p.percentage)})` : String(item.parsed);
      },
    },
  };
  const chart = new Chart(canvas, {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], borderWidth: 2 }] },
    options,
  });
  styleChart(chart);
  chart.update("none");
  return chart;
}

// data: { labels: string[], series: number[][], meta: any[] }
export function updateChart(chart, data) {
  chart.data.labels = data.labels;
  data.series.forEach((values, i) => {
    if (chart.data.datasets[i]) chart.data.datasets[i].data = values;
  });
  chart.$meta = data.meta || [];
  styleChart(chart);
  chart.update();
}

export function applyChartTheme(charts) {
  for (const chart of Object.values(charts)) {
    if (!chart) continue;
    styleChart(chart);
    chart.update("none");
  }
}

export function setChartCurrency(currency) {
  currentCurrency = currency;
}
