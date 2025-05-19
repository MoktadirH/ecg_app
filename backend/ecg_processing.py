# backend/ecg_processing.py

# Core signal-processing routines
from Functions import (
    butterworthFilter,
    detectPeaks,
    hrvMetrics,
    load_ecg_model,
    classify_segments,
    summarize_predictions,
    generate_report_all
)  # :contentReference[oaicite:0]{index=0}:contentReference[oaicite:1]{index=1}

# I/O and record-loading utilities
from Main import (
    load_wfdb_record,
    find_ecg_file,
    read_csv_ecg
)  # :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}


import os
from typing import Dict, Any
import numpy as np
from typing import Dict, Any

def process_file(record_path: str) -> Dict[str, Any]:
    """
    record_path must include the .dat extension,
    e.g. "C:/…/tmpXYZ/100.dat".  This function:
      1) loads via WFDB or CSV
      2) filters each lead
      3) detects R-peaks & HRV
      4) classifies segments
      5) generates a PDF report
    """

    # 1) Load data
    ext = os.path.splitext(record_path)[1].lower()
    if ext in (".dat", ".hea"):
        ecg_df, fs, record = load_wfdb_record(record_path)
    elif ext == ".csv":
        ecg_df, fs = read_csv_ecg(record_path)
        record = None
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # 2) Filter
    leads = [c for c in ecg_df.columns if c.startswith("lead")]
    filtered = {
        lead: butterworthFilter(ecg_df[lead].values, order=4, fs=fs)
        for lead in leads
    }

    # 3) Detect R-peaks & compute HRV per lead
    hrv_per_lead = {}
    for lead, sig in filtered.items():
        peaks = detectPeaks(sig, fs)
        # convert to ms intervals
        times_ms = peaks * (1000.0 / fs)
        rr = np.diff(times_ms)
        hrv_per_lead[lead] = hrvMetrics(rr)

    # 4) Classification
    #Uses path logic in order to find the classifier file so no need to have an argument
    model = load_ecg_model()
    pred_summary = {
        lead: summarize_predictions(classify_segments(model, sig, fs))
        for lead, sig in filtered.items()
    }

    # 5) PDF report
    report_path = os.path.splitext(record_path)[0] + "_report.pdf"
    generate_report_all(hrv_per_lead, pred_summary, report_path)

    return {
        "hrv_metrics": hrv_per_lead,
        "predictions": pred_summary,
        "report_path": report_path
    }
