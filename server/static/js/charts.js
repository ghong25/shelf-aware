// Shelf Aware - Chart.js rendering functions (warm palette)

// ===== Dark-mode-aware color system =====
function getChartColors() {
    const isDark = document.documentElement.classList.contains('dark');
    return isDark ? {
        primary: '#F0E9DF',
        secondary: '#9C8E7C',
        accent: '#D97706',
        grid: '#3D3429',
        tooltipBg: '#1A150E',
        tooltipText: '#F0E9DF',
        palette: [
            '#D97706', '#22D3EE', '#A78BFA', '#F87171',
            '#34D399', '#F472B6', '#60A5FA', '#FBBF24',
        ],
    } : {
        primary: '#6B5E50',
        secondary: '#9C8E7C',
        accent: '#B45309',
        grid: '#E8E0D4',
        tooltipBg: '#2D2319',
        tooltipText: '#FFFBF5',
        palette: [
            '#B45309', '#0E7490', '#7C3AED', '#DC2626',
            '#047857', '#BE185D', '#1D4ED8', '#A16207',
        ],
    };
}

// Legacy compat
const COLORS = getChartColors();

// Set Chart.js defaults
Chart.defaults.font.family = '"DM Sans", Inter, system-ui, sans-serif';
Chart.defaults.color = COLORS.primary;

// Custom tooltip styling
Chart.defaults.plugins.tooltip.backgroundColor = '#2D2319';
Chart.defaults.plugins.tooltip.titleColor = '#FFFBF5';
Chart.defaults.plugins.tooltip.bodyColor = '#F0E9DF';
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.displayColors = false;
Chart.defaults.plugins.tooltip.titleFont = { family: '"DM Sans", system-ui, sans-serif', weight: '600' };

function getDefaultOptions() {
    const c = getChartColors();
    return {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: c.tooltipBg,
                titleColor: c.tooltipText,
                bodyColor: c.tooltipText,
            },
        },
        scales: {
            x: {
                grid: { color: c.grid },
                ticks: { color: c.secondary },
            },
            y: {
                grid: { color: c.grid },
                ticks: { color: c.secondary },
                beginAtZero: true,
            },
        },
    };
}

function renderBar(canvasId, chartData, label, color) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    const c = getChartColors();
    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: label || 'Count',
                data: chartData.values,
                backgroundColor: color || c.accent,
                borderRadius: 8,
            }],
        },
        options: getDefaultOptions(),
    });
}

function renderLine(canvasId, chartData, label) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    const c = getChartColors();
    new Chart(el, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: label || 'Books',
                data: chartData.values,
                borderColor: c.accent,
                backgroundColor: c.accent + '22',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: c.accent,
            }],
        },
        options: getDefaultOptions(),
    });
}

