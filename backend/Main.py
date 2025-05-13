import pandas as pd
import sys
import os
import matplotlib.pyplot as plt
from . import Functions as fx
import numpy as np
import wfdb
from typing import Optional, Tuple
import io
import base64
from fastapi import FastAPI


def find_ecg_file(input_dir, exts):
    """
    Scan `input_dir` for files with extensions in `exts`,
    return the most recently modified one.
    """
    # list all files matching allowed extensions
    candidates = [
        f for f in os.listdir(input_dir)
        if os.path.isfile(os.path.join(input_dir, f))
        and os.path.splitext(f)[1].lower() in exts
    ]
    if not candidates:
        print(f" No ECG files found in {input_dir}")
        sys.exit(1)
    # sort by modification time, newest first
    candidates.sort(
        key=lambda f: os.path.getmtime(os.path.join(input_dir, f)),
        reverse=True
    )
    chosen = candidates[0]
    print(f"Found ECG file: {chosen}")
    return os.path.join(input_dir, chosen)



    """
    Reads an MIT-BIH style record (dat + hea) and its annotations.
    
    Parameters
    ----------
    record_path_base : str
        Full path up to—but excluding—the extension.
        e.g. 'C:\\Users\\mokta\\Data\\100' if files are 100.dat, 100.hea, 100.atr
    num_leads : int
        Number of channels / leads to load (0-based indices: 0..num_leads-1)
    
    Returns
    -------
    ecg_df : pd.DataFrame
        Columns ['lead1', 'lead2', …] and a 'Time' column in milliseconds
    fs : float
        Sampling frequency (Hz)
    ann : wfdb.Annotation
        The annotation object (samples & symbols)
    """

def load_wfdb_record(record_path_base: str, num_leads: Optional[int]= None) -> Tuple[pd.DataFrame, float, wfdb.Record, Optional[wfdb.Annotation]]:

    base = os.path.splitext(record_path_base)[0]
    #Read the multi-channel signal
    if num_leads is None:
        record = wfdb.rdrecord(base)
    else:
        record = wfdb.rdrecord(base, channels=list(range(num_leads)))
    # shape: (n_samples, num_leads) yuhhhh
    sig    = record.p_signal        
    # samples per second   
    fs     = record.fs                 

    #Build a DataFrame of the leads
    cols = [f"lead{i+1}" for i in range(sig.shape[1])]
    ecg_df = pd.DataFrame(sig, columns=cols)
    ecg_df["Time"] = np.arange(len(ecg_df)) * (1000.0 / fs)

    #Add a Time axis in milliseconds
    ecg_df["Time"] = np.arange(len(ecg_df)) * (1000.0 / fs)

    #Read the annotations (.atr)
    ann = None
    for ext in ("atr", "qrs"):
        ann_file = f"{record_path_base}.{ext}"
        if os.path.exists(ann_file):
            ann = wfdb.rdann(record_path_base, extension=ext)
            break
    return ecg_df, fs, ann

def read_csv_ecg(path: str, num_leads: int, fs: float):
    """
    Load a plain-text ECG (CSV or whitespace-delimited) into a DataFrame,
    assign Time using the user-supplied sampling rate.
    """
    try:
        raw = pd.read_csv(path, sep=",", header=None)
    except Exception:
        raw = pd.read_csv(path, sep=r"\s+", header=None, engine="python")

    df = raw.iloc[:, :num_leads].copy()
    cols = [f"lead{i+1}" for i in range(num_leads)]
    df.columns = cols

    # build time (ms) from fs
    N = len(df)
    df["Time"] = np.arange(N) * (1000.0 / fs)
    return df, cols


