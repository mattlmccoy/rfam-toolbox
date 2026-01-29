#!/usr/bin/env python3
"""
concentration_estimator.py — Standalone carbon-concentration estimator for BJAM.

Workflow:
  1. Load 5 wt% & 25 wt% petroleum training CSVs
  2. Load session CSVs to predict
  3. Select the best feature by Pearson |r| correlation
  4. Fit IsotonicRegression and multivariate KNeighborsRegressor
  5. Plot calibration curves
  6. Output session predictions to CSV

All outputs go under ``bjam_output/concentration_est/`` in the current
working directory.

Dependencies: pandas, numpy, matplotlib, scikit-learn
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.isotonic import IsotonicRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import StandardScaler

# Seaborn theme for concentration estimator plots
_CE_THEME = dict(style="whitegrid", font_scale=1.05, palette="muted")

# Full set of features used for concentration estimation
FEATURES = [
    "mean_I", "std_I", "skewness_I", "kurtosis_I",
    "entropy_I", "pct_zero", "tail_delta_95_99",
]


# ---------------------------------------------------------------------------
# Helper I/O
# ---------------------------------------------------------------------------
def select_csvs_dialog(title):
    """File dialog for selecting one or more CSVs."""
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title=title,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    root.destroy()
    return list(paths)


def load_and_tag(paths):
    """Load CSVs and tag each row with the source filename."""
    dfs = []
    for p in paths:
        df = pd.read_csv(p)
        df["__source"] = os.path.basename(p)
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


# ---------------------------------------------------------------------------
# GUI dialog
# ---------------------------------------------------------------------------
class ConcentrationDialog(tk.Toplevel):
    """Tkinter dialog for selecting training and session CSVs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("BJAM Concentration Estimation")
        self.resizable(False, False)
        self.result = None

        self.train_paths = []
        self.session_paths = []

        # --- File selection ---
        file_frame = tk.LabelFrame(self, text="Data Files", padx=10, pady=5)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(
            file_frame,
            text="Select Petroleum Training CSVs",
            command=self._browse_train,
        ).pack(fill="x", pady=2)
        self.train_label = tk.Label(file_frame, text="No files selected", anchor="w")
        self.train_label.pack(fill="x")

        tk.Button(
            file_frame,
            text="Select Session CSVs to Estimate",
            command=self._browse_session,
        ).pack(fill="x", pady=2)
        self.session_label = tk.Label(
            file_frame, text="No files selected", anchor="w"
        )
        self.session_label.pack(fill="x")

        # --- OK / Cancel ---
        btn_frame = tk.Frame(self, pady=10)
        btn_frame.pack()
        tk.Button(
            btn_frame, text="Run Estimation", width=20, command=self._ok
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame, text="Cancel", width=10, command=self._cancel
        ).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

    def _browse_train(self):
        paths = filedialog.askopenfilenames(
            title="Select PETROLEUM TRAINING CSVs",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if paths:
            self.train_paths = list(paths)
            self.train_label.config(text=f"{len(paths)} file(s) selected")

    def _browse_session(self):
        paths = filedialog.askopenfilenames(
            title="Select SESSION CSVs",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if paths:
            self.session_paths = list(paths)
            self.session_label.config(text=f"{len(paths)} file(s) selected")

    def _ok(self):
        if not self.train_paths:
            messagebox.showwarning("Missing Data", "Please select training CSVs.")
            return
        if not self.session_paths:
            messagebox.showwarning("Missing Data", "Please select session CSVs.")
            return
        self.result = {
            "train_paths": self.train_paths,
            "session_paths": self.session_paths,
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Run the concentration estimation workflow with a GUI dialog."""
    root = tk.Tk()
    root.withdraw()

    dlg = ConcentrationDialog(root)
    root.wait_window(dlg)

    opts = dlg.result
    if opts is None:
        root.destroy()
        return  # user cancelled

    # ----- output directory -----
    output_dir = os.path.join(os.getcwd(), "bjam_output", "concentration_est")
    os.makedirs(output_dir, exist_ok=True)

    # 1) Load petroleum training data
    train_df_raw = load_and_tag(opts["train_paths"])
    if train_df_raw.empty:
        messagebox.showerror("Error", "No training data loaded.")
        root.destroy()
        return
    # Filter to petroleum samples only (ink_key 1 & 2) — IPA (ink_key 3)
    # has no petroleum concentration and would produce NaN targets.
    train_df = train_df_raw[train_df_raw["ink_key"].isin([1, 2])].copy()
    if train_df.empty:
        messagebox.showerror(
            "Error",
            "No petroleum samples (ink_key 1 or 2) found in training data.\n"
            "Concentration estimation requires petroleum samples.",
        )
        root.destroy()
        return
    train_df["conc_wt%"] = train_df["ink_key"].map({1: 5.0, 2: 25.0})
    for f in FEATURES:
        train_df[f] = train_df.get(f, np.nan)
    print(f"Petroleum training samples: {len(train_df)} "
          f"(5wt%: {(train_df['ink_key']==1).sum()}, "
          f"25wt%: {(train_df['ink_key']==2).sum()})")

    # 2) Load session data
    sess_df = load_and_tag(opts["session_paths"])
    if sess_df.empty:
        messagebox.showerror("Error", "No session data loaded.")
        root.destroy()
        return
    for f in FEATURES:
        sess_df[f] = sess_df.get(f, np.nan)

    # 3) Pick best feature by Pearson |r|
    corr = (
        train_df[FEATURES + ["conc_wt%"]]
        .corr()["conc_wt%"]
        .drop("conc_wt%")
        .abs()
        .sort_values(ascending=False)
    )
    best = corr.idxmax()
    print("Feature correlations:\n", corr.to_string())
    print(f"\n→ Best feature: {best} (r = {corr[best]:.3f})")

    # 4) Isotonic regression on best feature
    Xb = train_df[best].values
    yb = train_df["conc_wt%"].values
    iso = IsotonicRegression(out_of_bounds="clip").fit(Xb, yb)

    # 5) Multivariate kNN regression
    Xm = train_df[FEATURES].fillna(0).values
    scaler = StandardScaler().fit(Xm)
    knnr = KNeighborsRegressor(n_neighbors=3).fit(scaler.transform(Xm), yb)

    # 6) Plot calibration curves
    sns.set_theme(**_CE_THEME)

    xs = np.linspace(Xb.min(), Xb.max(), 200)
    iso_y = iso.predict(xs)
    grid = pd.DataFrame(
        {
            **{best: xs},
            **{f: train_df[f].mean() for f in FEATURES if f != best},
        }
    )
    knn_y = knnr.predict(scaler.transform(grid[FEATURES].values))

    fig, ax = plt.subplots(figsize=(8, 5.5))
    colors = ["#e74c3c" if k == 1 else "#3498db" for k in train_df["ink_key"]]
    ax.scatter(
        Xb,
        yb,
        c=colors,
        edgecolor="white",
        alpha=0.8,
        s=55,
        zorder=5,
    )
    ax.plot(xs, iso_y, "--", lw=2.5, color=sns.color_palette("muted")[2],
            label="Isotonic Regression")
    ax.plot(xs, knn_y, "-", lw=2.5, color=sns.color_palette("muted")[4],
            label="kNN Multi-feature")

    # Add scatter legend manually
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c",
               markersize=8, label="5 wt% Petroleum"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db",
               markersize=8, label="25 wt% Petroleum"),
        Line2D([0], [0], linestyle="--", lw=2, color=sns.color_palette("muted")[2],
               label="Isotonic Regression"),
        Line2D([0], [0], linestyle="-", lw=2, color=sns.color_palette("muted")[4],
               label="kNN Multi-feature"),
    ]
    ax.legend(handles=legend_elements, loc="best", fontsize=9)
    ax.set_xlabel(best)
    ax.set_ylabel("Carbon Concentration (wt%)")
    ax.set_title("Concentration Calibration Curves", fontweight="bold")
    plt.tight_layout()

    calib_path = os.path.join(output_dir, "concentration_calibration.png")
    fig.savefig(calib_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)
    print(f"Saved calibration plot: {calib_path}")

    # 7) Estimate session data
    sess_df["conc_iso"] = iso.predict(sess_df[best].values)
    sess_df["conc_knn"] = knnr.predict(
        scaler.transform(sess_df[FEATURES].fillna(0).values)
    )

    # 8) Save session predictions
    out_csv = os.path.join(output_dir, "session_concentration_estimates.csv")
    sess_df[["__source", "conc_iso", "conc_knn"]].to_csv(out_csv, index=False)
    print(f"Saved session estimates: {out_csv}")

    messagebox.showinfo(
        "Concentration Estimation Complete",
        f"Results saved to:\n{output_dir}\n\n"
        f"Calibration plot: {calib_path}\n"
        f"Predictions CSV: {out_csv}",
    )
    root.destroy()


if __name__ == "__main__":
    main()
