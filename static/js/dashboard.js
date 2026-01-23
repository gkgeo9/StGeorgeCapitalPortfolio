// dashboard.js
/**
 * Frontend logic for portfolio dashboard
 * Fetches data from API endpoints and renders charts using Plotly
 * Now with MANUAL refresh instead of automatic updates
 */

// Configuration
const CONFIG = {
  LIVE_TICKER_ENABLED: true, // Enable fake real-time price fluctuations
  LIVE_TICKER_INTERVAL: 3000, // Update every 3 seconds
  LIVE_TICKER_NOISE: 0.001, // Max noise: 0.1% of price
  // Premium dark theme chart colors
  CHART_COLORS: [
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#8b5cf6",
    "#ec4899",
    "#14b8a6",
    "#f97316",
  ],
  // Dark theme settings for Plotly
  THEME: {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(13, 20, 33, 0.3)",
    gridcolor: "rgba(30, 58, 95, 0.3)",
    textcolor: "#94a3b8",
    axiscolor: "#64748b",
    font: {
      family: "Inter, -apple-system, sans-serif",
      color: "#94a3b8",
    },
  },
};

// Timeline chart state
let timelineData = null; // Cache fetched data for mode switching
let chartMode = "absolute"; // 'absolute' or 'percentage'
let showBenchmark = true;

// Stock prices chart state
let stockPricesData = null; // Cache fetched data for mode switching
let stockChartMode = "absolute"; // 'absolute' or 'percentage'

// Market status (from server - used for live ticker)
let isMarketCurrentlyOpen = false; // Cached from /api/provider-status

/**
 * Theme Management
 */
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
  const currentTheme = getTheme();
  const newTheme = currentTheme === "dark" ? "light" : "dark";
  setTheme(newTheme);
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("theme-icon");
  if (icon) {
    icon.innerHTML = theme === "dark" ? "&#9790;" : "&#9728;"; // Moon or Sun
  }
}

function loadSavedTheme() {
  const savedTheme = localStorage.getItem("theme") || "dark";
  setTheme(savedTheme);
}

function getChartTheme() {
  const theme = getTheme();
  if (theme === "light") {
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
  // Re-render KPI cards with new theme colors
  loadPerformance().catch(() => {}); // Re-render KPIs silently

  // Re-render charts with new theme if they exist
  const pieChart = document.getElementById("pie-chart");
  const timelineChart = document.getElementById("timeline-chart");
  const stockChart = document.getElementById("stock-prices-chart");

  if (pieChart && pieChart.data) {
    Plotly.relayout("pie-chart", {
      paper_bgcolor: getChartTheme().paper_bgcolor,
      plot_bgcolor: getChartTheme().plot_bgcolor,
    });
  }

  if (timelineChart && timelineChart.data) {
    Plotly.relayout("timeline-chart", {
      paper_bgcolor: getChartTheme().paper_bgcolor,
      plot_bgcolor: getChartTheme().plot_bgcolor,
      "xaxis.gridcolor": getChartTheme().gridcolor,
      "yaxis.gridcolor": getChartTheme().gridcolor,
      "xaxis.tickfont.color": getChartTheme().axiscolor,
      "yaxis.tickfont.color": getChartTheme().axiscolor,
    });
  }

  if (stockChart && stockChart.data) {
    Plotly.relayout("stock-prices-chart", {
      paper_bgcolor: getChartTheme().paper_bgcolor,
      plot_bgcolor: getChartTheme().plot_bgcolor,
      "xaxis.gridcolor": getChartTheme().gridcolor,
      "yaxis.gridcolor": getChartTheme().gridcolor,
      "xaxis.tickfont.color": getChartTheme().axiscolor,
      "yaxis.tickfont.color": getChartTheme().axiscolor,
      "legend.font.color": getChartTheme().textcolor,
    });
  }
}

// Live ticker state - stores base values for noise calculation
let liveTickerBaseValues = {};
let liveTickerInterval = null;

/**
 * Initialize dashboard on page load
 */
document.addEventListener("DOMContentLoaded", function () {
  console.log("Dashboard initializing...");

  // Load saved theme preference
  loadSavedTheme();

  loadAllData();

  // Start live ticker effect for "real-time" feel
  if (CONFIG.LIVE_TICKER_ENABLED) {
    startLiveTicker();
  }

  // Refresh market status every 5 minutes to detect market open/close
  const quotaInterval = setInterval(loadQuotaStatus, 5 * 60 * 1000);

  // Clean up intervals on page unload to prevent memory leaks
  window.addEventListener("beforeunload", function () {
    if (liveTickerInterval) {
      clearInterval(liveTickerInterval);
    }
    clearInterval(quotaInterval);
  });
});

/**
 * Load all dashboard data
 */
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
    showLoading(false);
  } catch (error) {
    console.error("Error loading dashboard data:", error);
    showError("Failed to load dashboard data. Please refresh the page.");
    showLoading(false);
  }
}

