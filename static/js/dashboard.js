// Dashboard - Portfolio visualization and data fetching

const CONFIG = {
  CHART_COLORS: ["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"],
  THEME: {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(13, 20, 33, 0.3)",
    gridcolor: "rgba(30, 58, 95, 0.3)",
    textcolor: "#94a3b8",
    axiscolor: "#64748b",
    font: { family: "Inter, -apple-system, sans-serif", color: "#94a3b8" },
  },
};

// Chart state
let timelineData = null;
let chartMode = "absolute";
let showBenchmark = true;
let stockPricesData = null;
let stockChartMode = "absolute";

// Theme functions
function getTheme() {
  return document.documentElement.getAttribute("data-theme") || "dark";
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  updateThemeIcon(theme);
  updateChartsForTheme(theme);
}

function toggleTheme() {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.innerHTML = theme === "dark" ? "&#9790;" : "&#9728;";
  }
}

function loadSavedTheme() {
  setTheme(localStorage.getItem("theme") || "dark");
}

function getChartTheme() {
  if (getTheme() === "light") {
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(248, 250, 252, 0.5)",
      gridcolor: "rgba(226, 232, 240, 0.8)",
      textcolor: "#475569",
      axiscolor: "#64748b",
      font: { family: "Inter, -apple-system, sans-serif", color: "#475569" },
    };
  }
  return CONFIG.THEME;
}

function updateChartsForTheme(theme) {
  loadPerformance().catch(() => {});

  const charts = ["pie-chart", "timeline-chart", "stock-prices-chart"];
  const chartTheme = getChartTheme();

  charts.forEach((id) => {
    const el = document.getElementById(id);
    if (el && el.data) {
      const updates = {
        paper_bgcolor: chartTheme.paper_bgcolor,
        plot_bgcolor: chartTheme.plot_bgcolor,
      };
      if (id !== "pie-chart") {
        updates["xaxis.gridcolor"] = chartTheme.gridcolor;
        updates["yaxis.gridcolor"] = chartTheme.gridcolor;
        updates["xaxis.tickfont.color"] = chartTheme.axiscolor;
        updates["yaxis.tickfont.color"] = chartTheme.axiscolor;
      }
      if (id === "stock-prices-chart") {
        updates["legend.font.color"] = chartTheme.textcolor;
      }
      Plotly.relayout(id, updates);
    }
  });
}

// Initialize
document.addEventListener("DOMContentLoaded", function () {
  loadSavedTheme();
  loadAllData();
});

async function loadAllData() {
  showLoading(true);
  hideError();

  try {
    await Promise.all([
      loadPortfolio(),
      loadTimeline(),
      loadStockPrices(),
      loadTrades(),
      loadPerformance(),
      loadQuotaStatus(),
    ]);
    updateLastUpdateTime();
  } catch (error) {
    console.error("Error loading dashboard:", error);
    showError("Failed to load dashboard data. Please refresh the page.");
  }
  showLoading(false);
}

async function loadQuotaStatus() {
  try {
    const response = await fetch("/api/provider-status");
    if (!response.ok) {
      const quotaEl = document.getElementById("quota-status");
      if (quotaEl) quotaEl.textContent = "";
      return;
    }

    const data = await response.json();
    const quotaEl = document.getElementById("quota-status");

    if (quotaEl && data.quota) {
      const { daily_remaining: remaining, daily_limit: limit } = data.quota;
      if (remaining === "unlimited") {
        quotaEl.textContent = "API: Paid tier (unlimited)";
        quotaEl.style.color = "#22c55e";
      } else {
        const pct = (remaining / limit) * 100;
        quotaEl.textContent = `API: ${remaining}/${limit} calls remaining`;
        quotaEl.style.color = pct < 20 ? "#ef4444" : pct < 50 ? "#f59e0b" : "#64748b";
      }
    } else if (quotaEl) {
      quotaEl.textContent = "";
    }
  } catch (error) {
    console.error("Error loading quota status:", error);
  }
}

async function loadPortfolio() {
  const response = await fetch("/api/portfolio");
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  updatePortfolioStats(data);
  renderPieChart(data.holdings, data.cash);
  renderHoldingsTable(data.holdings);
  storeLiveTickerBaseValues(data.cash, data.holdings);
}

async function loadTimeline() {
  const response = await fetch("/api/timeline?days=90&include_benchmark=true");
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  timelineData = data;
  renderTimelineChart();
}

