#!/usr/bin/env python3
import math
import cv2
import numpy as np

# ---------------------------------------------------------
# Resolution / DPI control
# ---------------------------------------------------------
# Target printer/scanner DPI. You can change this to 600, 1200, 3000, etc.
TARGET_DPI = 3000

# Conversion: 1 inch = 25.4 mm
PX_PER_MM = TARGET_DPI / 25.4  # ≈ 118.11 px/mm at 3000 dpi

# If you *really* want an integer scale, you can instead do:
# PX_PER_MM = int(round(TARGET_DPI / 25.4))

# Development flag:
#   True  -> display with cv2.imshow and do NOT save
#   False -> save PNG/TIF and do NOT display
DEVELOPMENT = False

# ---------------------------------------------------------
# Global geometry parameters (all in mm)
# ---------------------------------------------------------
CIRCLE_DIAMETER_MM = 100.0   # outer circle
MARGIN_MM          = 4.0     # extra canvas margin outside circle

# Dot array
DOT_ROWS        = 5
DOT_COLS        = 5
DOT_DIAMETER_MM = 2.0
DOT_PITCH_MM    = 6.0        # centre-to-centre spacing

DOT_CENTER_X_MM = -18.0      # base centre (before shift)
DOT_CENTER_Y_MM =  18.0
DOT_SHIFT_X_MM  =  5.0       # +X is right
DOT_SHIFT_Y_MM  =  5.0       # +Y is up

# Checkerboard
CB_ROWS         = 8
CB_COLS         = 8
CB_SQUARE_MM    = 2.0
CB_CENTER_X_MM  = 22.0
CB_CENTER_Y_MM  = 12.0

# Concentric rings
RING_COUNT       = 20
RING_LINE_MM     = 0.5       # line thickness
RING_GAP_MM      = 0.5       # spacing between rings
RING_CENTER_X_MM = -18.0
RING_CENTER_Y_MM = -16.0

# Pitch ruler (L-shaped)
BASE_SIZE_MM         = 6.0       # 6x6 mm base square (shared by X and Y)
PITCH_BASE_X_MM      = 15.0      # bottom-left of the 6x6 base
PITCH_BASE_Y_MM      = -18.0
PITCH_BAR_HEIGHT_MM  = 6.0       # height of X bars
PITCH_WIDTHS_MM      = [4.0, 2.0, 1.0, 0.8, 0.6, 0.4, 0.2, 0.1]
PITCH_GAP_MM         = 0.5       # gap between bars

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def mm_to_px(x_mm: float, y_mm: float, cx_px: int, cy_px: int) -> tuple[int, int]:
    """
    Convert (x_mm, y_mm) from mm in a centre-based coordinate system
    to image pixel coordinates (x_px, y_px).
    +x_mm -> right, +y_mm -> up.
    """
    x_px = int(round(cx_px + x_mm * PX_PER_MM))
    y_px = int(round(cy_px - y_mm * PX_PER_MM))  # minus: +y_mm is up
    return x_px, y_px


