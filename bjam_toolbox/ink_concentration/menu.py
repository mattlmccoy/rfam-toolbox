#!/usr/bin/env python3
"""
menu.py — Tkinter launcher for the Ink Concentration analysis modes.

Presents a menu with four mode buttons:
  1. Data Collection   — launches the ROI + analysis pipeline
  2. Classification    — material & concentration classifiers
  3. Plotting          — grouped intensity / histogram-metric plots
  4. Concentration Estimation — isotonic + kNN regression estimator

This replaces the previous direct-launch behaviour so users see
the available modes before entering a workflow.
"""

import tkinter as tk
from tkinter import messagebox


def main():
    """Show the ink concentration mode-selection window."""
    root = tk.Tk()
    root.title("BJAM Ink Concentration Analyzer")
    root.resizable(False, False)

    # ── Header ──────────────────────────────────────────────
    header = tk.Label(
        root,
        text="Ink Concentration Analysis",
        font=("Helvetica", 16, "bold"),
        pady=10,
    )
    header.pack(fill="x")

    subtitle = tk.Label(
        root,
        text="Select an analysis mode to begin.",
        font=("Helvetica", 11),
    )
    subtitle.pack(fill="x", pady=(0, 10))

    # ── Button frame ────────────────────────────────────────
    btn_frame = tk.Frame(root, padx=20, pady=10)
    btn_frame.pack(fill="both", expand=True)

    btn_width = 35

    # 1) Data Collection
    def _launch_data_collection():
        root.destroy()
        from bjam_toolbox.ink_concentration.main import main as dc_main
        dc_main()

    tk.Button(
        btn_frame,
        text="Data Collection",
        width=btn_width,
        height=2,
        command=_launch_data_collection,
    ).pack(pady=5)

    # 2) Classification
    def _launch_classification():
        root.destroy()
        from bjam_toolbox.ink_concentration.classification import main as cls_main
        cls_main()

    tk.Button(
        btn_frame,
        text="Classification",
        width=btn_width,
        height=2,
        command=_launch_classification,
    ).pack(pady=5)

    # 3) Plotting (Coming Soon — plotting is embedded in Classification)
    def _stub_plotting():
        messagebox.showinfo(
            "Plotting",
            "Plotting is currently integrated into the Classification mode.\n\n"
            "Run Classification to generate grouped plots by sample type "
            "or ROI label.\n\n"
            "A standalone plotting mode is planned for a future release.",
        )

    tk.Button(
        btn_frame,
        text="Plotting  (see Classification)",
        width=btn_width,
        height=2,
        command=_stub_plotting,
    ).pack(pady=5)

    # 4) Concentration Estimation
    def _launch_concentration():
        root.destroy()
        from bjam_toolbox.ink_concentration.concentration_estimator import (
            main as ce_main,
        )
        ce_main()

    tk.Button(
        btn_frame,
        text="Concentration Estimation",
        width=btn_width,
        height=2,
        command=_launch_concentration,
    ).pack(pady=5)

    # ── Quit button ─────────────────────────────────────────
    tk.Button(
        btn_frame,
        text="Quit",
        width=btn_width,
        command=root.destroy,
    ).pack(pady=15)

    root.mainloop()


if __name__ == "__main__":
    main()
