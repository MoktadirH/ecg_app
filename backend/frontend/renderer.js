// backend/static/renderer.js

document.addEventListener('DOMContentLoaded', () => {
  // UI element references
  const input = document.getElementById('fileInput');
  const btn = document.getElementById('analyzeBtn');
  const pre = document.getElementById('jsonOutput');
  const img = document.getElementById('ecgPlot');
  const progress = document.getElementById('uploadProgress');
  const etaDisplay = document.getElementById('eta');
  const themeToggle = document.getElementById('themeToggle');

  // Create and insert percentage display
  let percentDisplay = document.getElementById('progressPercent');
  if (!percentDisplay) {
    percentDisplay = document.createElement('span');
    percentDisplay.id = 'progressPercent';
    percentDisplay.style.marginLeft = '10px';
    progress.parentNode.insertBefore(percentDisplay, progress.nextSibling);
  }

  // Create and insert Download button
  let downloadBtn = document.getElementById('downloadReportBtn');
  if (!downloadBtn) {
    downloadBtn = document.createElement('button');
    downloadBtn.id = 'downloadReportBtn';
    downloadBtn.textContent = 'Download Report';
    downloadBtn.style.display = 'none';
    downloadBtn.style.marginLeft = '10px';
    btn.insertAdjacentElement('afterend', downloadBtn);
  }

  // Dark-mode setup
  if (localStorage.getItem('darkMode') === 'enabled') {
    document.body.classList.add('dark');
    themeToggle.checked = true;
  }
  themeToggle.addEventListener('change', () => {
    if (themeToggle.checked) {
      document.body.classList.add('dark');
      localStorage.setItem('darkMode', 'enabled');
    } else {
      document.body.classList.remove('dark');
      localStorage.setItem('darkMode', 'disabled');
    }
  });

  // Load average processing time (seconds) from previous runs or default to 5s
  let avgProcTime = parseFloat(localStorage.getItem('avgProcTime')) || 5;
  let uploadEndTime = null;
  let procInterval = null;

  btn.addEventListener('click', () => {
    if (input.files.length < 2) {
      alert('Please select .dat + .hea files.');
      return;
    }

    // Build FormData
    const form = new FormData();
    for (const file of input.files) form.append('files', file);

    // Reset UI
    pre.textContent = 'Analyzing…';
    img.src = '';
    downloadBtn.style.display = 'none';
    clearInterval(procInterval);

    // Initialize progress UI
    progress.style.display = 'block';
    etaDisplay.style.display = 'block';
    percentDisplay.style.display = 'inline';
    progress.value = 0;
    percentDisplay.textContent = '0%';
    etaDisplay.textContent = 'ETA: calculating…';

    const xhr = new XMLHttpRequest();
    const startTime = Date.now();

    // Use relative path for proxy
    xhr.open('POST', '/analyze');

    // Upload progress (0–50%)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const uploadPct = (e.loaded / e.total) * 50;
        progress.value = uploadPct;
        percentDisplay.textContent = `${uploadPct.toFixed(1)}%`;
        const elapsedSec = (Date.now() - startTime) / 1000;
        const rate = e.loaded / elapsedSec;
        const remainingBytes = e.total - e.loaded;
        const etaUp = remainingBytes / rate;
        etaDisplay.textContent = `ETA: ${formatTime(etaUp)}`;
      }
    };

    xhr.upload.onloadend = () => {
      uploadEndTime = Date.now();
      procInterval = setInterval(() => {
        const elapsedProc = (Date.now() - uploadEndTime) / 1000;
        const procPct = Math.min((elapsedProc / avgProcTime) * 50, 50);
        const totalPct = 50 + procPct;
        progress.value = totalPct;
        percentDisplay.textContent = `${totalPct.toFixed(1)}%`;
        const etaProc = Math.max(avgProcTime - elapsedProc, 0);
        etaDisplay.textContent = `ETA: ${formatTime(etaProc)}`;
      }, 200);
    };

    xhr.onload = async () => {
      clearInterval(procInterval);
      const totalTime = (Date.now() - uploadEndTime) / 1000;
      avgProcTime = (avgProcTime + totalTime) / 2;
      localStorage.setItem('avgProcTime', avgProcTime);

      progress.value = 100;
      percentDisplay.textContent = '100%';
      etaDisplay.textContent = 'ETA: 00:00';

      setTimeout(() => {
        progress.style.display = 'none';
        etaDisplay.style.display = 'none';
        percentDisplay.style.display = 'none';
      }, 500);

      if (xhr.status < 200 || xhr.status >= 300) {
        pre.textContent = `Error: ${xhr.status}`;
        return;
      }

      const data = JSON.parse(xhr.responseText);
      renderTables(data);

      if (data.report_path) {
        downloadBtn.onclick = () => window.open(`/download-report?path=${encodeURIComponent(data.report_path)}`, '_blank');
        downloadBtn.style.display = 'inline-block';
      }

      if (data.record_path) await renderPlot(data.record_path);
      pre.textContent = 'Results below:';
    };

    xhr.onerror = () => {
      clearInterval(procInterval);
      pre.textContent = 'Network error.';
      progress.style.display = 'none';
      etaDisplay.style.display = 'none';
      percentDisplay.style.display = 'none';
    };

    xhr.send(form);
  });

  function formatTime(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    const hh = h > 0 ? h.toString().padStart(2, '0') + ':' : '';
    return `${hh}${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  function renderTables(data) {
    document.getElementById('hrvTableContainer').innerHTML = '';
    document.getElementById('predTableContainer').innerHTML = '';
    const hrv = data.hrv_metrics;
    const hrvCols = Object.keys(hrv[Object.keys(hrv)[0]]);
    const hrvTable = createTable(['Lead', ...hrvCols], Object.entries(hrv).map(([lead, metrics]) => [lead, ...hrvCols.map(c => Array.isArray(metrics[c]) ? metrics[c].slice(0,5).map(v=>v.toFixed(1)).join(', ') : (Math.round(metrics[c]*100)/100).toString())]));
    document.getElementById('hrvTableContainer').appendChild(hrvTable);

    const preds = data.predictions;
    const allTypes = Array.from(new Set(Object.values(preds).flatMap(p => Object.keys(p))));
    const predRows = Object.entries(preds).map(([lead, counts]) => [lead, ...allTypes.map(t => counts[t]||0)]);
    const predTable = createTable(['Lead', ...allTypes], predRows);
    document.getElementById('predTableContainer').appendChild(predTable);
  }

  function createTable(headers, rows) {
    const tbl = document.createElement('table'); tbl.style.borderCollapse='collapse';
    const thead = tbl.createTHead(); const hdr = thead.insertRow();
    headers.forEach(h => hdr.insertCell().textContent = h);
    const tbody = tbl.createTBody();
    rows.forEach(r => { const row=tbody.insertRow(); r.forEach(cell => row.insertCell().textContent = cell); });
    return tbl;
  }

  async function renderPlot(path) {
    const res = await fetch(`/plot?record_path=${encodeURIComponent(path)}`);
    if (res.ok) {
      const blob = await res.blob();
      img.src = URL.createObjectURL(blob);
      img.alt = 'ECG Plot';
    }
  }

    // === 4) Insert “Run Sample” button ===
  let runSampleBtn = document.getElementById('runSampleBtn');
  if (!runSampleBtn) {
    runSampleBtn = document.createElement('button');
    runSampleBtn.id = 'runSampleBtn';
    runSampleBtn.textContent = 'Run Sample';
    btn.insertAdjacentElement('afterend', runSampleBtn);
  }

  runSampleBtn.addEventListener('click', async () => {
    pre.textContent = 'Running sample…';
    img.src = '';
    downloadBtn.style.display = 'none';
    document.getElementById('hrvTableContainer').innerHTML = '';
    document.getElementById('predTableContainer').innerHTML = '';
    try {
      const res = await fetch('/analyze-sample');
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const data = await res.json();
      renderTables(data);
      if (data.report_path) {
        downloadBtn.onclick = () =>
          window.open(`/download-report?path=${encodeURIComponent(data.report_path)}`, '_blank');
        downloadBtn.style.display = 'inline-block';
      }
      if (data.record_path) await renderPlot(data.record_path);
      pre.textContent = 'Results below:';
    } catch (err) {
      console.error(err);
      pre.textContent = `Error: ${err.message}`;
    }
  });

  // === 5) Inject MIT‐DB footer ===
  const footer = document.createElement('footer');
  footer.innerHTML = `
    Data sourced from the
    <a href="https://physionet.org/about/database/" target="_blank">
      MIT-BIH Arrhythmia Database
    </a>. Visit PhysioNet for more recordings.
  `;
  footer.style = 'margin-top:2em; font-size:0.9em; text-align:center; color:#888;';
  document.body.appendChild(footer);
});