function renderRadar(canvasId, chartData) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    const c = getChartColors();
    new Chart(el, {
        type: 'radar',
        data: {
            labels: chartData.labels,
            datasets: [{
                data: chartData.values,
                backgroundColor: c.accent + '33',
                borderColor: c.accent,
                pointBackgroundColor: c.accent,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: c.tooltipBg,
                    titleColor: c.tooltipText,
                    bodyColor: c.tooltipText,
                },
            },
            scales: {
                r: {
                    beginAtZero: true,
                    grid: { color: c.grid },
                    angleLines: { color: c.grid },
                    pointLabels: {
                        font: { size: 11, family: 'Inter, system-ui, sans-serif' },
                        color: c.primary,
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
    const c = getChartColors();

    const hypeColor = '#047857';
    const haterColor = '#DC2626';
    const neutralColor = c.accent;
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
            ...getDefaultOptions(),
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: c.tooltipBg,
                    titleColor: c.tooltipText,
                    bodyColor: c.tooltipText,
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
                x: { title: { display: true, text: 'Average Rating', color: c.secondary }, grid: { color: c.grid }, ticks: { color: c.secondary }, min: 1, max: 5 },
                y: { title: { display: true, text: 'Your Rating', color: c.secondary }, grid: { color: c.grid }, ticks: { color: c.secondary }, min: 1, max: 5 },
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
            const y = current.getFullYear();
            const mo = String(current.getMonth() + 1).padStart(2, '0');
            const dy = String(current.getDate()).padStart(2, '0');
            const dateStr = `${y}-${mo}-${dy}`;
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

    const tooltipId = containerId + '-tooltip';

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

    html += '<div style="position:relative;height:16px;margin-top:4px;">';
    let lastMonth = -1;
    for (let wi = 0; wi < weekColumns.length; wi++) {
        const m = weekColumns[wi].start.getMonth();
        if (m !== lastMonth) {
            const xPos = wi * 14; // 12px cell + 2px gap
            html += `<span style="position:absolute;left:${xPos}px;font-size:10px;color:#9C8E7C;white-space:nowrap;">${months[m]}</span>`;
            lastMonth = m;
        }
    }
    html += '</div>';

    html += `<div id="${tooltipId}" style="display:none;position:fixed;background:#2D2319;color:#FFFBF5;padding:4px 8px;border-radius:6px;font-size:12px;pointer-events:none;z-index:50;white-space:nowrap;"></div>`;
    html += '</div>';
    container.innerHTML = html;

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
    const c = getChartColors();
    new Chart(el, {
        type: 'radar',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: labelA || 'Reader A',
                    data: chartData.values_a,
                    backgroundColor: c.accent + '33',
                    borderColor: c.accent,
                    pointBackgroundColor: c.accent,
                    borderWidth: 2,
                },
                {
                    label: labelB || 'Reader B',
                    data: chartData.values_b,
                    backgroundColor: c.palette[1] + '33',
                    borderColor: c.palette[1],
                    pointBackgroundColor: c.palette[1],
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    backgroundColor: c.tooltipBg,
                    titleColor: c.tooltipText,
                    bodyColor: c.tooltipText,
                },
            },
            scales: {
                r: {
                    beginAtZero: true,
                    grid: { color: c.grid },
                    angleLines: { color: c.grid },
                    pointLabels: {
                        font: { size: 11, family: 'Inter, system-ui, sans-serif' },
                        color: c.primary,
                    },
                },
            },
        },
    });
}

function renderGenreHBar(canvasId, chartData, labelA, labelB) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    const c = getChartColors();
    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: labelA || 'Reader A',
                    data: chartData.values_a,
                    backgroundColor: c.accent + 'cc',
                    borderColor: c.accent,
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: labelB || 'Reader B',
                    data: chartData.values_b,
                    backgroundColor: c.palette[1] + 'cc',
                    borderColor: c.palette[1],
                    borderWidth: 1,
                    borderRadius: 4,
                },
            ],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    backgroundColor: c.tooltipBg,
                    titleColor: c.tooltipText,
                    bodyColor: c.tooltipText,
                },
            },
            scales: {
                x: {
                    grid: { color: c.grid },
                    ticks: { color: c.secondary },
                    beginAtZero: true,
                },
                y: {
                    grid: { color: c.grid },
                    ticks: { color: c.secondary, font: { size: 11 } },
                },
            },
        },
    });
}

function renderDualBar(canvasId, chartData, labelA, labelB) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData) return;
    const c = getChartColors();
    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [
                {
                    label: labelA || 'Reader A',
                    data: chartData.values_a,
                    backgroundColor: c.accent,
                    borderRadius: 8,
                },
                {
                    label: labelB || 'Reader B',
                    data: chartData.values_b,
                    backgroundColor: c.palette[1],
                    borderRadius: 8,
                },
            ],
        },
        options: {
            ...getDefaultOptions(),
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    backgroundColor: c.tooltipBg,
                    titleColor: c.tooltipText,
                    bodyColor: c.tooltipText,
                },
            },
        },
    });
}

