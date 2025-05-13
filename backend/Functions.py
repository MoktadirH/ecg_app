import os
import tensorflow as tf
import pandas as pd
from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
from scipy import signal
from scipy.signal import resample
import neurokit2 as nk

"""def detectPeaks(ecgSignal,time):
    # Using the Pan-Tompkins algorithm
    #larger window size more smoothing but less visible sharp features, smaller are more sensitive to noise
    #At each point, find average of data in the window to make a "smoother version, the window moves and groups an area into one point to smoothen it out
    #Window size just depends on just the ecg signal
    windowSize = int(0.10 * 200)

    #mode same means that the output has the same length as the input signal, so the actual graph doesnt become shorter or bigger
    #Convolve is how the moving average is computer
    movingAvg = np.convolve(ecgSignal, np.ones(windowSize) / windowSize, mode="same")

    # Calc std dev of moving average
    stdDev = np.std(movingAvg)

    # Set high and low thresholds, and is dynamic so it can be used in many different files
    #A valid r peak comes when it satisfies both thresholds, so that it can get precise with the low value but only goes throigh if the high also allows, letting it refine it further
    threshold_high = 0.5 * stdDev
    threshold_low = 0.3 * stdDev

    # Find peaks in the moving average
    #Distance is half the window size so that it doesnt detect the QRS complex multiple times
    peaks, _ = signal.find_peaks(movingAvg, height=threshold_high, distance=(windowSize//2))

    # Refine peaks using the lower threshold
    refinedPeaks, _ = signal.find_peaks(movingAvg, height=threshold_low, distance=(windowSize//2))

    # Keep only the peaks that satisfy both thresholds
    finalPeaks = np.intersect1d(peaks, refinedPeaks)
    

    return finalPeaks"""


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print(f"Functions.py directory: {BASE_DIR}")

# Absolute path to the .h5 model in this folder
MODEL_PATH = os.path.join(BASE_DIR, "ecg_classifier.h5")

def load_ecg_model(path: str = None):
    """
    Load the ECG classifier model.
    If no path is provided, uses MODEL_PATH.
    """
    model_file = path or MODEL_PATH
    if not os.path.exists(model_file):
        raise FileNotFoundError(f"Model file not found at {model_file}")
    return tf.keras.models.load_model(model_file)


#Same as above but from a library
def detectPeaks(signal: np.ndarray, sampling_rate: float) -> np.ndarray:
    """
    Uses NeuroKit2 to detect R-peaks reliably.
    
    Returns
    -------
    rpeaks_idx : np.ndarray
        Array of sample indices where R-peaks occur.
    """
    # nk.ecg_peaks returns a dict of arrays with binary indicators
    signals, info = nk.ecg_peaks(signal, sampling_rate=sampling_rate)
    # Extract the boolean mask for R-peaks and get their indices
    mask = signals["ECG_R_Peaks"].astype(bool)
    rpeaks_idx = np.where(mask)[0]
    return rpeaks_idx


#Remove noise so it becomes easier to find r peaks
def butterworthFilter(data, order, fs=200.0, lowcut=0.5, highcut=45.0):
    """
    Apply a bandpass Butterworth filter to the data.
    - data: 1D array of ECG signal values
    - order: filter order
    - fs: sampling frequency (Hz)
    - lowcut: lower cutoff frequency (Hz)
    - highcut: upper cutoff frequency (Hz)
    Returns the filtered signal array.
    """
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = signal.butter(order, [low, high], btype='band')
    return signal.filtfilt(b, a, data)




def hrvMetrics(rrInt):
    # Time-domain metrics, all of these measurements are based on the intervals between the r peaks

    #Standard deviation of the intervals
    sdrr = np.std(rrInt)
    #Root mean square of the differences between the intervals, much better than finding average rr interval
    rmssd = np.sqrt(np.mean(np.diff(rrInt)**2))
    #Pairs of intervals that are longer than 50ms, put into a percentage form
    prr = np.sum(np.abs(np.diff(rrInt)) > 50) / len(rrInt) * 100

    # Frequency-domain metrics, counts how much low and high frequency beats occur

    #Using the welch method to find power specrtral density, allowing us to evaluate how the power is distributed over the frequencies
    #psd can be used to analyze how the energy is distributed, which we need for hrv
    #nperseg is the length of the segment
    f, psd = signal.welch(rrInt, fs=200, nperseg=len(rrInt))

    #Trapz method is an integration method that calculates the area under a specific curve (psd), the values gives us area at the specific frequencies that we need for each
    
    #Very low = Below 0.04Hz
    #Low = 0.04-0.015 Hz
    #High = 0.015-0.4 Hz

    #(psd >= 0.0033)
    vlowPower = np.trapz(psd[psd < 4])
    lowPower = np.trapz(psd[(psd >= 4) & (psd < 15)])
    highPower = np.trapz(psd[(psd >= 15) & (psd < 4)])

    return {
        "SDRR":    sdrr,
        "RMSSD":   rmssd,
        "PRR":     prr,
        "VLF Power": vlowPower,
        "LF Power":  lowPower,
        "HF Power":  highPower,
        "PSD":       psd
    }


def preprocess_ecg(segment, target_len=1800):
    segment = (segment - np.mean(segment)) / np.std(segment)
    return resample(segment, target_len)

def classify_segments(model, signal, fs, window_seconds=5):
    preds = []
    #Segment of 5 seconds
    window_size = int(window_seconds*fs)
    label_map = {0: "Normal", 1: "PVC", 2: "AFib", 3: "LBBB", 4: "RBBB"}
    for i in range(0, len(signal) - window_size, window_size):
        segment = preprocess_ecg(signal[i:i + window_size])
        pred = model.predict(segment.reshape(1, -1, 1), verbose=0)
        label = label_map[np.argmax(pred)]
        preds.append(label)
    return preds

def summarize_predictions(preds):
    from collections import Counter
    return dict(Counter(preds))

def generate_report_all(leads_hrv: dict, leads_pred: dict, filename="ecg_report.pdf"):
    """
    Create a single PDF report summarizing HRV and arrhythmia counts per lead.
    
    Parameters
    ----------
    leads_hrv : dict
        { lead_name: {metric_name: value, ...}, ... }
    leads_pred : dict
        { lead_name: {class_label: count, ...}, ... }
    filename : str
        Path to output PDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "ECG Diagnostic Report", ln=True, align="C")
    pdf.ln(5)

    # Section: HRV Metrics
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "HRV Metrics by Lead:", ln=True)
    pdf.set_font("Arial", "", 11)
    for lead, metrics in leads_hrv.items():
        pdf.cell(0, 6, f"{lead}", ln=True)
        for name, val in metrics.items():
            pdf.cell(0, 6, f"  {name}: {val}", ln=True)
        pdf.ln(2)

    pdf.ln(4)
    # Section: Arrhythmia Counts
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Arrhythmia Counts by Lead:", ln=True)
    pdf.set_font("Arial", "", 11)
    for lead, counts in leads_pred.items():
        pdf.cell(0, 6, f"{lead}", ln=True)
        for cls, cnt in counts.items():
            pdf.cell(0, 6, f"  {cls}: {cnt}", ln=True)
        pdf.ln(2)

    pdf.output(filename)