/**
 * Load API quota status (no API call to Alpha Vantage - just internal status)
 */
async function loadQuotaStatus() {
  try {
    const response = await fetch("/api/provider-status");
    const data = await response.json();

    // Cache market status for live ticker (server-side, not client time)
    isMarketCurrentlyOpen = data.market_open === true;

    const quotaEl = document.getElementById("quota-status");
    if (quotaEl && data.quota) {
      const remaining = data.quota.daily_remaining;
      const limit = data.quota.daily_limit;
      if (remaining === "unlimited") {
        quotaEl.textContent = "API: Paid tier (unlimited)";
        quotaEl.style.color = "#22c55e";
      } else {
        const pct = (remaining / limit) * 100;
        quotaEl.textContent = `API: ${remaining}/${limit} calls remaining`;
        quotaEl.style.color =
          pct < 20 ? "#ef4444" : pct < 50 ? "#f59e0b" : "#64748b";
      }
    } else if (quotaEl) {
      quotaEl.textContent = "";
    }
  } catch (error) {
    console.error("Error loading quota status:", error);
    // Don't throw - quota display is optional
  }
}

/**
 * Load portfolio data
 */
async function loadPortfolio() {
  try {
    const response = await fetch("/api/portfolio");
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    updatePortfolioStats(data);
    renderPieChart(data.holdings, data.cash);
    renderHoldingsTable(data.holdings);

    // Store base values for live ticker noise effect
    if (CONFIG.LIVE_TICKER_ENABLED) {
      storeLiveTickerBaseValues(data, data.holdings);
    }
  } catch (error) {
    console.error("Error loading portfolio:", error);
    throw error;
  }
}

/**
 * Load portfolio timeline data with S&P 500 benchmark
 */
async function loadTimeline() {
  try {
    const response = await fetch(
      "/api/timeline?days=90&include_benchmark=true",
    );
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    // Cache the data for mode switching
    timelineData = data;

    // Render based on current mode
    renderTimelineChart();
  } catch (error) {
    console.error("Error loading timeline:", error);
    throw error;
  }
}

/**
 * Toggle between absolute ($) and percentage (%) view
 */
function toggleChartMode() {
  chartMode = chartMode === "absolute" ? "percentage" : "absolute";

  // Update button text
  const modeIcon = document.getElementById("mode-icon");
  const modeText = document.getElementById("mode-text");

  if (chartMode === "absolute") {
    modeIcon.textContent = "$";
    modeText.textContent = "Show %";
  } else {
    modeIcon.textContent = "%";
    modeText.textContent = "Show $";
  }

  // Re-render chart with new mode
  if (timelineData) {
    renderTimelineChart();
  }
}

/**
 * Toggle S&P 500 benchmark visibility
 */
function toggleBenchmark() {
  showBenchmark = document.getElementById("show-benchmark").checked;

  if (timelineData) {
    renderTimelineChart();
  }
}

/**
 * Load stock prices
 */