def main() -> None:
    # ---------------------------------------------------------
    # Canvas setup
    # ---------------------------------------------------------
    radius_mm = CIRCLE_DIAMETER_MM / 2.0
    half_extent_mm = radius_mm + MARGIN_MM  # include margin
    half_size_px = int(math.ceil(half_extent_mm * PX_PER_MM))
    size_px = 2 * half_size_px

    # White background
    img = np.ones((size_px, size_px, 3), dtype=np.uint8) * 255
    cx, cy = half_size_px, half_size_px  # image centre in pixels

    # ---------------------------------------------------------
    # Draw outer circle (light grey guide)
    # ---------------------------------------------------------
    outer_radius_px = int(round(radius_mm * PX_PER_MM))
    cv2.circle(
        img,
        (cx, cy),
        outer_radius_px,
        (240, 240, 240),
        thickness=1,
        lineType=cv2.LINE_8,
    )

    # ---------------------------------------------------------
    # Dot array with shift
    # ---------------------------------------------------------
    dot_radius_px = int(round((DOT_DIAMETER_MM / 2.0) * PX_PER_MM))

    dot_center_x_mm = DOT_CENTER_X_MM + DOT_SHIFT_X_MM
    dot_center_y_mm = DOT_CENTER_Y_MM + DOT_SHIFT_Y_MM

    # Top-left dot centre in mm
    span_x_mm = DOT_PITCH_MM * (DOT_COLS - 1)
    span_y_mm = DOT_PITCH_MM * (DOT_ROWS - 1)
    start_x_mm = dot_center_x_mm - span_x_mm / 2.0
    start_y_mm = dot_center_y_mm + span_y_mm / 2.0

    for r in range(DOT_ROWS):
        for c in range(DOT_COLS):
            x_mm = start_x_mm + c * DOT_PITCH_MM
            y_mm = start_y_mm - r * DOT_PITCH_MM
            x_px, y_px = mm_to_px(x_mm, y_mm, cx, cy)
            cv2.circle(
                img,
                (x_px, y_px),
                dot_radius_px,
                (0, 0, 0),
                thickness=-1,
                lineType=cv2.LINE_8,
            )

    # ---------------------------------------------------------
    # Checkerboard (8x8, 2mm squares)
    # ---------------------------------------------------------
    cb_half_w_mm = (CB_COLS * CB_SQUARE_MM) / 2.0
    cb_half_h_mm = (CB_ROWS * CB_SQUARE_MM) / 2.0

    for i in range(CB_ROWS):
        for j in range(CB_COLS):
            # Standard chess pattern: black squares where (i + j) is even
            if (i + j) % 2 == 0:
                x0_mm = CB_CENTER_X_MM - cb_half_w_mm + j * CB_SQUARE_MM
                y0_mm = CB_CENTER_Y_MM + cb_half_h_mm - (i + 1) * CB_SQUARE_MM
                x1_mm = x0_mm + CB_SQUARE_MM
                y1_mm = y0_mm + CB_SQUARE_MM

                x0_px, y0_px = mm_to_px(x0_mm, y0_mm, cx, cy)
                x1_px, y1_px = mm_to_px(x1_mm, y1_mm, cx, cy)

                # OpenCV rectangle uses (x0,y1) bottom-left, (x1,y0) top-right
                cv2.rectangle(
                    img,
                    (x0_px, y1_px),
                    (x1_px, by0_px := y0_px),
                    (0, 0, 0),
                    thickness=-1,
                    lineType=cv2.LINE_8,
                )

    # ---------------------------------------------------------
    # Concentric rings (20 rings, 0.5mm line / 0.5mm gap)
    # ---------------------------------------------------------
    ring_center_x_px, ring_center_y_px = mm_to_px(
        RING_CENTER_X_MM,
        RING_CENTER_Y_MM,
        cx,
        cy,
    )
    ring_pitch_mm = RING_LINE_MM + RING_GAP_MM

    # Key: force thickness >= 2 px so rings draw cleanly at high DPI
    thickness_px = max(2, int(round(RING_LINE_MM * PX_PER_MM)))

    for k in range(RING_COUNT):
        # ring centre radius in mm
        r_mm = (k + 1) * ring_pitch_mm
        r_px = int(round(r_mm * PX_PER_MM))
        cv2.circle(
            img,
            (ring_center_x_px, ring_center_y_px),
            r_px,
            (0, 0, 0),
            thickness=thickness_px,
            lineType=cv2.LINE_8,
        )

    # ---------------------------------------------------------
    # Pitch ruler bars — L-shaped
    # ---------------------------------------------------------
    # Base 6x6mm square
    base_x0_mm = PITCH_BASE_X_MM
    base_y0_mm = PITCH_BASE_Y_MM
    base_x1_mm = base_x0_mm + BASE_SIZE_MM
    base_y1_mm = base_y0_mm + BASE_SIZE_MM

    bx0_px, by0_px = mm_to_px(base_x0_mm, base_y0_mm, cx, cy)
    bx1_px, by1_px = mm_to_px(base_x1_mm, base_y1_mm, cx, cy)

    cv2.rectangle(
        img,
        (bx0_px, by1_px),
        (bx1_px, by0_px),
        (0, 0, 0),
        thickness=-1,
        lineType=cv2.LINE_8,
    )

    # X-direction bars to the right of the base
    current_x_mm = base_x1_mm + PITCH_GAP_MM
    for w_mm in PITCH_WIDTHS_MM:
        x0_mm = current_x_mm
        x1_mm = current_x_mm + w_mm
        y0_mm = PITCH_BASE_Y_MM
        y1_mm = PITCH_BASE_Y_MM + PITCH_BAR_HEIGHT_MM

        x0_px, y0_px = mm_to_px(x0_mm, y0_mm, cx, cy)
        x1_px, y1_px = mm_to_px(x1_mm, y1_mm, cx, cy)

        cv2.rectangle(
            img,
            (x0_px, y1_px),
            (x1_px, y0_px),
            (0, 0, 0),
            thickness=-1,
            lineType=cv2.LINE_8,
        )
        current_x_mm = x1_mm + PITCH_GAP_MM

    # Y-direction bars above the base
    current_y_mm = base_y1_mm + PITCH_GAP_MM
    for h_mm in PITCH_WIDTHS_MM:
        x0_mm = PITCH_BASE_X_MM
        x1_mm = PITCH_BASE_X_MM + BASE_SIZE_MM
        y0_mm = current_y_mm
        y1_mm = current_y_mm + h_mm

        x0_px, y0_px = mm_to_px(x0_mm, y0_mm, cx, cy)
        x1_px, y1_px = mm_to_px(x1_mm, y1_mm, cx, cy)

        cv2.rectangle(
            img,
            (x0_px, y1_px),
            (x1_px, y0_px),
            (0, 0, 0),
            thickness=-1,
            lineType=cv2.LINE_8,
        )
        current_y_mm = y1_mm + PITCH_GAP_MM

    # ---------------------------------------------------------
    # Show or save
    # ---------------------------------------------------------
    if DEVELOPMENT:
        cv2.imshow("gold_standard_pattern", img)
        print(f"Development mode: {size_px}x{size_px} px, {TARGET_DPI} dpi")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        png_name = f"gold_standard_pattern_{TARGET_DPI}dpi.png"
        tif_name = f"gold_standard_pattern_{TARGET_DPI}dpi.tif"
        cv2.imwrite(png_name, img)
        cv2.imwrite(tif_name, img)
        print(f"Saved {png_name} and {tif_name}")
        print(f"Canvas: {size_px} x {size_px} px, approximately {TARGET_DPI:.1f} dpi")


if __name__ == "__main__":
    main()
