document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('[data-table-search]').forEach((input) => {
    input.addEventListener('input', () => {
      const table = document.getElementById(input.dataset.tableSearch);
      const query = input.value.toLocaleLowerCase();
      table?.querySelectorAll('tbody tr').forEach((row) => {
        row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
      });
    });
  });
  document.querySelector('.menu-toggle')?.addEventListener('click', () => {
    document.querySelector('.sidebar')?.classList.toggle('open');
  });
});

window.initTrendChart = () => {
  const canvas = document.getElementById('trend-chart');
  const chartData = document.getElementById('trend-data');
  if (!canvas || !chartData || !window.Chart) return;
  const values = JSON.parse(chartData.textContent);
  new window.Chart(canvas, {
    type: 'bar',
    data: {
      labels: values.map((entry) => entry.period),
      datasets: [{ label: 'Valid kWh', data: values.map((entry) => entry.consumption_kwh), backgroundColor: '#0c8b7b', borderRadius: 3, maxBarThickness: 30 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (context) => `${context.parsed.y.toFixed(1)} kWh` } } },
      scales: { x: { grid: { display: false }, ticks: { color: '#72817d' } }, y: { beginAtZero: true, grid: { color: '#e8eeeb' }, ticks: { color: '#72817d' } } },
    },
  });
};