function renderHaterHype(canvasId, chartData) {
    const el = document.getElementById(canvasId);
    if (!el || !chartData || !chartData.labels.length) return;
    const c = getChartColors();

    const colors = [
        '#DC2626', '#F87171', '#FCA5A5',
        '#86EFAC', '#4ADE80', '#16A34A',
    ];

    new Chart(el, {
        type: 'bar',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Books',
                data: chartData.values,
                backgroundColor: colors,
                borderRadius: 8,
            }],
        },
        options: {
            ...getDefaultOptions(),
            scales: {
                x: {
                    title: { display: true, text: 'Your Rating − Average', color: c.secondary },
                    grid: { color: c.grid },
                    ticks: { color: c.secondary },
                },
                y: {
                    grid: { color: c.grid },
                    ticks: { color: c.secondary },
                    beginAtZero: true,
                },
            },
        },
    });
}

// ===== Render all charts (compare page) =====
function renderAllCharts(stats) {
    const c = getChartColors();

    if (stats.rating_distribution)
        renderBar('chart-ratings', stats.rating_distribution.chart_data, 'Books', c.accent);

    if (stats.genre_radar)
        renderRadar('chart-genres', stats.genre_radar.chart_data);

    if (stats.reading_eras)
        renderBar('chart-eras', stats.reading_eras.chart_data, 'Books', c.palette[1]);

    if (stats.attention_span)
        renderBar('chart-pages', stats.attention_span.chart_data, 'Books', c.palette[2]);

    if (stats.reading_pace)
        renderLine('chart-pace', stats.reading_pace.chart_data, 'Books');

    if (stats.author_loyalty && stats.author_loyalty.chart_data)
        renderBar('chart-authors', stats.author_loyalty.chart_data, 'Books', c.palette[4]);

    if (stats.hater_hype && stats.hater_hype.chart_data)
        renderHaterHype('chart-hater', stats.hater_hype.chart_data);

    if (stats.reading_heatmap && stats.reading_heatmap.daily_counts)
        renderHeatmap('heatmap-container', stats.reading_heatmap.daily_counts);
}

// ===== Lazy per-tab chart rendering (profile page) =====
function renderChartsForTab(tabName, stats) {
    if (typeof chartRendered === 'undefined') return;
    if (chartRendered.has(tabName)) return;
    chartRendered.add(tabName);

    const c = getChartColors();

    if (tabName === 'numbers') {
        if (stats.rating_distribution)
            renderBar('chart-ratings', stats.rating_distribution.chart_data, 'Books', c.accent);
        if (stats.hater_hype && stats.hater_hype.chart_data)
            renderHaterHype('chart-hater', stats.hater_hype.chart_data);
    }

    if (tabName === 'reading') {
        if (stats.genre_radar)
            renderRadar('chart-genres', stats.genre_radar.chart_data);
        if (stats.reading_eras)
            renderBar('chart-eras', stats.reading_eras.chart_data, 'Books', c.palette[1]);
        if (stats.attention_span)
            renderBar('chart-pages', stats.attention_span.chart_data, 'Books', c.palette[2]);
        if (stats.reading_pace)
            renderLine('chart-pace', stats.reading_pace.chart_data, 'Books');
        if (stats.author_loyalty && stats.author_loyalty.chart_data)
            renderBar('chart-authors', stats.author_loyalty.chart_data, 'Books', c.palette[4]);
        if (stats.reading_heatmap && stats.reading_heatmap.daily_counts)
            renderHeatmap('heatmap-container', stats.reading_heatmap.daily_counts);
    }
}