// Unified chart mode toggle
function toggleChartMode(chartType) {
  const isTimeline = chartType === "timeline";
  const currentMode = isTimeline ? chartMode : stockChartMode;
  const newMode = currentMode === "absolute" ? "percentage" : "absolute";

  if (isTimeline) {
    chartMode = newMode;
  } else {
    stockChartMode = newMode;
  }

  const iconId = isTimeline ? "mode-icon" : "stock-mode-icon";
  const textId = isTimeline ? "mode-text" : "stock-mode-text";
  const modeIcon = document.getElementById(iconId);
  const modeText = document.getElementById(textId);

  if (newMode === "absolute") {
    modeIcon.textContent = "$";
    modeText.textContent = "Show %";
  } else {
    modeIcon.textContent = "%";
    modeText.textContent = "Show $";
  }

  if (isTimeline && timelineData) {
    renderTimelineChart();
  } else if (!isTimeline && stockPricesData) {
    renderStockPricesChart();
  }
}

function toggleBenchmark() {
  showBenchmark = document.getElementById("show-benchmark").checked;
  if (timelineData) renderTimelineChart();
}

async function loadStockPrices() {
  const response = await fetch("/api/stocks?days=90");
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  stockPricesData = data;
  renderStockPricesChart();
}

async function loadTrades() {
  const response = await fetch("/api/trades?limit=10");
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  renderRecentTrades(data.trades);
}

async function loadPerformance() {
  const response = await fetch("/api/performance");
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  renderKPICards(data);
}