async function loadStockPrices() {
  try {
    const response = await fetch("/api/stocks?days=90");
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    // Cache the data for mode switching
    stockPricesData = data;

    // Render based on current mode
    renderStockPricesChart();
  } catch (error) {
    console.error("Error loading stock prices:", error);
    throw error;
  }
}

/**
 * Toggle between absolute ($) and percentage (%) view for stock prices
 */
function toggleStockChartMode() {
  stockChartMode = stockChartMode === "absolute" ? "percentage" : "absolute";

  // Update button text
  const modeIcon = document.getElementById("stock-mode-icon");
  const modeText = document.getElementById("stock-mode-text");

  if (stockChartMode === "absolute") {
    modeIcon.textContent = "$";
    modeText.textContent = "Show %";
  } else {
    modeIcon.textContent = "%";
    modeText.textContent = "Show $";
  }

  // Re-render chart with new mode
  if (stockPricesData) {
    renderStockPricesChart();
  }
}

/**
 * Load recent trades
 */
async function loadTrades() {
  try {
    const response = await fetch("/api/trades?limit=10");
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    renderRecentTrades(data.trades);
  } catch (error) {
    console.error("Error loading trades:", error);
    throw error;
  }
}

/**
 * Load performance metrics
 */
async function loadPerformance() {
  try {
    const response = await fetch("/api/performance");
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error);
    }

    renderKPICards(data);
  } catch (error) {
    console.error("Error loading performance:", error);
    throw error;
  }
}

/**
 * Update portfolio statistics display
 */
function updatePortfolioStats(data) {
  document.getElementById("total-value").textContent =
    `$${data.total_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("cash-value").textContent =
    `$${data.cash.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById("stock-value").textContent =
    `$${data.stock_value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Render KPI cards
 */
function renderKPICards(data) {
  const container = document.getElementById("kpi-container");
  const isPositive = data.total_return >= 0;
  const pnlColor = isPositive ? "#22c55e" : "#ef4444";
  // Use theme-aware default color for neutral KPIs
  const defaultColor = getTheme() === "dark" ? "#f8fafc" : "#1e3a5f";

  // Sharpe ratio color: green if good (>1), yellow if ok (0-1), red if negative
  const sharpeColor = data.sharpe_ratio >= 1 ? "#22c55e" : data.sharpe_ratio >= 0 ? "#f59e0b" : "#ef4444";

  const cards = [
    {
      value: `${isPositive ? "+" : ""}${data.total_return}%`,
      label: "Total Return",
      color: pnlColor,
      className: isPositive ? "positive" : "negative",
    },
    {
      value: data.sharpe_ratio.toFixed(2),
      label: "Sharpe Ratio",
      color: sharpeColor,
      className: "",
    },
    {
      value: `${data.volatility.toFixed(1)}%`,
      label: "Volatility",
      color: defaultColor,
      className: "",
    },
    {
      value: data.total_trades.toString(),
      label: "Total Trades",
      color: defaultColor,
      className: "",
    },
  ];

  container.innerHTML = cards
    .map(
      (card) => `
        <div class="kpi-card ${card.className}">
            <div class="kpi-value" style="color: ${card.color}">${card.value}</div>
            <div class="kpi-label">${card.label}</div>
        </div>
    `,
    )
    .join("");
}

/**
 * Render portfolio pie chart
 */
function renderPieChart(holdings, cash) {
  const labels = holdings.map((h) => h.ticker);
  const values = holdings.map((h) => h.value);

  if (cash > 0) {
    labels.push("Cash");
    values.push(cash);
  }

  const data = [
    {
      type: "pie",
      labels: labels,
      values: values,
      marker: {
        colors: CONFIG.CHART_COLORS,
        line: {
          color: "#0d1421",
          width: 2,
        },
      },
      textinfo: "label+percent",
      textfont: {
        family: "JetBrains Mono, monospace",
        size: 12,
        color: "#f8fafc",
      },
      hole: 0.45,
      hovertemplate:
        "<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>",
    },
  ];

  const layout = {
    height: 400,
    showlegend: true,
    legend: {
      orientation: "v",
      yanchor: "middle",
      y: 0.5,
      xanchor: "left",
      x: 1.05,
      font: {
        family: "Inter, sans-serif",
        size: 12,
        color: getChartTheme().textcolor,
      },
    },
    paper_bgcolor: getChartTheme().paper_bgcolor,
    plot_bgcolor: getChartTheme().plot_bgcolor,
    margin: { t: 20, b: 20, l: 20, r: 120 },
  };

  Plotly.newPlot("pie-chart", data, layout, {
    responsive: true,
    displayModeBar: false,
  });
}

/**
 * Render holdings table
 */
function renderHoldingsTable(holdings) {
  const container = document.getElementById("holdings-table-container");

  if (holdings.length === 0) {
    container.innerHTML = '<p class="no-data">No current holdings</p>';
    return;
  }

  const tableHTML = `
        <table class="holdings-table">
            <thead>
                <tr>
                    <th>Stock</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>Weight</th>
                </tr>
            </thead>
            <tbody>
                ${holdings
                  .map(
                    (h) => `
                    <tr>
                        <td class="stock-ticker">${h.ticker}</td>
                        <td>${h.shares}</td>
                        <td>$${h.price.toFixed(2)}</td>
                        <td>$${h.value.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                        <td>${h.weight.toFixed(1)}%</td>
                    </tr>
                `,
                  )
                  .join("")}
            </tbody>
        </table>
    `;

  container.innerHTML = tableHTML;
}

/**
 * Render recent trades
 */
function renderRecentTrades(trades) {
  const container = document.getElementById("recent-trades-container");

  if (trades.length === 0) {
    container.innerHTML = '<p class="no-data">No recent trades</p>';
    return;
  }

  const tradesHTML = trades
    .slice(0, 5)
    .map((trade) => {
      const date = new Date(trade.timestamp);
      const timeStr =
        date.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" }) +
        " " +
        date.toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        });

      const actionClass = trade.action === "BUY" ? "buy" : "sell";
      const actionColor = trade.action === "BUY" ? "#22c55e" : "#ef4444";

      return `
            <div class="trade-item ${actionClass}">
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
    })
    .join("");

  container.innerHTML = tradesHTML;
}

