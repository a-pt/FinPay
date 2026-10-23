/**
 * FinPay Insights - Frontend Dashboard Controller
 * Integrates Chart.js visualizations, API queries, telemetry indicators, and AI playground.
 */

let categoryChartInstance = null;
let trendChartInstance = null;

// Palette for financial categories
const CATEGORY_COLORS = {
    'Food & Dining': '#f59e0b',
    'Transportation': '#3b82f6',
    'Entertainment': '#8b5cf6',
    'Shopping': '#ec4899',
    'Utilities & Bills': '#64748b',
    'Healthcare': '#10b981',
    'Income': '#16a34a',
    'Uncategorized': '#94a3b8'
};

document.addEventListener('DOMContentLoaded', async () => {
    const startInput = document.getElementById('filter-start-date');
    const endInput = document.getElementById('filter-end-date');
    const shouldSync = !startInput || !startInput.value || !endInput || !endInput.value;
    await loadDashboardData(shouldSync);
    await loadTransactions();
});

function formatCurrency(val) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2
    }).format(val || 0);
}

/**
 * Loads aggregated insights from /api/insights and updates KPI cards and charts.
 * When syncDates is true, date query parameters are omitted to fetch unconstrained dataset
 * date bounds, and the date pickers are updated with the actual dataset min and max dates.
 */
async function loadDashboardData(syncDates = false) {
    const startInput = document.getElementById('filter-start-date');
    const endInput = document.getElementById('filter-end-date');
    const categorySelect = document.getElementById('filter-category');

    const startDate = startInput ? startInput.value : '';
    const endDate = endInput ? endInput.value : '';
    const category = categorySelect ? categorySelect.value : '';

    const urlParams = new URLSearchParams(window.location.search);
    const viewUserId = urlParams.get('view_user_id');

    const params = new URLSearchParams();
    if (!syncDates) {
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
    }
    if (category && category !== 'All') params.append('category', category);
    if (viewUserId) params.append('user_id', viewUserId);

    const startTime = performance.now();
    try {
        const response = await fetch(`/api/insights?${params.toString()}`);
        const clientElapsedMs = (performance.now() - startTime).toFixed(1);

        const cacheHeader = response.headers.get('X-Cache') || 'MISS';
        const serverLatencyMs = response.headers.get('X-Response-Time-Ms') || clientElapsedMs;

        updateCacheTelemetry(cacheHeader, serverLatencyMs);

        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();

        // Dynamically update min and max date pickers to reflect active dataset bounds
        if ((syncDates || !startDate || !endDate) && data.summary && data.summary.date_range) {
            const minDate = data.summary.date_range.start;
            const maxDate = data.summary.date_range.end;
            if (startInput && minDate) {
                startInput.value = minDate;
                startInput.min = minDate;
                startInput.max = maxDate;
            }
            if (endInput && maxDate) {
                endInput.value = maxDate;
                endInput.min = minDate;
                endInput.max = maxDate;
            }
        }

        updateKPICards(data.summary, data.category_breakdown);
        renderCategoryDoughnut(data.category_breakdown);
        renderMonthlyTrendBar(data.monthly_trend);
        renderTopMerchants(data.top_merchants);

        return data;
    } catch (err) {
        console.error('Failed to load dashboard insights:', err);
    }
}

/**
 * Updates Cache status indicator and server latency
 */
function updateCacheTelemetry(status, latencyMs) {
    const statusText = document.getElementById('cache-status-text');
    const latencyText = document.getElementById('cache-latency-text');
    const badge = document.getElementById('cache-telemetry-badge');

    statusText.textContent = `Cache: ${status}`;
    latencyText.textContent = `${latencyMs} ms`;

    if (status === 'HIT') {
        badge.style.backgroundColor = '#dcfce7';
        badge.style.borderColor = '#86efac';
        statusText.style.color = '#166534';
    } else {
        badge.style.backgroundColor = '#eff6ff';
        badge.style.borderColor = '#bfdbfe';
        statusText.style.color = '#1e40af';
    }
}

/**
 * Updates KPI Metrics
 */
