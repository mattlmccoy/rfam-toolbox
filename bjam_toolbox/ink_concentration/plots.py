#!/usr/bin/env python3
"""
plots.py — Seaborn/Matplotlib plotting for BJAM ROI tool.

Provides publication-quality visualisations of per-ROI histogram metrics
with consistent theming across the ink-concentration analysis suite.
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# Always show figures in interactive windows
SHOW_FIGURES = True

# Consistent BJAM theme applied before every plot
_THEME = dict(style="whitegrid", font_scale=1.05, palette="muted")

# Standard colour palette for ink types
INK_PALETTE = {
    "5 wt% C, petroleum": "#e74c3c",
    "25 wt% C, petroleum": "#3498db",
    "25 wt% C, IPA": "#2ecc71",
    "Sharpie (control)": "#95a5a6",
}


def _apply_theme():
    """Apply the shared BJAM seaborn theme."""
    sns.set_theme(**_THEME)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def _plot_metric(values, labels, title, ylabel, save_dir=None, filename=None):
    """Seaborn-styled bar plot for a list of values and labels.

    If *labels* contains repeated entries (e.g. grouped by sample type), the
    bars are automatically coloured by label using the INK_PALETTE.
    """
    _apply_theme()
    import pandas as pd

    df = pd.DataFrame({"label": labels, "value": values})
    fig, ax = plt.subplots(figsize=(max(6, len(set(labels)) * 0.8), 5))

    # Determine if labels map to known ink types for colour coding
    unique_labels = list(dict.fromkeys(labels))  # preserve order
    palette = None
    if any(l in INK_PALETTE for l in unique_labels):
        palette = {l: INK_PALETTE.get(l, "#7f8c8d") for l in unique_labels}

    sns.barplot(
        data=df,
        x="label",
        y="value",
        hue="label",
        palette=palette,
        edgecolor="white",
        ax=ax,
        legend=False,
        errorbar=("sd", 1),
    )
    ax.set_title(title, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300, bbox_inches="tight")
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Individual plot functions
# ---------------------------------------------------------------------------
def plot_histogram(intensities, label, save_dir=None):
    """Seaborn-styled histogram of pixel intensities."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.histplot(
        intensities,
        bins=256,
        kde=True,
        color=sns.color_palette("muted")[0],
        edgecolor="white",
        ax=ax,
    )
    ax.set_title(f"Intensity Histogram: {label}", fontweight="bold")
    ax.set_xlabel("Pixel Intensity")
    ax.set_ylabel("Frequency")
    plt.tight_layout()
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(
            os.path.join(save_dir, f"hist_{label}.png"),
            dpi=300,
            bbox_inches="tight",
        )
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_boxplot(means, labels, save_dir=None, filename="boxplot.png"):
    """Seaborn-styled boxplot of mean intensities."""
    _apply_theme()
    import pandas as pd

    df = pd.DataFrame({"Group": labels, "Mean Intensity": means})
    fig, ax = plt.subplots(figsize=(max(6, len(set(labels)) * 0.8), 5))

    unique_labels = list(dict.fromkeys(labels))
    palette = None
    if any(l in INK_PALETTE for l in unique_labels):
        palette = {l: INK_PALETTE.get(l, "#7f8c8d") for l in unique_labels}

    sns.boxplot(
        data=df,
        x="Group",
        y="Mean Intensity",
        hue="Group",
        palette=palette,
        ax=ax,
        legend=False,
        linewidth=1.2,
    )
    sns.stripplot(
        data=df,
        x="Group",
        y="Mean Intensity",
        color="0.3",
        size=4,
        alpha=0.5,
        ax=ax,
        jitter=True,
    )
    ax.set_title("Mean Intensity Boxplot", fontweight="bold")
    ax.set_ylabel("Mean Intensity (0-255)")
    ax.set_xlabel("")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(
            os.path.join(save_dir, filename), dpi=300, bbox_inches="tight"
        )
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_area_histogram(areas, save_dir=None, filename="area_hist.png"):
    """Seaborn-styled ROI area distribution histogram."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.histplot(
        areas,
        bins=20,
        kde=True,
        color=sns.color_palette("muted")[1],
        edgecolor="white",
        ax=ax,
    )
    ax.set_title("ROI Area Distribution", fontweight="bold")
    ax.set_xlabel("Area (px\u00b2)")
    ax.set_ylabel("Count")
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(
            os.path.join(save_dir, filename), dpi=300, bbox_inches="tight"
        )
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_area_vs_intensity(
    areas, means, save_dir=None, filename="area_vs_intensity.png"
):
    """Seaborn-styled scatter of area vs mean intensity."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.scatterplot(
        x=areas,
        y=means,
        ax=ax,
        s=50,
        edgecolor="white",
        alpha=0.7,
    )
    ax.set_title("Area vs. Mean Intensity", fontweight="bold")
    ax.set_xlabel("Area (px\u00b2)")
    ax.set_ylabel("Mean Intensity")
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(
            os.path.join(save_dir, filename), dpi=300, bbox_inches="tight"
        )
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_circularity_vs_intensity(
    circs, means, save_dir=None, filename="circ_vs_intensity.png"
):
    """Seaborn-styled scatter of circularity vs mean intensity."""
    _apply_theme()
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.scatterplot(
        x=circs,
        y=means,
        ax=ax,
        s=50,
        edgecolor="white",
        alpha=0.7,
    )
    ax.set_title("Circularity vs. Mean Intensity", fontweight="bold")
    ax.set_xlabel("Circularity")
    ax.set_ylabel("Mean Intensity")
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(
            os.path.join(save_dir, filename), dpi=300, bbox_inches="tight"
        )
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Histogram-metric bar plots (delegates to _plot_metric)
# ---------------------------------------------------------------------------
def plot_spread(stds, labels, save_dir=None, filename="spread_std.png"):
    """Bar chart comparing standard deviations of intensity distributions."""
    _plot_metric(
        values=stds,
        labels=labels,
        title="Histogram Spread (Std Dev)",
        ylabel="Standard Deviation",
        save_dir=save_dir,
        filename=filename,
    )