/**
 * Render portfolio timeline chart with optional S&P 500 comparison
 */
function renderTimelineChart() {
  if (!timelineData || !timelineData.dates || timelineData.dates.length === 0) {
    document.getElementById("timeline-chart").innerHTML =
      '<p class="no-data">No timeline data available</p>';
    return;
  }

  const dates = timelineData.dates;
  const traces = [];

  // Determine which values to use based on mode
  const isPercentage = chartMode === "percentage";

  // Portfolio trace
  const portfolioValues = isPercentage
    ? timelineData.portfolio_pct
    : timelineData.values;
  const portfolioColor = "#3b82f6"; // Blue

  traces.push({
    type: "scatter",
    mode: "lines",
    x: dates,
    y: portfolioValues,
    name: "Portfolio",
    line: {
      color: portfolioColor,
      width: 3,
      shape: "spline",
    },
    fill: showBenchmark ? "none" : "tozeroy",
    fillcolor: showBenchmark ? undefined : "rgba(59, 130, 246, 0.1)",
    hovertemplate: isPercentage
      ? "<b>Portfolio</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>"
      : "<b>Portfolio</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
  });

  // S&P 500 (SPY) trace - only if benchmark is enabled and data exists
  if (
    showBenchmark &&
    timelineData.benchmark_pct &&
    timelineData.benchmark_values
  ) {
    const benchmarkValues = isPercentage
      ? timelineData.benchmark_pct
      : timelineData.benchmark_values;

    // Filter out null values by creating clean arrays
    const cleanDates = [];
    const cleanValues = [];
    for (let i = 0; i < benchmarkValues.length; i++) {
      if (benchmarkValues[i] !== null) {
        cleanDates.push(dates[i]);
        cleanValues.push(benchmarkValues[i]);
      }
    }

    if (cleanValues.length > 0) {
      const benchmarkColor = "#f59e0b"; // Amber/Gold

      traces.push({
        type: "scatter",
        mode: "lines",
        x: cleanDates,
        y: cleanValues,
        name: "S&P 500 (SPY)",
        line: {
          color: benchmarkColor,
          width: 2,
          dash: "dot",
        },
        hovertemplate: isPercentage
          ? "<b>S&P 500</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>"
          : "<b>S&P 500</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
      });
    }
  }

  // Build layout
  const yAxisTitle = isPercentage ? "Change (%)" : "Portfolio Value ($)";
  const tickFormat = isPercentage ? "+.1f" : "$,.0f";

  const layout = {
    height: 400,
    showlegend: showBenchmark,
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
      font: {
        family: "Inter, sans-serif",
        size: 12,
        color: getChartTheme().textcolor,
      },
    },
    xaxis: {
      title: {
        text: "Date",
        font: { color: "#64748b", size: 12, family: "Inter, sans-serif" },
      },
      gridcolor: getChartTheme().gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickfont: {
        color: getChartTheme().axiscolor,
        size: 11,
        family: "Inter, sans-serif",
      },
    },
    yaxis: {
      title: {
        text: yAxisTitle,
        font: {
          color: getChartTheme().axiscolor,
          size: 12,
          family: "Inter, sans-serif",
        },
      },
      gridcolor: getChartTheme().gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickformat: tickFormat,
      tickfont: {
        color: getChartTheme().axiscolor,
        size: 11,
        family: "JetBrains Mono, monospace",
      },
    },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: getTheme() === "dark" ? "#111827" : "#ffffff",
      bordercolor: "#1e3a5f",
      font: {
        family: "JetBrains Mono, monospace",
        color: getTheme() === "dark" ? "#f8fafc" : "#0f172a",
      },
    },
    paper_bgcolor: getChartTheme().paper_bgcolor,
    plot_bgcolor: getChartTheme().plot_bgcolor,
    margin: { t: 40, b: 60, l: 70, r: 20 },
    shapes: [],
    annotations: [],
  };

  // Add reference line based on mode
  if (isPercentage) {
    // Add 0% reference line in percentage mode
    layout.shapes.push({
      type: "line",
      x0: dates[0],
      x1: dates[dates.length - 1],
      y0: 0,
      y1: 0,
      line: {
        color: "rgba(148, 163, 184, 0.5)",
        width: 1,
        dash: "dash",
      },
    });
  } else {
    // Add initial value reference line ($100k) in absolute mode
    const initialValue = timelineData.values[0] || 100000;
    layout.shapes.push({
      type: "line",
      x0: dates[0],
      x1: dates[dates.length - 1],
      y0: initialValue,
      y1: initialValue,
      line: {
        color: "rgba(239, 68, 68, 0.5)",
        width: 2,
        dash: "dash",
      },
    });
    layout.annotations.push({
      x: dates[dates.length - 1],
      y: initialValue,
      text: "Initial Value",
      showarrow: false,
      xanchor: "left",
      font: {
        size: 10,
        color: "#ef4444",
        family: "Inter, sans-serif",
      },
    });
  }

  Plotly.newPlot("timeline-chart", traces, layout, {
    responsive: true,
    displayModeBar: false,
  });
}

