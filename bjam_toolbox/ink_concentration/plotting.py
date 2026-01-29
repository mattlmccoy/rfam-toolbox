#!/usr/bin/env python3
"""
plotting.py — Standalone plotting mode for BJAM ink concentration analysis.

Loads one or more session CSVs and generates publication-quality
seaborn/matplotlib plots of ROI histogram metrics, grouped by sample
type or ROI label.

Plots produced:
  - Mean intensity boxplot (with strip overlay)
  - Mean intensity bar chart (with error bars)
  - Swarm plot of individual replicates
  - Histogram-metric bar charts: spread, IQR, skewness, kurtosis,
    entropy, pct_zero, tail_delta_95_99
  - Feature pairplot (if seaborn available)

All outputs go under ``bjam_output/plotting/`` in the current
working directory.
"""

import os
import hashlib
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from bjam_toolbox.ink_concentration.plots import (
    plot_spread,
    plot_iqr,
    plot_skewness,
    plot_kurtosis,
    plot_entropy,
    plot_pct_zero,
    plot_tail_delta,
    _apply_theme,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
INK_DESC = {
    1: "5 wt% C, petroleum",
    2: "25 wt% C, petroleum",
    3: "25 wt% C, IPA",
    4: "Sharpie (control)",
}

FEATURE_COLS = [
    "std_I",
    "skewness_I",
    "kurtosis_I",
    "entropy_I",
    "pct_zero",
    "tail_delta_95_99",
]


# ---------------------------------------------------------------------------
# Helper I/O
# ---------------------------------------------------------------------------
def load_and_tag(paths):
    """Load CSVs and tag each row with the source filename."""
    frames = []
    for p in paths:
        df = pd.read_csv(p)
        df["__source"] = os.path.basename(p)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# GUI dialog
# ---------------------------------------------------------------------------
class PlottingDialog(tk.Toplevel):
    """Tkinter dialog for selecting CSVs and grouping options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("BJAM Plotting Options")
        self.resizable(False, False)
        self.result = None

        self.csv_paths = []

        # --- File selection ---
        file_frame = tk.LabelFrame(self, text="Data Files", padx=10, pady=5)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(
            file_frame,
            text="Select CSVs to Plot",
            command=self._browse,
        ).pack(fill="x", pady=2)
        self.file_label = tk.Label(
            file_frame, text="No files selected", anchor="w"
        )
        self.file_label.pack(fill="x")

        # --- Grouping ---
        group_frame = tk.LabelFrame(
            self, text="Plot Grouping", padx=10, pady=5
        )
        group_frame.pack(fill="x", padx=10, pady=5)

        self.group_var = tk.StringVar(value="type")
        tk.Radiobutton(
            group_frame,
            text="Group by Sample Type (ink_desc)",
            variable=self.group_var,
            value="type",
        ).pack(anchor="w")
        tk.Radiobutton(
            group_frame,
            text="Group by ROI Label",
            variable=self.group_var,
            value="label",
        ).pack(anchor="w")

        # --- Plot options ---
        opts_frame = tk.LabelFrame(
            self, text="Plot Options", padx=10, pady=5
        )
        opts_frame.pack(fill="x", padx=10, pady=5)

        self.var_boxplot = tk.BooleanVar(value=True)
        self.var_barplot = tk.BooleanVar(value=True)
        self.var_swarm = tk.BooleanVar(value=True)
        self.var_metrics = tk.BooleanVar(value=True)
        self.var_pairplot = tk.BooleanVar(value=True)

        tk.Checkbutton(
            opts_frame, text="Boxplot (mean intensity)", variable=self.var_boxplot
        ).pack(anchor="w")
        tk.Checkbutton(
            opts_frame, text="Bar chart (avg intensity)", variable=self.var_barplot
        ).pack(anchor="w")
        tk.Checkbutton(
            opts_frame, text="Swarm plot (replicates)", variable=self.var_swarm
        ).pack(anchor="w")
        tk.Checkbutton(
            opts_frame,
            text="Histogram-metric bar charts",
            variable=self.var_metrics,
        ).pack(anchor="w")
        tk.Checkbutton(
            opts_frame,
            text="Feature pairplot",
            variable=self.var_pairplot,
        ).pack(anchor="w")

        # --- OK / Cancel ---
        btn_frame = tk.Frame(self, pady=10)
        btn_frame.pack()
        tk.Button(
            btn_frame,
            text="Generate Plots",
            width=20,
            command=self._ok,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame, text="Cancel", width=10, command=self._cancel
        ).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

    def _browse(self):
        paths = filedialog.askopenfilenames(
            title="Select CSVs to Plot",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if paths:
            self.csv_paths = list(paths)
            self.file_label.config(text=f"{len(paths)} file(s) selected")

    def _ok(self):
        if not self.csv_paths:
            messagebox.showwarning(
                "Missing Data", "Please select at least one CSV."
            )
            return
        self.result = {
            "csv_paths": self.csv_paths,
            "group_col": "ink_desc" if self.group_var.get() == "type" else "label",
            "boxplot": self.var_boxplot.get(),
            "barplot": self.var_barplot.get(),
            "swarm": self.var_swarm.get(),
            "metrics": self.var_metrics.get(),
            "pairplot": self.var_pairplot.get(),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Run the standalone plotting workflow."""
    root = tk.Tk()
    root.withdraw()

    dlg = PlottingDialog(root)
    root.wait_window(dlg)

    opts = dlg.result
    if opts is None:
        root.destroy()
        return

    # ----- load data -----
    df = load_and_tag(opts["csv_paths"])
    if df.empty:
        messagebox.showerror("Error", "No data loaded.")
        root.destroy()
        return

    # Map ink_key → ink_desc if not present
    if "ink_key" in df.columns:
        df["ink_key"] = df["ink_key"].astype(int)
        if "ink_desc" not in df.columns:
            df["ink_desc"] = df["ink_key"].map(INK_DESC)

    group_col = opts["group_col"]
    group_label = "Sample Type" if group_col == "ink_desc" else "ROI Label"

    # Fall back if group column doesn't exist
    if group_col not in df.columns:
        if "label" in df.columns:
            group_col = "label"
            group_label = "ROI Label"
        else:
            group_col = "__source"
            group_label = "Source File"

    print(f"Loaded {len(df)} samples from {len(opts['csv_paths'])} file(s)")
    print(f"Grouping by: {group_label} ({group_col})")

    # ----- output directory -----
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = "__".join(
        os.path.splitext(os.path.basename(p))[0] for p in opts["csv_paths"]
    )
    short_id = hashlib.md5(session_id.encode("utf-8")).hexdigest()[:8]
    unique_id = f"{short_id}_{timestamp}"

    fig_dir = os.path.join(
        os.getcwd(), "bjam_output", "plotting", "figures"
    )
    os.makedirs(fig_dir, exist_ok=True)

    _apply_theme()
    order = df[group_col].unique().tolist()

    # ---- Boxplot ----
    if opts["boxplot"] and "mean_I" in df.columns:
        fig, ax = plt.subplots(figsize=(max(8, len(order) * 1.5), 5))
        sns.boxplot(
            data=df,
            x=group_col,
            y="mean_I",
            hue=group_col,
            order=order,
            ax=ax,
            linewidth=1.2,
            legend=False,
        )
        sns.stripplot(
            data=df,
            x=group_col,
            y="mean_I",
            order=order,
            color="0.3",
            size=4,
            alpha=0.5,
            ax=ax,
            jitter=True,
        )
        ax.set_title(f"Mean Intensity by {group_label}", fontweight="bold")
        ax.set_ylabel("Mean Intensity (0-255)")
        ax.set_xlabel("")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = os.path.join(fig_dir, f"boxplot_{unique_id}.png")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.show()
        plt.close(fig)
        print(f"Saved: {path}")

    # ---- Bar chart ----
    if opts["barplot"] and "mean_I" in df.columns:
        fig, ax = plt.subplots(figsize=(max(6, len(order) * 1.2), 4.5))
        sns.barplot(
            data=df,
            x=group_col,
            y="mean_I",
            hue=group_col,
            order=order,
            ax=ax,
            errorbar="sd",
            capsize=0.15,
            edgecolor="white",
            legend=False,
        )
        ax.set_title(
            f"Average Mean Intensity by {group_label}", fontweight="bold"
        )
        ax.set_ylabel("Mean Intensity (0-255)")
        ax.set_xlabel("")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = os.path.join(fig_dir, f"avg_intensity_{unique_id}.png")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.show()
        plt.close(fig)
        print(f"Saved: {path}")

    # ---- Swarm plot ----
    if opts["swarm"] and "mean_I" in df.columns:
        fig, ax = plt.subplots(figsize=(max(8, len(order) * 1.5), 5))
        sns.swarmplot(
            data=df,
            x=group_col,
            y="mean_I",
            hue=group_col,
            order=order,
            ax=ax,
            size=6,
            alpha=0.8,
            legend=False,
        )
        ax.set_title(
            f"Individual Replicate Mean Intensities by {group_label}",
            fontweight="bold",
        )
        ax.set_ylabel("Mean Intensity (0-255)")
        ax.set_xlabel("")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = os.path.join(fig_dir, f"replicates_{unique_id}.png")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        plt.show()
        plt.close(fig)
        print(f"Saved: {path}")

    # ---- Histogram-metric bar charts ----
    if opts["metrics"]:
        labels_group = df[group_col].tolist()
        metric_map = {
            "std_I": plot_spread,
            "iqr_I": plot_iqr,
            "skewness_I": plot_skewness,
            "kurtosis_I": plot_kurtosis,
            "entropy_I": plot_entropy,
            "pct_zero": plot_pct_zero,
            "tail_delta_95_99": plot_tail_delta,
        }
        for col, func in metric_map.items():
            if col in df.columns:
                func(df[col].tolist(), labels_group, save_dir=fig_dir)
        print(f"Saved histogram-metric plots to {fig_dir}")

    # ---- Feature pairplot ----
    if opts["pairplot"]:
        avail_feats = [f for f in FEATURE_COLS if f in df.columns]
        if avail_feats and group_col in df.columns:
            g = sns.pairplot(
                df,
                vars=avail_feats,
                hue=group_col,
                diag_kind="kde",
                plot_kws={"alpha": 0.6, "s": 40, "edgecolor": "white"},
            )
            g.figure.suptitle(
                f"Feature Pairplot by {group_label}",
                y=1.02,
                fontsize=14,
                fontweight="bold",
            )
            path = os.path.join(fig_dir, f"pairplot_{unique_id}.png")
            g.savefig(path, dpi=200, bbox_inches="tight")
            plt.show()
            plt.close()
            print(f"Saved: {path}")

    messagebox.showinfo(
        "Plotting Complete",
        f"All figures saved to:\n{fig_dir}",
    )
    root.destroy()


if __name__ == "__main__":
    main()