def plot_iqr(iqrs, labels, save_dir=None, filename="iqr.png"):
    """Bar chart comparing interquartile range of intensity distributions."""
    _plot_metric(
        values=iqrs,
        labels=labels,
        title="Histogram IQR",
        ylabel="IQR",
        save_dir=save_dir,
        filename=filename,
    )


def plot_skewness(skews, labels, save_dir=None, filename="skewness.png"):
    """Bar chart comparing skewness of intensity distributions."""
    _plot_metric(
        values=skews,
        labels=labels,
        title="Histogram Skewness",
        ylabel="Skewness",
        save_dir=save_dir,
        filename=filename,
    )


def plot_kurtosis(kurts, labels, save_dir=None, filename="kurtosis.png"):
    """Bar chart comparing kurtosis of intensity distributions."""
    _plot_metric(
        values=kurts,
        labels=labels,
        title="Histogram Kurtosis",
        ylabel="Kurtosis",
        save_dir=save_dir,
        filename=filename,
    )


def plot_entropy(entropies, labels, save_dir=None, filename="entropy.png"):
    """Bar chart comparing entropy of intensity distributions."""
    _plot_metric(
        values=entropies,
        labels=labels,
        title="Histogram Entropy",
        ylabel="Entropy (bits)",
        save_dir=save_dir,
        filename=filename,
    )


def plot_pct_zero(pct_zeros, labels, save_dir=None, filename="pct_zero.png"):
    """Bar chart of fraction of zero-intensity pixels per ROI."""
    _plot_metric(
        values=pct_zeros,
        labels=labels,
        title="Fraction of Zero-Intensity Pixels",
        ylabel="Fraction == 0",
        save_dir=save_dir,
        filename=filename,
    )


def plot_tail_delta(
    delta_vals, labels, save_dir=None, filename="tail_delta_95_99.png"
):
    """Bar chart of 95th to 99th percentile intensity spread per ROI."""
    _plot_metric(
        values=delta_vals,
        labels=labels,
        title="95th\u219999th Percentile Intensity Spread",
        ylabel="Intensity \u0394",
        save_dir=save_dir,
        filename=filename,
    )
