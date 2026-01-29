#!/usr/bin/env python3
"""
menu.py — Tkinter launcher for the Ink Concentration analysis modes.

Presents a menu with four mode buttons:
  1. Data Collection  (active — launches the ROI + analysis pipeline)
  2. Classification    (coming soon)
  3. Plotting          (coming soon)
  4. Concentration Estimation (coming soon)

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
        pady=(0, 10),
    )
    subtitle.pack(fill="x")

    # ── Button frame ────────────────────────────────────────
    btn_frame = tk.Frame(root, padx=20, pady=10)
    btn_frame.pack(fill="both", expand=True)

    btn_width = 35

    # 1) Data Collection — active
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

    # 2) Classification — stub
    def _stub_classification():
        messagebox.showinfo(
            "Coming Soon",
            "Classification mode is not yet implemented.\n\n"
            "Planned features:\n"
            "  • Weighted model\n"
            "  • k-NN model\n"
            "  • Logistic regression model\n"
            "  • Concentration by skewness\n"
            "  • Group plots by sample type or ROI label",
        )

    tk.Button(
        btn_frame,
        text="Classification  (Coming Soon)",
        width=btn_width,
        height=2,
        command=_stub_classification,
        state="normal",
    ).pack(pady=5)

    # 3) Plotting — stub
    def _stub_plotting():
        messagebox.showinfo(
            "Coming Soon",
            "Plotting mode is not yet implemented.\n\n"
            "Planned features:\n"
            "  • Group plots by sample type\n"
            "  • Group plots by ROI label\n"
            "  • Custom plot export",
        )

    tk.Button(
        btn_frame,
        text="Plotting  (Coming Soon)",
        width=btn_width,
        height=2,
        command=_stub_plotting,
        state="normal",
    ).pack(pady=5)

    # 4) Concentration Estimation — stub
    def _stub_concentration():
        messagebox.showinfo(
            "Coming Soon",
            "Concentration Estimation mode is not yet implemented.\n\n"
            "Planned features:\n"
            "  • Select training data CSV\n"
            "  • Select session CSV for classification\n"
            "  • Run concentration estimate",
        )

    tk.Button(
        btn_frame,
        text="Concentration Estimation  (Coming Soon)",
        width=btn_width,
        height=2,
        command=_stub_concentration,
        state="normal",
    ).pack(pady=5)

    # ── Quit button ─────────────────────────────────────────
    tk.Button(
        btn_frame,
        text="Quit",
        width=btn_width,
        command=root.destroy,
    ).pack(pady=(15, 5))

    root.mainloop()


if __name__ == "__main__":
    main()
