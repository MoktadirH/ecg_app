document.addEventListener('DOMContentLoaded', () => {

// UI element references
const input = document.getElementById('fileInput');
const btn   = document.getElementById('analyzeBtn');
console.log('Renderer loaded, button is', btn);
const pre   = document.getElementById('jsonOutput');
const img   = document.getElementById('ecgPlot');
const link  = document.getElementById('downloadReport');

btn.addEventListener('click', async () => {
  // 1) Validate file selection
  if (input.files.length < 2) {
    alert('Please select at least the .dat and .hea files (and optional .qrs/.atr).');
    return;
  }

  // 2) Build FormData
  const form = new FormData();
  for (const file of input.files) {
    form.append('files', file);
  }

  // 3) UI reset
  pre.textContent = 'Analyzing…';
  img.src = '';
  link.style.display = 'none';

  try {
    // 4) Send to /analyze
    const res = await fetch('http://127.0.0.1:8000/analyze', {
      method: 'POST',
      body: form
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Analyze failed: ${res.status} ${res.statusText}\n${text}`);
    }

    // 5) Parse and log the JSON
    const data = await res.json();
    console.log('Analysis response:', data);

    document.getElementById('hrvTableContainer').innerHTML = '';
    //Ts not a predator, its a prediction
    document.getElementById('predTableContainer').innerHTML = '';

    // ---- 1) Render HRV Metrics Table ----
    const hrv = data.hrv_metrics;         // { lead1: { SDRR:.., RMSSD:.., … }, lead2: {...}, … }
    const hrvContainer = document.getElementById('hrvTableContainer');

    const hrvCols = Object.keys(hrv[Object.keys(hrv)[0]]);  
    // e.g. ['SDRR','RMSSD','PRR','VLF Power',…,'PSD']
    const hrvTable = document.createElement('table');
    hrvTable.border = 1;
    hrvTable.style.borderCollapse = 'collapse';

    // header
    let thead = hrvTable.createTHead();
    let hdrRow = thead.insertRow();
    hdrRow.insertCell().textContent = 'Lead';
    for (const col of hrvCols) {
    hdrRow.insertCell().textContent = col;
    }

    // body
    let tbody = hrvTable.createTBody();
    for (const [lead, metrics] of Object.entries(hrv)) {
    let row = tbody.insertRow();
    row.insertCell().textContent = lead;
    for (const col of hrvCols) {
        let cell = row.insertCell();
        let val = metrics[col];
        // if it's an array (PSD), join first N values or show length
        if (Array.isArray(val)) {
        cell.textContent = val.slice(0,5).map(v=>v.toFixed(1)).join(', ') + '…';
        cell.title = JSON.stringify(val);  // full on hover
        } else {
        cell.textContent = (Math.round(val*100)/100).toString();
        }
    }
    }
    hrvContainer.appendChild(hrvTable);

    // ---- 2) Render Predictions Table ----
    const preds = data.predictions;       // { lead1: { Normal:8, PVC:1, … }, lead2: {...}, … }
    const predContainer = document.getElementById('predTableContainer');

    const allTypes = new Set();
    for (const p of Object.values(preds))
    Object.keys(p).forEach(t => allTypes.add(t));
    const predCols = Array.from(allTypes);

    const predTable = document.createElement('table');
    predTable.border = 1;
    predTable.style.borderCollapse = 'collapse';

    // header
    thead = predTable.createTHead();
    hdrRow = thead.insertRow();
    hdrRow.insertCell().textContent = 'Lead';
    for (const col of predCols) {
    hdrRow.insertCell().textContent = col;
    }

    // body
    tbody = predTable.createTBody();
    for (const [lead, counts] of Object.entries(preds)) {
    let row = tbody.insertRow();
    row.insertCell().textContent = lead;
    for (const col of predCols) {
        let cell = row.insertCell();
        cell.textContent = counts[col] || 0;
    }
    }
    predContainer.appendChild(predTable);

    // 6) Verify record_path is present
    if (!data.record_path) {
      throw new Error('Server did not return record_path');
    }
    console.log('Using record_path:', data.record_path);

    // 7) Display the JSON in the <pre>
    pre.textContent = "Results below: ";

    // 8) Show “Download Report” link
    const dlUrl = `http://127.0.0.1:8000/download-report?path=${encodeURIComponent(data.report_path)}`;
    link.href = dlUrl;
    link.textContent = 'Download Report PDF';
    link.style.display = 'block';

    // 9) Fetch the ECG plot as a Blob
    const plotUrl = `http://127.0.0.1:8000/plot?record_path=${encodeURIComponent(data.record_path)}`;
    console.log('Fetching plot from:', plotUrl);

    const plotRes = await fetch(plotUrl);
    console.log('Plot response status:', plotRes.status, plotRes.statusText);
    if (!plotRes.ok) {
      const errText = await plotRes.text();
      throw new Error(`Plot failed: ${plotRes.status} ${plotRes.statusText}\n${errText}`);
    }

    const blob = await plotRes.blob();
    console.log('Received plot blob (bytes):', blob.size);
    const blobUrl = URL.createObjectURL(blob);

    // 10) Display the ECG in the <img>
    img.src = blobUrl;
    img.alt = 'ECG Plot';

  } catch (err) {
    console.error('Error in Analyze flow:', err);
    pre.textContent = `Error: ${err.message}`;
  }
});
});
