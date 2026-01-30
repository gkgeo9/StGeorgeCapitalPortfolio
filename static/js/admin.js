// admin.js - Admin-only trade and reset functionality

let currentPrices = {};

// Extend loadPortfolio to store prices
const originalLoadPortfolio = loadPortfolio;
loadPortfolio = async function () {
    await originalLoadPortfolio();
    try {
        const response = await fetch('/api/portfolio');
        const data = await response.json();
        data.holdings.forEach(h => {
            currentPrices[h.ticker] = h.price;
        });
    } catch (error) {
        console.error('Error loading prices:', error);
    }
};

function openTradeModal() {
    document.getElementById('trade-date').valueAsDate = new Date();
    document.getElementById('trade-modal').classList.remove('hidden');
    document.getElementById('trade-modal').style.display = 'flex';
}

function closeTradeModal() {
    document.getElementById('trade-modal').style.display = 'none';
    document.getElementById('trade-form').reset();
    document.getElementById('current-price-info').classList.add('hidden');
}

document.getElementById('stock-select').addEventListener('change', function (e) {
    let ticker = e.target.value.toUpperCase().trim();
    const exchange = document.getElementById('exchange-select').value;
    let lookupTicker = ticker;
    if (exchange !== 'US' && !ticker.includes('.')) {
        lookupTicker = `${ticker}.${exchange}`;
    }

    const priceInput = document.getElementById('price-input');
    const priceInfo = document.getElementById('current-price-info');
    const marketPrice = document.getElementById('market-price');

    let foundPrice = currentPrices[ticker] || currentPrices[lookupTicker];

    if (foundPrice) {
        priceInput.value = foundPrice.toFixed(2);
        marketPrice.textContent = `$${foundPrice.toFixed(2)}`;
        priceInfo.classList.remove('hidden');
    } else {
        priceInfo.classList.add('hidden');
    }
});

document.getElementById('exchange-select').addEventListener('change', function () {
    document.getElementById('stock-select').dispatchEvent(new Event('change'));
});

async function executeTrade(action) {
    let ticker = document.getElementById('stock-select').value.toUpperCase().trim();
    const exchange = document.getElementById('exchange-select').value;
    const quantity = parseInt(document.getElementById('quantity-input').value);
    const price = parseFloat(document.getElementById('price-input').value);
    const date = document.getElementById('trade-date').value;
    const note = document.getElementById('note-input').value;

    if (!ticker || !quantity || !price || !date) {
        showError('Please fill in all required fields');
        return;
    }

    if (exchange !== 'US' && !ticker.includes('.')) {
        ticker = `${ticker}.${exchange}`;
    }

    showLoading(true);

    try {
        const response = await fetch('/api/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker,
                action: action,
                quantity: quantity,
                price: price,
                date: date,
                note: note || `${action} trade via dashboard`
            })
        });

        const data = await response.json();

        if (response.ok) {
            showSuccess(`${action} ${quantity} ${ticker} @ $${price.toFixed(2)} = $${(quantity * price).toFixed(2)}`);
            closeTradeModal();
            setTimeout(() => loadAllData(), 1000);
        } else {
            showError(data.error || 'Trade failed');
        }
    } catch (error) {
        console.error('Error executing trade:', error);
        showError('Failed to execute trade: ' + error.message);
    } finally {
        showLoading(false);
    }
}

document.getElementById('trade-modal').addEventListener('click', function (e) {
    if (e.target === this) {
        closeTradeModal();
    }
});

async function resetDatabase() {
    if (!confirm("WARNING: This will delete ALL data!\nAre you ABSOLUTELY sure? This action cannot be undone.")) {
        return;
    }

    showLoading(true);

    try {
        const response = await fetch('/api/reset_db', { method: 'POST' });
        const data = await response.json();

        if (response.ok) {
            alert("Database reset successfully.");
            location.reload();
        } else {
            showError(data.error || "Reset failed");
        }
    } catch (error) {
        console.error('Error resetting DB:', error);
        showError('Failed to reset DB: ' + error.message);
    } finally {
        showLoading(false);
    }
}
