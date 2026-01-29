#!/usr/bin/env python3
"""
dim_gui.py — graphical dimensional analysis tool for BJAM patterns.

Each run is stored in:
  session_data/run_YYYYMMDD_HHMMSS_<sanitized tags>/
    - results.csv
    - raw.csv
    - dimensional_compensation.txt (if any)
    - <feature>_overlay.png (+ ring debug images from feature_analysis)
    - source_image.png (full-resolution copy of the input)
    - <feature>_roi.png (full-resolution ROI used for analysis)

Metadata per run:
  - sample_id (auto-generated, editable)
  - ink_type (checkbox tags + free text)
  - feather_pct (dropdown + free text)
  - gantry_speed_mmps

Cross-session plotting:
  - Uses the same feature checkboxes (dot / checkerboard / rings / pitch_x / pitch_y)
  - Scans all CSVs under session_data
  - Saves plots to session_data/figures/plot_<feature>_<timestamp>.png

Supports image inputs:
  - PNG, JPG/JPEG, BMP, TIF/TIFF
  - PDF (first page is used)

Important:
  The full-resolution image is ALWAYS used for analysis and overlay generation.
  A downscaled copy is used ONLY for interactive ROI selection.
"""

from __future__ import annotations
GUI_VERSION = "2025.12.15-d"


import csv
import os
from datetime import datetime
from typing import List, Tuple, Dict

import cv2
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from pdf2image import convert_from_path

from bjam_toolbox.defaults.config_loader import load_config
_CFG = load_config()

from bjam_toolbox.dimensional.analysis import (
    analyze_dot_array,
    analyze_checkerboard,
    analyze_concentric_rings,
    analyze_pitch_ruler,
    recommend_compensation_overall,
)
from bjam_toolbox.dimensional.analysis import FEATURE_ANALYSIS_VERSION, CIRCULARITY_NORM_BASE


