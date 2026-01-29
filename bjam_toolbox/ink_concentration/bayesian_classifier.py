#!/usr/bin/env python3
"""
bayesian_classifier.py — Bayesian GMM classification & GP regression for BJAM.

Implements two production-ready models validated in the exploratory notebook:

1. **BayesianGMMClassifier** — Per-class Bayesian Gaussian Mixture Model
   - n_components=1, covariance_type="full" (simplest config at 98.9% accuracy)
   - Posterior probability via Bayes' rule: P(y|x) ~ P(x|y) * P(y)
   - Built-in uncertainty via normalized posterior entropy

2. **GP Regressor** — Gaussian Process for continuous concentration estimation
   - Matern-2.5 kernel + WhiteKernel, normalize_y=True
   - LOO MAE = 0.68 wt%, calibrated 1-sigma and 2-sigma confidence bands

Workflow:
  1. User selects training CSVs and session CSVs via Tkinter dialog
  2. Fits BayesianGMMClassifier (classification) and GP Regressor (continuous)
  3. Generates publication-quality figures with seaborn:
     - Decision boundary with posterior probability contours
     - Uncertainty heatmap over feature space
     - Calibration curve (predicted vs observed)
     - Continuous concentration estimates with confidence intervals
     - Per-class posterior distributions
  4. Exports session predictions + uncertainty to CSV

All outputs go under ``bjam_output/bayesian_classification/`` in the current
working directory.

Dependencies: pandas, numpy, matplotlib, seaborn, scikit-learn
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

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.mixture import BayesianGaussianMixture
from sklearn.preprocessing import StandardScaler
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import (
    ConstantKernel,
    Matern,
    WhiteKernel,
)
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_predict, LeaveOneOut
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONC_FEATURES = [
    "std_I",
    "skewness_I",
    "kurtosis_I",
    "entropy_I",
    "pct_zero",
    "tail_delta_95_99",
]

INK_DESC = {
    1: "5 wt% C, petroleum",
    2: "25 wt% C, petroleum",
    3: "25 wt% C, IPA",
    4: "Sharpie (control)",
}
CONC_MAP = {1: 5.0, 2: 25.0, 3: 25.0}

# Seaborn theme applied at plot time (not at import)
_SNS_THEME = dict(style="whitegrid", font_scale=1.05, palette="muted")

# Class colors
CLASS_COLORS = {
    "5 wt% petro": "#e74c3c",
    "25 wt% petro": "#3498db",
    "25 wt% IPA": "#2ecc71",
}


# ---------------------------------------------------------------------------
# BayesianGMMClassifier — production version
# ---------------------------------------------------------------------------
class BayesianGMMClassifier(BaseEstimator, ClassifierMixin):
    """Per-class Bayesian Gaussian Mixture Model with posterior inference.

    Fits one BayesianGaussianMixture per class, then classifies new samples
    via Bayes' rule:  P(y|x) proportional to P(x|y) * P(y).

    Parameters
    ----------
    n_components : int, default=1
        Number of Gaussian components per class.
    covariance_type : str, default="full"
        Covariance parameterisation ("full", "tied", "diag", "spherical").
    """

    def __init__(self, n_components=1, covariance_type="full"):
        self.n_components = n_components
        self.covariance_type = covariance_type

    def fit(self, X, y):
        """Fit one BayesianGaussianMixture per class."""
        self.classes_ = np.unique(y)
        self.models_ = {}
        self.priors_ = {}
        self.scaler_ = StandardScaler().fit(X)
        X_s = self.scaler_.transform(X)

        for c in self.classes_:
            mask = y == c
            self.priors_[c] = mask.sum() / len(y)
            model = BayesianGaussianMixture(
                n_components=min(self.n_components, mask.sum()),
                covariance_type=self.covariance_type,
                random_state=42,
                max_iter=500,
            )
            model.fit(X_s[mask])
            self.models_[c] = model
        return self

    def predict_proba(self, X):
        """Return posterior class probabilities via numerically-stable softmax."""
        X_s = self.scaler_.transform(X)
        log_likes = np.column_stack(
            [
                self.models_[c].score_samples(X_s) + np.log(self.priors_[c])
                for c in self.classes_
            ]
        )
        log_likes -= log_likes.max(axis=1, keepdims=True)
        probs = np.exp(log_likes)
        probs /= probs.sum(axis=1, keepdims=True)
        return probs

    def predict(self, X):
        """Return predicted class labels."""
        probs = self.predict_proba(X)
        return self.classes_[probs.argmax(axis=1)]

    def predict_with_uncertainty(self, X):
        """Return (predictions, probabilities, uncertainty).

        Uncertainty is the normalised posterior entropy in [0, 1],
        where 0 = perfectly confident and 1 = maximally uncertain.
        """
        probs = self.predict_proba(X)
        preds = self.classes_[probs.argmax(axis=1)]
        entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)
        max_entropy = np.log(len(self.classes_))
        uncertainty = entropy / max_entropy
        return preds, probs, uncertainty


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
# Plotting helpers (seaborn-based, publication-quality)
# ---------------------------------------------------------------------------
def _apply_theme():
    """Apply the BJAM seaborn theme."""
    sns.set_theme(**_SNS_THEME)


def plot_decision_boundary(clf, X_2d, y, feat_names, save_path=None):
    """Decision boundary + posterior probability contours (2-D projection)."""
    _apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    x_min, x_max = X_2d[:, 0].min() - 0.5, X_2d[:, 0].max() + 0.5
    y_min, y_max = X_2d[:, 1].min() - 0.5, X_2d[:, 1].max() + 0.5
    xx, yy = np.meshgrid(
        np.linspace(x_min, x_max, 150),
        np.linspace(y_min, y_max, 150),
    )
    grid = np.c_[xx.ravel(), yy.ravel()]
    probs = clf.predict_proba(grid)

    # --- Left: decision boundary ---
    ax = axes[0]
    ax.contourf(
        xx,
        yy,
        probs[:, 0].reshape(xx.shape),
        levels=20,
        cmap="RdBu",
        alpha=0.4,
    )
    ax.contour(
        xx,
        yy,
        probs[:, 0].reshape(xx.shape),
        levels=[0.5],
        colors="black",
        linewidths=2,
        linestyles="--",
    )
    for label_val, color, marker, label_text in [
        (1, "#e74c3c", "o", "5 wt%"),
        (0, "#3498db", "s", "25 wt%"),
    ]:
        mask = y == label_val
        ax.scatter(
            X_2d[mask, 0],
            X_2d[mask, 1],
            c=color,
            marker=marker,
            edgecolors="k",
            s=60,
            label=label_text,
            zorder=5,
        )
    ax.set_xlabel(feat_names[0])
    ax.set_ylabel(feat_names[1])
    ax.set_title("Decision Boundary (Posterior P)")
    ax.legend(loc="best")

    # --- Right: uncertainty heatmap ---
    ax = axes[1]
    entropy = -np.sum(probs * np.log(probs + 1e-10), axis=1)
    max_entropy = np.log(probs.shape[1])
    uncertainty = (entropy / max_entropy).reshape(xx.shape)
    im = ax.contourf(xx, yy, uncertainty, levels=20, cmap="YlOrRd")
    plt.colorbar(im, ax=ax, label="Uncertainty (normalised entropy)")
    for label_val, color, marker, label_text in [
        (1, "white", "o", "5 wt%"),
        (0, "black", "s", "25 wt%"),
    ]:
        mask = y == label_val
        ax.scatter(
            X_2d[mask, 0],
            X_2d[mask, 1],
            c=color,
            marker=marker,
            edgecolors="gray",
            s=50,
            label=label_text,
            zorder=5,
        )
    ax.set_xlabel(feat_names[0])
    ax.set_ylabel(feat_names[1])
    ax.set_title("Uncertainty Map")
    ax.legend(loc="best", fontsize=8)

    fig.suptitle(
        "Bayesian GMM: Decision Boundary & Uncertainty",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_calibration(y_true, probs_cv, save_path=None):
    """Calibration curve + predicted probability histogram."""
    _apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Calibration curve
    ax = axes[0]
    prob_true, prob_pred = calibration_curve(y_true, probs_cv, n_bins=8)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect")
    ax.plot(
        prob_pred,
        prob_true,
        "o-",
        color=sns.color_palette("muted")[0],
        label="Bayesian GMM",
        markersize=7,
    )
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Calibration Curve")
    ax.legend()

    # Probability histogram
    ax = axes[1]
    for val, color, label in [
        (1, "#e74c3c", "5 wt% (true)"),
        (0, "#3498db", "25 wt% (true)"),
    ]:
        mask = y_true == val
        ax.hist(
            probs_cv[mask],
            bins=20,
            alpha=0.55,
            color=color,
            label=label,
            density=True,
            edgecolor="white",
        )
    ax.set_xlabel("Predicted P(5 wt%)")
    ax.set_ylabel("Density")
    ax.set_title("Predicted Probability Distribution")
    ax.legend()

    fig.suptitle("Model Calibration Analysis", fontsize=13, fontweight="bold")
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_gp_regression(y_true, y_pred, y_std, save_path=None):
    """LOO GP regression: predicted vs actual + uncertainty distribution."""
    _apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    mae = np.mean(np.abs(y_pred - y_true))
    rmse = np.sqrt(np.mean((y_pred - y_true) ** 2))

    # Predicted vs actual with error bars
    ax = axes[0]
    colors = ["#e74c3c" if y == 5 else "#3498db" for y in y_true]
    jitter = np.random.default_rng(42).normal(0, 0.3, len(y_true))
    ax.errorbar(
        y_true + jitter,
        y_pred,
        yerr=2 * y_std,
        fmt="none",
        ecolor="gray",
        alpha=0.3,
        capsize=2,
    )
    ax.scatter(
        y_true + jitter,
        y_pred,
        c=colors,
        s=45,
        edgecolors="k",
        zorder=5,
    )
    ax.plot([0, 30], [0, 30], "k--", alpha=0.5)
    ax.set_xlabel("True Concentration (wt%)")
    ax.set_ylabel("Predicted Concentration (wt%)")
    ax.set_title(f"LOO GP Regression (MAE = {mae:.2f} wt%)")
    ax.set_xlim(-2, 32)
    ax.set_ylim(-2, 32)

    # Uncertainty distribution by class
    ax = axes[1]
    for conc, color, label in [
        (5.0, "#e74c3c", "5 wt%"),
        (25.0, "#3498db", "25 wt%"),
    ]:
        mask = y_true == conc
        ax.hist(
            y_std[mask],
            bins=15,
            alpha=0.55,
            color=color,
            label=label,
            density=True,
            edgecolor="white",
        )
    ax.set_xlabel("Predicted Std Dev (wt%)")
    ax.set_ylabel("Density")
    ax.set_title("Uncertainty Distribution by Class")
    ax.legend()

    fig.suptitle(
        "Gaussian Process Concentration Estimation",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_confusion_matrix(y_true, y_pred, class_names, save_path=None):
    """Seaborn heatmap confusion matrix."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(6, 5))
    cm = confusion_matrix(y_true, y_pred)
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=class_names,
        yticklabels=class_names,
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix — Bayesian GMM")
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_posterior_distributions(probs, y_true, class_labels, save_path=None):
    """Per-sample posterior probability strip plot."""
    _apply_theme()
    n_classes = probs.shape[1]
    fig, axes = plt.subplots(1, n_classes, figsize=(5 * n_classes, 5), sharey=True)
    if n_classes == 1:
        axes = [axes]

    for i, (ax, cl) in enumerate(zip(axes, class_labels)):
        # Build a DataFrame for seaborn
        df_plot = pd.DataFrame(
            {
                "P(" + cl + ")": probs[:, i],
                "True class": [class_labels[int(c) - 1] if c <= len(class_labels) else str(c) for c in y_true],
            }
        )
        sns.stripplot(
            data=df_plot,
            x="True class",
            y="P(" + cl + ")",
            ax=ax,
            jitter=0.2,
            alpha=0.6,
            size=5,
        )
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(f"Posterior P({cl})")
        ax.axhline(0.5, color="gray", linestyle="--", alpha=0.5)

    fig.suptitle(
        "Per-Sample Posterior Probabilities",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


def plot_session_predictions(sess_df, save_path=None):
    """Bar chart of session predictions with uncertainty colour coding."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(max(8, len(sess_df) * 0.4), 5))

    palette = {
        "5 wt% C, petroleum": "#e74c3c",
        "25 wt% C, petroleum": "#3498db",
        "25 wt% C, IPA": "#2ecc71",
        "Sharpie (control)": "#95a5a6",
    }
    # Fall back for unknown classes
    bar_colors = [palette.get(p, "#7f8c8d") for p in sess_df["prediction"]]

    bars = ax.bar(
        range(len(sess_df)),
        sess_df["confidence"],
        color=bar_colors,
        edgecolor="white",
    )
    ax.set_xticks(range(len(sess_df)))
    ax.set_xticklabels(sess_df["label"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Prediction Confidence")
    ax.set_ylim(0, 1.05)
    ax.set_title("Session Predictions with Confidence")

    # Legend
    from matplotlib.patches import Patch

    handles = [Patch(facecolor=c, label=l) for l, c in palette.items() if l in sess_df["prediction"].values]
    if handles:
        ax.legend(handles=handles, loc="lower right", fontsize=8)

    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# GUI dialog
# ---------------------------------------------------------------------------
class BayesianClassifierDialog(tk.Toplevel):
    """Tkinter dialog for selecting training/session CSVs and run options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title("BJAM Bayesian Classification")
        self.resizable(False, False)
        self.result = None

        self.train_paths = []
        self.session_paths = []

        # --- File selection ---
        file_frame = tk.LabelFrame(self, text="Data Files", padx=10, pady=5)
        file_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(
            file_frame,
            text="Select Training CSVs",
            command=self._browse_train,
        ).pack(fill="x", pady=2)
        self.train_label = tk.Label(
            file_frame, text="No files selected", anchor="w"
        )
        self.train_label.pack(fill="x")

        tk.Button(
            file_frame,
            text="Select Session CSVs to Classify",
            command=self._browse_session,
        ).pack(fill="x", pady=2)
        self.session_label = tk.Label(
            file_frame, text="No files selected", anchor="w"
        )
        self.session_label.pack(fill="x")

        # --- Options ---
        opt_frame = tk.LabelFrame(self, text="Analysis Options", padx=10, pady=5)
        opt_frame.pack(fill="x", padx=10, pady=5)

        self.var_gp_regression = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_frame,
            text="Run GP continuous concentration estimation",
            variable=self.var_gp_regression,
        ).pack(anchor="w")

        self.var_decision_boundary = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_frame,
            text="Generate decision boundary / uncertainty plots",
            variable=self.var_decision_boundary,
        ).pack(anchor="w")

        self.var_calibration = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_frame,
            text="Generate calibration analysis plots",
            variable=self.var_calibration,
        ).pack(anchor="w")

        # --- OK / Cancel ---
        btn_frame = tk.Frame(self, pady=10)
        btn_frame.pack()
        tk.Button(
            btn_frame,
            text="Run Bayesian Classification",
            width=25,
            command=self._ok,
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame, text="Cancel", width=10, command=self._cancel
        ).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()

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
            title="Select SESSION CSVs to classify",
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
            "gp_regression": self.var_gp_regression.get(),
            "decision_boundary": self.var_decision_boundary.get(),
            "calibration": self.var_calibration.get(),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Run the Bayesian classification workflow with a GUI dialog."""
    root = tk.Tk()
    root.withdraw()

    dlg = BayesianClassifierDialog(root)
    root.wait_window(dlg)

    opts = dlg.result
    if opts is None:
        root.destroy()
        return  # user cancelled

    # ----- output directory -----
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_base = os.path.join(os.getcwd(), "bjam_output", "bayesian_classification")
    fig_dir = os.path.join(out_base, "figures")
    data_dir = os.path.join(out_base, "data")
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    # ----- load data -----
    train_df = load_and_tag(opts["train_paths"])
    if train_df.empty:
        messagebox.showerror("Error", "No training data loaded.")
        root.destroy()
        return

    sess_df = load_and_tag(opts["session_paths"])
    if sess_df.empty:
        messagebox.showerror("Error", "No session data loaded.")
        root.destroy()
        return

    # Ensure feature columns exist
    for c in CONC_FEATURES:
        train_df[c] = train_df.get(c, np.nan)
        sess_df[c] = sess_df.get(c, np.nan)

    # Map ink_key to descriptions
    train_df["ink_key"] = train_df["ink_key"].astype(int)
    train_df["ink_desc"] = train_df["ink_key"].map(INK_DESC)
    sess_df["ink_key"] = sess_df["ink_key"].astype(int)
    sess_df["ink_desc"] = sess_df["ink_key"].map(INK_DESC)

    # Detect class structure
    unique_keys = sorted(train_df["ink_key"].unique())
    n_classes = len(unique_keys)
    print(f"Training classes: {n_classes} — keys {unique_keys}")
    print(f"Training samples: {len(train_df)}")
    print(f"Session samples:  {len(sess_df)}")

    X_train = train_df[CONC_FEATURES].fillna(0).values
    y_train = train_df["ink_key"].values
    X_sess = sess_df[CONC_FEATURES].fillna(0).values

    # Build unique ID for filenames
    session_id = "__".join(
        os.path.splitext(os.path.basename(p))[0] for p in opts["session_paths"]
    )
    short_id = hashlib.md5(session_id.encode("utf-8")).hexdigest()[:8]
    unique_id = f"{short_id}_{timestamp}"

    # ================================================================
    # 1) FIT BAYESIAN GMM CLASSIFIER
    # ================================================================
    print("\n--- Fitting Bayesian GMM Classifier ---")
    clf = BayesianGMMClassifier(n_components=1, covariance_type="full")
    clf.fit(X_train, y_train)

    # Cross-validation on training data
    # Use per-class counts (ignoring unused bin-0 from bincount)
    _, class_counts = np.unique(y_train, return_counts=True)
    n_splits = min(5, int(class_counts.min()))
    n_splits = max(2, n_splits)  # at least 2-fold
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    y_pred_cv = cross_val_predict(clf, X_train, y_train, cv=cv)

    class_names = [INK_DESC.get(k, str(k)) for k in sorted(np.unique(y_train))]
    print("\nCross-Validation Classification Report:")
    print(classification_report(y_train, y_pred_cv, target_names=class_names))

    cv_acc = accuracy_score(y_train, y_pred_cv)
    print(f"CV Accuracy: {cv_acc:.3f}")

    # ---- Confusion matrix ----
    cm_path = os.path.join(fig_dir, f"confusion_matrix_{unique_id}.png")
    plot_confusion_matrix(y_train, y_pred_cv, class_names, save_path=cm_path)
    print(f"Saved: {cm_path}")

    # ---- Decision boundary (2-D projection on top-2 features by Cohen's d) ----
    if opts["decision_boundary"] and n_classes == 2:
        # Binary case: use top-2 separable features
        # Compute Cohen's d for each feature
        g1_mask = y_train == unique_keys[0]
        g2_mask = y_train == unique_keys[1]
        cohens_d = []
        for i, feat in enumerate(CONC_FEATURES):
            v1 = X_train[g1_mask, i]
            v2 = X_train[g2_mask, i]
            pooled = np.sqrt(
                ((len(v1) - 1) * v1.std() ** 2 + (len(v2) - 1) * v2.std() ** 2)
                / (len(v1) + len(v2) - 2)
            )
            d = abs(v1.mean() - v2.mean()) / pooled if pooled > 0 else 0
            cohens_d.append((feat, d))
        cohens_d.sort(key=lambda x: x[1], reverse=True)
        top2_feats = [cohens_d[0][0], cohens_d[1][0]]
        top2_idx = [CONC_FEATURES.index(f) for f in top2_feats]
        X_2d = X_train[:, top2_idx]

        clf_2d = BayesianGMMClassifier(n_components=1, covariance_type="full")
        y_binary = (y_train == unique_keys[0]).astype(int)
        clf_2d.fit(X_2d, y_binary)

        db_path = os.path.join(fig_dir, f"decision_boundary_{unique_id}.png")
        plot_decision_boundary(clf_2d, X_2d, y_binary, top2_feats, save_path=db_path)
        print(f"Saved: {db_path}")

    elif opts["decision_boundary"] and n_classes > 2:
        # Multi-class: top-2 features, train 2D model for viz only
        # Use overall variance-weighted separability
        from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        lda = LinearDiscriminantAnalysis(n_components=2)
        X_lda = lda.fit_transform(X_train, y_train)
        clf_lda_viz = BayesianGMMClassifier(n_components=1, covariance_type="full")
        clf_lda_viz.fit(X_lda, y_train)

        _apply_theme()
        fig, ax = plt.subplots(figsize=(8, 6))
        palette = sns.color_palette("Set2", n_classes)
        for i, k in enumerate(unique_keys):
            mask = y_train == k
            ax.scatter(
                X_lda[mask, 0],
                X_lda[mask, 1],
                c=[palette[i]],
                label=INK_DESC.get(k, str(k)),
                edgecolors="k",
                s=50,
                alpha=0.7,
            )
        ax.set_xlabel("LDA Component 1")
        ax.set_ylabel("LDA Component 2")
        ax.set_title("Bayesian GMM — LDA Projection")
        ax.legend(fontsize=8)
        plt.tight_layout()
        lda_path = os.path.join(fig_dir, f"lda_projection_{unique_id}.png")
        fig.savefig(lda_path, dpi=300, bbox_inches="tight")
        plt.show()
        plt.close(fig)
        print(f"Saved: {lda_path}")

    # ---- Calibration analysis ----
    if opts["calibration"] and n_classes == 2:
        try:
            y_binary = (y_train == unique_keys[0]).astype(int)
            probs_cv = cross_val_predict(
                BayesianGMMClassifier(n_components=1, covariance_type="full"),
                X_train,
                y_binary,
                cv=cv,
                method="predict_proba",
            )[:, 1]
            cal_path = os.path.join(fig_dir, f"calibration_{unique_id}.png")
            plot_calibration(y_binary, probs_cv, save_path=cal_path)
            print(f"Saved: {cal_path}")
        except Exception as e:
            print(f"Calibration plot skipped: {e}")

    # ---- Posterior distributions ----
    try:
        probs_train = cross_val_predict(
            BayesianGMMClassifier(n_components=1, covariance_type="full"),
            X_train,
            y_train,
            cv=cv,
            method="predict_proba",
        )
        post_path = os.path.join(fig_dir, f"posteriors_{unique_id}.png")
        plot_posterior_distributions(
            probs_train, y_train, class_names, save_path=post_path
        )
        print(f"Saved: {post_path}")
    except Exception as e:
        print(f"Posterior plot skipped: {e}")

    # ================================================================
    # 2) SESSION PREDICTIONS
    # ================================================================
    print("\n--- Session Predictions ---")
    preds, probs, uncertainty = clf.predict_with_uncertainty(X_sess)
    sess_df["prediction"] = [INK_DESC.get(p, str(p)) for p in preds]
    sess_df["confidence"] = probs.max(axis=1)
    sess_df["uncertainty"] = uncertainty

    # Add per-class probabilities
    for i, k in enumerate(clf.classes_):
        col_name = f"P({INK_DESC.get(k, str(k))})"
        sess_df[col_name] = probs[:, i]

    print(
        sess_df[
            ["label", "prediction", "confidence", "uncertainty"]
        ].to_string(index=False)
    )

    # Session prediction bar chart
    pred_path = os.path.join(fig_dir, f"session_predictions_{unique_id}.png")
    plot_session_predictions(sess_df, save_path=pred_path)
    print(f"Saved: {pred_path}")

    # ================================================================
    # 3) GP REGRESSION (continuous concentration estimation)
    # ================================================================
    if opts["gp_regression"]:
        # Only run GP regression on petroleum samples (where concentration varies)
        train_petro = train_df[train_df["ink_key"].isin([1, 2])].copy()
        if len(train_petro) >= 10:
            print("\n--- GP Continuous Concentration Estimation ---")
            X_reg = train_petro[CONC_FEATURES].fillna(0).values
            y_reg = train_petro["ink_key"].map(CONC_MAP).values

            kernel_reg = (
                ConstantKernel(1.0) * Matern(length_scale=1.0, nu=2.5)
                + WhiteKernel(noise_level=1.0)
            )
            gpr_pipe = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "gpr",
                        GaussianProcessRegressor(
                            kernel=kernel_reg,
                            random_state=42,
                            normalize_y=True,
                        ),
                    ),
                ]
            )

            # Leave-one-out with uncertainty
            loo = LeaveOneOut()
            y_pred_loo = np.zeros(len(y_reg))
            y_std_loo = np.zeros(len(y_reg))

            for train_idx, test_idx in loo.split(X_reg):
                gpr_pipe.fit(X_reg[train_idx], y_reg[train_idx])
                gpr = gpr_pipe.named_steps["gpr"]
                X_test_s = gpr_pipe.named_steps["scaler"].transform(
                    X_reg[test_idx]
                )
                pred, std = gpr.predict(X_test_s, return_std=True)
                y_pred_loo[test_idx] = pred
                y_std_loo[test_idx] = std

            mae = np.mean(np.abs(y_pred_loo - y_reg))
            rmse = np.sqrt(np.mean((y_pred_loo - y_reg) ** 2))
            within_1s = np.mean(np.abs(y_pred_loo - y_reg) <= y_std_loo)
            within_2s = np.mean(np.abs(y_pred_loo - y_reg) <= 2 * y_std_loo)

            print(f"LOO MAE  = {mae:.2f} wt%")
            print(f"LOO RMSE = {rmse:.2f} wt%")
            print(f"Within 1-sigma: {within_1s:.1%}")
            print(f"Within 2-sigma: {within_2s:.1%}")

            gp_path = os.path.join(fig_dir, f"gp_regression_{unique_id}.png")
            plot_gp_regression(y_reg, y_pred_loo, y_std_loo, save_path=gp_path)
            print(f"Saved: {gp_path}")

            # Apply GP to session petroleum samples
            sess_petro_mask = sess_df["ink_key"].isin([1, 2])
            if sess_petro_mask.any():
                gpr_pipe.fit(X_reg, y_reg)  # final fit on all training data
                gpr = gpr_pipe.named_steps["gpr"]
                X_sess_petro = sess_df.loc[
                    sess_petro_mask, CONC_FEATURES
                ].fillna(0).values
                X_sess_petro_s = gpr_pipe.named_steps["scaler"].transform(
                    X_sess_petro
                )
                conc_pred, conc_std = gpr.predict(
                    X_sess_petro_s, return_std=True
                )
                sess_df.loc[sess_petro_mask, "conc_gp_wt%"] = conc_pred
                sess_df.loc[sess_petro_mask, "conc_gp_std"] = conc_std
                print("\nGP concentration estimates for session petroleum samples:")
                print(
                    sess_df.loc[
                        sess_petro_mask,
                        ["label", "conc_gp_wt%", "conc_gp_std"],
                    ].to_string(index=False)
                )
        else:
            print(
                "Skipping GP regression: fewer than 10 petroleum training samples."
            )

    # ================================================================
    # 4) SAVE RESULTS
    # ================================================================
    out_cols = ["__source", "label", "ink_key", "prediction", "confidence", "uncertainty"]
    # Add probability columns
    prob_cols = [c for c in sess_df.columns if c.startswith("P(")]
    out_cols.extend(prob_cols)
    # Add GP columns if present
    if "conc_gp_wt%" in sess_df.columns:
        out_cols.extend(["conc_gp_wt%", "conc_gp_std"])

    csv_path = os.path.join(
        data_dir, f"bayesian_predictions_{unique_id}.csv"
    )
    sess_df[[c for c in out_cols if c in sess_df.columns]].to_csv(
        csv_path, index=False
    )
    print(f"\nSaved predictions CSV: {csv_path}")

    # Save metrics summary
    metrics_rows = []
    metrics_rows.append(
        {
            "model": "BayesianGMM(n=1,full)",
            "task": "classification",
            "cv_accuracy": round(cv_acc, 4),
            "n_train": len(train_df),
            "n_session": len(sess_df),
            "n_classes": n_classes,
        }
    )
    if opts["gp_regression"] and "conc_gp_wt%" in sess_df.columns:
        metrics_rows.append(
            {
                "model": "GP_Matern25",
                "task": "regression",
                "loo_mae": round(mae, 4),
                "loo_rmse": round(rmse, 4),
                "within_1sigma": round(within_1s, 4),
                "within_2sigma": round(within_2s, 4),
            }
        )
    metrics_path = os.path.join(data_dir, f"bayesian_metrics_{unique_id}.csv")
    pd.DataFrame(metrics_rows).to_csv(metrics_path, index=False)
    print(f"Saved metrics CSV: {metrics_path}")

    messagebox.showinfo(
        "Bayesian Classification Complete",
        f"Results saved to:\n{out_base}\n\n"
        f"Figures: {fig_dir}\n"
        f"Predictions: {csv_path}\n"
        f"Metrics: {metrics_path}",
    )
    root.destroy()


if __name__ == "__main__":
    main()