// ===== Animated Number Counters =====
function initCountUps() {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.querySelectorAll('.count-up[data-count-target]').forEach(el => {
        if (el.dataset.countDone) return;

        // Only animate if element is visible
        const rect = el.getBoundingClientRect();
        if (rect.top > window.innerHeight || rect.bottom < 0) return;
        if (el.offsetParent === null) return; // hidden

        const target = parseInt(el.dataset.countTarget, 10);
        if (isNaN(target)) return;

        el.dataset.countDone = 'true';

        if (prefersReducedMotion) {
            el.textContent = target.toLocaleString();
            return;
        }

        const duration = 1200;
        const start = performance.now();

        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            // Ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(eased * target);
            el.textContent = current.toLocaleString();
            if (progress < 1) requestAnimationFrame(update);
        }

        el.textContent = '0';
        requestAnimationFrame(update);
    });
}

// ===== Confetti on Roast Reveal =====
function fireConfetti(targetEl) {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion) return;

    const rect = targetEl.getBoundingClientRect();
    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:9999;';
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const colors = ['#D97706', '#F59E0B', '#DC2626', '#7C3AED', '#B45309', '#E11D48'];
    const particles = [];
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 3;

    for (let i = 0; i < 60; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 3 + Math.random() * 5;
        particles.push({
            x: cx, y: cy,
            vx: Math.cos(angle) * speed,
            vy: Math.sin(angle) * speed - 3,
            size: 4 + Math.random() * 4,
            color: colors[Math.floor(Math.random() * colors.length)],
            alpha: 1,
            rotation: Math.random() * 360,
            rotSpeed: (Math.random() - 0.5) * 10,
        });
    }

    let frame = 0;
    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let alive = false;

        for (const p of particles) {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.15; // gravity
            p.alpha -= 0.012;
            p.rotation += p.rotSpeed;

            if (p.alpha <= 0) continue;
            alive = true;

            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rotation * Math.PI / 180);
            ctx.globalAlpha = p.alpha;
            ctx.fillStyle = p.color;
            ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
            ctx.restore();
        }

        frame++;
        if (alive && frame < 120) {
            requestAnimationFrame(animate);
        } else {
            canvas.remove();
        }
    }

    requestAnimationFrame(animate);
}

// Setup confetti observer for roast card
function setupRoastConfetti() {
    const roastCard = document.getElementById('roast-card');
    if (!roastCard) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                fireConfetti(roastCard);
                observer.disconnect();
            }
        });
    }, { threshold: 0.3 });

    observer.observe(roastCard);
}

// ===== Dark mode chart re-render =====
window.addEventListener('darkModeToggle', () => {
    // Destroy and re-render visible charts
    document.querySelectorAll('canvas').forEach(canvas => {
        const chart = Chart.getChart(canvas);
        if (chart) chart.destroy();
    });

    // Reset chart rendered tracking
    if (typeof chartRendered !== 'undefined') {
        chartRendered.clear();
    }

    // Re-render charts for current tab if on profile page
    if (typeof statsData !== 'undefined' && typeof switchTab === 'function') {
        const activeTab = document.querySelector('.tab-item.active');
        if (activeTab) {
            renderChartsForTab(activeTab.dataset.tab, statsData);
        }
    }

    // Re-render compare page charts
    if (typeof compData !== 'undefined') {
        const c = getChartColors();
        if (compData.genre_overlap && compData.genre_overlap.dual_chart_data) {
            const labelA = document.querySelector('[class*="text-amber-700"]')?.textContent;
            const labelB = document.querySelector('[class*="text-cyan-700"]')?.textContent;
            renderGenreHBar('chart-genre-dual', compData.genre_overlap.dual_chart_data, labelA, labelB);
        }
        if (compData.decades_alignment && compData.decades_alignment.dual_chart_data) {
            const labelA = document.querySelector('[class*="text-amber-700"]')?.textContent;
            const labelB = document.querySelector('[class*="text-cyan-700"]')?.textContent;
            renderDualBar('chart-decades-dual', compData.decades_alignment.dual_chart_data, labelA, labelB);
        }
    }
});

// Initialize count-ups on load
document.addEventListener('DOMContentLoaded', () => {
    initCountUps();
    setupRoastConfetti();
});