function updateKPICards(summary, breakdown) {
    document.getElementById('kpi-total-spent').textContent = formatCurrency(summary.total_spent);
    document.getElementById('kpi-total-income').textContent = formatCurrency(summary.total_income);
    document.getElementById('kpi-net-savings').textContent = formatCurrency(summary.net_savings);

    const txCountEl = document.getElementById('kpi-tx-count');
    if (txCountEl) {
        if (summary.date_range && summary.date_range.start && summary.date_range.end) {
            txCountEl.textContent = `${summary.total_transactions} txs (${summary.date_range.start} to ${summary.date_range.end})`;
        } else {
            txCountEl.textContent = `${summary.total_transactions} transactions`;
        }
    }

    // Savings rate
    if (summary.total_income > 0) {
        const rate = ((summary.net_savings / summary.total_income) * 100).toFixed(1);
        document.getElementById('kpi-savings-rate').textContent = `Savings Rate: ${rate}%`;
    } else {
        document.getElementById('kpi-savings-rate').textContent = 'Savings Rate: N/A';
    }

    // Top Category
    if (breakdown && breakdown.length > 0) {
        const top = breakdown[0];
        document.getElementById('kpi-top-category').textContent = top.category;
        document.getElementById('kpi-top-category-amount').textContent = `${formatCurrency(top.total_spent)} (${top.percentage}%)`;
    } else {
        document.getElementById('kpi-top-category').textContent = 'None';
        document.getElementById('kpi-top-category-amount').textContent = '$0.00 (0%)';
    }
}

/**
 * Renders Categorized Spending Doughnut Chart (Requirement 4)
 */
function renderCategoryDoughnut(breakdown) {
    const ctx = document.getElementById('categoryDoughnutChart').getContext('2d');

    if (categoryChartInstance) {
        categoryChartInstance.destroy();
    }

    if (!breakdown || breakdown.length === 0) {
        return;
    }

    const labels = breakdown.map(item => item.category);
    const dataValues = breakdown.map(item => item.total_spent);
    const backgroundColors = labels.map(label => CATEGORY_COLORS[label] || '#94a3b8');

    categoryChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: backgroundColors,
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        font: { size: 11, family: 'Inter' }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const val = context.raw;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = ((val / total) * 100).toFixed(1);
                            return ` ${context.label}: ${formatCurrency(val)} (${pct}%)`;
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

/**
 * Renders Monthly Trends Bar Chart (Expenses vs Inflow)
 */
function renderMonthlyTrendBar(monthlyTrend) {
    const ctx = document.getElementById('monthlyTrendBarChart').getContext('2d');

    if (trendChartInstance) {
        trendChartInstance.destroy();
    }

    if (!monthlyTrend || monthlyTrend.length === 0) {
        return;
    }

    const labels = monthlyTrend.map(item => item.month);
    const expenses = monthlyTrend.map(item => item.spent);
    const income = monthlyTrend.map(item => item.income);

    trendChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Expenses ($)',
                    data: expenses,
                    backgroundColor: '#ef4444',
                    borderRadius: 4
                },
                {
                    label: 'Income ($)',
                    data: income,
                    backgroundColor: '#10b981',
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: value => '$' + value
                    },
                    grid: { color: '#f1f5f9' }
                },
                x: {
                    grid: { display: false }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11, family: 'Inter' } }
                }
            }
        }
    });
}

/**
 * Renders Top Merchants List
 */
function renderTopMerchants(merchants) {
    const container = document.getElementById('top-merchants-list');
    container.innerHTML = '';

    if (!merchants || merchants.length === 0) {
        container.innerHTML = '<p class="text-muted">No merchant data available.</p>';
        return;
    }

    merchants.forEach(m => {
        const item = document.createElement('div');
        item.className = 'merchant-item';
        item.innerHTML = `
            <span class="merchant-name">${m.merchant} <small class="text-muted">(${m.count}x)</small></span>
            <span class="merchant-spent">${formatCurrency(m.total_spent)}</span>
        `;
        container.appendChild(item);
    });
}

/**
 * Loads transactions table records from /api/transactions
 */
