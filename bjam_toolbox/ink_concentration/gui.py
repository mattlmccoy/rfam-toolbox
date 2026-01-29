#!/usr/bin/env python3

"""
GUI for ROI drawing and labeling for the BJAM analysis tool.

This module provides an interactive interface to select regions of interest
(ROIs) on a scanned image.  ROIs can be polygons, circles or ruler
measurements.  Large images are downsampled for display while the original
coordinates are preserved for analysis.  Inks are labeled via the
number keys 1–4 with automatic replicate numbering, and the ruler ROI
option triggers a dialog to capture the real‐world length for
pixel/mm conversion.  The state of enabled analyses (intensity, shape,
halo) is toggled via the I/S/H keys.  Press Q to finish the session.
"""

import os

import cv2
import numpy as np
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog

# --- Global state ---
mode = 'polygon'   # 'polygon', 'circle', 'ruler'
do_intensity = True
do_shape = False
do_halo = False

# Completed ROIs: list of dicts with original-resolution coords and metadata
completed_rois = []

# In-progress ROI points in display coords
disp_roi_points = []
drawing = False
disp_circle_center = None
current_mouse_pos = None

# Replicate counters for inks 1–4
replicate_counters = {'1': 0, '2': 0, '3': 0, '4': 0}

# Calibration
px_per_mm = None
conversion_used = False

# Ink short names
ink_shortnames = {
    '1': '5wtp_petro',
    '2': '25wtp_petro',
    '3': '25wtp_IPA',
    '4': 'sharpie'
}

window_name = 'BJAM Analyzer'

def ask_ruler_length():
    """Dialog: ask for real-world length (mm) and conversion choice."""
    root = tk.Tk()
    root.withdraw()
    length = simpledialog.askfloat("Ruler Length", "Enter real-world length (mm):")
    convert = messagebox.askyesno("Unit Conversion", "Convert px→mm for this session?")
    root.destroy()
    return length, convert