if __name__ == "__main__":
    script_dir = os.path.dirname(__file__)
    input_dir  = os.path.join(script_dir, "Input")
    file_path  = find_ecg_file(input_dir, {".dat", ".hea", ".csv", ".txt"})


    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".dat", ".hea") or os.path.exists(os.path.splitext(file_path)[0] + ".hea"):
        # WFDB record
        base = os.path.splitext(file_path)[0]
        # WFDB branch: record.p_signal.shape[1] is number of channels
        record = wfdb.rdrecord(base)  
        num_leads = record.p_signal.shape[1]
        ecg_df, fs, annotation = load_wfdb_record(base, num_leads)
        lead_cols = [c for c in ecg_df.columns if c.startswith("lead")]
    else:
        # CSV/TXT record — use user’s samplingRate
        #numleads
        try:
            tmp = pd.read_csv(file_path, sep=",", header=None)
        except:
            tmp = pd.read_csv(file_path, sep=r"\s+", header=None, engine="python")
        num_leads = tmp.shape[1]

        ecg_df, lead_cols = read_csv_ecg(file_path, num_leads, mp.samplingRate)
        #ONLY FOR THIS FILE IS IT 1000
        fs = 1000
        annotation = None

    # --- Generate a true time axis in milliseconds ---
    #ONLY FOR THIS FILE IS IT 1000
    fs = 1000

    # --- Filter each lead ---
    filtered_ecg = pd.DataFrame({"Time": ecg_df["Time"]})
    for col in lead_cols:
        filtered_ecg[col] = fx.butterworthFilter(ecg_df[col], 4)

    # --- Detect R-peaks on primary lead and compute HRV ---
    r_peaks_dict = {}
    hrv_per_lead  = {}

    for col in lead_cols:
        # 1) Detect peaks on this lead
        peaks = fx.detectPeaks(filtered_ecg[col].values, fs)  # or detect_rpeaks
        r_peaks_dict[col] = peaks

        # 2) Compute HRV metrics from its RR intervals
        #    Convert sample indices → times (ms) then diffs
        r_times      = np.array(peaks) * (1000.0 / fs)
        rr_intervals = np.diff(r_times)
        hrv_per_lead[col] = fx.hrvMetrics(rr_intervals)

    # --- Classify beats using pre-trained model on primary lead ---
    hrv_per_lead   = {}
    #PREDICTION
    pred_summary_all = {}

    model = fx.load_ecg_model()

    for col in lead_cols:
        # 1) R-peaks & HRV
        peaks = fx.detectPeaks(filtered_ecg[col].values, fs)
        times = np.array(peaks) * (1000.0 / fs)
        rr    = np.diff(times)
        hrv_per_lead[col] = fx.hrvMetrics(rr)

        # 2) Classification (optional)
        preds = fx.classify_segments(model,filtered_ecg[col].values, fs)
        pred_summary_all[col] = fx.summarize_predictions(preds)

    # --- Generate one combined PDF ---
    report_path = os.path.join(os.path.dirname(file_path), "ecg_report.pdf")
    fx.generate_report_all(hrv_per_lead, pred_summary_all, report_path)
    print(f"Combined report saved to {report_path}")



    # --- Plot the filtered ECG and R-peaks ---
    plt.figure(figsize=(10, 6))

    #Plot each lead and collect the Line2D artists
    line_artists = []
    for i, col in enumerate(lead_cols):
        line, = plt.plot(
            filtered_ecg["Time"],
            filtered_ecg[col],
            label=f"Lead {i+1}"
        )
        line_artists.append(line)

    plt.figure(figsize=(10, 6))
    for i, col in enumerate(lead_cols):
        # Plot waveform
        plt.plot(filtered_ecg["Time"], filtered_ecg[col], label=f"Lead {i+1}")

        # Overlay its peaks
        plt.scatter(
            filtered_ecg["Time"].iloc[r_peaks_dict[col]],
            filtered_ecg[col].iloc[r_peaks_dict[col]],
            s=20, marker="x",
            label=f"Peaks {i+1}"
        )

    # Build a legend that only shows leads and peak markers
    handles, labels = plt.gca().get_legend_handles_labels()
    plt.legend(handles, labels, loc="upper right")

    plt.title("Filtered ECG with R-peaks (all leads)")
    plt.xlabel("Time (ms)")
    plt.ylabel("Amplitude")
    plt.tight_layout()
    plt.show()