/**
 * Render stock prices chart with optional percentage mode
 */
function renderStockPricesChart() {
  if (!stockPricesData) {
    document.getElementById("stock-prices-chart").innerHTML =
      '<p class="no-data">No price data available</p>';
    return;
  }

  const traces = [];
  const tickers = Object.keys(stockPricesData);

  if (tickers.length === 0) {
    document.getElementById("stock-prices-chart").innerHTML =
      '<p class="no-data">No price data available</p>';
    return;
  }

  const isPercentage = stockChartMode === "percentage";

  tickers.forEach((ticker, index) => {
    const data = stockPricesData[ticker];

    if (data.timestamps.length > 0) {
      let yValues = data.prices;
      let hoverTemplate =
        "<b>%{fullData.name}</b><br>%{x|%b %d, %Y}<br>$%{y:.2f}<extra></extra>";

      // Calculate percentage change from first value if in percentage mode
      if (isPercentage) {
        const initialPrice = data.prices[0];
        yValues = data.prices.map((price) => {
          if (initialPrice > 0) {
            return ((price / initialPrice - 1) * 100).toFixed(2);
          }
          return 0;
        });
        hoverTemplate =
          "<b>%{fullData.name}</b><br>%{x|%b %d, %Y}<br>%{y:+.2f}%<extra></extra>";
      }

      traces.push({
        type: "scatter",
        mode: "lines",
        name: ticker,
        x: data.timestamps,
        y: yValues,
        line: {
          color: CONFIG.CHART_COLORS[index % CONFIG.CHART_COLORS.length],
          width: 2.5,
        },
        hovertemplate: hoverTemplate,
      });
    }
  });

  // Build layout
  const yAxisTitle = isPercentage ? "Change (%)" : "Stock Price ($)";
  const tickFormat = isPercentage ? "+.1f" : "$,.2f";

  const layout = {
    height: 400,
    xaxis: {
      title: {
        text: "Date",
        font: { color: "#64748b", size: 12, family: "Inter, sans-serif" },
      },
      gridcolor: getChartTheme().gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickfont: {
        color: getChartTheme().axiscolor,
        size: 11,
        family: "Inter, sans-serif",
      },
    },
    yaxis: {
      title: {
        text: yAxisTitle,
        font: {
          color: getChartTheme().axiscolor,
          size: 12,
          family: "Inter, sans-serif",
        },
      },
      gridcolor: getChartTheme().gridcolor,
      linecolor: "rgba(30, 58, 95, 0.4)",
      tickformat: tickFormat,
      tickfont: {
        color: getChartTheme().axiscolor,
        size: 11,
        family: "JetBrains Mono, monospace",
      },
    },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: getTheme() === "dark" ? "#111827" : "#ffffff",
      bordercolor: "#1e3a5f",
      font: {
        family: "JetBrains Mono, monospace",
        color: getTheme() === "dark" ? "#f8fafc" : "#0f172a",
      },
    },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
      font: {
        family: "Inter, sans-serif",
        size: 12,
        color: getChartTheme().textcolor,
      },
    },
    paper_bgcolor: getChartTheme().paper_bgcolor,
    plot_bgcolor: getChartTheme().plot_bgcolor,
    margin: { t: 40, b: 60, l: 70, r: 20 },
    shapes: [],
    annotations: [],
  };

  // Add 0% reference line in percentage mode
  if (isPercentage && traces.length > 0 && traces[0].x.length > 0) {
    layout.shapes.push({
      type: "line",
      x0: traces[0].x[0],
      x1: traces[0].x[traces[0].x.length - 1],
      y0: 0,
      y1: 0,
      line: {
        color: "rgba(148, 163, 184, 0.5)",
        width: 1,
        dash: "dash",
      },
    });
  }

  Plotly.newPlot("stock-prices-chart", traces, layout, {
    responsive: true,
    displayModeBar: false,
  });
}