async function loadTransactions() {
    const startDate = document.getElementById('filter-start-date').value;
    const endDate = document.getElementById('filter-end-date').value;
    const category = document.getElementById('filter-category').value;
    const search = document.getElementById('filter-search').value;

    const urlParams = new URLSearchParams(window.location.search);
    const viewUserId = urlParams.get('view_user_id');

    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    if (category && category !== 'All') params.append('category', category);
    if (search) params.append('search', search);
    if (viewUserId) params.append('user_id', viewUserId);
    params.append('limit', '50');

    try {
        const res = await fetch(`/api/transactions?${params.toString()}`);
        if (!res.ok) return;
        const data = await res.json();

        const tbody = document.getElementById('transactions-table-body');
        tbody.innerHTML = '';

        if (!data.transactions || data.transactions.length === 0) {
            document.getElementById('table-record-count').textContent = 'Showing 0 records';
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 2.5rem; color: #64748b;">
                        <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">📂</div>
                        <strong>No transactions found for this workspace.</strong>
                        <p style="margin-top: 0.25rem; font-size: 0.85rem;">Upload a CSV using the button above to populate this ledger.</p>
                    </td>
                </tr>
            `;
            return;
        }

        document.getElementById('table-record-count').textContent = `Showing ${data.transactions.length} of ${data.count} records`;

        data.transactions.forEach(tx => {
            const row = document.createElement('tr');
            const confPct = Math.round(tx.confidence * 100);
            const badgeClass = tx.is_income ? 'badge-income' : 'badge-expense';
            const typeLabel = tx.is_income ? 'Income' : 'Expense';

            row.innerHTML = `
                <td><strong>${tx.date}</strong></td>
                <td>${tx.description}</td>
                <td><strong>${formatCurrency(tx.amount)}</strong></td>
                <td><span class="category-tag">${tx.category}</span></td>
                <td><strong>${confPct}%</strong></td>
                <td><span class="tag-badge ${badgeClass}">${typeLabel}</span></td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        console.error('Failed to load transactions:', err);
    }
}

/**
 * Switch analyst workspace (Admin only)
 */
function switchAnalystView(userId) {
    if (userId) {
        window.location.href = `/dashboard?view_user_id=${encodeURIComponent(userId)}`;
    } else {
        window.location.href = '/dashboard';
    }
}

/**
 * Filters handler
 */
async function applyFilters() {
    await loadDashboardData(false);
    await loadTransactions();
}

async function resetFilters() {
    const startInput = document.getElementById('filter-start-date');
    const endInput = document.getElementById('filter-end-date');
    const categorySelect = document.getElementById('filter-category');
    const searchInput = document.getElementById('filter-search');

    if (startInput) startInput.value = '';
    if (endInput) endInput.value = '';
    if (categorySelect) categorySelect.value = 'All';
    if (searchInput) searchInput.value = '';

    // Fetch unconstrained insights to dynamically populate min/max dataset dates
    await loadDashboardData(true);
    await loadTransactions();
}

/**
 * AI Sandbox prediction tester
 */
async function testAIClassification() {
    const input = document.getElementById('ai-test-input').value.trim();
    if (!input) return;

    try {
        const res = await fetch('/api/predict', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: input })
        });
        const data = await res.json();

        document.getElementById('ai-prediction-result').style.display = 'block';
        document.getElementById('ai-res-category').textContent = data.category;
        document.getElementById('ai-res-confidence').textContent = `${(data.confidence * 100).toFixed(1)}%`;
        document.getElementById('ai-res-method').textContent = data.method === 'rule_based' ? 'Rule Engine (Deterministic)' : 'NLP Model (TF-IDF + Logistic)';
    } catch (err) {
        alert('Failed to classify transaction: ' + err.message);
    }
}

/**
 * CSV Upload handling
 */
function openUploadModal() {
    document.getElementById('upload-modal').style.display = 'flex';
}

function closeUploadModal() {
    document.getElementById('upload-modal').style.display = 'none';
}

function updateFileName(input) {
    if (input.files && input.files[0]) {
        document.getElementById('file-chosen-text').textContent = `Selected: ${input.files[0].name}`;
    }
}

async function handleCSVUpload(event) {
    event.preventDefault();
    const fileInput = document.getElementById('csv-file-input');
    const statusDiv = document.getElementById('upload-status');
    const submitBtn = document.getElementById('btn-submit-upload');

    if (!fileInput.files || !fileInput.files[0]) {
        alert('Please choose a CSV file first.');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Ingesting & Classifying...';

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (res.ok) {
            statusDiv.style.display = 'block';
            statusDiv.className = 'upload-status flash-info';
            statusDiv.textContent = data.message;

            // Hide empty state banner if present
            const emptyBanner = document.getElementById('empty-state-banner');
            if (emptyBanner) {
                emptyBanner.style.display = 'none';
            }

            setTimeout(async () => {
                closeUploadModal();
                await resetFilters();
            }, 1000);
        } else {
            statusDiv.style.display = 'block';
            statusDiv.className = 'upload-status flash-danger';
            statusDiv.textContent = data.error || 'Upload failed.';
        }
    } catch (err) {
        statusDiv.style.display = 'block';
        statusDiv.className = 'upload-status flash-danger';
        statusDiv.textContent = 'Error uploading file: ' + err.message;
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Process & Ingest';
    }
}
