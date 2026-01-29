#!/usr/bin/env python3
"""
classification.py — Material and concentration classification for BJAM.

Loads fixed "training" session CSVs, then loads one or more "session"
CSVs to analyse.  Produces:
  - Material classification via weighted score, kNN, logistic regression
  - Petroleum concentration via skewness threshold, kNN, logistic regression
  - Decision-region 2×2 visualisation
  - Error-analysis metrics CSV
  - Grouped intensity / histogram-metric plots

All interactive prompts are handled via a Tkinter GUI so no terminal
input is required.

Dependencies: pandas, numpy, scipy, matplotlib, scikit-learn
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
from scipy.spatial import ConvexHull

from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    r2_score, mean_absolute_error,
)
from sklearn.model_selection import StratifiedKFold, GridSearchCV

from bjam_toolbox.ink_concentration.plots import (
    plot_spread, plot_iqr, plot_skewness, plot_kurtosis,
    plot_entropy, plot_pct_zero, plot_tail_delta,
)

# ---------------------------------------------------------------------------
# Feature definitions
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "std_I", "tail_delta_95_99",
    "skewness_I", "kurtosis_I",
    "entropy_I", "pct_zero",
]
MATERIAL_PLOT_FEATS = ["std_I", "tail_delta_95_99"]
CONC_PLOT_FEATS = ["skewness_I", "std_I"]


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
    frames = []
    for p in paths:
        df = pd.read_csv(p)
        df["__source"] = os.path.basename(p)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------
def find_best_k(X, y, k_values=None, cv_splits=5):
    """Grid-search KNeighborsClassifier over *k_values* with stratified CV."""
    if k_values is None:
        k_values = [1, 3, 5, 7, 9]
    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=42)
    grid = GridSearchCV(
        KNeighborsClassifier(),
        {"n_neighbors": k_values},
        cv=cv,
        scoring="accuracy",
        n_jobs=-1,
    )
    grid.fit(X, y)
    print(
        f"→ Best k = {grid.best_params_['n_neighbors']}  "
        f"(mean CV acc {grid.best_score_:.3f})"
    )
    return grid.best_params_["n_neighbors"]


def compute_normalised_scores(df, ref_df):
    """Normalise feature columns and compute weighted *material_score*."""
    metrics = {
        "std_I": False,
        "tail_delta_95_99": True,
        "skewness_I": True,
        "kurtosis_I": True,
        "pct_zero": False,
        "entropy_I": False,
    }
    weights = {
        "std_I": 0.4894,
        "tail_delta_95_99": 0.2271,
        "skewness_I": 0.0429,
        "kurtosis_I": 0.1399,
        "pct_zero": 0.0331,
        "entropy_I": 0.0676,
    }
    dfn = df.copy()
    for col, inv in metrics.items():
        s = dfn.get(col, pd.Series(np.nan, index=dfn.index)).astype(float)
        mn = float(ref_df[col].min()) if col in ref_df.columns else s.min()
        mx = float(ref_df[col].max()) if col in ref_df.columns else s.max()
        if mn == mx or np.isnan(mn) or np.isnan(mx):
            dfn[col + "_norm"] = 0.0
        else:
            norm = (s - mn) / (mx - mn)
            dfn[col + "_norm"] = ((1.0 - norm) if inv else norm).fillna(0.0)
    dfn["material_score"] = sum(weights[c] * dfn[c + "_norm"] for c in weights)
    return dfn


def classify_material(dfn, thresh=0.43):
    """Classify material by weighted-score threshold."""
    return np.where(
        dfn["material_score"] >= thresh, "IPA-based", "Petroleum-based"
    )


def classify_petroleum_concentration(df, skew_thresh=1.63):
    """Classify petroleum concentration by skewness threshold."""
    return np.where(
        df["skewness_I"] > skew_thresh,
        "5 wt% petroleum",
        "25 wt% petroleum",
    )


def train_knn(df, feats, k=3):
    """Train a kNN classifier (IPA vs petroleum)."""
    X = df[feats].fillna(0).values
    y = (df["ink_key"] == 3).astype(int).values
    m = KNeighborsClassifier(n_neighbors=k)
    m.fit(X, y)
    return m


def train_lr(df, feats):
    """Train a logistic-regression classifier (IPA vs petroleum)."""
    X = df[feats].fillna(0).values
    y = (df["ink_key"] == 3).astype(int).values
    m = LogisticRegression(max_iter=200)
    m.fit(X, y)
    return m


# Seaborn theme for classification plots
_CLS_THEME = dict(style="whitegrid", font_scale=1.05, palette="muted")

_CLS_PALETTE = {
    "IPA-based": "#2ecc71",
    "Petroleum-based": "#e74c3c",
    "5 wt% petroleum": "#e74c3c",
    "25 wt% petroleum": "#3498db",
}


def _apply_cls_theme():
    """Apply the BJAM classification seaborn theme."""
    sns.set_theme(**_CLS_THEME)


# ---------------------------------------------------------------------------
# Decision-region plot helpers
# ---------------------------------------------------------------------------
def plot_knn_training_region(train_df, model, plot_feats, ax, title):
    x, y = plot_feats
    preds = model.predict(train_df[FEATURE_COLS].fillna(0).values)
    train_df["_p"] = np.where(preds == 1, "IPA-based", "Petroleum-based")
    ax.set_title(title, fontweight="bold")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    hull_colors = {"IPA-based": "#2ecc71", "Petroleum-based": "#e74c3c"}
    for cls, color in hull_colors.items():
        pts_df = train_df.loc[train_df["_p"] == cls, [x, y]].dropna()
        if len(pts_df) >= 3:
            pts = pts_df.values
            hull = ConvexHull(pts)
            ax.add_patch(plt.Polygon(pts[hull.vertices], color=color, alpha=0.2))
    actual = train_df["ink_key"].map(
        {3: "IPA-based", 1: "Petroleum-based", 2: "Petroleum-based", 4: "Control"}
    )
    edge_colors = {"IPA-based": "#27ae60", "Petroleum-based": "#c0392b"}
    for cls, edge in edge_colors.items():
        mask = actual == cls
        ax.scatter(
            train_df.loc[mask, x],
            train_df.loc[mask, y],
            facecolors="none",
            edgecolors=edge,
            s=50,
            linewidths=1.2,
            label=f"Train {cls}",
        )
    train_df.drop(columns=["_p"], inplace=True)
    ax.legend(loc="best", fontsize=8)


def plot_lr_training_boundary(train_df, model, plot_feats, ax, title):
    x, y = plot_feats
    coef, inter = model.coef_[0], model.intercept_[0]
    xi = np.array([train_df[x].min(), train_df[x].max()])
    yi = -(coef[FEATURE_COLS.index(x)] * xi + inter) / coef[FEATURE_COLS.index(y)]
    ax.set_title(title, fontweight="bold")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.plot(xi, yi, "k--", lw=1.5, label="LR boundary")
    actual = train_df["ink_key"].map(
        {3: "IPA-based", 1: "Petroleum-based", 2: "Petroleum-based", 4: "Control"}
    )
    edge_colors = {"IPA-based": "#27ae60", "Petroleum-based": "#c0392b"}
    for cls, edge in edge_colors.items():
        mask = actual == cls
        ax.scatter(
            train_df.loc[mask, x],
            train_df.loc[mask, y],
            facecolors="none",
            edgecolors=edge,
            s=50,
            linewidths=1.2,
            label=f"Train {cls}",
        )
    ax.legend(loc="best", fontsize=8)


def plot_knn_conc_region(train_petro, model, plot_feats, ax, title):
    x, y = plot_feats
    preds = model.predict(train_petro[FEATURE_COLS].fillna(0).values)
    train_petro["_pc"] = np.where(
        preds == 1, "5 wt% petroleum", "25 wt% petroleum"
    )
    ax.set_title(title, fontweight="bold")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    hull_colors = {"5 wt% petroleum": "#e74c3c", "25 wt% petroleum": "#3498db"}
    for cls, color in hull_colors.items():
        pts_df = train_petro.loc[train_petro["_pc"] == cls, [x, y]].dropna()
        if len(pts_df) >= 3:
            pts = pts_df.values
            hull = ConvexHull(pts)
            ax.add_patch(plt.Polygon(pts[hull.vertices], color=color, alpha=0.2))
    actual = train_petro["ink_key"].map(
        {1: "5 wt% petroleum", 2: "25 wt% petroleum"}
    )
    edge_colors = {"5 wt% petroleum": "#c0392b", "25 wt% petroleum": "#2980b9"}
    for cls, edge in edge_colors.items():
        mask = actual == cls
        ax.scatter(
            train_petro.loc[mask, x],
            train_petro.loc[mask, y],
            facecolors="none",
            edgecolors=edge,
            s=50,
            linewidths=1.2,
            label=f"Train {cls}",
        )
    train_petro.drop(columns=["_pc"], inplace=True)
    ax.legend(loc="best", fontsize=8)


def plot_lr_conc_contour(
    train_petro, model, plot_feats, ax, title, df_test, grid_size=200
):
    x_feat, y_feat = plot_feats
    comb = pd.concat([train_petro, df_test], ignore_index=True)
    x_min, x_max = comb[x_feat].min(), comb[x_feat].max()
    y_min, y_max = comb[y_feat].min(), comb[y_feat].max()
    xs = np.linspace(x_min, x_max, grid_size)
    ys = np.linspace(y_min, y_max, grid_size)
    XX, YY = np.meshgrid(xs, ys)
    other = [f for f in FEATURE_COLS if f not in plot_feats]
    means = train_petro[other].mean()
    grid = np.zeros((grid_size * grid_size, len(FEATURE_COLS)))
    for i, f in enumerate(FEATURE_COLS):
        if f == x_feat:
            grid[:, i] = XX.ravel()
        elif f == y_feat:
            grid[:, i] = YY.ravel()
        else:
            grid[:, i] = means[f]
    Z = model.predict_proba(grid)[:, 1].reshape(XX.shape)
    ax.contour(XX, YY, Z, levels=[0.5], colors="k", linestyles="--")
    ax.set_title(title)
    ax.set_xlabel(x_feat)
    ax.set_ylabel(y_feat)
    actual = train_petro["ink_key"].map(
        {1: "5 wt% petroleum", 2: "25 wt% petroleum"}
    )
    for cls, edge in [
        ("5 wt% petroleum", "green"),
        ("25 wt% petroleum", "orange"),
    ]:
        mask = actual == cls
        ax.scatter(
            train_petro.loc[mask, x_feat],
            train_petro.loc[mask, y_feat],
            facecolors="none",
            edgecolors=edge,
            label=f"Train {cls}",
        )
    ax.legend(loc="best")


def safe_metrics(name, y_true, y_pred, prob=None, task=""):
    """Compute classification accuracy / precision / recall / F1 (+ R2, MAE)."""
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    r2 = np.nan
    mae = np.nan
    if prob is not None and prob.shape[0] == y_true.shape[0]:
        r2 = r2_score(y_true, prob)
        mae = mean_absolute_error(y_true, prob)
    return {
        "classifier": name,
        "task": task,
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "r2": r2,
        "mae": mae,
    }


# ---------------------------------------------------------------------------
# GUI for classification options
# ---------------------------------------------------------------------------
class ClassificationDialog(tk.Toplevel):
    """Tkinter dialog that collects all classification options at once."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("BJAM Classification Options")
        self.resizable(False, False)
        self.result = None  # will be set on OK

        # --- CSV paths (populated via browse buttons) ---
        self.train_paths = []
        self.session_paths = []

        # --- File selection ---
        file_frame = tk.LabelFrame(self, text="Data Files", padx=10, pady=5)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(
            file_frame, text="Select Training CSVs", command=self._browse_train
        ).pack(fill="x", pady=2)
        self.train_label = tk.Label(file_frame, text="No files selected", anchor="w")
        self.train_label.pack(fill="x")

        tk.Button(
            file_frame, text="Select Session CSVs", command=self._browse_session
        ).pack(fill="x", pady=2)
        self.session_label = tk.Label(
            file_frame, text="No files selected", anchor="w"
        )
        self.session_label.pack(fill="x")

        # --- Classifiers ---
        clf_frame = tk.LabelFrame(self, text="Classifiers", padx=10, pady=5)
        clf_frame.pack(fill="x", padx=10, pady=5)

        self.var_weighted = tk.BooleanVar(value=True)
        self.var_knn_mat = tk.BooleanVar(value=True)
        self.var_lr_mat = tk.BooleanVar(value=True)
        self.var_conc_skew = tk.BooleanVar(value=True)
        self.var_knn_conc = tk.BooleanVar(value=True)
        self.var_lr_conc = tk.BooleanVar(value=True)

        tk.Checkbutton(
            clf_frame, text="Weighted Score (material)", variable=self.var_weighted
        ).pack(anchor="w")
        tk.Checkbutton(
            clf_frame, text="kNN (material)", variable=self.var_knn_mat
        ).pack(anchor="w")
        tk.Checkbutton(
            clf_frame, text="Logistic Regression (material)", variable=self.var_lr_mat
        ).pack(anchor="w")
        tk.Checkbutton(
            clf_frame, text="Concentration by Skewness", variable=self.var_conc_skew
        ).pack(anchor="w")
        tk.Checkbutton(
            clf_frame, text="kNN (concentration)", variable=self.var_knn_conc
        ).pack(anchor="w")
        tk.Checkbutton(
            clf_frame, text="Logistic Regression (concentration)", variable=self.var_lr_conc
        ).pack(anchor="w")

        # --- Plot grouping ---
        group_frame = tk.LabelFrame(self, text="Plot Grouping", padx=10, pady=5)
        group_frame.pack(fill="x", padx=10, pady=5)

        self.group_var = tk.StringVar(value="type")
        tk.Radiobutton(
            group_frame, text="Group by Sample Type", variable=self.group_var, value="type"
        ).pack(anchor="w")
        tk.Radiobutton(
            group_frame, text="Group by ROI Label", variable=self.group_var, value="label"
        ).pack(anchor="w")

        # --- OK / Cancel ---
        btn_frame = tk.Frame(self, pady=10)
        btn_frame.pack()
        tk.Button(btn_frame, text="Run Classification", width=20, command=self._ok).pack(
            side="left", padx=5
        )
        tk.Button(btn_frame, text="Cancel", width=10, command=self._cancel).pack(
            side="left", padx=5
        )

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

    # -- browse helpers --
    def _browse_train(self):
        paths = filedialog.askopenfilenames(
            title="Select TRAINING CSVs",
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

    # -- submit --
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
            "weighted": self.var_weighted.get(),
            "knn_material": self.var_knn_mat.get(),
            "lr_material": self.var_lr_mat.get(),
            "conc_skew": self.var_conc_skew.get(),
            "knn_conc": self.var_knn_conc.get(),
            "lr_conc": self.var_lr_conc.get(),
            "group_col": "ink_desc" if self.group_var.get() == "type" else "label",
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Run the classification workflow with a GUI options dialog."""
    root = tk.Tk()
    root.withdraw()

    dlg = ClassificationDialog(root)
    root.wait_window(dlg)

    opts = dlg.result
    if opts is None:
        root.destroy()
        return  # user cancelled

    group_col = opts["group_col"]
    group_label = "Sample Type" if group_col == "ink_desc" else "Sample Label"

    # ----- load data -----
    train_df = load_and_tag(opts["train_paths"])
    if train_df.empty:
        messagebox.showerror("Error", "No training data loaded.")
        root.destroy()
        return
    df = load_and_tag(opts["session_paths"])
    if df.empty:
        messagebox.showerror("Error", "No session data loaded.")
        root.destroy()
        return

    # ensure feature columns exist
    for c in FEATURE_COLS:
        train_df[c] = train_df.get(c, np.nan)
        df[c] = df.get(c, np.nan)

    # map ink_key → ink_desc
    desc_map = {
        1: "5 wt% C, petroleum",
        2: "25 wt% C, petroleum",
        3: "25 wt% C, IPA",
        4: "Sharpie (control)",
    }
    train_df["ink_key"] = train_df["ink_key"].astype(int)
    train_df["ink_desc"] = train_df["ink_key"].map(desc_map)
    df["ink_key"] = df["ink_key"].astype(int)
    df["ink_desc"] = df["ink_key"].map(desc_map)

    # detect sample types
    types = sorted(df["ink_desc"].unique())
    code_map = {
        "5 wt% C, petroleum": "petro5",
        "25 wt% C, petroleum": "petro25",
        "25 wt% C, IPA": "ipa25",
        "Sharpie (control)": "ctrl",
    }
    type_codes = [code_map.get(t, t.replace(" ", "").lower()) for t in types]
    type_str = "__".join(type_codes)
    print(f"Classifying sample types: {', '.join(types)}")

    # build unique ID
    session_id = "__".join(
        os.path.splitext(os.path.basename(p))[0] for p in opts["session_paths"]
    )
    short_id = hashlib.md5(session_id.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = f"{type_str}_{short_id}_{timestamp}"

    # ----- output directory -----
    out_base = os.path.join(os.getcwd(), "bjam_output", "classification")
    fig_dir = os.path.join(out_base, "figures")
    data_dir = os.path.join(out_base, "data")
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    # ----- auto-tune k for material kNN -----
    X_mat = train_df[FEATURE_COLS].fillna(0).values
    y_mat = (train_df["ink_key"] == 3).astype(int).values
    best_k_mat = find_best_k(X_mat, y_mat)

    # ----- classification steps -----
    dfn = None
    knn = None
    lr = None
    knn_conc = None
    lr_conc = None

    # 7) Weighted-score material
    if opts["weighted"]:
        dfn = compute_normalised_scores(df, train_df)
        df["material_score"] = dfn["material_score"]
        df["material_guess_wgt"] = classify_material(dfn)
        print("\nWeighted-score predictions:")
        print(df[["label", "material_guess_wgt"]].to_string(index=False))

    # 8) kNN material
    if opts["knn_material"]:
        knn = train_knn(train_df, FEATURE_COLS, k=best_k_mat)
        preds_knn = knn.predict(df[FEATURE_COLS].fillna(0).values)
        df["material_guess_knn"] = np.where(
            preds_knn == 1, "IPA-based", "Petroleum-based"
        )
        print("\nkNN predictions:")
        print(df[["label", "material_guess_knn"]].to_string(index=False))

    # 9) LR material
    if opts["lr_material"]:
        lr = train_lr(train_df, FEATURE_COLS)
        preds_lr = lr.predict(df[FEATURE_COLS].fillna(0).values)
        df["material_guess_lr"] = np.where(
            preds_lr == 1, "IPA-based", "Petroleum-based"
        )
        print("\nLogistic-regression predictions:")
        print(df[["label", "material_guess_lr"]].to_string(index=False))

    # 10) Concentration by skewness
    if opts["conc_skew"]:
        petro = df[df["ink_key"].isin([1, 2])].copy()
        if petro.empty:
            print("No petroleum samples.")
        else:
            petro["conc_guess"] = classify_petroleum_concentration(petro)
            print("\nConcentration (skewness) predictions:")
            print(petro[["label", "conc_guess"]].to_string(index=False))

    # auto-tune k for concentration kNN
    train_petro = train_df[train_df["ink_key"].isin([1, 2])].copy()
    best_k_conc = 3
    if not train_petro.empty:
        X_conc = train_petro[FEATURE_COLS].fillna(0).values
        y_conc = (train_petro["ink_key"] == 1).astype(int).values
        best_k_conc = find_best_k(X_conc, y_conc)

    # 11) kNN concentration
    if opts["knn_conc"]:
        if train_petro.empty:
            print("No petroleum samples in training set; skipping kNN concentration.")
        else:
            knn_conc = train_knn(train_petro, FEATURE_COLS, k=best_k_conc)
            mask = df["ink_key"].isin([1, 2])
            if mask.any():
                preds_c = knn_conc.predict(
                    df.loc[mask, FEATURE_COLS].fillna(0).values
                )
                df.loc[mask, "conc_guess_knn"] = np.where(
                    preds_c == 1, "5 wt% petroleum", "25 wt% petroleum"
                )
                print("\nConcentration (kNN) predictions:")
                print(
                    df.loc[mask, ["label", "conc_guess_knn"]].to_string(index=False)
                )

    # 12) LR concentration
    if opts["lr_conc"]:
        if train_petro.empty:
            print("No petroleum samples in training set; skipping LR concentration.")
        else:
            lr_conc = LogisticRegression(max_iter=200).fit(
                train_petro[FEATURE_COLS].fillna(0).values,
                (train_petro["ink_key"] == 1).astype(int).values,
            )
            mask = df["ink_key"].isin([1, 2])
            if mask.any():
                preds_lr_conc = lr_conc.predict(
                    df.loc[mask, FEATURE_COLS].fillna(0).values
                )
                df.loc[mask, "conc_guess_lr"] = np.where(
                    preds_lr_conc == 1, "5 wt% petroleum", "25 wt% petroleum"
                )
                print("\nConcentration (LR) predictions:")
                print(
                    df.loc[mask, ["label", "conc_guess_lr"]].to_string(index=False)
                )

    # ----- 13) Decision-region 2×2 grid -----
    _apply_cls_theme()
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    if knn:
        plot_knn_training_region(
            train_df, knn, MATERIAL_PLOT_FEATS, axes[0, 0], "kNN Material Region"
        )
        axes[0, 0].scatter(
            df["std_I"], df["tail_delta_95_99"], marker="X", c="black", label="Test"
        )
        axes[0, 0].legend(loc="best")
    if lr:
        plot_lr_training_boundary(
            train_df, lr, MATERIAL_PLOT_FEATS, axes[0, 1], "LR Material Boundary"
        )
        axes[0, 1].scatter(
            df["std_I"], df["tail_delta_95_99"], marker="X", c="black", label="Test"
        )
        axes[0, 1].legend(loc="best")
    if knn_conc:
        plot_knn_conc_region(
            train_petro, knn_conc, CONC_PLOT_FEATS, axes[1, 0],
            "kNN Concentration Region",
        )
        m = df["ink_key"].isin([1, 2])
        axes[1, 0].scatter(
            df.loc[m, CONC_PLOT_FEATS[0]],
            df.loc[m, CONC_PLOT_FEATS[1]],
            marker="X", c="black", label="Test",
        )
        axes[1, 0].legend(loc="best")
    if lr_conc:
        plot_lr_conc_contour(
            train_petro, lr_conc, CONC_PLOT_FEATS, axes[1, 1],
            "LR Concentration Boundary",
            df[df["ink_key"].isin([1, 2])],
        )
        m = df["ink_key"].isin([1, 2])
        axes[1, 1].scatter(
            df.loc[m, CONC_PLOT_FEATS[0]],
            df.loc[m, CONC_PLOT_FEATS[1]],
            marker="X", c="black", label="Test",
        )
        axes[1, 1].legend(loc="best")
    plt.tight_layout()

    fig_path = os.path.join(fig_dir, f"classification_regions_{unique_id}.png")
    fig.savefig(fig_path, dpi=300)
    print(f"Saved regions figure to {fig_path}")
    plt.show()

    # ----- 14) Error analysis & CSV export -----
    results = []
    y_mat_true = (df["ink_key"] == 3).astype(int).values
    mask_conc = df["ink_key"].isin([1, 2])
    y_conc_true = (df.loc[mask_conc, "ink_key"] == 1).astype(int).values

    if dfn is not None:
        y_pred = (df["material_guess_wgt"] == "IPA-based").astype(int).values
        prob = dfn["material_score"].values
        results.append(
            safe_metrics("weighted_score_material", y_mat_true, y_pred, prob, task="material")
        )
    if knn:
        y_pred = (df["material_guess_knn"] == "IPA-based").astype(int).values
        prob = knn.predict_proba(df[FEATURE_COLS].fillna(0).values)[:, 1]
        results.append(
            safe_metrics("knn_material", y_mat_true, y_pred, prob, task="material")
        )
    if lr:
        y_pred = (df["material_guess_lr"] == "IPA-based").astype(int).values
        prob = lr.predict_proba(df[FEATURE_COLS].fillna(0).values)[:, 1]
        results.append(
            safe_metrics("lr_material", y_mat_true, y_pred, prob, task="material")
        )
    if knn_conc is not None and "conc_guess_knn" in df.columns:
        y_pred = (
            df.loc[mask_conc, "conc_guess_knn"] == "5 wt% petroleum"
        ).astype(int).values
        proba = None
        if hasattr(knn_conc, "classes_") and len(knn_conc.classes_) > 1:
            proba = knn_conc.predict_proba(
                df.loc[mask_conc, FEATURE_COLS].fillna(0).values
            )[:, 1]
        results.append(
            safe_metrics("knn_concentration", y_conc_true, y_pred, prob=proba, task="concentration")
        )
    if lr_conc is not None and "conc_guess_lr" in df.columns:
        y_pred = (
            df.loc[mask_conc, "conc_guess_lr"] == "5 wt% petroleum"
        ).astype(int).values
        proba = None
        if hasattr(lr_conc, "classes_") and len(lr_conc.classes_) > 1:
            proba = lr_conc.predict_proba(
                df.loc[mask_conc, FEATURE_COLS].fillna(0).values
            )[:, 1]
        results.append(
            safe_metrics("lr_concentration", y_conc_true, y_pred, prob=proba, task="concentration")
        )

    csv_path = os.path.join(data_dir, f"classification_metrics_{unique_id}.csv")
    pd.DataFrame(results).to_csv(csv_path, index=False)
    print(f"Saved metrics CSV to {csv_path}")

    # ----- 15) Grouped intensity / histogram-metric plots -----
    _apply_cls_theme()

    # Seaborn boxplot of mean intensity with strip overlay
    order = df[group_col].unique().tolist()
    fig2, ax2 = plt.subplots(figsize=(max(8, len(order) * 1.5), 5))
    sns.boxplot(
        data=df, x=group_col, y="mean_I", hue=group_col,
        order=order, ax=ax2, linewidth=1.2, legend=False,
    )
    sns.stripplot(
        data=df, x=group_col, y="mean_I",
        order=order, color="0.3", size=4, alpha=0.5, ax=ax2, jitter=True,
    )
    ax2.set_title(f"Mean Intensity by {group_label}", fontweight="bold")
    ax2.set_ylabel("Mean Intensity (0-255)")
    ax2.set_xlabel("")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig2.savefig(
        os.path.join(fig_dir, f"boxplot_{unique_id}.png"),
        dpi=300, bbox_inches="tight",
    )
    plt.show()

    # Seaborn bar chart of average mean intensity by group
    fig3, ax3 = plt.subplots(figsize=(max(6, len(order) * 1.2), 4.5))
    sns.barplot(
        data=df, x=group_col, y="mean_I", hue=group_col,
        order=order, ax=ax3, errorbar="sd", capsize=0.15,
        edgecolor="white", legend=False,
    )
    ax3.set_title(f"Average Mean Intensity by {group_label}", fontweight="bold")
    ax3.set_ylabel("Mean Intensity (0-255)")
    ax3.set_xlabel("")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig3.savefig(
        os.path.join(fig_dir, f"avg_intensity_{unique_id}.png"),
        dpi=300, bbox_inches="tight",
    )
    plt.show()

    # Seaborn swarm plot of individual replicates by group
    fig4, ax4 = plt.subplots(figsize=(max(8, len(order) * 1.5), 5))
    sns.swarmplot(
        data=df, x=group_col, y="mean_I", hue=group_col,
        order=order, ax=ax4, size=6, alpha=0.8, legend=False,
    )
    ax4.set_title(
        f"Individual Replicate Mean Intensities by {group_label}",
        fontweight="bold",
    )
    ax4.set_ylabel("Mean Intensity (0-255)")
    ax4.set_xlabel("")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig4.savefig(
        os.path.join(fig_dir, f"replicates_{unique_id}.png"),
        dpi=300, bbox_inches="tight",
    )
    plt.show()

    # histogram-metric plots (now seaborn-themed via plots.py)
    labels_group = df[group_col].tolist()
    plot_spread(df["std_I"].tolist(), labels_group, save_dir=fig_dir)
    plot_iqr(df["iqr_I"].tolist(), labels_group, save_dir=fig_dir)
    plot_skewness(df["skewness_I"].tolist(), labels_group, save_dir=fig_dir)
    plot_kurtosis(df["kurtosis_I"].tolist(), labels_group, save_dir=fig_dir)
    plot_entropy(df["entropy_I"].tolist(), labels_group, save_dir=fig_dir)
    plot_pct_zero(df["pct_zero"].tolist(), labels_group, save_dir=fig_dir)
    plot_tail_delta(
        df["tail_delta_95_99"].tolist(), labels_group, save_dir=fig_dir
    )

    messagebox.showinfo(
        "Classification Complete",
        f"Results saved to:\n{out_base}\n\n"
        f"Figures: {fig_dir}\nMetrics: {csv_path}",
    )
    root.destroy()


if __name__ == "__main__":
    main()
