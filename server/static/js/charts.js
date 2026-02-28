// Shelf Aware - Chart.js rendering functions (warm palette)

const COLORS = {
    primary: '#6B5E50',    // warm-500
    secondary: '#9C8E7C',  // warm-400
    accent: '#B45309',     // rich amber
    grid: '#E8E0D4',       // warm-200
    palette: [
        '#B45309', '#0E7490', '#7C3AED', '#DC2626',
        '#047857', '#BE185D', '#1D4ED8', '#A16207',
    ],
};

Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
Chart.defaults.color = COLORS.primary;

const defaultOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
        legend: { display: false },
    },
    scales: {
        x: {
            grid: { color: COLORS.grid },
            ticks: { color: COLORS.secondary },
        },
        y: {
            grid: { color: COLORS.grid },
            ticks: { color: COLORS.secondary },
            beginAtZero: true,
        },
    },
};

function renderBar(canvasId, chartData, label, color) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: label || 'Count',
                data: chartData.values,
                backgroundColor: color || COLORS.accent,
                borderRadius: 6,
            }],
        },
        options: defaultOptions,
    });
}

function renderLine(canvasId, chartData, label) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    new Chart(el, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: label || 'Books',
                data: chartData.values,
                borderColor: COLORS.accent,
                backgroundColor: COLORS.accent + '22',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: COLORS.accent,
            }],
        },
        options: defaultOptions,
    });
}

function renderRadar(canvasId, chartData) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    new Chart(el, {
        type: 'radar',
        data: {
            labels: chartData.labels,
            datasets: [{
                data: chartData.values,
                backgroundColor: COLORS.accent + '33',
                borderColor: COLORS.accent,
                pointBackgroundColor: COLORS.accent,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { display: false } },
            scales: {
                r: {
                    beginAtZero: true,
                    grid: { color: COLORS.grid },
                    angleLines: { color: COLORS.grid },
                    pointLabels: {
                        font: { size: 11, family: 'Inter, system-ui, sans-serif' },
                        color: COLORS.primary,
                    },
                },
            },
        },
    });
}

// Plugin: draw a diagonal "agree" line so you can see hater vs hype at a glance
const diagonalLinePlugin = {
    id: 'diagonalLine',
    beforeDraw(chart) {
        const { ctx, scales: { x, y } } = chart;
        const minVal = Math.max(x.min, y.min);
        const maxVal = Math.min(x.max, y.max);
        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = '#D4C8B8';
        ctx.lineWidth = 1.5;
        ctx.moveTo(x.getPixelForValue(minVal), y.getPixelForValue(minVal));
        ctx.lineTo(x.getPixelForValue(maxVal), y.getPixelForValue(maxVal));
        ctx.stroke();
        ctx.restore();
    }
};

function renderScatter(canvasId, points) {
    const el = document.getElementById(canvasId);
    if (!el || !points) return;

    // Color-code: above line = hype (rated higher than avg), below = hater
    const hypeColor = '#047857';  // green
    const haterColor = '#DC2626'; // red
    const neutralColor = COLORS.accent;
    const bgColors = points.map(p => {
        const diff = p.y - p.x;
        if (diff > 0.3) return hypeColor + 'bb';
        if (diff < -0.3) return haterColor + 'bb';
        return neutralColor + '88';
    });

    new Chart(el, {
        type: 'scatter',
        data: {
            datasets: [{
                data: points,
                backgroundColor: bgColors,
                pointRadius: 5,
                pointHoverRadius: 7,
            }],
        },
        options: {
            ...defaultOptions,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const p = ctx.raw;
                            const diff = p.y - p.x;
                            const tag = diff > 0.3 ? ' (hype)' : diff < -0.3 ? ' (hater)' : '';
                            return `${p.title || ''}: avg ${p.x.toFixed(1)}, yours ${p.y}${tag}`;
                        },
                    },
                },
            },
            scales: {
                x: { title: { display: true, text: 'Average Rating', color: COLORS.secondary }, grid: { color: COLORS.grid }, ticks: { color: COLORS.secondary }, min: 1, max: 5 },
                y: { title: { display: true, text: 'Your Rating', color: COLORS.secondary }, grid: { color: COLORS.grid }, ticks: { color: COLORS.secondary }, min: 1, max: 5 },
            },
        },
        plugins: [diagonalLinePlugin],
    });
}