/**
 * Show/hide loading indicator (small spinner next to quota status)
 */
function showLoading(show) {
  const spinner = document.getElementById("loading-spinner");
  if (spinner) {
    spinner.style.display = show ? "inline-block" : "none";
  }
}

/**
 * Show error message
 */
function showError(message) {
  const errorDiv = document.getElementById("error-message");
  const errorText = document.getElementById("error-text");

  errorText.textContent = message;
  errorDiv.style.display = "flex";

  // Auto-hide after 10 seconds
  setTimeout(() => {
    errorDiv.style.display = "none";
  }, 10000);
}

/**
 * Show success message
 */
function showSuccess(message) {
  const successDiv = document.getElementById("success-message");
  const successText = document.getElementById("success-text");

  successText.textContent = message;
  successDiv.style.display = "flex";

  setTimeout(() => {
    successDiv.style.display = "none";
  }, 5000);
}

/**
 * Hide error message
 */
function hideError() {
  const errorDiv = document.getElementById("error-message");
  errorDiv.style.display = "none";
}

/**
 * Update last update time
 */
function updateLastUpdateTime() {
  const now = new Date();
  const timeString = now.toLocaleString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  document.getElementById("last-update-time").textContent = timeString;
}

/**
 * Live Ticker Effect - adds coherent random noise to values for "real-time" feel
 *
 * The noise is applied consistently:
 * 1. Each stock gets a random price multiplier (e.g., 1.001 = +0.1%)
 * 2. Holding value = price * shares (calculated, not random)
 * 3. Total stock value = sum of all holding values
 * 4. Total portfolio value = stock value + cash
 */
