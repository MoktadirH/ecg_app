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
    <a href="https://physionet.org/content/mitdb/1.0.0/" target="_blank">
      MIT-BIH Arrhythmia Database
    </a>. Visit PhysioNet for more recordings.
  `;
  footer.style = 'margin-top:2em; font-size:0.9em; text-align:center; color:#888;';
  document.body.appendChild(footer);