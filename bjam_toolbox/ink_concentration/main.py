#!/usr/bin/env python3
"""
main.py — orchestrates GUI, analysis, and data export for BJAM ROI tool with extended metrics and organized figure output at 300 dpi
"""
import os
import cv2
import matplotlib.pyplot as plt
from datetime import datetime

from bjam_toolbox.ink_concentration.gui import main as gui_main
from bjam_toolbox.ink_concentration.analyzer import compute_metrics, threshold_image
import numpy as np
from bjam_toolbox.common.dataio import build_dataframe, export_csv
from bjam_toolbox.ink_concentration.plots import (
    plot_histogram,
    plot_boxplot,
    plot_area_histogram,
    plot_area_vs_intensity,
    plot_circularity_vs_intensity,
    plot_spread,
    plot_iqr,
    plot_skewness,
    plot_kurtosis,
    plot_entropy,
    plot_pct_zero,
    plot_tail_delta
)


def main():
    """Run the BJAM ROI selection and analysis pipeline.

    This function orchestrates the ROI selection, metric computation and
    plotting for a single session.  A full‐resolution copy of the input
    image is always preserved and never modified in place.  Downsampled
    versions of the image are created on the fly for display and
    visualisation only.  Heatmaps are generated from a copy of the
    full‐resolution ROI and can optionally be downsampled to reduce
    file size.  The original input file on disk is never overwritten.
    """
    # Launch the GUI to collect user‐defined ROIs and analysis flags
    session = gui_main()
    if not session or not session.get('rois'):
        print("No ROIs collected; exiting.")
        return

    # Ask whether to display figures during analysis via a GUI dialog.
    # Figures are always saved to disk regardless of the choice.
    import tkinter as _tk
    from tkinter import messagebox as _mb
    _root = _tk.Tk()
    _root.withdraw()
    show_figs = _mb.askyesno(
        "Display Figures",
        "Show figures during analysis?\n(Figures are always saved to disk.)",
    )
    _root.destroy()
    if not show_figs:
        from bjam_toolbox.ink_concentration import plots  # late import to avoid circular dependency
        plots.SHOW_FIGURES = False

    # Reload the original image from disk.  Reading the file again
    # guarantees that we operate on an unmodified, full‐resolution copy.
    img_path = session['file_path']
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"Failed to reload image from {img_path}; exiting.")
        return

    # Make an explicit copy of the full‐resolution image.  All
    # computations and visualisations will use this copy to avoid
    # inadvertently modifying the original array returned by cv2.imread().
    img_full = img.copy()

    # Prepare output directories
    outdir = os.path.join(os.path.dirname(__file__), 'session_data')
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    flags = session['analysis']
    conv_flag = session.get('conversion_used', False)
    session_id = f"{ts}_I{int(flags['intensity'])}_S{int(flags['shape'])}_H{int(flags['halo'])}_C{int(conv_flag)}"
    fig_dir = os.path.join(outdir, 'figures', session_id)
    os.makedirs(fig_dir, exist_ok=True)



    # We no longer precompute a grayscale image or global threshold mask.
    # Each ROI will perform its own conversion and thresholding.

    # Results list will hold per–ROI dictionaries returned by compute_metrics
    results = []
    # This scale factor comes from the GUI and is used only for
    # converting display coordinates back to full resolution.  It may
    # be less than 1 for very large images.  Do not reuse this value
    # for downsampling ROIs in the heatmap; see `heatmap_scale` below.
    display_scale = session['scale']

    # Define a separate downsample factor for heatmap images.  A value
    # of 1.0 means heatmaps are saved at full resolution.  To reduce
    # file sizes you can set this to a number between 0 and 1 (e.g. 0.5).
    heatmap_scale = 1.0

    for roi in session['rois']:
        metrics = compute_metrics(
            image=img_full,
            roi=roi,
            px_per_mm=session['px_per_mm'],
            do_intensity=session['analysis']['intensity'],
            do_shape=session['analysis']['shape'],
            do_halo=session['analysis']['halo']
        )
        # Augment metrics with ROI metadata (label, ink key, replicate)
        metrics.update({
            'label': roi['label'],
            'ink_key': roi['ink_key'],
            'rep': roi['rep'],
            'mask_full': metrics.get('mask_full')
        })
        # Keep the intensity_pixels as returned from compute_metrics.  This
        # field will contain a NumPy array of intensities; pandas
        # truncates its representation when writing to CSV.  We no longer
        # write the full array to a separate file to reduce overhead.

        results.append(metrics)
        mask = metrics.get('mask_full')
        # When a mask is available we generate a heatmap image around
        # the bounding box of the object.  We avoid mutating the
        # full‐resolution image by working on a fresh slice.
        if mask is not None:
            ys, xs = np.nonzero(mask)
            # Compute bounding box of the object mask
            y0, y1 = ys.min(), ys.max()
            x0, x1 = xs.min(), xs.max()
            # Pad the box by a fixed number of pixels on all sides
            pad = 1000
            y0p, y1p = max(0, y0 - pad), min(img_full.shape[0] - 1, y1 + pad)
            x0p, x1p = max(0, x0 - pad), min(img_full.shape[1] - 1, x1 + pad)
            # Extract a copy of the ROI from the full‐resolution image
            crop = img_full[y0p:y1p + 1, x0p:x1p + 1].copy()
            # Convert to grayscale if needed
            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.copy()
            # Optionally downsample the crop for the heatmap.  We never
            # overwrite `gray_crop`; instead we write to `gray_ds`.
            if heatmap_scale != 1.0:
                new_w = max(1, int(gray_crop.shape[1] * heatmap_scale))
                new_h = max(1, int(gray_crop.shape[0] * heatmap_scale))
                gray_ds = cv2.resize(gray_crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                gray_ds = gray_crop
            # Normalise to 0–255 for display.  Again, we operate on a
            # copy to avoid modifying gray_ds in place.
            norm = cv2.normalize(gray_ds, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            # Create a heatmap figure
            fig, ax = plt.subplots(figsize=(5, 5))
            hm = ax.imshow(norm, cmap='viridis', vmin=norm.min(), vmax=norm.max(), aspect='equal')
            cbar = fig.colorbar(hm, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Pixel Intensity (0–255)')
            mean_val = metrics.get('mean_I')
            if mean_val is not None:
                cbar.ax.hlines(mean_val, *cbar.ax.get_xlim(), colors='white', linestyles='--', linewidth=1)
                cbar.ax.text(cbar.ax.get_xlim()[1], mean_val, f' μ={mean_val:.1f}', va='center', ha='left', color='white', fontsize=8)
            ax.set_title(f'ROI Heatmap: {roi["label"]}')
            ax.axis('off')
            # Save heatmap image.  The DPI setting will control the
            # resolution of the saved PNG; using 300 is generally
            # sufficient for publication.  We never write back to the
            # original input file.
            fig.savefig(os.path.join(fig_dir, f'heatmap_{roi["label"]}.png'), dpi=300)
            plt.close(fig)

    labels = [r['label'] for r in results if r.get('intensity_pixels') is not None]
    arrays = [r['intensity_pixels'] for r in results if r.get('intensity_pixels') is not None]
    for arr, lbl in zip(arrays, labels):
        plot_histogram(arr, lbl, save_dir=fig_dir)

    mean_vals = [r['mean_I'] for r in results if r.get('mean_I') is not None]
    mean_labels = [r['label'] for r in results if r.get('mean_I') is not None]
    if mean_vals:
        # new — pass save_dir + filename
        plot_boxplot(
            [[v] for v in mean_vals],
            mean_labels,
            save_dir=fig_dir,
            filename='mean_boxplot.png'
        )

    areas = [r['area_px'] for r in results if r.get('area_px') is not None]
    if areas:
        plot_area_histogram(areas, save_dir=fig_dir)
    if areas and mean_vals:
        plot_area_vs_intensity(areas, mean_vals, save_dir=fig_dir)

    if session['analysis']['shape']:
        circs = [r['circularity'] for r in results if r.get('circularity') is not None]
        if circs and mean_vals:
            plot_circularity_vs_intensity(circs, mean_vals, save_dir=fig_dir)

    stds  = [r['std_I'] for r in results if r.get('std_I') is not None]
    iqrs  = [r['iqr_I'] for r in results if r.get('iqr_I') is not None]
    skews = [r['skewness_I'] for r in results if r.get('skewness_I') is not None]
    kurts = [r['kurtosis_I'] for r in results if r.get('kurtosis_I') is not None]
    ents  = [r['entropy_I'] for r in results if r.get('entropy_I') is not None]
    if stds:  plot_spread(stds,  labels, save_dir=fig_dir)
    if iqrs:  plot_iqr(iqrs,  labels, save_dir=fig_dir)
    if skews: plot_skewness(skews, labels, save_dir=fig_dir)
    if kurts: plot_kurtosis(kurts, labels, save_dir=fig_dir)
    if ents:  plot_entropy(ents, labels, save_dir=fig_dir)

    # 9) Zero-fraction & tail-delta plots
    pct_zeros   = [r['pct_zero'] for r in results if r.get('pct_zero') is not None]
    tail_deltas = [r['tail_delta_95_99'] for r in results if r.get('tail_delta_95_99') is not None]
    labels_zero = [r['label'] for r in results if r.get('pct_zero') is not None]
    if pct_zeros:
        plot_pct_zero(pct_zeros, labels_zero, save_dir=fig_dir)
    if tail_deltas:
        plot_tail_delta(tail_deltas, labels_zero, save_dir=fig_dir)

    metadata = {
        'analysis_intensity': session['analysis']['intensity'],
        'analysis_shape':     session['analysis']['shape'],
        'analysis_halo':      session['analysis']['halo'],
        'conversion_used':    session['conversion_used'],
    }
    df = build_dataframe(results, metadata)
    csv_path = export_csv(df, outdir)
    print(f"Results written to {csv_path}")

    try:
        # Resize the full‐resolution image for display.  The display_scale
        # factor comes from the GUI and is used solely for visualising
        # contours; it should never be reused for analysis or heatmaps.
        if display_scale != 1.0:
            vis = cv2.resize(img_full, (int(img_full.shape[1] * display_scale), int(img_full.shape[0] * display_scale)), interpolation=cv2.INTER_AREA)
        else:
            vis = img_full.copy()
        # Ensure the image has three colour channels so contours appear in green
        if vis.ndim == 2:
            vis_color = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
        elif vis.shape[2] == 4:
            vis_color = cv2.cvtColor(vis, cv2.COLOR_BGRA2BGR)
        else:
            vis_color = vis.copy()
        # Draw contours scaled to the display resolution
        for r in results:
            for cnt in r.get('contours', []):
                cnt_disp = (cnt * display_scale).astype(int)
                cv2.drawContours(vis_color, [cnt_disp], -1, (0, 255, 0), 2)
        cv2.imshow('Object Outlines', vis_color)
        print("Press 'q' or ESC to close outlines.")
        while True:
            # Break the loop when the user presses 'q' or ESC
            key = cv2.waitKey(0) & 0xFF
            if key in (ord('q'), 27):
                break
        cv2.destroyWindow('Object Outlines')
    except Exception as e:
        print(f"Note: could not display outlines: {e}")

if __name__ == "__main__":
    main()