function updatePortfolioStats(data) {
  const fmt = (v) => `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("total-value").textContent = fmt(data.total_value);
  document.getElementById("cash-value").textContent = fmt(data.cash);
  document.getElementById("stock-value").textContent = fmt(data.stock_value);
}

function renderKPICards(data) {
  const container = document.getElementById("kpi-container");
  const isPositive = data.total_return >= 0;
  const pnlColor = isPositive ? "#22c55e" : "#ef4444";
  const defaultColor = getTheme() === "dark" ? "#f8fafc" : "#1e3a5f";
  const sharpeColor = data.sharpe_ratio >= 1 ? "#22c55e" : data.sharpe_ratio >= 0 ? "#f59e0b" : "#ef4444";

  const cards = [
    { value: `${isPositive ? "+" : ""}${data.total_return}%`, label: "Total Return", color: pnlColor, className: isPositive ? "positive" : "negative" },
    { value: data.sharpe_ratio.toFixed(2), label: "Sharpe Ratio", color: sharpeColor, className: "" },
    { value: `${data.volatility.toFixed(1)}%`, label: "Volatility", color: defaultColor, className: "" },
    { value: data.total_trades.toString(), label: "Total Trades", color: defaultColor, className: "" },
  ];

  container.innerHTML = cards
    .map((c) => `<div class="kpi-card ${c.className}"><div class="kpi-value" style="color: ${c.color}">${c.value}</div><div class="kpi-label">${c.label}</div></div>`)
    .join("");
}

function renderPieChart(holdings, cash) {
  const labels = holdings.map((h) => h.ticker);
  const values = holdings.map((h) => h.value);

  if (cash > 0) {
    labels.push("Cash");
    values.push(cash);
  }

  const data = [{
    type: "pie",
    labels,
    values,
    marker: { colors: CONFIG.CHART_COLORS, line: { color: "#0d1421", width: 2 } },
    textinfo: "label+percent",
    textfont: { family: "JetBrains Mono, monospace", size: 12, color: "#f8fafc" },
    hole: 0.45,
    hovertemplate: "<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>",
  }];

  const layout = {
    height: 400,
    showlegend: true,
    legend: {
      orientation: "v",
      yanchor: "middle",
      y: 0.5,
      xanchor: "left",
      x: 1.05,
      font: { family: "Inter, sans-serif", size: 12, color: getChartTheme().textcolor },
    },
    paper_bgcolor: getChartTheme().paper_bgcolor,
    plot_bgcolor: getChartTheme().plot_bgcolor,
    margin: { t: 20, b: 20, l: 20, r: 120 },
  };

  Plotly.newPlot("pie-chart", data, layout, { responsive: true, displayModeBar: false });
}

function renderHoldingsTable(holdings) {
  const container = document.getElementById("holdings-table-container");

  if (holdings.length === 0) {
    container.innerHTML = '<p class="no-data">No current holdings</p>';
    return;
  }

  container.innerHTML = `
    <table class="holdings-table">
      <thead>
        <tr><th>Stock</th><th>Shares</th><th>Price</th><th>Value</th><th>Weight</th></tr>
      </thead>
      <tbody>
        ${holdings.map((h) => `
          <tr>
            <td class="stock-ticker">${h.ticker}</td>
            <td>${h.shares}</td>
            <td>$${h.price.toFixed(2)}</td>
            <td>$${h.value.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
            <td>${h.weight.toFixed(1)}%</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderRecentTrades(trades) {
  const container = document.getElementById("recent-trades-container");

  if (trades.length === 0) {
    container.innerHTML = '<p class="no-data">No recent trades</p>';
    return;
  }

  container.innerHTML = trades.slice(0, 5).map((trade) => {
    const date = new Date(trade.timestamp);
    const timeStr = date.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" }) + " " +
      date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    const actionColor = trade.action === "BUY" ? "#22c55e" : "#ef4444";

    return `
      <div class="trade-item ${trade.action.toLowerCase()}">
        <div class="trade-header">
          <span class="trade-time">${timeStr}</span>
          <span class="trade-stock">${trade.ticker}</span>
          <span style="color: ${actionColor}; font-weight: 600; margin-left: auto; font-family: 'Inter', sans-serif; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">${trade.action}</span>
        </div>
        <div class="trade-details">
          ${trade.quantity} shares @ $${trade.price.toFixed(2)} = $${trade.total_cost.toLocaleString("en-US", { minimumFractionDigits: 2 })}
        </div>
      </div>
    `;
  }).join("");
}

function renderTimelineChart() {
  if (!timelineData?.dates?.length) {
    document.getElementById("timeline-chart").innerHTML = '<p class="no-data">No timeline data available</p>';
    return;
  }

  const dates = timelineData.dates;
  const isPercentage = chartMode === "percentage";
  const traces = [];

  // Portfolio trace
  traces.push({
    type: "scatter",
    mode: "lines",
    x: dates,
    y: isPercentage ? timelineData.portfolio_pct : timelineData.values,
    name: "Portfolio",
    line: { color: "#3b82f6", width: 3, shape: "spline" },
    fill: showBenchmark ? "none" : "tozeroy",
    fillcolor: showBenchmark ? undefined : "rgba(59, 130, 246, 0.1)",
    hovertemplate: isPercentage
      ? "<b>Portfolio</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>"
      : "<b>Portfolio</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
  });

  // Benchmark trace
  if (showBenchmark && timelineData.benchmark_pct && timelineData.benchmark_values) {
    const benchmarkValues = isPercentage ? timelineData.benchmark_pct : timelineData.benchmark_values;
    const cleanDates = [], cleanValues = [];

    for (let i = 0; i < benchmarkValues.length; i++) {
      if (benchmarkValues[i] !== null) {
        cleanDates.push(dates[i]);
        cleanValues.push(benchmarkValues[i]);
      }
    }

    if (cleanValues.length > 0) {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: cleanDates,
        y: cleanValues,
        name: "S&P 500 (SPY)",
        line: { color: "#f59e0b", width: 2, dash: "dot" },
        hovertemplate: isPercentage
          ? "<b>S&P 500</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>"
          : "<b>S&P 500</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
      });
    }
  }

  const chartTheme = getChartTheme();
  const layout = {
    height: 400,
    showlegend: showBenchmark,
    legend: {
      orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1,
      font: { family: "Inter, sans-serif", size: 12, color: chartTheme.textcolor },
    },
    xaxis: {
      title: { text: "Date", font: { color: "#64748b", size: 12, family: "Inter, sans-serif" } },
      gridcolor: chartTheme.gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickfont: { color: chartTheme.axiscolor, size: 11, family: "Inter, sans-serif" },
    },
    yaxis: {
      title: { text: isPercentage ? "Change (%)" : "Portfolio Value ($)", font: { color: chartTheme.axiscolor, size: 12, family: "Inter, sans-serif" } },
      gridcolor: chartTheme.gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickformat: isPercentage ? "+.1f" : "$,.0f",
      tickfont: { color: chartTheme.axiscolor, size: 11, family: "JetBrains Mono, monospace" },
    },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: getTheme() === "dark" ? "#111827" : "#ffffff",
      bordercolor: "#1e3a5f",
      font: { family: "JetBrains Mono, monospace", color: getTheme() === "dark" ? "#f8fafc" : "#0f172a" },
    },
    paper_bgcolor: chartTheme.paper_bgcolor,
    plot_bgcolor: chartTheme.plot_bgcolor,
    margin: { t: 40, b: 60, l: 70, r: 20 },
    shapes: [],
    annotations: [],
  };

  // Reference line
  if (isPercentage) {
    layout.shapes.push({
      type: "line", x0: dates[0], x1: dates[dates.length - 1], y0: 0, y1: 0,
      line: { color: "rgba(148, 163, 184, 0.5)", width: 1, dash: "dash" },
    });
  } else {
    const initialValue = timelineData.values[0] || 100000;
    layout.shapes.push({
      type: "line", x0: dates[0], x1: dates[dates.length - 1], y0: initialValue, y1: initialValue,
      line: { color: "rgba(239, 68, 68, 0.5)", width: 2, dash: "dash" },
    });
    layout.annotations.push({
      x: dates[dates.length - 1], y: initialValue, text: "Initial Value", showarrow: false, xanchor: "left",
      font: { size: 10, color: "#ef4444", family: "Inter, sans-serif" },
    });
  }

  Plotly.newPlot("timeline-chart", traces, layout, { responsive: true, displayModeBar: false });
}

function renderStockPricesChart() {
  if (!stockPricesData) {
    document.getElementById("stock-prices-chart").innerHTML = '<p class="no-data">No price data available</p>';
    return;
  }

  const tickers = Object.keys(stockPricesData);
  if (tickers.length === 0) {
    document.getElementById("stock-prices-chart").innerHTML = '<p class="no-data">No price data available</p>';
    return;
  }

  const isPercentage = stockChartMode === "percentage";
  const traces = [];

  tickers.forEach((ticker, index) => {
    const data = stockPricesData[ticker];
    if (data.timestamps.length === 0) return;

    let yValues = data.prices;
    let hovertemplate = "<b>%{fullData.name}</b><br>%{x|%b %d, %Y}<br>$%{y:.2f}<extra></extra>";

    if (isPercentage) {
      const initialPrice = data.prices[0];
      yValues = data.prices.map((p) => initialPrice > 0 ? ((p / initialPrice - 1) * 100).toFixed(2) : 0);
      hovertemplate = "<b>%{fullData.name}</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>";
    }

    traces.push({
      type: "scatter",
      mode: "lines",
      name: ticker,
      x: data.timestamps,
      y: yValues,
      line: { color: CONFIG.CHART_COLORS[index % CONFIG.CHART_COLORS.length], width: 2.5 },
      hovertemplate,
    });
  });

  const chartTheme = getChartTheme();
  const layout = {
    height: 400,
    xaxis: {
      title: { text: "Date", font: { color: "#64748b", size: 12, family: "Inter, sans-serif" } },
      gridcolor: chartTheme.gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickfont: { color: chartTheme.axiscolor, size: 11, family: "Inter, sans-serif" },
    },
    yaxis: {
      title: { text: isPercentage ? "Change (%)" : "Stock Price ($)", font: { color: chartTheme.axiscolor, size: 12, family: "Inter, sans-serif" } },
      gridcolor: chartTheme.gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickformat: isPercentage ? "+.1f" : "$,.2f",
      tickfont: { color: chartTheme.axiscolor, size: 11, family: "JetBrains Mono, monospace" },
    },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: getTheme() === "dark" ? "#111827" : "#ffffff",
      bordercolor: "#1e3a5f",
      font: { family: "JetBrains Mono, monospace", color: getTheme() === "dark" ? "#f8fafc" : "#0f172a" },
    },
    legend: {
      orientation: "h", yanchor: "bottom", y: 1.02, xanchor: "right", x: 1,
      font: { family: "Inter, sans-serif", size: 12, color: chartTheme.textcolor },
    },
    paper_bgcolor: chartTheme.paper_bgcolor,
    plot_bgcolor: chartTheme.plot_bgcolor,
    margin: { t: 40, b: 60, l: 70, r: 20 },
    shapes: [],
  };

  if (isPercentage && traces.length > 0 && traces[0].x.length > 0) {
    layout.shapes.push({
      type: "line", x0: traces[0].x[0], x1: traces[0].x[traces[0].x.length - 1], y0: 0, y1: 0,
      line: { color: "rgba(148, 163, 184, 0.5)", width: 1, dash: "dash" },
    });
  }

  Plotly.newPlot("stock-prices-chart", traces, layout, { responsive: true, displayModeBar: false });
}

// UI helpers
function showLoading(show) {
  const spinner = document.getElementById("loading-spinner");
  if (spinner) spinner.classList.toggle("hidden", !show);
}

function showError(message) {
  const errorDiv = document.getElementById("error-message");
  document.getElementById("error-text").textContent = message;
  errorDiv.classList.remove("hidden");
  setTimeout(() => errorDiv.classList.add("hidden"), 10000);
}

function showSuccess(message) {
  const successDiv = document.getElementById("success-message");
  document.getElementById("success-text").textContent = message;
  successDiv.classList.remove("hidden");
  setTimeout(() => successDiv.classList.add("hidden"), 5000);
}

function hideError() {
  document.getElementById("error-message").classList.add("hidden");
}

function updateLastUpdateTime() {
  const now = new Date();
  document.getElementById("last-update-time").textContent = now.toLocaleString("en-US", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

// Fake live ticker - simulates live price updates during market hours (demo only)
// Stores base values to prevent drift from repeated noise application
let fakeLiveTickerEnabled = false;
let fakeLiveTickerInterval = null;
let marketOpen = false;
let liveTickerBaseValues = { cash: 0, holdings: [] };

async function checkMarketStatus() {
  try {
    const response = await fetch("/api/market-status");
    const data = await response.json();
    marketOpen = data.market_open === true;
  } catch (error) {
    marketOpen = false;
  }
}

async function initFakeLiveTicker() {
  try {
    const response = await fetch("/api/settings");
    const settings = await response.json();
    fakeLiveTickerEnabled = settings.fake_live_ticker === true;

    if (fakeLiveTickerEnabled) {
      console.warn("⚠️ FAKE LIVE TICKER ENABLED - Prices shown are NOT real!");
      await checkMarketStatus();
      startFakeLiveTicker();
      setInterval(checkMarketStatus, 5 * 60 * 1000);
    }
  } catch (error) {
    console.error("Error checking fake ticker setting:", error);
  }
}

// Store base values when portfolio loads (called from loadPortfolio)
function storeLiveTickerBaseValues(cash, holdings) {
  liveTickerBaseValues = {
    cash: cash,
    holdings: holdings.map(h => ({ ticker: h.ticker, price: h.price, shares: h.shares }))
  };
}

function startFakeLiveTicker() {
  if (fakeLiveTickerInterval) return;

  fakeLiveTickerInterval = setInterval(() => {
    if (!marketOpen || liveTickerBaseValues.holdings.length === 0) return;

    const table = document.querySelector(".holdings-table tbody");
    if (!table) return;

    // Apply noise to base values (not current DOM values) to prevent drift
    let totalStockValue = 0;
    const rows = table.querySelectorAll("tr");

    liveTickerBaseValues.holdings.forEach((holding, index) => {
      const row = rows[index];
      if (!row) return;

      const noise = (Math.random() - 0.5) * 0.002; // ±0.1%
      const noisedPrice = Math.round(holding.price * (1 + noise) * 100) / 100;
      const noisedValue = noisedPrice * holding.shares;
      totalStockValue += noisedValue;

      const priceCell = row.querySelector("td:nth-child(3)");
      const valueCell = row.querySelector("td:nth-child(4)");

      if (priceCell && valueCell) {
        priceCell.textContent = `$${noisedPrice.toFixed(2)}`;
        valueCell.textContent = `$${noisedValue.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;

        // Flash effect
        priceCell.style.transition = "color 0.3s";
        priceCell.style.color = noise > 0 ? "#22c55e" : "#ef4444";
        setTimeout(() => { priceCell.style.color = ""; }, 500);
      }
    });

    // Update totals
    const totalValue = totalStockValue + liveTickerBaseValues.cash;
    const totalEl = document.getElementById("total-value");
    const stockEl = document.getElementById("stock-value");

    if (totalEl) totalEl.textContent = `$${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (stockEl) stockEl.textContent = `$${totalStockValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    // Update weights
    rows.forEach((row, index) => {
      const valueCell = row.querySelector("td:nth-child(4)");
      const weightCell = row.querySelector("td:nth-child(5)");
      if (valueCell && weightCell && totalValue > 0) {
        const value = parseFloat(valueCell.textContent.replace(/[$,]/g, ""));
        const weight = (value / totalValue) * 100;
        weightCell.textContent = `${weight.toFixed(1)}%`;
      }
    });
  }, 3000);
}

// Initialize fake ticker check after DOM loads
document.addEventListener("DOMContentLoaded", initFakeLiveTicker);
