/* ============================================================
   CHARDI.AI — CHARTS
   Bar chart: Tenders by State using Chart.js from CDN.
   ============================================================ */

const Charts = (() => {
  let chartInstance = null;

  function renderStateChart(tenders) {
    const canvas = document.getElementById('state-chart');
    const skeleton = document.getElementById('chart-skeleton');
    const errorEl  = document.getElementById('chart-error');

    if (!canvas) return;

    // Hide skeleton/error
    if (skeleton) skeleton.style.display = 'none';
    if (errorEl)  errorEl.style.display  = 'none';
    canvas.style.display = 'block';

    // Count tenders by state
    const counts = {};
    tenders.forEach(t => {
      const label = t.state || 'Central';
      counts[label] = (counts[label] || 0) + 1;
    });

    // Filter to states with at least 1 tender, sort descending
    const entries = Object.entries(counts)
      .filter(([, v]) => v > 0)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 20); // max 20 bars for readability

    if (entries.length === 0) {
      if (skeleton) skeleton.style.display = 'none';
      canvas.style.display = 'none';
      if (errorEl) {
        errorEl.innerHTML = `
          <div class="empty-state" style="padding: var(--spacing-xl)">
            <div class="empty-state__icon">📊</div>
            <div class="empty-state__message">No data to chart with current filters.</div>
          </div>`;
        errorEl.style.display = 'block';
      }
      return;
    }

    let labels = entries.map(([k]) => k);
    let data   = entries.map(([, v]) => v);

    // Pad with ghost ticks if entries < 5 (Bug 1)
    if (labels.length < 5) {
      const padding = 5 - labels.length;
      for (let i = 0; i < padding; i++) {
        labels.push('');
        data.push(null);
      }
    }

    // Destroy previous instance to avoid memory leaks
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }

    // Color: accent for max bar, dimmer for rest
    const maxVal = Math.max(...data);
    const bgColors = data.map(v =>
      v !== null && v === maxVal ? 'rgba(245, 166, 35, 0.85)' : 'rgba(245, 166, 35, 0.22)'
    );
    const borderColors = data.map(v =>
      v !== null && v === maxVal ? 'rgba(245, 166, 35, 1)' : 'rgba(245, 166, 35, 0.45)'
    );

    const ctx = canvas.getContext('2d');

    chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Tenders',
          data,
          backgroundColor: bgColors,
          borderColor: borderColors,
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false,
          maxBarThickness: 48,
          barPercentage: 0.6,
          categoryPercentage: 0.8
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 600,
          easing: 'easeOutQuart'
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1d2028',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            titleColor: '#f0f0ee',
            bodyColor: '#9a9a94',
            titleFont: { family: "'JetBrains Mono', monospace", size: 12 },
            bodyFont:  { family: "'JetBrains Mono', monospace", size: 11 },
            padding: 10,
            callbacks: {
              title: items => items[0].label,
              label: item => `${item.raw} tender${item.raw !== 1 ? 's' : ''}`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: '#55564f',
              font: { family: "'JetBrains Mono', monospace", size: 10 },
              maxRotation: 0
            }
          },
          y: {
            grid: {
              color: 'rgba(255,255,255,0.04)',
              drawBorder: false
            },
            border: { display: false, dash: [3, 3] },
            ticks: {
              color: '#55564f',
              font: { family: "'JetBrains Mono', monospace", size: 10 },
              stepSize: 1,
              precision: 0
            },
            beginAtZero: true
          }
        }
      }
    });
  }

  function showSkeleton() {
    const skeleton = document.getElementById('chart-skeleton');
    const canvas   = document.getElementById('state-chart');
    const errorEl  = document.getElementById('chart-error');
    if (skeleton) skeleton.style.display = 'flex';
    if (canvas)   canvas.style.display   = 'none';
    if (errorEl)  errorEl.style.display  = 'none';
  }

  function showError(message) {
    const skeleton = document.getElementById('chart-skeleton');
    const canvas   = document.getElementById('state-chart');
    const errorEl  = document.getElementById('chart-error');
    if (skeleton) skeleton.style.display = 'none';
    if (canvas)   canvas.style.display   = 'none';
    if (errorEl) {
      errorEl.innerHTML = `
        <div class="error-state" style="padding: var(--spacing-xl)">
          <div class="error-state__icon">⚠</div>
          <div class="error-state__message">${message}</div>
        </div>`;
      errorEl.style.display = 'block';
    }
  }

  return { renderStateChart, showSkeleton, showError };
})();

window.Charts = Charts;