#!/usr/bin/env python3
"""
bjam_launcher.py — unified entry point for the BJAM analysis toolkit.

This script provides a simple graphical prompt for users to choose
between the original ROI‑based ink concentration workflow and the
dimensional analysis workflow.  On launch, a small Tkinter dialog
asks which analysis to run.  Depending on the selection, the
corresponding module's ``main`` function is invoked.  This keeps
both workflows accessible through a single top‑level entry point
without removing any existing functionality.

Usage::

    bjam-toolbox
    python -m bjam_toolbox

The launcher uses message boxes for simplicity; it does not
interfere with the individual GUIs of the respective workflows.
"""
import sys
import tkinter as tk
from tkinter import messagebox


def main() -> None:
    """Prompt the user to choose a workflow and dispatch accordingly."""
    # Handle --version flag
    if "--version" in sys.argv or "-V" in sys.argv:
        from bjam_toolbox import __version__
        print(f"bjam-toolbox {__version__}")
        return

    # Handle --show-config flag
    if "--show-config" in sys.argv:
        from bjam_toolbox.defaults.config_loader import config_path
        path = config_path()
        print(f"Config file: {path}")
        with open(path, "r", encoding="utf-8") as f:
            print(f.read())
        return

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
            from bjam_toolbox.dimensional.gui import main as dimensional_main
            dimensional_main()
        except Exception as e:
            print("Error launching dimensional analysis:", e)
            raise
    else:
        # Launch the ink concentration mode-selection menu.
        try:
            from bjam_toolbox.ink_concentration.menu import main as ic_menu
            ic_menu()
        except Exception as e:
            print("Error launching ink concentration workflow:", e)
            raise


if __name__ == '__main__':
    main()