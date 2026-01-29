#!/usr/bin/env python3
"""
plots.py — Matplotlib plotting for BJAM ROI tool, with saving and multi-metric visualization
"""

import os
import matplotlib.pyplot as plt

# Always show figures in interactive windows
SHOW_FIGURES = True


def _plot_metric(values, labels, title, ylabel, save_dir=None, filename=None):
    """Generic bar plot for a list of values and labels."""
    fig, ax = plt.subplots()
    ax.bar(labels, values, edgecolor='black')
    ax.set_title(title)
    ax.set_xlabel('Sample Label')
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300)
    # always show
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_histogram(intensities, label, save_dir=None):
    """Show and optionally save histogram of pixel intensities."""
    fig, ax = plt.subplots()
    ax.hist(intensities, bins=256, edgecolor='black')
    ax.set_title(f'Intensity Histogram: {label}')
    ax.set_xlabel('Pixel Intensity')
    ax.set_ylabel('Frequency')
    plt.tight_layout()
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, f'hist_{label}.png'), dpi=300)
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_boxplot(means, labels, save_dir=None, filename='boxplot.png'):
    """Show and optionally save boxplot of mean intensities."""
    fig, ax = plt.subplots()
    ax.boxplot(means, labels=labels)
    ax.set_title('Mean Intensity Boxplot')
    ax.set_ylabel('Mean Intensity')
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300)
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_area_histogram(areas, save_dir=None, filename='area_hist.png'):
    """Show and optionally save ROI area distribution histogram."""
    fig, ax = plt.subplots()
    ax.hist(areas, bins=20, edgecolor='black')
    ax.set_title('ROI Area Distribution')
    ax.set_xlabel('Area (px²)')
    ax.set_ylabel('Count')
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300)
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_area_vs_intensity(areas, means, save_dir=None, filename='area_vs_intensity.png'):
    """Show and optionally save scatter of area vs mean intensity."""
    fig, ax = plt.subplots()
    ax.scatter(areas, means)
    ax.set_title('Area vs. Mean Intensity')
    ax.set_xlabel('Area (px²)')
    ax.set_ylabel('Mean Intensity')
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300)
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_circularity_vs_intensity(circs, means, save_dir=None, filename='circ_vs_intensity.png'):
    """Show and optionally save scatter of circularity vs mean intensity."""
    fig, ax = plt.subplots()
    ax.scatter(circs, means)
    ax.set_title('Circularity vs. Mean Intensity')
    ax.set_xlabel('Circularity')
    ax.set_ylabel('Mean Intensity')
    plt.tight_layout()
    if save_dir and filename:
        os.makedirs(save_dir, exist_ok=True)
        fig.savefig(os.path.join(save_dir, filename), dpi=300)
    if SHOW_FIGURES:
        plt.show()
    plt.close(fig)


def plot_spread(stds, labels, save_dir=None, filename='spread_std.png'):
    """Bar chart comparing standard deviations of intensity distributions."""
    _plot_metric(
        values=stds,
        labels=labels,
        title='Histogram Spread (Std Dev)',
        ylabel='Standard Deviation',
        save_dir=save_dir,
        filename=filename
    )


def plot_iqr(iqrs, labels, save_dir=None, filename='iqr.png'):
    """Bar chart comparing interquartile range of intensity distributions."""
    _plot_metric(
        values=iqrs,
        labels=labels,
        title='Histogram IQR',
        ylabel='IQR',
        save_dir=save_dir,
        filename=filename
    )


def plot_skewness(skews, labels, save_dir=None, filename='skewness.png'):
    """Bar chart comparing skewness of intensity distributions."""
    _plot_metric(
        values=skews,
        labels=labels,
        title='Histogram Skewness',
        ylabel='Skewness',
        save_dir=save_dir,
        filename=filename
    )


def plot_kurtosis(kurts, labels, save_dir=None, filename='kurtosis.png'):
    """Bar chart comparing kurtosis of intensity distributions."""
    _plot_metric(
        values=kurts,
        labels=labels,
        title='Histogram Kurtosis',
        ylabel='Kurtosis',
        save_dir=save_dir,
        filename=filename
    )


def plot_entropy(entropies, labels, save_dir=None, filename='entropy.png'):
    """Bar chart comparing entropy of intensity distributions."""
    _plot_metric(
        values=entropies,
        labels=labels,
        title='Histogram Entropy',
        ylabel='Entropy (bits)',
        save_dir=save_dir,
        filename=filename
    )


def plot_pct_zero(pct_zeros, labels, save_dir=None, filename='pct_zero.png'):
    """Bar chart of fraction of zero-intensity pixels per ROI."""
    _plot_metric(
        values=pct_zeros,
        labels=labels,
        title='Fraction of Zero-Intensity Pixels',
        ylabel='Fraction == 0',
        save_dir=save_dir,
        filename=filename
    )


def plot_tail_delta(delta_vals, labels, save_dir=None, filename='tail_delta_95_99.png'):
    """Bar chart of 95th→99th percentile intensity spread per ROI."""
    _plot_metric(
        values=delta_vals,
        labels=labels,
        title='95th→99th Percentile Intensity Spread',
        ylabel='Intensity Δ',
        save_dir=save_dir,
        filename=filename
    )