def draw_legend(img):
    """Overlay mode, analysis flags, and keystroke instructions."""
    # first, draw a white background box so black text is legible
    # cv2.rectangle(img, (5,5), (400, 180), (255,255,255), thickness=-1)

    # now draw all text in black
    color = (0,0,0)
    y = 25
    line_height = 18

    # Mode and analysis status
    cv2.putText(img, f"Mode: {mode.upper()}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    y += line_height
    cv2.putText(img,
        f"Analysis: I={'On' if do_intensity else 'Off'}  "
        f"S={'On' if do_shape else 'Off'}  "
        f"H={'On' if do_halo else 'Off'}",
        (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    y += line_height

    # Ink key descriptions
    cv2.putText(img, "Ink keys:", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    y += line_height
    cv2.putText(img, "1 → 5 wt% C, petroleum", (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    y += line_height
    cv2.putText(img, "2 → 25 wt% C, petroleum", (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    y += line_height
    cv2.putText(img, "3 → 25 wt% C, IPA",         (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    y += line_height
    cv2.putText(img, "4 → Sharpie (control)",     (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    y += line_height

    # Keystroke instructions
    instructions = [
        "P: Polygon → Left-click add, Right-click close",
        "C: Circle  → Hold C + drag",
        "L: Ruler   → Hold L + click start/end",
        "R: Label last ROI as ruler",
        "I/S/H: Toggle Intensity/Shape/Halo",
        "Q: Quit & save"
    ]
    for txt in instructions:
        cv2.putText(img, txt, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        y += line_height


def mouse_callback(scale, event, x_disp, y_disp, flags, param):
    """Handle mouse events on downsampled image, store original-coord ROIs."""
    global disp_roi_points, drawing, disp_circle_center
    global px_per_mm, conversion_used, current_mouse_pos

    # track display coords
    current_mouse_pos = (x_disp, y_disp)
    x_orig = int(x_disp / scale)
    y_orig = int(y_disp / scale)

    if mode == 'polygon':
        if event == cv2.EVENT_LBUTTONDOWN:
            disp_roi_points.append((x_disp, y_disp))
        elif event == cv2.EVENT_RBUTTONDOWN:
            # finalize polygon
            if len(disp_roi_points) >= 3:
                # convert disp points to orig
                orig_pts = [(int(x/scale), int(y/scale)) for x,y in disp_roi_points]
                completed_rois.append({
                    'type': 'polygon',
                    'points': orig_pts,
                    'label': None, 'ink_key': None, 'rep': None
                })
            disp_roi_points.clear()

    elif mode == 'circle':
        if event == cv2.EVENT_LBUTTONDOWN:
            disp_circle_center = (x_disp, y_disp)
            drawing = True
        elif event == cv2.EVENT_LBUTTONUP and drawing:
            # calculate radius
            dx = x_disp - disp_circle_center[0]
            dy = y_disp - disp_circle_center[1]
            disp_radius = int(np.hypot(dx, dy))
            # convert center+radius
            cx_o = int(disp_circle_center[0] / scale)
            cy_o = int(disp_circle_center[1] / scale)
            r_o = int(disp_radius / scale)
            completed_rois.append({
                'type': 'circle',
                'center': (cx_o, cy_o),
                'radius': r_o,
                'label': None, 'ink_key': None, 'rep': None
            })
            drawing = False
            disp_circle_center = None

    elif mode == 'ruler':
        if event == cv2.EVENT_LBUTTONDOWN:
            disp_roi_points.append((x_disp, y_disp))
            if len(disp_roi_points) == 2:
                # convert to orig
                p1 = (int(disp_roi_points[0][0]/scale), int(disp_roi_points[0][1]/scale))
                p2 = (int(disp_roi_points[1][0]/scale), int(disp_roi_points[1][1]/scale))
                length_mm, convert = ask_ruler_length()
                conversion_used = convert
                dist_px = np.hypot(p2[0]-p1[0], p2[1]-p1[1])
                if convert and length_mm:
                    globals()['px_per_mm'] = dist_px / length_mm
                completed_rois.append({
                    'type': 'ruler',
                    'points': [p1, p2],
                    'length_mm': length_mm,
                    'px_per_mm': px_per_mm
                })
                disp_roi_points.clear()

def main():
    """Launch GUI, let user draw & label ROIs, return session data.

    This function resets all persistent state at the start of each
    invocation so that repeated runs do not carry over ROI lists or
    replicate counters from previous sessions.
    """
    global mode, do_intensity, do_shape, do_halo
    global completed_rois, disp_roi_points, disp_circle_center, current_mouse_pos
    global replicate_counters, px_per_mm, conversion_used

    # Reset state for a new session
    completed_rois.clear()
    disp_roi_points.clear()
    disp_circle_center = None
    current_mouse_pos = None
    # reset counters and flags
    replicate_counters = {'1': 0, '2': 0, '3': 0, '4': 0}
    do_intensity = True
    do_shape = False
    do_halo = False
    px_per_mm = None
    conversion_used = False

    # File dialog
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        initialdir=os.path.expanduser("~"),
        title="Select image",
        filetypes=[
            ("Images", ("*.png","*.jpg","*.jpeg","*.tif","*.tiff","*.bmp")),
            ("All", "*.*")
        ]
    )
    root.destroy()
    if not path:
        print("No file selected."); return {}

    # Load original
    orig = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if orig is None:
        print("Failed to load."); return {}

    # Downsample for display
    MAX_DIM = 1024
    h, w = orig.shape[:2]
    scale = 1.0
    if max(h,w) > MAX_DIM:
        scale = MAX_DIM / max(h,w)
        disp = cv2.resize(orig, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
    else:
        disp = orig.copy()

    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, lambda e,x,y,f,p: mouse_callback(scale, e, x, y, f, p))

    while True:
        # copy the downsampled frame
        vis = disp.copy()

        # ensure it's 3-channel BGR so colored overlays work
        if vis.ndim == 2:
            # grayscale → BGR
            vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
        elif vis.shape[2] == 4:
            # BGRA → BGR (drop alpha)
            vis = cv2.cvtColor(vis, cv2.COLOR_BGRA2BGR)

        # draw completed ROIs on display
        for roi in completed_rois:
            if roi['type'] == 'polygon':
                pts = np.array([(int(x*scale),int(y*scale)) for x,y in roi['points']], np.int32).reshape(-1,1,2)
                cv2.polylines(vis, [pts], True, (0,255,0), 2)
                if roi['label']:
                    cv2.putText(vis, roi['label'], pts[0][0], cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
            elif roi['type'] == 'circle':
                cx, cy = int(roi['center'][0]*scale), int(roi['center'][1]*scale)
                r = int(roi['radius']*scale)
                cv2.circle(vis, (cx,cy), r, (0,255,0),2)
                if roi['label']:
                    cv2.putText(vis, roi['label'], (cx,cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0),1)
            elif roi['type'] == 'ruler':
                p1 = (int(roi['points'][0][0]*scale), int(roi['points'][0][1]*scale))
                p2 = (int(roi['points'][1][0]*scale), int(roi['points'][1][1]*scale))
                cv2.line(vis, p1, p2, (255,0,0),2)
        # draw in-progress ROI
        if mode=='polygon' and disp_roi_points:
            for i,p in enumerate(disp_roi_points):
                cv2.circle(vis, p, 3, (0,255,0), -1)
                if i>0:
                    cv2.line(vis, disp_roi_points[i-1], p, (0,255,0),1)
        if mode=='circle' and drawing and disp_circle_center and current_mouse_pos:
            dx = current_mouse_pos[0]-disp_circle_center[0]
            dy = current_mouse_pos[1]-disp_circle_center[1]
            cv2.circle(vis, disp_circle_center, int(np.hypot(dx,dy)), (0,255,0),1)
        if mode=='ruler' and len(disp_roi_points)==1 and current_mouse_pos:
            cv2.line(vis, disp_roi_points[0], current_mouse_pos, (255,0,0),1)

        draw_legend(vis)
        cv2.imshow(window_name, vis)
        key = cv2.waitKey(1) & 0xFF

        # Mode keys
        if key in (ord('q'),ord('Q')):
            break
        elif key in (ord('p'),ord('P')):
            mode='polygon'
            disp_roi_points.clear()
        elif key in (ord('c'),ord('C')):
            mode='circle'
            disp_roi_points.clear()
        elif key in (ord('l'),ord('L')):
            mode='ruler'
            disp_roi_points.clear()
        # Label keys for inks
        elif key in (ord('1'),ord('2'),ord('3'),ord('4')):
            k = chr(key)
            # find last unlabeled ROI that is not ruler
            for roi in reversed(completed_rois):
                if roi.get('type')!='ruler' and roi.get('label') is None:
                    replicate_counters[k] +=1
                    label = f"{k}_{ink_shortnames[k]}_{replicate_counters[k]:02d}"
                    roi['ink_key']=k; roi['rep']=replicate_counters[k]; roi['label']=label
                    break
        # toggles
        elif key in (ord('i'),ord('I')):
            do_intensity = not do_intensity
        elif key in (ord('s'),ord('S')):
            do_shape = not do_shape
        elif key in (ord('h'),ord('H')):
            do_halo = not do_halo

    cv2.destroyAllWindows()
    # Return collected ROI data and session settings.  Include the
    # originating file path so downstream processing can reload the
    # full‐resolution image without relying on global state.
    return {
        'rois': completed_rois,
        'analysis': {'intensity': do_intensity,
                     'shape': do_shape,
                     'halo': do_halo},
        'conversion_used': conversion_used,
        'px_per_mm': px_per_mm,
        'scale': scale,
        'file_path': path
    }

if __name__=="__main__":
    data = main()
    print("Session data:", data)
