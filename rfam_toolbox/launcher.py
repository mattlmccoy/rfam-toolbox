#!/usr/bin/env python3
"""
rfam_launcher.py — unified entry point for the RFAM analysis toolkit.

This script provides a simple graphical prompt for users to choose
between the original ROI‑based ink concentration workflow and the
dimensional analysis workflow.  On launch, a small Tkinter dialog
asks which analysis to run.  Depending on the selection, the
corresponding module's ``main`` function is invoked.  This keeps
both workflows accessible through a single top‑level entry point
without removing any existing functionality.

Usage::

    python rfam_launcher.py

The launcher uses message boxes for simplicity; it does not
interfere with the individual GUIs of the respective workflows.
"""
import tkinter as tk
from tkinter import messagebox


def main() -> None:
    """Prompt the user to choose a workflow and dispatch accordingly."""
    # Create a hidden root window for the dialog
    root = tk.Tk()
    root.withdraw()
    # Ask the user which analysis to run.  A Yes/No question is
    # sufficient: Yes → dimensional analysis, No → ink concentration.
    choice = messagebox.askquestion(
        "Select Analysis",
        "Would you like to run the dimensional analysis workflow?\n"
        "(Selecting 'No' will run the ink concentration/ROI workflow.)",
        icon='question'
    )
    # Destroy the root window immediately to avoid interfering with other GUIs
    root.destroy()
    # Dispatch based on choice.  Use local imports to avoid circular
    # dependency issues.
    if choice == 'yes':
        # When the user chooses dimensional analysis, invoke the
        # GUI-based dimensional workflow defined in the dimensional subpackage.
        try:
            from rfam_toolbox.dimensional.gui import run_dimensional_analysis
            run_dimensional_analysis()
        except Exception as e:
            print("Error launching dimensional analysis:", e)
            raise
    else:
        # For any other choice (No), fall back to the original ROI tool.
        try:
            from rfam_toolbox.ink_concentration.main import main as roi_main
            roi_main()
        except Exception as e:
            print("Error launching ink concentration workflow:", e)
            raise


if __name__ == '__main__':
    main()