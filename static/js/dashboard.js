// dashboard.js
/**
 * Frontend logic for portfolio dashboard
 * Fetches data from API endpoints and renders charts using Plotly
 * Now with MANUAL refresh instead of automatic updates
 */

// Configuration
const CONFIG = {
    AUTO_REFRESH: false,  // DISABLED automatic refresh
    // Premium dark theme chart colors
    CHART_COLORS: ['#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'],
    // Dark theme settings for Plotly
    THEME: {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(13, 20, 33, 0.3)',
        gridcolor: 'rgba(30, 58, 95, 0.3)',
        textcolor: '#94a3b8',
        axiscolor: '#64748b',
        font: {
            family: 'Inter, -apple-system, sans-serif',
            color: '#94a3b8'
        }
    }
};

// State
let isRefreshing = false;

/**
 * Initialize dashboard on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard initializing...');

    loadAllData();

    // No automatic refresh interval - all updates are manual now
    console.log('Manual refresh mode enabled - use refresh button to update data');
});

/**
 * Manual refresh button handler
 */
async function refreshData() {
    if (isRefreshing) {
        showError('Refresh already in progress...');
        return;
    }

    isRefreshing = true;
    showLoading(true);
    hideError();

    try {
        // Call the manual refresh API endpoint
        const response = await fetch('/api/refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (!response.ok) {
            if (response.status === 429) {
                // Cooldown active
                showError(data.message);
            } else {
                throw new Error(data.error || 'Refresh failed');
            }
        } else {
            // Success - reload all dashboard data
            await loadAllData();
            showSuccess(data.message || '✓ Data refreshed successfully');
        }

    } catch (error) {
        console.error('Error during refresh:', error);
        showError('Failed to refresh data: ' + error.message);
    } finally {
        isRefreshing = false;
        showLoading(false);
    }
}

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
            loadQuotaStatus()
        ]);

        updateLastUpdateTime();
        showLoading(false);

    } catch (error) {
        console.error('Error loading dashboard data:', error);
        showError('Failed to load dashboard data. Please refresh the page.');
        showLoading(false);
    }
}

/**
 * Load API quota status (no API call to Alpha Vantage - just internal status)
 */
async function loadQuotaStatus() {
    try {
        const response = await fetch('/api/provider-status');
        const data = await response.json();

        const quotaEl = document.getElementById('quota-status');
        if (quotaEl && data.quota) {
            const remaining = data.quota.daily_remaining;
            const limit = data.quota.daily_limit;
            if (remaining === 'unlimited') {
                quotaEl.textContent = 'API: Paid tier (unlimited)';
                quotaEl.style.color = '#22c55e';
            } else {
                const pct = (remaining / limit) * 100;
                quotaEl.textContent = `API: ${remaining}/${limit} calls remaining`;
                quotaEl.style.color = pct < 20 ? '#ef4444' : pct < 50 ? '#f59e0b' : '#64748b';
            }
        } else if (quotaEl) {
            quotaEl.textContent = '';
        }
    } catch (error) {
        console.error('Error loading quota status:', error);
        // Don't throw - quota display is optional
    }
}

/**
 * Load portfolio data
 */
async function loadPortfolio() {
    try {
        const response = await fetch('/api/portfolio');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        updatePortfolioStats(data);
        renderPieChart(data.holdings, data.cash);
        renderHoldingsTable(data.holdings);

    } catch (error) {
        console.error('Error loading portfolio:', error);
        throw error;
    }
}

/**
 * Load portfolio timeline data
 */
async function loadTimeline() {
    try {
        const response = await fetch('/api/timeline?days=90');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderTimelineChart(data.dates, data.values);

    } catch (error) {
        console.error('Error loading timeline:', error);
        throw error;
    }
}

/**
 * Load stock prices
 */
async function loadStockPrices() {
    try {
        const response = await fetch('/api/stocks?days=90');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderStockPricesChart(data);

    } catch (error) {
        console.error('Error loading stock prices:', error);
        throw error;
    }
}

/**
 * Load recent trades
 */
async function loadTrades() {
    try {
        const response = await fetch('/api/trades?limit=10');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderRecentTrades(data.trades);

    } catch (error) {
        console.error('Error loading trades:', error);
        throw error;
    }
}

/**
 * Load performance metrics
 */
async function loadPerformance() {
    try {
        const response = await fetch('/api/performance');
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderKPICards(data);

    } catch (error) {
        console.error('Error loading performance:', error);
        throw error;
    }
}

/**
 * Update portfolio statistics display
 */