function startLiveTicker() {
  console.log("Starting live ticker effect...");

  liveTickerInterval = setInterval(() => {
    applyCoherentNoise();
  }, CONFIG.LIVE_TICKER_INTERVAL);
}

function applyCoherentNoise() {
  // Only apply noise during market hours (from server, not client time)
  if (!isMarketCurrentlyOpen) {
    return;
  }

  if (!liveTickerBaseValues.holdings || liveTickerBaseValues.holdings.length === 0) {
    return;
  }

  // Step 1: Generate a noise multiplier for each stock (e.g., 0.999 to 1.001)
  // Round to cents for realistic stock price granularity (no sub-cent prices)
  const noisedHoldings = liveTickerBaseValues.holdings.map(holding => {
    const noiseMultiplier = 1 + (Math.random() - 0.5) * 2 * CONFIG.LIVE_TICKER_NOISE;
    const noisedPrice = Math.round(holding.price * noiseMultiplier * 100) / 100;
    const noisedValue = noisedPrice * holding.shares;
    return {
      price: noisedPrice,
      value: noisedValue,
      shares: holding.shares
    };
  });

  // Step 2: Calculate total stock value from noised holdings
  const noisedStockValue = noisedHoldings.reduce((sum, h) => sum + h.value, 0);

  // Step 3: Total portfolio = stock value + cash (cash doesn't fluctuate)
  const noisedTotalValue = noisedStockValue + liveTickerBaseValues.cash;

  // Step 4: Update the DOM
  const totalValueEl = document.getElementById("total-value");
  if (totalValueEl) {
    totalValueEl.textContent = formatCurrency(noisedTotalValue);
  }

  const stockValueEl = document.getElementById("stock-value");
  if (stockValueEl) {
    stockValueEl.textContent = formatCurrency(noisedStockValue);
  }

  // Update holdings table
  const holdingsTable = document.querySelector(".holdings-table tbody");
  if (holdingsTable) {
    const rows = holdingsTable.querySelectorAll("tr");
    rows.forEach((row, index) => {
      const holding = noisedHoldings[index];
      if (holding) {
        const priceCell = row.querySelector("td:nth-child(3)");
        const valueCell = row.querySelector("td:nth-child(4)");
        if (priceCell) {
          priceCell.textContent = formatCurrency(holding.price);
        }
        if (valueCell) {
          valueCell.textContent = formatCurrency(holding.value);
        }
      }
    });
  }
}

function formatCurrency(value) {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function storeLiveTickerBaseValues(portfolioData, holdingsData) {
  liveTickerBaseValues = {
    cash: portfolioData.cash,
    holdings: holdingsData ? holdingsData.map(h => ({
      price: h.price,
      value: h.value,
      shares: h.shares
    })) : []
  };
}
