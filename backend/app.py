# backend/app.py

import os
import uuid
import io
import tempfile
from urllib.parse import unquote

import numpy as np
import wfdb
import matplotlib.pyplot as plt

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from Functions import butterworthFilter, detectPeaks
from .ecg_processing import process_file

app = FastAPI()

# CORS (must come first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 1) API routes ===

@app.post("/analyze")
async def analyze_ecg(
    files: list[UploadFile] = File(
        ...,
        description="Upload .dat/.hea pair and optional .qrs/.atr"
    )
):
    temp_dir = tempfile.mkdtemp()
    saved = []
    for f in files:
        path = os.path.join(temp_dir, f.filename)
        with open(path, "wb") as dst:
            dst.write(await f.read())
        saved.append(path)

    dats = [p for p in saved if p.lower().endswith(".dat")]
    heas = [p for p in saved if p.lower().endswith(".hea")]
    if not dats or not heas:
        raise HTTPException(400, "Must upload both a .dat and a .hea file.")
    dat_path = dats[0]
    base     = os.path.splitext(os.path.basename(dat_path))[0]

    for ext in ("qrs", "atr"):
        for p in saved:
            if p.lower().endswith(f".{ext}"):
                os.rename(p, os.path.join(temp_dir, f"{base}.{ext}"))
                break

    full = process_file(dat_path)
    full["record_path"] = dat_path

    clean = {
        "hrv_metrics": {
            lead: {
                k: (v.tolist() if isinstance(v, np.ndarray) else float(v))
                for k, v in metrics.items()
            }
            for lead, metrics in full["hrv_metrics"].items()
        },
        "predictions": full["predictions"],
        "report_path": full["report_path"],
        "record_path": full["record_path"],
    }
    if ann := full.get("annotation"):
        clean["annotation_samples"] = ann.sample.tolist()
        if hasattr(ann, "symbol"):
            clean["annotation_symbols"] = ann.symbol.tolist()

    return JSONResponse(content=clean)

@app.get("/plot")
async def plot_ecg_all_leads(record_path: str):
    if not os.path.exists(record_path):
        raise HTTPException(404, f"Record not found: {record_path}")

    base   = os.path.splitext(record_path)[0]
    record = wfdb.rdrecord(base)
    sigs   = record.p_signal
    fs     = record.fs
    n_leads = sigs.shape[1]

    fig, axs = plt.subplots(n_leads, 1, figsize=(10, 2.5 * n_leads), sharex=True)
    if n_leads == 1:
        axs = [axs]

    times = np.arange(sigs.shape[0]) / fs
    for i, ax in enumerate(axs):
        raw   = sigs[:, i]
        filt  = butterworthFilter(raw, order=4, fs=fs)
        peaks = detectPeaks(filt, fs)
        ax.plot(times, filt, linewidth=0.8)
        ax.scatter(times[peaks], filt[peaks], marker="x", color="red", s=20)
        ax.set_ylabel(f"Lead {i+1}")
        ax.grid(True)

    axs[-1].set_xlabel("Time (s)")
    fig.suptitle("ECG Traces with R-Peaks", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/download-report")
async def download_report(path: str):
    """
    Streams back the PDF at `path`, where `path` is URL-encoded.
    """
    local_path = unquote(path)
    # Ensure it's in the temp directory for safety
    temp_root = os.path.realpath(tempfile.gettempdir())
    if not os.path.realpath(local_path).startswith(temp_root):
        raise HTTPException(400, "Invalid report path")
    if not os.path.isfile(local_path):
        raise HTTPException(404, "Report not found")
    return FileResponse(
        local_path,
        media_type="application/pdf",
        filename=os.path.basename(local_path),
    )

# === 2) Static files under /static ===

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(BASE_DIR, "frontend")

app.mount(
    "/static",
    StaticFiles(directory=frontend_dir),
    name="static"
)

# === 3) Serve index.html at / ===

@app.get("/", include_in_schema=False)
async def read_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"), media_type="text/html")


@app.post("/api/upload_ecg")
async def upload_ecg(file: UploadFile = File(...)):
    # Generate a unique ID and file path
    file_id = str(uuid.uuid4())
    save_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"{file_id}{os.path.splitext(file.filename)[1]}")
    
    # Stream to disk and track bytes for progress
    with open(out_path, "wb") as buffer:
        chunk_size = 1024 * 1024
        total = 0
        while chunk := await file.read(chunk_size):
            buffer.write(chunk)
            total += len(chunk)
            # (Optionally emit server‐sent events or store progress in-memory)
    
    return {"file_id": file_id, "filename": file.filename}

@app.get("/")
async def read_root():
    return {"message": "ECG Analyzer is online!"}