class DimensionalGUI:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("BJAM Dimensional Accuracy Tool")



        # Version display
        self._version_str = f"GUI {GUI_VERSION} | Analysis {FEATURE_ANALYSIS_VERSION}"
        try:
            ver_lbl = tk.Label(master, text=self._version_str, font=("Arial", 9), fg="gray25")
            ver_lbl.pack(anchor="w", padx=8, pady=(4, 0))
        except Exception:
            pass

        # Directory defaults
        self.input_dir = os.path.expanduser("~")
        self.output_dir = os.path.join(os.getcwd(), "bjam_output")

        # Directory StringVars
        self.input_dir_var = tk.StringVar(value=self.input_dir)
        self.output_dir_var = tk.StringVar(value=self.output_dir + "  (default)")

        # State
        self.image_path: str | None = None
        self.full_image: np.ndarray | None = None

        # Internal calibration state: pixels per mm (default from config)
        self.px_per_mm: float = _CFG["calibration"]["default_dpi"] / 25.4
        # User-facing calibration variables
        self.dpi_var = tk.StringVar(value=str(_CFG["calibration"]["default_dpi"]))
        self.px_per_mm_var = tk.StringVar(value=f"{self.px_per_mm:.3f}")

        # Track last run directory for per-run plotting
        self._last_run_dir: str | None = None

        # Metadata vars
        ts_now = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.sample_id_var = tk.StringVar(value=f"sample_{ts_now}")
        self.ink_25cbipa = tk.BooleanVar(value=False)
        self.ink_kipa = tk.BooleanVar(value=False)
        self.ink_cipa = tk.BooleanVar(value=False)
        self.ink_gold = tk.BooleanVar(value=False)
        self.ink_other_var = tk.StringVar()
        self.feather_choice_var = tk.StringVar(value="100%")
        self.feather_other_var = tk.StringVar()
        self.gantry_speed_var = tk.StringVar(value=str(_CFG["calibration"]["default_gantry_speed_mmps"]))

        # Feature selection vars
        self.var_dot = tk.BooleanVar(value=True)
        self.var_checker = tk.BooleanVar(value=True)
        self.var_rings = tk.BooleanVar(value=False)
        self.var_pitch_x = tk.BooleanVar(value=False)
        self.var_pitch_y = tk.BooleanVar(value=False)
        self.var_pitch_true_edge = tk.BooleanVar(value=False)

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        # Directories
        dir_frame = tk.LabelFrame(self.master, text="Directories")
        dir_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(dir_frame, text="Input:").grid(row=0, column=0, sticky="w", padx=(5, 2))
        tk.Button(dir_frame, text="Browse...", command=self._browse_input_dir).grid(row=0, column=1, padx=2)
        tk.Label(dir_frame, textvariable=self.input_dir_var, anchor="w").grid(row=0, column=2, sticky="w", padx=5)

        tk.Label(dir_frame, text="Output:").grid(row=1, column=0, sticky="w", padx=(5, 2))
        tk.Button(dir_frame, text="Browse...", command=self._browse_output_dir).grid(row=1, column=1, padx=2)
        tk.Label(dir_frame, textvariable=self.output_dir_var, anchor="w").grid(row=1, column=2, sticky="w", padx=5)
        tk.Button(dir_frame, text="Reset", command=self._reset_output_dir).grid(row=1, column=3, padx=5)

        # File selection
        file_frame = tk.Frame(self.master)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(file_frame, text="Select Image / PDF", command=self.select_image).pack(side="left")
        self.file_label = tk.Label(file_frame, text="No file selected", anchor="w")
        self.file_label.pack(side="left", padx=5)

        # Calibration (DPI input, computed pixels/mm displayed live)
        cal_frame = tk.Frame(self.master)
        cal_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(cal_frame, text="Scanner DPI:").pack(side="left")
        self.dpi_entry = tk.Entry(cal_frame, width=10, textvariable=self.dpi_var)
        self.dpi_entry.pack(side="left", padx=5)

        tk.Label(cal_frame, text="Pixels per mm:").pack(side="left")
        self.cal_label = tk.Label(cal_frame, textvariable=self.px_per_mm_var)
        self.cal_label.pack(side="left", padx=5)

        # Update pixels/mm in real time as DPI changes
        self.dpi_var.trace_add("write", lambda *args: self._on_dpi_change())

        # Metadata frame
        meta_frame = tk.LabelFrame(self.master, text="Sample metadata")
        meta_frame.pack(fill="x", padx=10, pady=5)

        # Row 0: Sample ID
        tk.Label(meta_frame, text="Sample ID:").grid(row=0, column=0, sticky="w")
        tk.Entry(meta_frame, textvariable=self.sample_id_var, width=30).grid(
            row=0, column=1, columnspan=3, sticky="w"
        )

        # Row 1: Ink type checkboxes
        tk.Label(meta_frame, text="Ink type:").grid(row=1, column=0, sticky="nw")
        ink_frame = tk.Frame(meta_frame)
        ink_frame.grid(row=1, column=1, columnspan=3, sticky="w")
        tk.Checkbutton(ink_frame, text="25CBIPA", variable=self.ink_25cbipa).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(ink_frame, text="KIPA", variable=self.ink_kipa).grid(row=0, column=1, sticky="w")
        tk.Checkbutton(ink_frame, text="CIPA", variable=self.ink_cipa).grid(row=0, column=2, sticky="w")
        tk.Checkbutton(ink_frame, text="GOLDSTANDARD", variable=self.ink_gold).grid(row=0, column=3, sticky="w")
        tk.Label(ink_frame, text="Other:").grid(row=1, column=0, sticky="w")
        tk.Entry(ink_frame, textvariable=self.ink_other_var, width=20).grid(
            row=1, column=1, columnspan=3, sticky="w"
        )

        # Row 2: Feathering
        tk.Label(meta_frame, text="Feathering:").grid(row=2, column=0, sticky="w")
        feather_options = [
            "100%", "90%", "80%", "75%", "70%", "60%", "50%", "40%",
            "30%", "20%", "15%", "10%", "5%", "3%", "2%", "1%",
        ]
        tk.OptionMenu(meta_frame, self.feather_choice_var, *feather_options).grid(row=2, column=1, sticky="w")
        tk.Label(meta_frame, text="Other:").grid(row=2, column=2, sticky="e")
        tk.Entry(meta_frame, textvariable=self.feather_other_var, width=10).grid(row=2, column=3, sticky="w")

        # Row 3: Gantry speed
        tk.Label(meta_frame, text="Gantry speed (mm/s):").grid(row=3, column=0, sticky="w")
        tk.Entry(meta_frame, textvariable=self.gantry_speed_var, width=10).grid(row=3, column=1, sticky="w")

        # Feature selection
        feat_frame = tk.LabelFrame(self.master, text="Features (used for analysis and plotting)")
        feat_frame.pack(fill="x", padx=10, pady=5)
        tk.Checkbutton(feat_frame, text="Dot array", variable=self.var_dot).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(feat_frame, text="Checkerboard", variable=self.var_checker).grid(row=1, column=0, sticky="w")
        tk.Checkbutton(feat_frame, text="Concentric rings", variable=self.var_rings).grid(row=0, column=1, sticky="w")
        tk.Checkbutton(feat_frame, text="Pitch X", variable=self.var_pitch_x).grid(row=1, column=1, sticky="w")
        tk.Checkbutton(feat_frame, text="Pitch Y", variable=self.var_pitch_y).grid(row=2, column=1, sticky="w")
        tk.Checkbutton(feat_frame, text="Pitch: true-edge widths", variable=self.var_pitch_true_edge).grid(row=3, column=1, sticky="w")

        # Run / plot buttons
        run_frame = tk.Frame(self.master)
        run_frame.pack(fill="x", padx=10, pady=10)
        tk.Button(run_frame, text="Run analysis", command=self.run_analysis).pack(side="left", padx=5)
        tk.Button(run_frame, text="Plot this run", command=self.plot_current_run_data).pack(side="right", padx=5)
        tk.Button(run_frame, text="Plot all sessions", command=self.plot_session_data).pack(side="right", padx=5)

    # ------------------------------------------------------------------ helpers

    def _on_dpi_change(self) -> None:
        """Update pixels-per-mm whenever the DPI entry changes."""
        val = self.dpi_var.get().strip()
        try:
            dpi_val = float(val)
            if dpi_val <= 0:
                raise ValueError
        except ValueError:
            # Invalid DPI: show placeholder and do not change internal px_per_mm
            self.px_per_mm_var.set("—")
            return

        px_per_mm = dpi_val / 25.4
        self.px_per_mm = px_per_mm
        self.px_per_mm_var.set(f"{px_per_mm:.3f}")

    def _browse_input_dir(self):
        d = filedialog.askdirectory(initialdir=self.input_dir, title="Select input directory")
        if d:
            self.input_dir = d
            self.input_dir_var.set(d)

    def _browse_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir, title="Select output directory")
        if d:
            self.output_dir = d
            self.output_dir_var.set(d)

    def _reset_output_dir(self):
        self.output_dir = os.path.join(os.getcwd(), "bjam_output")
        self.output_dir_var.set(self.output_dir + "  (default)")

    def select_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image or PDF",
            initialdir=self.input_dir,
            filetypes=[
                ("Images/PDF", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.pdf"),
                ("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                ("PDF", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        img = self._load_image_any(path)
        if img is None:
            messagebox.showerror("BJAM", f"Failed to load image: {path}")
            return

        self.image_path = path
        self.full_image = img
        self.file_label.config(text=os.path.basename(path))
        self.master.title(f"BJAM Dimensional Accuracy Tool — {os.path.basename(path)}")

        # Update input directory to parent of the selected file
        self.input_dir = os.path.dirname(path)
        self.input_dir_var.set(self.input_dir)

    def _load_image_any(self, path: str) -> np.ndarray | None:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            try:
                pages = convert_from_path(path, dpi=300)
                if not pages:
                    return None
                pil_img = pages[0]
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                return img
            except Exception:
                return None
        else:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            return img

    @staticmethod
    def _sanitize_for_path(text: str) -> str:
        safe = []
        for ch in text:
            if ch.isalnum():
                safe.append(ch)
            elif ch in (" ", "-", "_"):
                safe.append("_")
            else:
                safe.append("_")
        s = "".join(safe).strip("_")
        return s or "sample"

    def _session_root(self) -> str:
        root = self.output_dir
        os.makedirs(root, exist_ok=True)
        return root

    # ------------------------------------------------------------------ main run

    def run_analysis(self) -> None:
        if self.full_image is None:
            messagebox.showwarning("BJAM", "Please select an image or PDF first.")
            return

        # Validate DPI and update internal pixels-per-mm before analysis
        try:
            dpi_val = float(self.dpi_var.get())
            if dpi_val <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("BJAM", "Invalid scanner DPI value.")
            return

        self.px_per_mm = dpi_val / 25.4
        self.px_per_mm_var.set(f"{self.px_per_mm:.3f}")

        img_full = self.full_image.copy()

        sample_id = self.sample_id_var.get().strip()
        if not sample_id:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            sample_id = f"sample_{ts}"
            self.sample_id_var.set(sample_id)

        # Build ink_type tag string
        ink_tags = []
        if self.ink_25cbipa.get():
            ink_tags.append("25CBIPA")
        if self.ink_kipa.get():
            ink_tags.append("KIPA")
        if self.ink_cipa.get():
            ink_tags.append("CIPA")
        if self.ink_gold.get():
            ink_tags.append("GOLDSTANDARD")
        if self.ink_other_var.get().strip():
            ink_tags.append(self.ink_other_var.get().strip())
        ink_type = ",".join(ik_tags for ik_tags in ink_tags)

        feather_pct = self.feather_choice_var.get()
        if self.feather_other_var.get().strip():
            feather_pct = self.feather_other_var.get().strip()

        try:
            gantry_speed_mmps = float(self.gantry_speed_var.get()) if self.gantry_speed_var.get() else float("nan")
        except ValueError:
            gantry_speed_mmps = float("nan")

        metadata = {
            "sample_id": sample_id,
            "ink_type": ink_type,
            "feather_pct": feather_pct,
            "gantry_speed_mmps": gantry_speed_mmps,
            "dpi": float(self.dpi_var.get()) if self.dpi_var.get().strip() else float("nan"),
            "px_per_mm": self.px_per_mm,
            "gui_version": GUI_VERSION,
            "analysis_version": FEATURE_ANALYSIS_VERSION,
            "circularity_norm_base": CIRCULARITY_NORM_BASE,
        }

        # Create a new run directory with metadata baked into the name
        session_root = self._session_root()
        ts_run = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag_str = "_".join(
            [
                self._sanitize_for_path(ink_type),
                self._sanitize_for_path(feather_pct),
                self._sanitize_for_path(
                    str(int(gantry_speed_mmps)) if np.isfinite(gantry_speed_mmps) else ""
                ),
            ]
        )
        tag_str = tag_str.strip("_")
        run_name = f"run_{ts_run}"
        if tag_str:
            run_name += f"_{tag_str}"
        run_dir = os.path.join(session_root, run_name)
        os.makedirs(run_dir, exist_ok=True)

        debug_log_path = os.path.join(run_dir, "run_debug.txt")
        with open(debug_log_path, "w") as f_dbg:
            f_dbg.write("BJAM Dimensional Accuracy Tool\\n")
            f_dbg.write(f"timestamp={ts_run}\\n")
            f_dbg.write(f"gui_version={GUI_VERSION}\\n")
            f_dbg.write(f"analysis_version={FEATURE_ANALYSIS_VERSION}\\n")
            f_dbg.write(f"circularity_norm_base={CIRCULARITY_NORM_BASE}\\n")
            f_dbg.write(f"image_path={self.image_path}\\n")
            f_dbg.write(f"dpi={metadata.get('dpi', '')}\\n")
            f_dbg.write(f"px_per_mm={metadata.get('px_per_mm', '')}\\n")
            f_dbg.write("source_image_saved=False\n")


        # Remember this run directory for per-run plotting
        self._last_run_dir = run_dir

        # Downscaled COPY for interactive ROI selection only
        h, w = img_full.shape[:2]
        max_dim = 1024
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            disp_img = cv2.resize(img_full, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            scale = 1.0
            disp_img = img_full.copy()

        feature_order: List[Tuple[str, bool]] = [
            ("dot", self.var_dot.get()),
            ("checkerboard", self.var_checker.get()),
            ("rings", self.var_rings.get()),
            ("pitch_x", self.var_pitch_x.get()),
            ("pitch_y", self.var_pitch_y.get()),
        ]

        if not any(flag for _, flag in feature_order):
            messagebox.showwarning("BJAM", "Please select at least one feature to analyse.")
            return

        # Get nominal parameters for each selected feature
        feature_params: Dict[str, Tuple] = {}
        for feat, enabled in feature_order:
            if not enabled:
                continue
            if feat == "dot":
                nom_d = simpledialog.askfloat(
                    "Dot array", "Nominal dot diameter (mm):", initialvalue=_CFG["dot_array"]["nominal_diameter_mm"], minvalue=0.0
                )
                nom_s = simpledialog.askfloat(
                    "Dot array", "Nominal dot spacing (mm):", initialvalue=_CFG["dot_array"]["nominal_spacing_mm"], minvalue=0.0
                )
                if not nom_d or not nom_s:
                    messagebox.showwarning("BJAM", "Invalid dot parameters; skipping.")
                    continue
                feature_params[feat] = (nom_d, nom_s)
            elif feat == "checkerboard":
                nom_sq = simpledialog.askfloat(
                    "Checkerboard", "Nominal checker square size (mm):", initialvalue=_CFG["checkerboard"]["nominal_square_size_mm"], minvalue=0.0
                )
                if not nom_sq:
                    messagebox.showwarning("BJAM", "Invalid checkerboard parameters; skipping.")
                    continue
                feature_params[feat] = (nom_sq,)
            elif feat == "rings":
                nom_line = simpledialog.askfloat(
                    "Concentric rings", "Nominal ring line width (mm):", initialvalue=_CFG["concentric_rings"]["nominal_line_width_mm"], minvalue=0.0
                )
                nom_space = simpledialog.askfloat(
                    "Concentric rings", "Nominal ring spacing (mm):", initialvalue=_CFG["concentric_rings"]["nominal_spacing_mm"], minvalue=0.0
                )
                num_rings = simpledialog.askinteger(
                    "Concentric rings", "Number of rings to sample:", initialvalue=_CFG["concentric_rings"]["num_rings"], minvalue=1
                )
                if not nom_line or not nom_space or not num_rings:
                    messagebox.showwarning("BJAM", "Invalid ring parameters; skipping.")
                    continue
                feature_params[feat] = (nom_line, nom_space, num_rings)
            elif feat in ("pitch_x", "pitch_y"):
                default_nom = ",".join(str(w) for w in _CFG["pitch_ruler"]["nominal_bar_widths_mm"])
                txt = simpledialog.askstring(
                    "Pitch ruler",
                    f"Nominal bar widths (mm) ({'left→right' if feat=='pitch_x' else 'bottom→top'}), "
                    f"default {default_nom}:",
                    initialvalue=default_nom,
                )
                if not txt:
                    messagebox.showwarning("BJAM", "Invalid pitch parameters; skipping.")
                    continue
                parts = [p.strip() for p in txt.split(",") if p.strip()]
                try:
                    nominal_widths = [float(p) for p in parts]
                except ValueError:
                    messagebox.showwarning("BJAM", "Invalid pitch parameters; skipping.")
                    continue
                feature_params[feat] = (nominal_widths,)

        if not feature_params:
            messagebox.showinfo("BJAM", "No valid feature parameters given.")
            return

        results_summary: List[Tuple[str, Dict[str, float]]] = []
        # Per-instance raw measurements for this run (all features)
        raw_rows: List[Dict[str, object]] = []

        for feat, enabled in feature_order:
            if not enabled or feat not in feature_params:
                continue

            messagebox.showinfo(
                "ROI selection",
                f"Select the ROI for the {feat} pattern.\n"
                "Drag a box with the mouse, then press Enter or Space.",
            )
            roi_box = cv2.selectROI(f"ROI for {feat}", disp_img, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(f"ROI for {feat}")
            x_disp, y_disp, w_box, h_box = roi_box
            if w_box <= 0 or h_box <= 0:
                messagebox.showwarning("BJAM", f"No ROI selected for {feat}; skipping.")
                continue

            # Map ROI back to full-resolution coordinates
            x_full = int(x_disp / scale)
            y_full = int(y_disp / scale)
            w_full = int(w_box / scale)
            h_full = int(h_box / scale)
            roi = img_full[y_full : y_full + h_full, x_full : x_full + w_full].copy()

            # Save the ROI image used for analysis
            roi_path = os.path.join(run_dir, f"{feat}_roi.png")
            cv2.imwrite(roi_path, roi)

            debug_path = os.path.join(run_dir, f"{feat}_overlay.png")

            params = feature_params[feat]

            if debug_log_path:
                try:
                    with open(debug_log_path, "a", encoding="utf-8") as f_dbg:
                        h, w = roi.shape[:2]
                        f_dbg.write(f"[{feat}] ROI_px={w}x{h} px_per_mm={self.px_per_mm:.6f} params={params}\\n")
                except Exception:
                    pass


            try:
                if feat == "dot":
                    nom_d, nom_s = params
                    summary, details = analyze_dot_array(
                        roi,
                        self.px_per_mm,
                        nominal_diameter_mm=nom_d,
                        nominal_spacing_mm=nom_s,
                        spacing_tol=_CFG["dot_array"]["spacing_tolerance"],
                        debug_overlay_path=debug_path,
                    )
                    # Collect per-blob raw measurements for this run
                    for idx_blob, d in enumerate(details):
                        centroid = d.get("centroid_mm") or (None, None)
                        raw_row: Dict[str, object] = {
                            "feature": "dot",
                            "instance_index": idx_blob,
                            "sample_id": metadata["sample_id"],
                            "ink_type": metadata["ink_type"],
                            "feather_pct": metadata["feather_pct"],
                            "gantry_speed_mmps": metadata["gantry_speed_mmps"],
                             "dpi": metadata.get("dpi", ""),
                             "px_per_mm": metadata.get("px_per_mm", ""),
                            "eq_diam_mm": d.get("eq_diam_mm"),
                            "centroid_x_mm": centroid[0],
                            "centroid_y_mm": centroid[1],
                            "circularity": d.get("circularity"),
                            "eccentricity": d.get("eccentricity"),
                            "major_mm": d.get("major_mm"),
                            "minor_mm": d.get("minor_mm"),
                            "orientation_deg": d.get("orientation_deg"),
                            "area_mm2": d.get("area_mm2"),
                            "nominal_diameter_mm": nom_d,
                            "nominal_spacing_mm": nom_s,
                        }
                        raw_row["dpi"] = metadata.get("dpi")
                        raw_row["px_per_mm"] = self.px_per_mm
                        raw_row["gui_version"] = GUI_VERSION
                        raw_row["analysis_version"] = FEATURE_ANALYSIS_VERSION
                        raw_row["circularity_norm_base"] = CIRCULARITY_NORM_BASE
                        raw_rows.append(raw_row)
                elif feat == "checkerboard":
                    (nom_sq,) = params
                    summary = analyze_checkerboard(
                        roi,
                        self.px_per_mm,
                        nominal_square_mm=nom_sq,
                        dpi=metadata.get("dpi", None),
                        debug_overlay_path=debug_path,
                        debug_log_path=debug_log_path,
                    )
                elif feat == "rings":
                    nom_line, nom_space, num_rings = params
                    summary = analyze_concentric_rings(
                        roi,
                        self.px_per_mm,
                        nominal_line_width_mm=nom_line,
                        nominal_spacing_mm=nom_space,
                        num_rings=num_rings,
                        debug_overlay_path=debug_path,
                        debug_log_path=debug_log_path,
                    )
                elif feat in ("pitch_x", "pitch_y"):
                    (nominal_widths,) = params
                    orientation = "x" if feat == "pitch_x" else "y"
                    summary = analyze_pitch_ruler(
                        roi,
                        self.px_per_mm,
                        nominal_widths_mm=nominal_widths,
                        orientation=orientation,
                        debug_overlay_path=debug_path,
                        debug_log_path=debug_log_path,
                        use_true_edge_width=self.var_pitch_true_edge.get(),
                    )
                else:
                    continue
            except Exception as exc:
                messagebox.showerror("BJAM", f"Error analysing {feat}: {exc}")
                continue

            results_summary.append((feat, summary))

            # Also store a summary-level raw row for this feature
            base_row: Dict[str, object] = {
                "feature": feat,
                "instance_index": -1,
                "sample_id": metadata["sample_id"],
                "ink_type": metadata["ink_type"],
                "feather_pct": metadata["feather_pct"],
                "gantry_speed_mmps": metadata["gantry_speed_mmps"],
                             "dpi": metadata.get("dpi", ""),
                             "px_per_mm": metadata.get("px_per_mm", ""),
            }
            for k, v in summary.items():
                # Avoid overwriting existing meta keys
                if k not in base_row:
                    base_row[k] = v
            raw_rows.append(base_row)

        if not results_summary:
            messagebox.showinfo("BJAM", "No analyses performed.")
            return

        # Save results for this run into run_dir/results.csv
        csv_path = os.path.join(run_dir, "results.csv")

        metric_keys = set()
        for _, summ in results_summary:
            metric_keys.update(summ.keys())
        metric_keys = sorted(metric_keys)

        meta_cols = ["sample_id", "ink_type", "feather_pct", "gantry_speed_mmps"]

        with open(csv_path, "w", newline="") as f:
            meta_cols_results = [
                "feature",
                "sample_id",
                "ink_type",
                "feather_pct",
                "gantry_speed_mmps",
                "dpi",
                "px_per_mm",
                "gui_version",
                "analysis_version",
                "circularity_norm_base",
            ]
            metric_keys: List[str] = []
            for feat, summ in results_summary:
                for k in summ.keys():
                    if k not in meta_cols_results and k not in metric_keys:
                        metric_keys.append(k)

            fieldnames = meta_cols_results + metric_keys
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for feat, summ in results_summary:
                row: Dict[str, object] = {k: metadata.get(k, "") for k in meta_cols_results}
                row["feature"] = feat
                for k in metric_keys:
                    row[k] = summ.get(k, "")
                writer.writerow(row)
# Save per-instance raw measurements for this run into run_dir/raw.csv
        if raw_rows:
            raw_path = os.path.join(run_dir, "raw.csv")
            meta_cols_raw = [
                "feature",
                "instance_index",
                "sample_id",
                "ink_type",
                "feather_pct",
                "gantry_speed_mmps",
                "dpi",
                "px_per_mm",
                "gui_version",
                "analysis_version",
                "circularity_norm_base",
            ]
            other_keys: List[str] = []
            for r in raw_rows:
                for k in r.keys():
                    if k not in meta_cols_raw and k not in other_keys:
                        other_keys.append(k)
            fieldnames_raw = meta_cols_raw + other_keys
            with open(raw_path, "w", newline="") as f_raw:
                writer_raw = csv.DictWriter(f_raw, fieldnames=fieldnames_raw)
                writer_raw.writeheader()
                for r in raw_rows:
                    clean_row = {}
                    for k in fieldnames_raw:
                        val = r.get(k, "")
                        clean_row[k] = "" if val is None else val
                    writer_raw.writerow(clean_row)

        # Human-readable summary
        text_lines: List[str] = []
        text_lines.append("BJAM Dimensional Analysis Summary")
        text_lines.append(f"Source image: {self.image_path}")
        text_lines.append(f"Run directory: {run_dir}")
        text_lines.append(f"Results CSV: {csv_path}")
        text_lines.append("")
        text_lines.append(f"  sample_id: {metadata['sample_id']}")
        text_lines.append(f"  ink_type: {metadata['ink_type']}")
        text_lines.append(f"  feather_pct: {metadata['feather_pct']}")
        text_lines.append(f"  gantry_speed_mmps: {metadata['gantry_speed_mmps']}")

        key_metrics = [
            "avg_diameter_mm",
            "diameter_error_mm",
            "diameter_error_pct",
            "spacing_x_mean_mm",
            "spacing_x_error_mm",
            "spacing_x_error_pct",
            "spacing_y_mean_mm",
            "spacing_y_error_mm",
            "spacing_y_error_pct",
            "mean_square_mm",
            "error_mm",
            "mean_line_width_mm",
            "line_width_error_mm",
        ]

        for feat, summ in results_summary:
            text_lines.append("")
            text_lines.append(f"[{feat}]")
            for k in key_metrics:
                if k in summ:
                    text_lines.append(f"  {k}: {summ[k]}")

        summary_txt = "\n".join(text_lines)
        summary_path = os.path.join(run_dir, "dimensional_summary.txt")
        with open(summary_path, "w") as f_txt:
            f_txt.write(summary_txt)

        # Compensation recommendation
        comp_txt = recommend_compensation_overall(results_summary)
        if comp_txt.strip():
            comp_path = os.path.join(run_dir, "dimensional_compensation.txt")
            with open(comp_path, "w") as f_comp:
                f_comp.write(comp_txt)

        messagebox.showinfo(
            "BJAM",
            f"Analysis complete.\n\nRun directory:\n{run_dir}\n\nResults:\n{csv_path}\n\n"
            f"Summary:\n{summary_path}",
        )

    # ------------------------------------------------------------------ session plotting

    def plot_current_run_data(self) -> None:
        """Plot per-instance metrics for the most recent run using raw.csv."""
        run_dir = getattr(self, "_last_run_dir", None)
        if not run_dir or not os.path.isdir(run_dir):
            messagebox.showwarning("BJAM", "No recent analysis run found. Please run analysis first.")
            return

        raw_path = os.path.join(run_dir, "raw.csv")
        if not os.path.exists(raw_path):
            messagebox.showinfo("BJAM", "No raw.csv file found for the most recent run.")
            return

        # Load all raw rows
        with open(raw_path, "r", newline="") as f_raw:
            reader = csv.DictReader(f_raw)
            raw_rows = list(reader)

        if not raw_rows:
            messagebox.showinfo("BJAM", "raw.csv is empty for this run.")
            return

        # Determine available features and provide a default
        features_available = sorted({r.get("feature", "") for r in raw_rows if r.get("feature")})
        if not features_available:
            messagebox.showinfo("BJAM", "No feature column found in raw.csv.")
            return

        feat_default = "dot" if "dot" in features_available else features_available[0]

        feat = simpledialog.askstring(
            "Plot current run feature",
            f"Feature to plot from raw.csv {features_available}:",
            initialvalue=feat_default,
        )
        if not feat or feat not in features_available:
            messagebox.showwarning("BJAM", "Invalid feature for plotting.")
            return

        metric_default = "eq_diam_mm" if feat == "dot" else ""
        metric = simpledialog.askstring(
            "Plot current run metric",
            "Metric key to plot (e.g. eq_diam_mm, circularity, eccentricity):",
            initialvalue=metric_default,
        )
        if not metric:
            messagebox.showwarning("BJAM", "No metric provided.")
            return

        xs: List[float] = []
        ys: List[float] = []

        for r in raw_rows:
            if r.get("feature") != feat:
                continue
            val_str = r.get(metric, "")
            if not val_str:
                continue
            try:
                val = float(val_str)
            except Exception:
                continue

            idx_str = r.get("instance_index", "")
            try:
                x_val = float(idx_str)
            except Exception:
                x_val = float(len(xs))
            xs.append(x_val)
            ys.append(val)

        if not ys:
            messagebox.showinfo("BJAM", f"No data found in raw.csv for feature '{feat}' and metric '{metric}'.")
            return

        fig_dir = os.path.join(run_dir, "figures")
        os.makedirs(fig_dir, exist_ok=True)
        ts_plot = datetime.now().strftime("%Y%m%d_%H%M%S")
        fig_path = os.path.join(fig_dir, f"runplot_{feat}_{metric}_{ts_plot}.png")

        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("instance_index" if any(r.get("instance_index") for r in raw_rows) else "index")
        plt.ylabel(metric)
        plt.title(f"Run {os.path.basename(run_dir)} — {feat} / {metric}")
        plt.tight_layout()
        plt.savefig(fig_path, dpi=200)
        plt.close()

        messagebox.showinfo(
            "Run plot",
            f"Saved per-instance plot for feature '{feat}' metric '{metric}' to:\n{fig_path}",
        )

    # ------------------------------------------------------------------ session plotting

    def plot_session_data(self) -> None:
        """Aggregate plotting across all session_data results.csv files."""
        session_root = self._session_root()

        feature_choices = []
        if self.var_dot.get():
            feature_choices.append("dot")
        if self.var_checker.get():
            feature_choices.append("checkerboard")
        if self.var_rings.get():
            feature_choices.append("rings")
        if self.var_pitch_x.get():
            feature_choices.append("pitch_x")
        if self.var_pitch_y.get():
            feature_choices.append("pitch_y")

        if not feature_choices:
            messagebox.showwarning("BJAM", "Please enable at least one feature for plotting.")
            return

        # Default metric is spacing_x_error_pct for dot, mean_line_width_mm for rings, etc.
        metric_default = "spacing_x_error_pct"

        # Very light UI: just use simpledialog
        feat = simpledialog.askstring(
            "Plot feature",
            f"Feature to plot {feature_choices}:",
            initialvalue="dot",
        )
        if not feat or feat not in feature_choices:
            messagebox.showwarning("BJAM", "Invalid feature for plotting.")
            return

        metric = simpledialog.askstring(
            "Plot metric",
            "Metric key to plot (e.g. spacing_x_error_pct, diameter_error_pct, mean_line_width_mm):",
            initialvalue=metric_default,
        )
        if not metric:
            messagebox.showwarning("BJAM", "No metric provided.")
            return

        csv_paths: List[str] = []
        for root, _dirs, files in os.walk(session_root):
            for fn in files:
                if fn == "results.csv":
                    csv_paths.append(os.path.join(root, fn))

        if not csv_paths:
            messagebox.showinfo("BJAM", "No results.csv files found under session_data.")
            return

        values: List[float] = []
        for path in csv_paths:
            with open(path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("feature") != feat:
                        continue
                    val_str = row.get(metric, "")
                    if not val_str:
                        continue
                    try:
                        val = float(val_str)
                    except ValueError:
                        continue
                    values.append(val)

        if not values:
            messagebox.showinfo("BJAM", f"No data found for feature '{feat}' and metric '{metric}'.")
            return

        fig_root = os.path.join(session_root, "figures")
        os.makedirs(fig_root, exist_ok=True)
        ts_plot = datetime.now().strftime("%Y%m%d_%H%M%S")
        fig_path = os.path.join(fig_root, f"plot_{feat}_{metric}_{ts_plot}.png")

        xs = list(range(len(values)))
        ys = values
        plt.figure()
        plt.plot(xs, ys, marker="o")
        plt.xlabel("Sample index")
        plt.ylabel(metric)
        plt.title(f"{feat} — {metric}")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(fig_path)
        plt.close()

        messagebox.showinfo(
            "Session plot",
            f"Saved plot for feature '{feat}' metric '{metric}' to:\n{fig_path}",
        )


def main() -> None:
    root = tk.Tk()
    app = DimensionalGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()