function updatePortfolioStats(data) {
    document.getElementById('total-value').textContent = `$${data.total_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById('cash-value').textContent = `$${data.cash.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById('stock-value').textContent = `$${data.stock_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

/**
 * Render KPI cards
 */
function renderKPICards(data) {
    const container = document.getElementById('kpi-container');
    const isPositive = data.total_return >= 0;
    const pnlColor = isPositive ? '#22c55e' : '#ef4444';

    const cards = [
        {
            value: `${isPositive ? '+' : ''}${data.total_return}%`,
            label: 'Total Return',
            color: pnlColor,
            className: isPositive ? 'positive' : 'negative'
        },
        {
            value: `${data.win_rate.toFixed(1)}%`,
            label: 'Win Rate',
            color: '#f8fafc',
            className: ''
        },
        {
            value: `${data.volatility.toFixed(1)}%`,
            label: 'Volatility',
            color: '#f8fafc',
            className: ''
        },
        {
            value: `${data.max_drawdown.toFixed(1)}%`,
            label: 'Max Drawdown',
            color: '#f59e0b',
            className: ''
        },
        {
            value: data.total_trades.toString(),
            label: 'Total Trades',
            color: '#f8fafc',
            className: ''
        }
    ];

    container.innerHTML = cards.map(card => `
        <div class="kpi-card ${card.className}">
            <div class="kpi-value" style="color: ${card.color}">${card.value}</div>
            <div class="kpi-label">${card.label}</div>
        </div>
    `).join('');
}

/**
 * Render portfolio pie chart
 */
function renderPieChart(holdings, cash) {
    const labels = holdings.map(h => h.ticker);
    const values = holdings.map(h => h.value);

    if (cash > 0) {
        labels.push('Cash');
        values.push(cash);
    }

    const data = [{
        type: 'pie',
        labels: labels,
        values: values,
        marker: {
            colors: CONFIG.CHART_COLORS,
            line: {
                color: '#0d1421',
                width: 2
            }
        },
        textinfo: 'label+percent',
        textfont: {
            family: 'JetBrains Mono, monospace',
            size: 12,
            color: '#f8fafc'
        },
        hole: 0.45,
        hovertemplate: '<b>%{label}</b><br>$%{value:,.2f}<br>%{percent}<extra></extra>'
    }];

    const layout = {
        height: 400,
        showlegend: true,
        legend: {
            orientation: 'v',
            yanchor: 'middle',
            y: 0.5,
            xanchor: 'left',
            x: 1.05,
            font: {
                family: 'Inter, sans-serif',
                size: 12,
                color: '#94a3b8'
            }
        },
        paper_bgcolor: CONFIG.THEME.paper_bgcolor,
        plot_bgcolor: CONFIG.THEME.plot_bgcolor,
        margin: { t: 20, b: 20, l: 20, r: 120 }
    };

    Plotly.newPlot('pie-chart', data, layout, {
        responsive: true,
        displayModeBar: false
    });
}

/**
 * Render holdings table
 */
function renderHoldingsTable(holdings) {
    const container = document.getElementById('holdings-table-container');

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
                ${holdings.map(h => `
                    <tr>
                        <td class="stock-ticker">${h.ticker}</td>
                        <td>${h.shares}</td>
                        <td>$${h.price.toFixed(2)}</td>
                        <td>$${h.value.toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                        <td>${h.weight.toFixed(1)}%</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

    container.innerHTML = tableHTML;
}

/**
 * Render recent trades
 */
function renderRecentTrades(trades) {
    const container = document.getElementById('recent-trades-container');

    if (trades.length === 0) {
        container.innerHTML = '<p class="no-data">No recent trades</p>';
        return;
    }

    const tradesHTML = trades.slice(0, 5).map((trade) => {
        const date = new Date(trade.timestamp);
        const timeStr = date.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' }) + ' ' +
                       date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });

        const actionClass = trade.action === 'BUY' ? 'buy' : 'sell';
        const actionColor = trade.action === 'BUY' ? '#22c55e' : '#ef4444';

        return `
            <div class="trade-item ${actionClass}">
                <div class="trade-header">
                    <span class="trade-time">${timeStr}</span>
                    <span class="trade-stock">${trade.ticker}</span>
                    <span style="color: ${actionColor}; font-weight: 600; margin-left: auto; font-family: 'Inter', sans-serif; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">${trade.action}</span>
                </div>
                <div class="trade-details">
                    ${trade.quantity} shares @ $${trade.price.toFixed(2)} = $${trade.total_cost.toLocaleString('en-US', {minimumFractionDigits: 2})}
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = tradesHTML;
}

/**
 * Render portfolio timeline chart
 */
function renderTimelineChart(dates, values) {
    if (dates.length === 0) {
        document.getElementById('timeline-chart').innerHTML = '<p class="no-data">No timeline data available</p>';
        return;
    }

    const colors = values.map(v => v >= 100000 ? '#22c55e' : '#ef4444');

    const data = [{
        type: 'scatter',
        mode: 'lines+markers',
        x: dates,
        y: values,
        name: 'Portfolio Value',
        line: {
            color: '#3b82f6',
            width: 3,
            shape: 'spline'
        },
        marker: {
            size: 6,
            color: colors,
            line: {
                color: '#0d1421',
                width: 2
            }
        },
        fill: 'tozeroy',
        fillcolor: 'rgba(59, 130, 246, 0.1)',
        hovertemplate: '<b>%{x}</b><br>$%{y:,.2f}<extra></extra>'
    }];

    const layout = {
        height: 400,
        xaxis: {
            title: {
                text: 'Date',
                font: { color: '#64748b', size: 12, family: 'Inter, sans-serif' }
            },
            gridcolor: CONFIG.THEME.gridcolor,
            linecolor: 'rgba(30, 58, 95, 0.4)',
            tickfont: { color: '#64748b', size: 11, family: 'Inter, sans-serif' }
        },
        yaxis: {
            title: {
                text: 'Portfolio Value ($)',
                font: { color: '#64748b', size: 12, family: 'Inter, sans-serif' }
            },
            gridcolor: CONFIG.THEME.gridcolor,
            linecolor: 'rgba(30, 58, 95, 0.4)',
            tickformat: '$,.0f',
            tickfont: { color: '#64748b', size: 11, family: 'JetBrains Mono, monospace' }
        },
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#111827',
            bordercolor: '#1e3a5f',
            font: { family: 'JetBrains Mono, monospace', color: '#f8fafc' }
        },
        paper_bgcolor: CONFIG.THEME.paper_bgcolor,
        plot_bgcolor: CONFIG.THEME.plot_bgcolor,
        margin: { t: 20, b: 60, l: 70, r: 20 },
        shapes: [{
            type: 'line',
            x0: dates[0],
            x1: dates[dates.length - 1],
            y0: 100000,
            y1: 100000,
            line: {
                color: 'rgba(239, 68, 68, 0.5)',
                width: 2,
                dash: 'dash'
            }
        }],
        annotations: [{
            x: dates[dates.length - 1],
            y: 100000,
            text: 'Initial Value',
            showarrow: false,
            xanchor: 'left',
            font: {
                size: 10,
                color: '#ef4444',
                family: 'Inter, sans-serif'
            }
        }]
    };

    Plotly.newPlot('timeline-chart', data, layout, {
        responsive: true,
        displayModeBar: false
    });
}

/**
 * Render stock prices chart
 */
function renderStockPricesChart(stocksData) {
    const traces = [];
    const tickers = Object.keys(stocksData);

    if (tickers.length === 0) {
        document.getElementById('stock-prices-chart').innerHTML = '<p class="no-data">No price data available</p>';
        return;
    }

    tickers.forEach((ticker, index) => {
        const data = stocksData[ticker];

        if (data.timestamps.length > 0) {
            traces.push({
                type: 'scatter',
                mode: 'lines',
                name: ticker,
                x: data.timestamps,
                y: data.prices,
                line: {
                    color: CONFIG.CHART_COLORS[index % CONFIG.CHART_COLORS.length],
                    width: 2.5
                },
                hovertemplate: '<b>%{fullData.name}</b><br>$%{y:.2f}<extra></extra>'
            });
        }
    });

    const layout = {
        height: 400,
        xaxis: {
            title: {
                text: 'Date',
                font: { color: '#64748b', size: 12, family: 'Inter, sans-serif' }
            },
            gridcolor: CONFIG.THEME.gridcolor,
            linecolor: 'rgba(30, 58, 95, 0.4)',
            tickfont: { color: '#64748b', size: 11, family: 'Inter, sans-serif' }
        },
        yaxis: {
            title: {
                text: 'Stock Price ($)',
                font: { color: '#64748b', size: 12, family: 'Inter, sans-serif' }
            },
            gridcolor: CONFIG.THEME.gridcolor,
            linecolor: 'rgba(30, 58, 95, 0.4)',
            tickformat: '$,.2f',
            tickfont: { color: '#64748b', size: 11, family: 'JetBrains Mono, monospace' }
        },
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#111827',
            bordercolor: '#1e3a5f',
            font: { family: 'JetBrains Mono, monospace', color: '#f8fafc' }
        },
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {
                family: 'Inter, sans-serif',
                size: 12,
                color: '#94a3b8'
            }
        },
        paper_bgcolor: CONFIG.THEME.paper_bgcolor,
        plot_bgcolor: CONFIG.THEME.plot_bgcolor,
        margin: { t: 40, b: 60, l: 70, r: 20 }
    };

    Plotly.newPlot('stock-prices-chart', traces, layout, {
        responsive: true,
        displayModeBar: false
    });
}

/**
 * Show/hide loading overlay
 */
function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    overlay.style.display = show ? 'flex' : 'none';
}

/**
 * Show error message
 */
function showError(message) {
    const errorDiv = document.getElementById('error-message');
    const errorText = document.getElementById('error-text');

    errorText.textContent = message;
    errorDiv.style.display = 'flex';

    // Auto-hide after 10 seconds
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 10000);
}

/**
 * Show success message
 */
function showSuccess(message) {
    const successDiv = document.getElementById('success-message');
    const successText = document.getElementById('success-text');

    successText.textContent = message;
    successDiv.style.display = 'flex';

    setTimeout(() => {
        successDiv.style.display = 'none';
    }, 5000);
}

/**
 * Hide error message
 */
function hideError() {
    const errorDiv = document.getElementById('error-message');
    errorDiv.style.display = 'none';
}

/**
 * Update last update time
 */
function updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    document.getElementById('last-update-time').textContent = timeString;
}