function renderHeatmap(containerId, dailyCounts) {
    const container = document.getElementById(containerId);
    if (!container || !dailyCounts || dailyCounts.length === 0) return;

    const countMap = {};
    let maxCount = 0;
    dailyCounts.forEach(d => {
        countMap[d.date] = d.count;
        if (d.count > maxCount) maxCount = d.count;
    });

    const today = new Date();
    const startDate = new Date(today);
    startDate.setDate(startDate.getDate() - 364);
    startDate.setDate(startDate.getDate() - startDate.getDay());

    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const weekColumns = [];
    const current = new Date(startDate);

    while (current <= today) {
        const weekCells = [];
        const weekStart = new Date(current);
        for (let day = 0; day < 7; day++) {
            const dateStr = current.toISOString().slice(0, 10);
            const count = countMap[dateStr] || 0;
            let level = 0;
            if (count > 0) {
                if (maxCount <= 1) level = 1;
                else level = Math.min(4, Math.ceil((count / maxCount) * 4));
            }
            weekCells.push({ dateStr, count, level, date: new Date(current) });
            current.setDate(current.getDate() + 1);
        }
        weekColumns.push({ cells: weekCells, start: weekStart });
    }

    // Build tooltip element
    const tooltipId = containerId + '-tooltip';

    // Build grid
    let html = '<div style="position:relative;">';
    html += '<div style="display:flex;gap:2px;">';
    for (const week of weekColumns) {
        html += '<div style="display:flex;flex-direction:column;gap:2px;">';
        for (const cell of week.cells) {
            html += `<div class="heatmap-cell heatmap-level-${cell.level}" data-date="${cell.dateStr}" data-count="${cell.count}" style="cursor:default;"></div>`;
        }
        html += '</div>';
    }
    html += '</div>';

    // Month labels
    html += '<div style="display:flex;gap:2px;margin-top:4px;">';
    let lastMonth = -1;
    for (const week of weekColumns) {
        const m = week.start.getMonth();
        const colWidth = '12px';
        if (m !== lastMonth) {
            html += `<div style="width:${colWidth};font-size:10px;color:#9C8E7C;white-space:nowrap;">${months[m]}</div>`;
            lastMonth = m;
        } else {
            html += `<div style="width:${colWidth};"></div>`;
        }
    }
    html += '</div>';

    // Floating tooltip
    html += `<div id="${tooltipId}" style="display:none;position:fixed;background:#2D2319;color:#FFFBF5;padding:4px 8px;border-radius:6px;font-size:12px;pointer-events:none;z-index:50;white-space:nowrap;"></div>`;
    html += '</div>';
    container.innerHTML = html;

    // Tooltip behavior
    const tooltip = document.getElementById(tooltipId);
    container.addEventListener('mouseover', (e) => {
        const cell = e.target.closest('.heatmap-cell');
        if (!cell) { tooltip.style.display = 'none'; return; }
        const date = cell.dataset.date;
        const count = cell.dataset.count;
        const d = new Date(date + 'T00:00:00');
        const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        tooltip.textContent = `${label}: ${count} book${count !== '1' ? 's' : ''}`;
        tooltip.style.display = 'block';
    });
    container.addEventListener('mousemove', (e) => {
        tooltip.style.left = (e.clientX + 12) + 'px';
        tooltip.style.top = (e.clientY - 28) + 'px';
    });
    container.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });
}

function renderDualRadar(canvasId, chartData, labelA, labelB) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    new Chart(el, {
        type: 'radar',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: labelA || 'Reader A',
                    data: chartData.values_a,
                    backgroundColor: COLORS.accent + '33',
                    borderColor: COLORS.accent,
                    pointBackgroundColor: COLORS.accent,
                    borderWidth: 2,
                },
                {
                    label: labelB || 'Reader B',
                    data: chartData.values_b,
                    backgroundColor: COLORS.palette[1] + '33',
                    borderColor: COLORS.palette[1],
                    pointBackgroundColor: COLORS.palette[1],
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { display: true, position: 'top' } },
            scales: {
                r: {
                    beginAtZero: true,
                    grid: { color: COLORS.grid },
                    angleLines: { color: COLORS.grid },
                    pointLabels: {
                        font: { size: 11, family: 'Inter, system-ui, sans-serif' },
                        color: COLORS.primary,
                    },
                },
            },
        },
    });
}

function renderDualBar(canvasId, chartData, labelA, labelB) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: labelA || 'Reader A',
                    data: chartData.values_a,
                    backgroundColor: COLORS.accent,
                    borderRadius: 6,
                },
                {
                    label: labelB || 'Reader B',
                    data: chartData.values_b,
                    backgroundColor: COLORS.palette[1],
                    borderRadius: 6,
                },
            ],
        },
        options: {
            ...defaultOptions,
            plugins: { legend: { display: true, position: 'top' } },
        },
    });
}

function renderAllCharts(stats) {
    if (stats.rating_distribution)
        renderBar('chart-ratings', stats.rating_distribution.chart_data, 'Books', COLORS.accent);

    if (stats.genre_radar)
        renderRadar('chart-genres', stats.genre_radar.chart_data);

    if (stats.reading_eras)
        renderBar('chart-eras', stats.reading_eras.chart_data, 'Books', COLORS.palette[1]);

    if (stats.attention_span)
        renderBar('chart-pages', stats.attention_span.chart_data, 'Books', COLORS.palette[2]);

    if (stats.reading_pace)
        renderLine('chart-pace', stats.reading_pace.chart_data, 'Books');

    if (stats.author_loyalty && stats.author_loyalty.chart_data)
        renderBar('chart-authors', stats.author_loyalty.chart_data, 'Books', COLORS.palette[4]);

    if (stats.hater_hype && stats.hater_hype.scatter_data)
        renderScatter('chart-hater', stats.hater_hype.scatter_data.points);

    if (stats.reading_heatmap && stats.reading_heatmap.daily_counts)
        renderHeatmap('heatmap-container', stats.reading_heatmap.daily_counts);
}
