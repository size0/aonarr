// ========== Stats Chart ==========
(function drawChart() {
  const canvas = document.getElementById('statsChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  const data = [800, 1200, 2100, 1800, 2400, 1900, 2200];
  const labels = ['05-14', '05-15', '05-16', '05-17', '05-18', '05-19', '05-20'];

  function draw() {
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    ctx.clearRect(0, 0, w, h);

    const padL = 0, padR = 0, padT = 10, padB = 24;
    const chartW = w - padL - padR;
    const chartH = h - padT - padB;
    const maxVal = Math.max(...data) * 1.2;
    const n = data.length;
    const stepX = chartW / (n - 1);

    // Grid lines
    ctx.strokeStyle = '#f3f4f6';
    ctx.lineWidth = 1;
    for (let i = 0; i < 4; i++) {
      const y = padT + (chartH / 3) * i;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + chartW, y); ctx.stroke();
    }

    // Gradient fill
    const grad = ctx.createLinearGradient(0, padT, 0, padT + chartH);
    grad.addColorStop(0, 'rgba(59,130,246,.15)');
    grad.addColorStop(1, 'rgba(59,130,246,0)');
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = padL + i * stepX;
      const y = padT + chartH - (v / maxVal) * chartH;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo(padL + (n - 1) * stepX, padT + chartH);
    ctx.lineTo(padL, padT + chartH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    data.forEach((v, i) => {
      const x = padL + i * stepX;
      const y = padT + chartH - (v / maxVal) * chartH;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Dots
    data.forEach((v, i) => {
      const x = padL + i * stepX;
      const y = padT + chartH - (v / maxVal) * chartH;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#3b82f6';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#fff';
      ctx.fill();
    });

    // X labels
    ctx.fillStyle = '#9ca3af';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    labels.forEach((l, i) => {
      const x = padL + i * stepX;
      ctx.fillText(l, x, h - 4);
    });
  }

  window.addEventListener('resize', resize);
  setTimeout(resize, 50);
})();

// ========== Nav interaction ==========
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
  });
});

// ========== Tab interaction ==========
document.querySelectorAll('.panel-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    tab.parentElement.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
  });
});

// ========== Action button hover effects ==========
document.querySelectorAll('.action-btn').forEach(btn => {
  btn.addEventListener('mouseenter', () => btn.style.transform = 'translateY(-2px)');
  btn.addEventListener('mouseleave', () => btn.style.transform = '');
});

// ========== Calendar day click ==========
document.querySelectorAll('.calendar-grid .day').forEach(day => {
  day.addEventListener('click', () => {
    document.querySelectorAll('.calendar-grid .day').forEach(d => d.classList.remove('today'));
    day.classList.add('today');
  });
});
