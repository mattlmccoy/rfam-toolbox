"""
feature_analysis.py — routines to analyse specific geometric features in the BJAM standard test pattern.

This module contains a collection of functions that operate on cropped regions
of scanned images to quantify dimensional accuracy of well-defined test
features.  Each function accepts a greyscale or colour image (numpy array),
the pixel-per-millimetre calibration factor, and any nominal dimensions, and
returns a summary dictionary of metrics along with optional per-feature
details.  The analyses are intended to be called after the user selects
regions of interest in the GUI and to complement the ROI-based ink
concentration workflow.

Functions provided:

  * ``analyze_dot_array`` — measure centroid positions, equivalent
    diameters and spacing in a dot array.

  * ``analyze_checkerboard`` — use OpenCV chessboard corner detection to
    estimate square size and orientation.

  * ``analyze_concentric_rings`` — estimate ring line width and spacing
    via contour-based analysis.

  * ``analyze_pitch_ruler`` — measure widths of a series of bars in X or
    Y to assess resolvable feature size.

  * ``recommend_compensation_for_dot`` — convert dot-array spacing and
    rotation errors into suggested CAD scaling and angular adjustments.
"""

from __future__ import annotations

import math
import os
import traceback
from typing import Dict, List, Tuple, Optional, Any

import cv2
import numpy as np

from bjam_toolbox.defaults.config_loader import load_config
_CFG = load_config()

# ---------------------------------------------------------------------------
# Public constants expected by dim_gui.py (do not rename)
# ---------------------------------------------------------------------------
FEATURE_ANALYSIS_VERSION = "2025-12-16-f-healthreport"
CIRCULARITY_NORM_BASE = _CFG["calibration"]["circularity_norm_base"]

# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
ANALYSIS_VERSION = "2025-12-16-f-healthreport"

# Theoretical max circularity used for normalization (calibrated from gold standard)
CIRCULARITY_MAX_THEORETICAL = CIRCULARITY_NORM_BASE


# ---------------------------------------------------------------------------
# Debug logging (always safe to call; caller decides whether to pass a path)
# ---------------------------------------------------------------------------
def _dbg_open(debug_log_path: Optional[str]) -> Optional[object]:
    if not debug_log_path:
        return None
    os.makedirs(os.path.dirname(debug_log_path) or ".", exist_ok=True)
    # Append mode: GUI/CLI can write headers once, feature functions append blocks.
    return open(debug_log_path, "a", encoding="utf-8")

def _dbg(f: Optional[object], msg: str) -> None:
    if not f:
        return
    try:
        f.write(msg.rstrip() + "\n")
        f.flush()
    except Exception:
        # Never let logging break analysis
        pass


# ---------------------------------------------------------------------------
# Dot-array analysis (single canonical blob/centroid pipeline)
# ---------------------------------------------------------------------------

def _to_gray(img: np.ndarray) -> np.ndarray:
    if img is None:
        raise ValueError("Image is None")
    if img.ndim == 3:
        if img.shape[2] == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 2:
        return img.copy()
    raise ValueError("Unsupported image format")


def _segment_blobs(gray: np.ndarray) -> np.ndarray:
    """Otsu threshold then invert so dark ink becomes white blobs."""
    g = gray.copy()
    if g.dtype != np.uint8:
        g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    g = cv2.GaussianBlur(g, tuple(_CFG["dot_array"]["gaussian_blur_kernel"]), 0)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Light cleanup: close then open
    _ks = _CFG["dot_array"]["morph_kernel_size"]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_ks, _ks))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k, iterations=_CFG["dot_array"]["morph_close_iterations"])
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, k, iterations=_CFG["dot_array"]["morph_open_iterations"])
    return bw


def _measure_blobs_legacy(
    roi: np.ndarray,
    px_per_mm: float,
    min_blob_area_px: int = _CFG["dot_array"]["min_blob_area_px"],
) -> List[Dict[str, Any]]:
    """Legacy blob metrics: contours -> centroids -> circularity/ellipse."""
    gray = _to_gray(roi)
    mask = _segment_blobs(gray)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    out: List[Dict[str, Any]] = []
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < float(min_blob_area_px):
            continue

        peri = float(cv2.arcLength(cnt, True))
        circ = 4.0 * math.pi * area / (peri**2) if peri > 0 else float("nan")
        circ_norm = circ / CIRCULARITY_MAX_THEORETICAL if CIRCULARITY_MAX_THEORETICAL > 0 else float("nan")

        M = cv2.moments(cnt)
        if M.get("m00", 0.0) == 0.0:
            continue
        cx = float(M["m10"] / M["m00"])
        cy = float(M["m01"] / M["m00"])

        eq_diam_px = 2.0 * math.sqrt(area / math.pi) if area > 0 else float("nan")
        eq_diam_mm = eq_diam_px / px_per_mm if px_per_mm > 0 else float("nan")

        major_mm = minor_mm = ecc = angle_deg = None
        if len(cnt) >= 5:
            (xc, yc), (axis1, axis2), ang = cv2.fitEllipse(cnt)
            major_px = max(axis1, axis2)
            minor_px = min(axis1, axis2)
            major_mm = float(major_px) / px_per_mm if px_per_mm > 0 else None
            minor_mm = float(minor_px) / px_per_mm if px_per_mm > 0 else None
            if major_px > 0:
                ecc = float(math.sqrt(max(0.0, 1.0 - (minor_px / major_px) ** 2)))
            angle_deg = float(ang)

        out.append({
            "centroid_px": (cx, cy),
            "centroid_mm": (cx / px_per_mm, cy / px_per_mm) if px_per_mm > 0 else (float("nan"), float("nan")),
            "area_px": area,
            "perimeter_px": peri,
            "circularity": float(circ),
            "circularity_norm": float(circ_norm),
            "eq_diam_px": float(eq_diam_px),
            "eq_diam_mm": float(eq_diam_mm),
            "major_mm": major_mm,
            "minor_mm": minor_mm,
            "eccentricity": ecc,
            "orientation_deg": angle_deg,
            "contour": cnt,
        })

    return out




def _compute_spacing_pairwise(
    centroids_px: List[Tuple[float, float]],
    px_per_mm: float,
    nominal_spacing_mm: Optional[float] = None,
    spacing_tol: float = 0.5,
) -> Dict[str, float]:
    """
    Estimate dot-grid spacing along two orthogonal grid axes.

    If a nominal spacing is provided, we treat the dot lattice as a rotated grid and
    estimate the two grid axes by PCA, then compute near-nominal spacings by projecting
    pairwise centroid differences onto those axes. This avoids the common failure mode
    where a rotated grid makes both "X" and "Y" spacing collapse onto the same value.

    If no nominal spacing is provided, we fall back to the simpler axis-aligned stats
    in image coordinates (legacy behavior).
    """
    if px_per_mm <= 0 or len(centroids_px) < 2:
        return {
            "spacing_x_mean_mm": float("nan"),
            "spacing_x_std_mm": float("nan"),
            "spacing_y_mean_mm": float("nan"),
            "spacing_y_std_mm": float("nan"),
        }

    pts = np.array(centroids_px, dtype=float)
    n = pts.shape[0]

    def _stats(arr: List[float]) -> Tuple[float, float]:
        if not arr:
            return float("nan"), float("nan")
        a = np.array(arr, dtype=float)
        return float(np.mean(a)), float(np.std(a, ddof=1) if len(a) > 1 else 0.0)

    # ------------------------------------------
    # Preferred: PCA-projected (rotation aware)
    # ------------------------------------------
    if nominal_spacing_mm is not None and not (isinstance(nominal_spacing_mm, float) and math.isnan(nominal_spacing_mm)):
        nom = float(nominal_spacing_mm)
        tol = float(spacing_tol)

        # Legacy-compatible tolerance semantics:
        #   - If tol <= 1.0, interpret as a fractional band around nominal (e.g., 0.5 => ±50%).
        #   - If tol  > 1.0, interpret as an absolute tolerance in mm.
        tol_mm = (abs(nom) * tol) if tol <= 1.0 else tol

        centered = pts - pts.mean(axis=0, keepdims=True)
        cov = centered.T @ centered / max(n, 1)
        vals, vecs = np.linalg.eig(cov)
        v1 = vecs[:, int(np.argmax(vals))]
        v1 = v1 / (np.linalg.norm(v1) + 1e-12)
        v2 = np.array([-v1[1], v1[0]], dtype=float)

        # Map axes to "X" and "Y" in a stable way: choose the axis more aligned with +X as "X".
        if abs(v2[0]) > abs(v1[0]):
            v1, v2 = v2, v1

        proj_x: List[float] = []
        proj_y: List[float] = []

        for i in range(n):
            for j in range(i + 1, n):
                d = pts[j] - pts[i]
                ax = abs(float(d @ v1)) / px_per_mm
                ay = abs(float(d @ v2)) / px_per_mm
                if ax > 0 and abs(ax - nom) <= tol_mm:
                    proj_x.append(ax)
                if ay > 0 and abs(ay - nom) <= tol_mm:
                    proj_y.append(ay)

        mx, sx = _stats(proj_x)
        my, sy = _stats(proj_y)

        # If PCA-projection fails (rare), fall back to image-axis stats
        if np.isfinite(mx) or np.isfinite(my):
            return {
                "spacing_x_mean_mm": mx,
                "spacing_x_std_mm": sx,
                "spacing_y_mean_mm": my,
                "spacing_y_std_mm": sy,
            }

    # -----------------------------
    # Fallback: axis-aligned image
    # -----------------------------
    dx_vals_mm: List[float] = []
    dy_vals_mm: List[float] = []
    xs = pts[:, 0]
    ys = pts[:, 1]

    for i in range(n):
        for j in range(i + 1, n):
            dx_mm = abs(xs[j] - xs[i]) / px_per_mm
            dy_mm = abs(ys[j] - ys[i]) / px_per_mm
            if dx_mm > 0:
                dx_vals_mm.append(dx_mm)
            if dy_mm > 0:
                dy_vals_mm.append(dy_mm)

    mx, sx = _stats(dx_vals_mm)
    my, sy = _stats(dy_vals_mm)

    return {
        "spacing_x_mean_mm": mx,
        "spacing_x_std_mm": sx,
        "spacing_y_mean_mm": my,
        "spacing_y_std_mm": sy,
    }


def _write_dot_overlay(roi: np.ndarray, details: List[Dict[str, Any]], path: str) -> None:
    if not path:
        return
    try:
        vis = roi.copy()
        if vis.ndim == 2:
            vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
        # green contours + blue centroids
        for d in details:
            cnt = d.get("contour")
            if cnt is not None:
                cv2.drawContours(vis, [cnt], -1, (0, 255, 0), 2)
            cx, cy = d.get("centroid_px", (None, None))
            if cx is not None and cy is not None:
                cv2.circle(vis, (int(round(cx)), int(round(cy))), 3, (255, 0, 0), -1)
        cv2.imwrite(path, vis)
    except Exception:
        pass


def analyze_dot_array(
    roi: np.ndarray,
    px_per_mm: float,
    nominal_diameter_mm: float,
    nominal_spacing_mm: float,
    spacing_tol: float = _CFG["dot_array"]["spacing_tolerance"],
    debug_overlay_path: Optional[str] = None,
    debug_log_path: Optional[str] = None,
    min_blob_area_px: int = _CFG["dot_array"]["min_blob_area_px"],
) -> Tuple[Dict[str, float], List[Dict]]:
    """Analyse a dot array inside a cropped ROI using the canonical blob/centroid pipeline.

    Notes
    -----
    This is the *only* dot-array method used by the tool. It intentionally avoids any
    alternate dispatch/mode selection to prevent bifurcation.

    Returns
    -------
    summary : Dict[str, float]
        Summary dot-array metrics.
    details : List[Dict]
        Per-blob measurements (includes contour for overlay).
    """
    dbg = _dbg_open(debug_log_path)
    _dbg(dbg, "[dot] method=blob_contours_centroids_v1")
    _dbg(dbg, f"[dot] px_per_mm={px_per_mm:.6f} nominal_diameter_mm={nominal_diameter_mm} nominal_spacing_mm={nominal_spacing_mm} spacing_tol={spacing_tol} min_blob_area_px={min_blob_area_px}")
    try:
        details = _measure_blobs_legacy(roi, px_per_mm=px_per_mm, min_blob_area_px=min_blob_area_px)

        # ------------------------------------------------------------------
        # Speck / fragment rejection (legacy behavior)
        # ------------------------------------------------------------------
        # Area-only filters are insufficient at high DPI (tiny specks can still have large pixel area).
        # Reject blobs whose equivalent diameter is implausibly small/large relative to the nominal and
        # the robust median of detected blobs.
        _diams_all = [d.get("eq_diam_mm") for d in details if d.get("eq_diam_mm") is not None and not math.isnan(d.get("eq_diam_mm"))]
        if len(_diams_all) >= 5 and nominal_diameter_mm and not (isinstance(nominal_diameter_mm, float) and math.isnan(nominal_diameter_mm)):
            _med = float(np.median(np.array(_diams_all, dtype=float)))
            # Keep window: combine nominal-based and median-based gates.
            _min_keep = max(_CFG["dot_array"]["min_keep_factor"] * float(nominal_diameter_mm), _CFG["dot_array"]["min_keep_factor_median"] * _med)
            _max_keep = max(_CFG["dot_array"]["max_keep_factor"] * float(nominal_diameter_mm), _CFG["dot_array"]["max_keep_factor_median"] * _med)
            _before = len(details)
            details = [d for d in details if d.get("eq_diam_mm") is not None and not math.isnan(d.get("eq_diam_mm")) and (_min_keep <= float(d.get("eq_diam_mm")) <= _max_keep)]
            _after = len(details)
            _dbg(dbg, f"[dot] speck_reject: before={_before} after={_after} min_keep_mm={_min_keep:.3f} max_keep_mm={_max_keep:.3f} median_mm={_med:.3f}")
        centroids_px = [tuple(d["centroid_px"]) for d in details if d.get("centroid_px") is not None]
        spacing_stats = _compute_spacing_pairwise(
            centroids_px=centroids_px,
            px_per_mm=px_per_mm,
            nominal_spacing_mm=nominal_spacing_mm,
            spacing_tol=spacing_tol,
        )

        diams = [d.get("eq_diam_mm") for d in details if d.get("eq_diam_mm") is not None and not math.isnan(d.get("eq_diam_mm"))]
        circs = [d.get("circularity") for d in details if d.get("circularity") is not None and not math.isnan(d.get("circularity"))]
        circs_norm = [d.get("circularity_norm") for d in details if d.get("circularity_norm") is not None and not math.isnan(d.get("circularity_norm"))]

        mean_diam = float(np.mean(diams)) if diams else float("nan")
        std_diam = float(np.std(diams, ddof=1) if len(diams) > 1 else 0.0) if diams else float("nan")
        diam_error = mean_diam - float(nominal_diameter_mm) if diams else float("nan")
        diam_error_pct = (diam_error / float(nominal_diameter_mm) * 100.0) if (diams and nominal_diameter_mm) else float("nan")

        sx = spacing_stats.get("spacing_x_mean_mm", float("nan"))
        sy = spacing_stats.get("spacing_y_mean_mm", float("nan"))
        spacing_x_error_mm = sx - float(nominal_spacing_mm) if not math.isnan(sx) else float("nan")
        spacing_y_error_mm = sy - float(nominal_spacing_mm) if not math.isnan(sy) else float("nan")
        spacing_x_error_pct = (spacing_x_error_mm / float(nominal_spacing_mm) * 100.0) if nominal_spacing_mm and not math.isnan(spacing_x_error_mm) else float("nan")
        spacing_y_error_pct = (spacing_y_error_mm / float(nominal_spacing_mm) * 100.0) if nominal_spacing_mm and not math.isnan(spacing_y_error_mm) else float("nan")

        summary: Dict[str, float] = {
            "num_blobs": float(len(details)),
            "avg_diameter_mm": float(mean_diam),
            "std_diameter_mm": float(std_diam),
            "diameter_error_mm": float(diam_error),
            "diameter_error_pct": float(diam_error_pct),
            "spacing_x_mean_mm": float(spacing_stats.get("spacing_x_mean_mm", float("nan"))),
            "spacing_x_std_mm": float(spacing_stats.get("spacing_x_std_mm", float("nan"))),
            "spacing_y_mean_mm": float(spacing_stats.get("spacing_y_mean_mm", float("nan"))),
            "spacing_y_std_mm": float(spacing_stats.get("spacing_y_std_mm", float("nan"))),
            "spacing_x_error_mm": float(spacing_x_error_mm),
            "spacing_y_error_mm": float(spacing_y_error_mm),
            "spacing_x_error_pct": float(spacing_x_error_pct),
            "spacing_y_error_pct": float(spacing_y_error_pct),
            "avg_circularity": float(np.mean(circs)) if circs else float("nan"),
            "std_circularity": float(np.std(circs, ddof=1) if len(circs) > 1 else 0.0) if circs else float("nan"),
            "avg_circularity_norm": float(np.mean(circs_norm)) if circs_norm else float("nan"),
            "std_circularity_norm": float(np.std(circs_norm, ddof=1) if len(circs_norm) > 1 else 0.0) if circs_norm else float("nan"),
            "algorithm_error": "",
        }

        _dbg(dbg, f"[dot] found_blobs={len(details)} mean_diam_mm={summary['avg_diameter_mm']} spacing_x_mean_mm={summary['spacing_x_mean_mm']} spacing_y_mean_mm={summary['spacing_y_mean_mm']}")
        if debug_overlay_path:
            _write_dot_overlay(roi, details, debug_overlay_path)
    except Exception as e:
        tb = traceback.format_exc()
        _dbg(dbg, f"[dot] ERROR: {e}\n{tb}")
        summary = {
            "num_blobs": 0.0,
            "avg_diameter_mm": float("nan"),
            "std_diameter_mm": float("nan"),
            "diameter_error_mm": float("nan"),
            "diameter_error_pct": float("nan"),
            "spacing_x_mean_mm": float("nan"),
            "spacing_x_std_mm": float("nan"),
            "spacing_y_mean_mm": float("nan"),
            "spacing_y_std_mm": float("nan"),
            "spacing_x_error_mm": float("nan"),
            "spacing_y_error_mm": float("nan"),
            "spacing_x_error_pct": float("nan"),
            "spacing_y_error_pct": float("nan"),
            "avg_circularity": float("nan"),
            "std_circularity": float("nan"),
            "avg_circularity_norm": float("nan"),
            "std_circularity_norm": float("nan"),
            "algorithm_error": f"dot_failed: {e}",
        }
        details = []
        # still try to write an overlay for visibility
        if debug_overlay_path:
            try:
                vis = roi.copy()
                if vis.ndim == 2:
                    vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
                cv2.putText(vis, "DOT FAIL", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.imwrite(debug_overlay_path, vis)
            except Exception:
                pass
    finally:
        try:
            if dbg:
                dbg.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Additional interpretation based on dot array context
    # ------------------------------------------------------------------

    # Halo / droplet eccentricity: mean eccentricity across all blobs
    eccs = [d.get("eccentricity") for d in details if d.get("eccentricity") is not None]
    mean_ecc = float(np.mean(eccs)) if eccs else float("nan")
    summary["mean_eccentricity"] = mean_ecc
    summary["halo_eccentricity"] = mean_ecc  # kept for backward compatibility

    # Orientation-aware halo metrics
    angles = [d.get("orientation_deg") for d in details if d.get("orientation_deg") is not None]
    if angles:
        summary["mean_major_axis_angle_deg"] = float(np.mean(angles))
    else:
        summary["mean_major_axis_angle_deg"] = float("nan")

    aspect_ratios: List[float] = []
    for d in details:
        maj = d.get("major_mm")
        minr = d.get("minor_mm")
        if maj is not None and minr is not None and minr > 0:
            aspect_ratios.append(maj / minr)
    if aspect_ratios:
        summary["mean_aspect_ratio"] = float(np.mean(aspect_ratios))
    else:
        summary["mean_aspect_ratio"] = float("nan")

    # Centroid-based metrics
    centroids = np.array([d["centroid_mm"] for d in details]) if details else np.empty((0, 2))
    if centroids.size:
        # Centre of the dot cloud (median is robust)
        median_c = np.median(centroids, axis=0)
        deviations = centroids - median_c
        mis_mags = np.linalg.norm(deviations, axis=1)

        # Historical fields: effectively the mean radial distance
        mean_radius = float(np.mean(mis_mags))
        summary["global_misalignment_mm"] = mean_radius
        summary["centroid_deviation_mm"] = mean_radius

        # Contextualised centroid radius relative to nominal 5x5 grid (6 mm pitch)
        # For that pattern, mean radius ≈ 11.2461856 mm
        centroid_nominal_radius_mm = _CFG["dot_array"]["nominal_grid_mean_radius"]
        summary["centroid_radius_mm"] = mean_radius
        summary["centroid_nominal_radius_mm"] = centroid_nominal_radius_mm
        radius_err = mean_radius - centroid_nominal_radius_mm
        summary["centroid_radius_error_mm"] = radius_err
        summary["centroid_radius_error_pct"] = (
            100.0 * radius_err / centroid_nominal_radius_mm
            if centroid_nominal_radius_mm > 0
            else float("nan")
        )

        # Approximate grid rotation using PCA of centroid cloud
        centered = centroids - np.mean(centroids, axis=0)
        cov = np.cov(centered.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        principal_vec = eigvecs[:, np.argmax(eigvals)]
        angle_rad = math.atan2(principal_vec[1], principal_vec[0])
        raw_angle_deg = float(np.degrees(angle_rad))
        summary["grid_rotation_raw_deg"] = raw_angle_deg
        # Normalise into range [-90, 90) so symmetric grids don't report 90°
        angle_mod = ((raw_angle_deg + 90.0) % 180.0) - 90.0
        summary["grid_rotation_deg"] = angle_mod
    else:
        summary["global_misalignment_mm"] = float("nan")
        summary["centroid_deviation_mm"] = float("nan")
        summary["centroid_radius_mm"] = float("nan")
        summary["centroid_nominal_radius_mm"] = float("nan")
        summary["centroid_radius_error_mm"] = float("nan")
        summary["centroid_radius_error_pct"] = float("nan")
        summary["grid_rotation_deg"] = float("nan")
        summary["grid_rotation_raw_deg"] = float("nan")

    return summary, details


# ---------------------------------------------------------------------------
# Checkerboard analysis
# ---------------------------------------------------------------------------

def analyze_checkerboard(
    roi: np.ndarray,
    px_per_mm: float,
    nominal_square_mm: float,
    dpi: Optional[float] = None,
    debug_overlay_path: Optional[str] = None,
    debug_log_path: Optional[str] = None,
    scale_min: float = _CFG["checkerboard"]["scale_min"],
    scale_step: float = _CFG["checkerboard"]["scale_step"],
    checkerboard_ref_angle_deg: float = _CFG["checkerboard"]["ref_angle_deg"],
) -> Dict[str, float]:
    """
    Analyse a checkerboard ROI using a component-based square filter that is robust to blur.

    This function intentionally avoids OpenCV chessboard corner detectors for the baseline metric.
    It attempts analysis at full resolution first, then downscales in fixed steps until success.

    Angle reporting:
      - checkerboard_angle_deg_raw: PCA orientation of the square-centroid lattice (degrees).
      - checkerboard_angle_error_deg: wrapped delta to checkerboard_ref_angle_deg with 90° periodicity
        (the "small sliver" error you care about for nozzle/stage rotation).
      - Hough stats are exposed/logged for debugging only and are NOT used for angle error.
    """
    # Toggle: write intermediate checkerboard debug PNGs
    save_checkerboard_debug_images = True
    method_name = "component_square_filter_v2"

    # Determine run directory for checkerboard debug PNGs (safe)
    run_dir = None
    for _p in (debug_overlay_path, debug_log_path):
        if _p:
            try:
                run_dir = os.path.dirname(_p)
                break
            except Exception:
                pass

    def _wrap90(delta_deg: float) -> float:
        d = delta_deg % 90.0
        if d > 45.0:
            d -= 90.0
        return d

    out: Dict[str, float] = {
        "found": 0,
        "num_squares": 0,
        "mean_square_mm": float("nan"),
        "std_square_mm": float("nan"),
        "square_error_mm": float("nan"),
        "square_error_pct": float("nan"),
        # Backward-compat field name used by earlier GUI versions
        "angle_deg": float("nan"),
        "checkerboard_angle_deg_raw": float("nan"),
        "checkerboard_angle_error_deg": float("nan"),
        "checkerboard_ref_angle_deg": float(checkerboard_ref_angle_deg),
        "scale_used": float("nan"),
        "effective_dpi": float("nan"),
        "effective_px_per_mm": float("nan"),
        "method": method_name,
        "algorithm_error": "",
        # Hough telemetry
        "hough_num_lines": float("nan"),
        "hough_angle_mean_deg": float("nan"),
        "hough_angle_std_deg": float("nan"),
    }

    gray0 = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()

    # Parameters (logged every attempt, even on failure)
    params = {
        "use_adaptive": _CFG["checkerboard"]["use_adaptive_threshold"],
        "gaussian_blur_ksize": _CFG["checkerboard"]["gaussian_blur_ksize"],
        "morph_kernel": _CFG["checkerboard"]["morph_kernel_size"],
        "morph_close_iter": _CFG["checkerboard"]["morph_close_iterations"],
        "morph_open_iter": _CFG["checkerboard"]["morph_open_iterations"],
        "min_squares_required": _CFG["checkerboard"]["min_squares_required"],
        "aspect_ratio_min": _CFG["checkerboard"]["aspect_ratio_min"],
        "aspect_ratio_max": _CFG["checkerboard"]["aspect_ratio_max"],
        "extent_min": _CFG["checkerboard"]["extent_min"],
        "extent_max": _CFG["checkerboard"]["extent_max"],
        "area_rel_min": _CFG["checkerboard"]["area_rel_min"],
        "area_rel_max": _CFG["checkerboard"]["area_rel_max"],
        # Hough/Canny params (logged + exposed)
        "canny_lo": _CFG["checkerboard"]["canny_low"],
        "canny_hi": _CFG["checkerboard"]["canny_high"],
        "hough_threshold": _CFG["checkerboard"]["hough_threshold"],
        "hough_min_line_frac": _CFG["checkerboard"]["hough_min_line_fraction"],
        "hough_max_line_gap": _CFG["checkerboard"]["hough_max_line_gap"],
    }

    def _dbg(msg: str) -> None:
        if debug_log_path:
            try:
                with open(debug_log_path, "a") as f:
                    f.write(msg.rstrip() + "\n")
            except Exception:
                pass

    # Small helper: analyze one scale and one polarity, return accepted stats
    def _analyze_mask(mask: np.ndarray, expected_area_px: float):
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        accepted = []
        for lab in range(1, num_labels):
            x, y, w, h, area = stats[lab]
            if area <= 0:
                continue
            if area < params["area_rel_min"] * expected_area_px or area > params["area_rel_max"] * expected_area_px:
                continue
            ar = (w / h) if h > 0 else 999.0
            if ar < params["aspect_ratio_min"] or ar > params["aspect_ratio_max"]:
                continue
            extent = area / float(w * h) if (w * h) > 0 else 0.0
            if extent < params["extent_min"] or extent > params["extent_max"]:
                continue
            accepted.append((x, y, w, h, area, centroids[lab]))
        return num_labels - 1, accepted

    # Multiscale sweep
    scale = 1.0
    scales = []
    while scale >= scale_min - 1e-9:
        scales.append(round(scale, 2))
        scale = round(scale - scale_step, 2)

    _dbg(f"[checkerboard] method={method_name}")
    _dbg(f"[checkerboard] px_per_mm={px_per_mm:.6f} nominal_square_mm={nominal_square_mm} dpi={dpi}")
    _dbg(f"[checkerboard] ref_angle_deg={checkerboard_ref_angle_deg}")
    _dbg(f"[checkerboard] multiscale: scale_step={scale_step} scale_min={scale_min}")

    for sc in scales:
        if sc == 1.0:
            gray = gray0
        else:
            gray = cv2.resize(gray0, (0, 0), fx=sc, fy=sc, interpolation=cv2.INTER_AREA)

        eff_dpi = float(dpi) * sc if (dpi is not None and np.isfinite(dpi)) else float("nan")
        eff_px_per_mm = px_per_mm * sc

        _dbg(f"[checkerboard] attempt scale={sc:.2f} roi_px={gray.shape[1]}x{gray.shape[0]} "
             f"effective_dpi={eff_dpi if np.isfinite(eff_dpi) else float('nan'):.2f} "
             f"effective_px_per_mm={eff_px_per_mm:.6f}")
        _dbg(f"[checkerboard] params={params}")

        blur = cv2.GaussianBlur(gray, (params["gaussian_blur_ksize"], params["gaussian_blur_ksize"]), 0)

        if params["use_adaptive"]:
            bw = cv2.adaptiveThreshold(
                blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
                _CFG["checkerboard"]["adaptive_block_size"],
                _CFG["checkerboard"]["adaptive_constant"],
            )
        else:
            _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        if save_checkerboard_debug_images and run_dir:
            try:
                cv2.imwrite(os.path.join(run_dir, f"checkerboard_scale_{sc:.2f}_binary_bw.png"), bw)
                cv2.imwrite(os.path.join(run_dir, f"checkerboard_scale_{sc:.2f}_binary_inv.png"), 255 - bw)
            except Exception:
                pass

        # Prepare morphology kernel
        k = int(params["morph_kernel"])
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))

        def prep(mask: np.ndarray) -> np.ndarray:
            m = mask.copy()
            if params["morph_open_iter"] > 0:
                m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel, iterations=int(params["morph_open_iter"]))
            if params["morph_close_iter"] > 0:
                m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel, iterations=int(params["morph_close_iter"]))
            return m

        # Expected square size at this scale
        expected_side_px = nominal_square_mm * eff_px_per_mm
        expected_area_px = expected_side_px * expected_side_px
        area_lo = params["area_rel_min"] * expected_area_px
        area_hi = params["area_rel_max"] * expected_area_px
        _dbg(f"[checkerboard] expected_side_px={expected_side_px:.2f} expected_area_px={expected_area_px:.2f} "
             f"area_gate=[{area_lo:.2f}, {area_hi:.2f}]")

        # Try both polarities: white components on black background vs inverted.
        mask_a = prep(bw)           # white = bright regions
        mask_b = prep(255 - bw)     # white = dark regions

        n_a, acc_a = _analyze_mask(mask_a, expected_area_px)
        n_b, acc_b = _analyze_mask(mask_b, expected_area_px)

        # choose polarity with more accepted squares
        polarity = "bw" if len(acc_a) >= len(acc_b) else "inv"
        accepted = acc_a if polarity == "bw" else acc_b
        total = n_a if polarity == "bw" else n_b

        _dbg(f"[checkerboard] polarity={polarity} components={total} accepted={len(accepted)} rejected={max(total - len(accepted),0)}")

        if len(accepted) < int(params["min_squares_required"]):
            _dbg(f"[checkerboard] FAIL scale={sc:.2f}: not enough squares ({len(accepted)}<{params['min_squares_required']})")
            continue

        # Compute side lengths from bounding boxes
        sides_px = [0.5 * (w + h) for (x, y, w, h, area, c) in accepted]
        sides_mm = [s / eff_px_per_mm for s in sides_px]
        mean_sq = float(np.mean(sides_mm))
        std_sq = float(np.std(sides_mm, ddof=1)) if len(sides_mm) > 1 else 0.0

        # Orientation: PCA on component centers (this is the angle to use)
        centers = np.array([[c[0], c[1]] for (_, _, _, _, _, c) in accepted], dtype=float)
        centers -= centers.mean(axis=0, keepdims=True)
        cov = centers.T @ centers / max(len(centers), 1)
        vals, vecs = np.linalg.eig(cov)
        v = vecs[:, int(np.argmax(vals))]
        angle_raw = float(np.degrees(np.arctan2(v[1], v[0])))

        angle_err = float(_wrap90(angle_raw - float(checkerboard_ref_angle_deg)))

        out.update(
            {
                "found": 1,
                "num_squares": int(len(accepted)),
                "mean_square_mm": mean_sq,
                "std_square_mm": std_sq,
                "square_error_mm": mean_sq - float(nominal_square_mm),
                "square_error_pct": (mean_sq - float(nominal_square_mm)) / float(nominal_square_mm) * 100.0
                if nominal_square_mm != 0
                else float("nan"),
                "angle_deg": angle_raw,
                "checkerboard_angle_deg_raw": angle_raw,
                "checkerboard_angle_error_deg": angle_err,
                "checkerboard_ref_angle_deg": float(checkerboard_ref_angle_deg),
                "scale_used": float(sc),
                "effective_dpi": eff_dpi,
                "effective_px_per_mm": float(eff_px_per_mm),
                "algorithm_error": "",
            }
        )

        _dbg(f"[checkerboard] PCA angle_raw_deg={angle_raw:.6f} angle_error_deg={angle_err:.6f} (ref={checkerboard_ref_angle_deg})")

        # Overlay
        if debug_overlay_path:
            overlay = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for (x, y, w, h, area, c) in accepted:
                cv2.rectangle(overlay, (int(x), int(y)), (int(x + w), int(y + h)), (0, 255, 0), 2)
                cv2.circle(overlay, (int(c[0]), int(c[1])), 3, (255, 0, 0), -1)
            cv2.putText(
                overlay,
                f"checkerboard OK sc={sc:.2f} squares={len(accepted)} mean={mean_sq:.4f}mm err={angle_err:+.3f}deg",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            try:
                cv2.imwrite(debug_overlay_path, overlay)
            except Exception:
                pass

        # Hough telemetry (debug only)
        try:
            edges = cv2.Canny(gray, int(params["canny_lo"]), int(params["canny_hi"]))
            if save_checkerboard_debug_images and run_dir:
                try:
                    cv2.imwrite(os.path.join(run_dir, f"checkerboard_scale_{sc:.2f}_edges.png"), edges)
                except Exception:
                    pass

            lines = cv2.HoughLinesP(
                edges, 1, np.pi / 180.0,
                threshold=int(params["hough_threshold"]),
                minLineLength=max(_CFG["checkerboard"]["hough_min_line_length_px"], int(min(gray.shape) * float(params["hough_min_line_frac"]))),
                maxLineGap=int(params["hough_max_line_gap"]),
            )

            angles_deg = []
            if lines is not None:
                for ln in lines[:, 0]:
                    x1, y1, x2, y2 = map(int, ln)
                    dx = (x2 - x1)
                    dy = (y2 - y1)
                    if dx == 0 and dy == 0:
                        continue
                    ang = float(np.degrees(np.arctan2(dy, dx)))
                    ang = abs(ang) % 180.0
                    if ang > 90.0:
                        ang = 180.0 - ang
                    angles_deg.append(ang)

            out["hough_num_lines"] = 0 if lines is None else int(len(lines))
            if angles_deg:
                out["hough_angle_mean_deg"] = float(np.mean(angles_deg))
                out["hough_angle_std_deg"] = float(np.std(angles_deg))
                _dbg(f"[checkerboard] hough_num_lines={out['hough_num_lines']} "
                     f"hough_angle_mean_deg={out['hough_angle_mean_deg']:.6f} "
                     f"hough_angle_std_deg={out['hough_angle_std_deg']:.6f}")
                _dbg(f"[checkerboard] hough_angles_deg={list(np.round(angles_deg, 3))[:200]}")
            else:
                _dbg(f"[checkerboard] hough_num_lines={out['hough_num_lines']} (no angles)")
        except Exception as e:
            _dbg(f"[checkerboard] hough_exception={e}")

        _dbg(f"[checkerboard] SUCCESS scale={sc:.2f} squares={len(accepted)} mean_square_mm={mean_sq:.6f}")
        return out

    out["algorithm_error"] = "checkerboard_failed_all_scales"
    _dbg("[checkerboard] FINAL FAIL: checkerboard_failed_all_scales")

    if debug_overlay_path:
        try:
            overlay = cv2.cvtColor(gray0, cv2.COLOR_GRAY2BGR)
            cv2.putText(
                overlay,
                "checkerboard FAIL (all scales)",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imwrite(debug_overlay_path, overlay)
        except Exception:
            pass

    return out


def _nan_ring_result(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Return a ring-analysis result dict with NaN metric values.

    Used when the algorithm exits early (no edges, zero moment, etc.).
    *overrides* lets the caller inject diagnostic keys such as
    ``algorithm_error``.
    """
    result: Dict[str, Any] = {
        "mean_line_width_mm": float("nan"),
        "std_line_width_mm": float("nan"),
        "mean_spacing_mm": float("nan"),
        "std_spacing_mm": float("nan"),
        "line_width_error_mm": float("nan"),
        "spacing_error_mm": float("nan"),
        "num_peaks": 0,
        "algorithm_error": "",
    }
    if overrides:
        result.update(overrides)
    return result


def analyze_concentric_rings(
    roi: np.ndarray,
    px_per_mm: float,
    nominal_line_width_mm: float,
    nominal_spacing_mm: float,
    num_rings: int,
    debug_overlay_path: Optional[str] = None,
    debug_log_path: Optional[str] = None,
) -> Dict[str, float]:
    """
    Analyse concentric rings to estimate line width and spacing.

    Steps:
      * threshold + invert
      * find centre via image moments
      * Canny edges
      * contours on edges (RETR_TREE so all rings are included)
      * for each contour, compute mean radius from centre
      * merge similar radii into unique edge radii
      * differences between radii => alternating line widths and spacings
    """
    overlay_path = None
    gray_path = None
    thresh_path = None
    edges_path = None
    if debug_overlay_path:
        base, ext = os.path.splitext(debug_overlay_path)
        if not ext:
            ext = ".png"
        overlay_path = debug_overlay_path
        gray_path = base + "_gray" + ext
        thresh_path = base + "_thresh" + ext
        edges_path = base + "_edges" + ext

    try:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
        gray_blur = cv2.GaussianBlur(gray, tuple(_CFG["concentric_rings"]["gaussian_blur_kernel"]), 0)

        if gray_path:
            cv2.imwrite(gray_path, gray_blur)

        _, thresh = cv2.threshold(
            gray_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        binary = cv2.bitwise_not(thresh)

        if thresh_path:
            cv2.imwrite(thresh_path, binary)

        # Centre of mass of ring structure
        M = cv2.moments(binary)
        if M["m00"] == 0:
            return _nan_ring_result({"algorithm_error": "zero_moment"})

        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # Edges and contours
        edges = cv2.Canny(binary, _CFG["concentric_rings"]["canny_low"], _CFG["concentric_rings"]["canny_high"])
        if edges_path:
            cv2.imwrite(edges_path, edges)

        contours, _ = cv2.findContours(
            edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE
        )
        if not contours:
            return _nan_ring_result({"algorithm_error": "no_edges"})

        # Compute mean radius for each contour relative to centre
        radii: List[float] = []
        for c in contours:
            if len(c) < 10:
                continue
            pts = c.reshape(-1, 2)
            xs = pts[:, 0].astype(np.float32)
            ys = pts[:, 1].astype(np.float32)
            dists = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
            r_mean = float(np.mean(dists))
            r_std = float(np.std(dists))
            # Filter out degenerate contours (too small or wildly noisy)
            if r_mean < _CFG["concentric_rings"]["min_radius_px"]:
                continue
            if r_std > max(_CFG["concentric_rings"]["max_radius_std_abs"], _CFG["concentric_rings"]["max_radius_std_rel"] * r_mean):
                continue
            radii.append(r_mean)

        if not radii:
            return _nan_ring_result({"algorithm_error": "no_valid_contours"})

        # Merge nearby radii (same edge detected in pieces)
        radii_sorted = sorted(radii)
        merged: List[float] = []
        current_group: List[float] = []
        merge_threshold = _CFG["concentric_rings"]["merge_threshold_px"]

        for r in radii_sorted:
            if not current_group:
                current_group = [r]
            else:
                if abs(r - current_group[-1]) <= merge_threshold:
                    current_group.append(r)
                else:
                    merged.append(float(np.mean(current_group)))
                    current_group = [r]
        if current_group:
            merged.append(float(np.mean(current_group)))

        peaks = np.array(sorted(merged), dtype=float)
        if peaks.size < _CFG["concentric_rings"]["min_peaks_required"]:
            result = _nan_ring_result(
                {"num_peaks": int(peaks.size), "algorithm_error": "too_few_peaks"}
            )
        else:
            peaks_mm = peaks / px_per_mm
            diffs_mm = np.diff(peaks_mm)

            line_widths = diffs_mm[::2]
            spacings = diffs_mm[1::2]

            n = min(len(line_widths), num_rings)
            line_widths = line_widths[:n]
            spacings = spacings[:n]

            if line_widths.size:
                mean_line = float(np.mean(line_widths))
                std_line = float(
                    np.std(line_widths, ddof=1) if line_widths.size > 1 else 0.0
                )
            else:
                mean_line = float("nan")
                std_line = float("nan")

            if spacings.size:
                mean_spacing = float(np.mean(spacings))
                std_spacing = float(
                    np.std(spacings, ddof=1) if spacings.size > 1 else 0.0
                )
            else:
                mean_spacing = float("nan")
                std_spacing = float("nan")

            line_err = (
                mean_line - nominal_line_width_mm
                if not math.isnan(mean_line)
                else float("nan")
            )
            spacing_err = (
                mean_spacing - nominal_spacing_mm
                if not math.isnan(mean_spacing)
                else float("nan")
            )

            result = {
                "mean_line_width_mm": mean_line,
                "std_line_width_mm": std_line,
                "mean_spacing_mm": mean_spacing,
                "std_spacing_mm": std_spacing,
                "line_width_error_mm": line_err,
                "spacing_error_mm": spacing_err,
                "num_peaks": int(peaks.size),
                "algorithm_error": "",
            }

    except Exception as exc:
        result = _nan_ring_result({"algorithm_error": f"{type(exc).__name__}: {exc}"})
        peaks = np.array([], dtype=float)

    # Debug overlay: centre + all merged edge radii
    if overlay_path:
        if roi.ndim == 2:
            overlay = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        else:
            overlay = roi.copy()
        cv2.circle(overlay, (cx, cy), 4, (0, 0, 255), -1)
        if "num_peaks" in result and result["num_peaks"] > 0:
            for r_px in peaks:
                cv2.circle(overlay, (cx, cy), int(round(r_px)), (0, 255, 0), 1)
        cv2.imwrite(overlay_path, overlay)

    return result


# ---------------------------------------------------------------------------
# Pitch ruler analysis — supports X/Y orientation
# ---------------------------------------------------------------------------

def analyze_pitch_ruler(
    roi: np.ndarray,
    px_per_mm: float,
    nominal_widths_mm: List[float],
    orientation: str = "x",
    debug_overlay_path: Optional[str] = None,
    debug_log_path: Optional[str] = None,
    use_true_edge_width: bool = False,
) -> Dict[str, float]:
    """Analyse a pitch ruler by measuring bar widths.

    orientation:
      - "x": bars primarily vertical, measure width in X
      - "y": bars primarily horizontal, measure width in Y

    By default this preserves the legacy bounding-box measurement. If
    use_true_edge_width=True, it will attempt to measure width from Canny
    edge pixels inside each bar's bounding box to reduce threshold bleed.
    """
    dbg = _dbg_open(debug_log_path)
    _dbg(dbg, f"[pitch] method={'true_edge_v1' if use_true_edge_width else 'bounding_rect_v1'} orientation={orientation} px_per_mm={px_per_mm:.6f}")
    try:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()
        if gray.dtype != np.uint8:
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # threshold ink (dark) -> white foreground
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        _pk = _CFG["pitch_ruler"]["morph_kernel_size"]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (_pk, _pk))
        binary = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=_CFG["pitch_ruler"]["morph_close_iterations"])
        clean = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=_CFG["pitch_ruler"]["morph_open_iterations"])

        cnts, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if orientation.lower() == "y":
            cnts_sorted = sorted(cnts, key=lambda c: cv2.boundingRect(c)[1])
            cnts_sorted = list(reversed(cnts_sorted))
        else:
            cnts_sorted = sorted(cnts, key=lambda c: cv2.boundingRect(c)[0])

        # optionally compute edge map once
        edges = None
        if use_true_edge_width:
            edges = cv2.Canny(gray, _CFG["pitch_ruler"]["canny_low"], _CFG["pitch_ruler"]["canny_high"])

        measured_widths: List[float] = []
        percent_errors: List[float] = []

        overlay = roi.copy()
        if overlay.ndim == 2:
            overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)

        for idx, cnt in enumerate(cnts_sorted[: len(nominal_widths_mm)]):
            x, y, w, h = cv2.boundingRect(cnt)

            width_px = None
            if use_true_edge_width and edges is not None:
                sub = edges[y:y+h, x:x+w]
                ys, xs = np.where(sub > 0)
                if xs.size > 0 and ys.size > 0:
                    if orientation.lower() == "y":
                        width_px = float(ys.max() - ys.min())
                    else:
                        width_px = float(xs.max() - xs.min())

            if width_px is None or width_px <= 0:
                width_px = float(h if orientation.lower() == "y" else w)

            width_mm = width_px / px_per_mm if px_per_mm > 0 else float("nan")
            measured_widths.append(float(width_mm))

            nom = float(nominal_widths_mm[idx]) if idx < len(nominal_widths_mm) else float("nan")
            if nom and not math.isnan(width_mm):
                percent_errors.append(float((width_mm - nom) / nom * 100.0))
            else:
                percent_errors.append(float("nan"))

            # overlay box
            cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 255, 0), 2)

        _dbg(dbg, f"[pitch] contours={len(cnts)} used={min(len(cnts_sorted), len(nominal_widths_mm))} widths_mm={measured_widths}")

        if debug_overlay_path:
            try:
                label = "true_edge" if use_true_edge_width else "bounding_rect"
                cv2.putText(overlay, f"{label} {orientation}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                cv2.imwrite(debug_overlay_path, overlay)
            except Exception:
                pass

        
        # ------------------------------------------------------------------
        # Derived resolution metrics (added for health/compensation reporting)
        # ------------------------------------------------------------------
        try:
            _pairs = []
            for _nom, _meas, _perr in zip(nominal_widths_mm, measured_widths, percent_errors):
                if _meas is None:
                    continue
                if isinstance(_meas, float) and math.isnan(_meas):
                    continue
                if isinstance(_nom, float) and math.isnan(_nom):
                    continue
                _pairs.append((float(_nom), float(_meas), float(_perr) if (_perr is not None and not (isinstance(_perr, float) and math.isnan(_perr))) else float('nan')))
            if _pairs:
                # Smallest nominal width that produced a finite measurement
                _min_nom, _min_meas, _min_perr = min(_pairs, key=lambda t: t[0])
                min_resolvable_nominal_mm = float(_min_nom)
                min_resolvable_measured_mm = float(_min_meas)
                min_resolvable_error_pct = float(_min_perr)
                min_resolvable_error_mm = float(_min_meas - _min_nom)
            else:
                min_resolvable_nominal_mm = float('nan')
                min_resolvable_measured_mm = float('nan')
                min_resolvable_error_pct = float('nan')
                min_resolvable_error_mm = float('nan')
        except Exception:
            min_resolvable_nominal_mm = float('nan')
            min_resolvable_measured_mm = float('nan')
            min_resolvable_error_pct = float('nan')
            min_resolvable_error_mm = float('nan')
        return {
            "measured_widths_mm": ",".join(f"{w:.4f}" if not math.isnan(w) else "nan" for w in measured_widths),
            "percent_errors": ",".join(f"{e:.2f}" if not math.isnan(e) else "nan" for e in percent_errors),
            "nominal_widths_mm": ",".join(f"{w:.4f}" if not math.isnan(float(w)) else "nan" for w in nominal_widths_mm),
            "min_resolvable_nominal_mm": float(min_resolvable_nominal_mm),
            "min_resolvable_measured_mm": float(min_resolvable_measured_mm),
            "min_resolvable_error_mm": float(min_resolvable_error_mm),
            "min_resolvable_error_pct": float(min_resolvable_error_pct),
            "width_mode": "true_edge" if use_true_edge_width else "bounding_rect",
            "algorithm_error": "",
        }
    except Exception as e:
        tb = traceback.format_exc()
        _dbg(dbg, f"[pitch] ERROR: {e}\n{tb}")
        if debug_overlay_path:
            try:
                vis = roi.copy()
                if vis.ndim == 2:
                    vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
                cv2.putText(vis, "PITCH ERROR", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                cv2.imwrite(debug_overlay_path, vis)
            except Exception:
                pass
        return {
            "measured_widths_mm": "",
            "percent_errors": "",
            "width_mode": "true_edge" if use_true_edge_width else "bounding_rect",
            "algorithm_error": f"pitch_exception: {e}",
        }
    finally:
        try:
            if dbg:
                dbg.close()
        except Exception:
            pass


def recommend_compensation_for_dot(summary: Dict[str, float]) -> str:
    """Generate geometric compensation recommendations from dot-array metrics."""
    lines: List[str] = []

    sx_err = summary.get("spacing_x_error_pct")
    sy_err = summary.get("spacing_y_error_pct")

    def add_scale(axis: str, err_pct: Optional[float]) -> None:
        if err_pct is None:
            return
        if isinstance(err_pct, float) and math.isnan(err_pct):
            return

        # Small deadband: ignore errors inside measurement noise
        deadband_pct = _CFG["health_report"]["deadband_threshold_pct"]
        if abs(err_pct) < deadband_pct:
            return

        # Printed spacing = nominal * (1 + err_pct/100)
        # To bring printed spacing back to nominal:
        scale = 1.0 / (1.0 + err_pct / 100.0)  # unitless factor, ~1.0

        if err_pct > 0:
            verb = "shrink"
            sense = "larger"
        else:
            verb = "enlarge"
            sense = "smaller"

        lines.append(
            f"Printed spacing in {axis} is {err_pct:+.2f}% {sense} than nominal. "
            f"Apply a scale factor of {scale:.4f} in {axis} "
            f"(i.e. {verb} geometry to {scale * 100:.2f}% of its current size)."
        )

    add_scale("X", sx_err)
    add_scale("Y", sy_err)

    # Dot-grid rotation is computed for diagnostics, but the tool does NOT recommend
    # using it for angular compensation (it is often unstable on symmetric grids).
    raw_angle = summary.get(
        "grid_rotation_raw_deg",
        summary.get("grid_rotation_deg"),
    )
    if raw_angle is not None and not (isinstance(raw_angle, float) and math.isnan(raw_angle)):
        angle = float(raw_angle)
        angle_mod = ((angle + 90.0) % 180.0) - 90.0
        if abs(angle_mod) > 0.1:
            lines.append(
                f"Dot-grid rotation diagnostic: {angle_mod:+.2f}° (raw {angle:+.2f}°). "
                f"Use checkerboard angle for yaw compensation; treat dot rotation as a stability check."
            )

    return "\n".join(lines)


from typing import List, Tuple  # ensure this import is present


def recommend_compensation_overall(
    results_summary: List[Tuple[str, Dict[str, float]]],
) -> str:
    """Generate a printer "health report" and compensation recommendations.

    Philosophy
    ----------
    - **Action metrics** produce explicit compensation: global scale (X/Y) and yaw (checkerboard angle).
    - **Diagnostic metrics** indicate process health or failure modes (repeatability, anisotropy, edge fidelity, resolution).

    The GUI writes this string to ``dimensional_compensation.txt`` when non-empty.
    """
    by_feat: Dict[str, Dict[str, float]] = {}
    for feat, summ in results_summary:
        if isinstance(summ, dict):
            by_feat[feat] = summ

    dot = by_feat.get("dot")
    cb = by_feat.get("checkerboard")

    # Rings may appear as 'rings'
    rings = by_feat.get("rings")

    # Pitch can appear as 'pitch_x' and/or 'pitch_y'
    pitch_x = by_feat.get("pitch_x")
    pitch_y = by_feat.get("pitch_y")

    lines: List[str] = []
    lines.append("BJAM Dimensional Health Report")
    lines.append("")

    # ------------------------------------------------------------------
    # 1) Actionable compensation (things the user can actually change)
    # ------------------------------------------------------------------
    lines.append("Actionable compensation")
    lines.append("----------------------")

    # Scale corrections:
    # Prefer dot-spacing (centroid lattice) because it is less sensitive to dot morphology/spread.
    # Fall back to dot diameter if spacing is unavailable.
    def _finite(x: Any) -> bool:
        return x is not None and not (isinstance(x, float) and math.isnan(x))

    # Helper to format signed percent
    def _pct(x: float) -> str:
        return f"{x:+.3f}%"

        # ------------------------------------------------------------------
    # 1) Actionable compensation (clear, non-duplicated recommendations)
    # ------------------------------------------------------------------
    lines.append("Actionable compensation")
    lines.append("----------------------")

    # Scaling philosophy:
    # - Use centroid-derived pitch (dot spacing) to calibrate *motion scale* (what the gantry thinks it is doing).
    # - Treat dot diameter as a *deposition/morphology* diagnostic (drop volume + wicking + spreading).
    #
    # This avoids telling the user to "scale" a motion system when the real issue is under/over deposition.
    spacing_action_thresh_pct = _CFG["health_report"]["scale_pct_threshold"]   # below this, we treat motion scale as "already calibrated"
    diameter_action_thresh_pct = _CFG["health_report"]["diameter_error_pct_threshold"]  # diameter error beyond this is worth calling out explicitly

    # ------------------------------------------------------------------
    # Calibration vs compensation: two distinct "scale" signals
    #
    # (A) Geometric (kinematic) scale: centroid spacing (trusted placement).
    # (B) Morphological (deposition) scale: dot diameter (feature growth / drop physics).
    #
    # We report BOTH, but label them clearly so users understand the tradeoff.
    # ------------------------------------------------------------------

    # Thresholds (percent). Keep small so we don't spam tiny changes.
    SCALE_PCT_THRESH = _CFG["health_report"]["scale_pct_threshold"]

    # --- A) Geometric scale (motion calibration) from dot centroid spacing ---
    geom_available = False
    if dot:
        x_err = dot.get("spacing_x_error_pct")
        y_err = dot.get("spacing_y_error_pct")
        if _finite(x_err) and _finite(y_err):
            geom_available = True
            mx = abs(float(x_err))
            my = abs(float(y_err))

            # Convert error to a multiplicative correction: nominal/measured = 1/(1+err)
            # where err = (measured-nominal)/nominal.
            def _mult_from_pct(err_pct: float) -> float:
                return 1.0 / (1.0 + (float(err_pct) / 100.0))

            xm = _mult_from_pct(float(x_err))
            ym = _mult_from_pct(float(y_err))

            if max(mx, my) < SCALE_PCT_THRESH:
                lines.append("Geometric scale (motion calibration): no significant centroid-based scale error detected.")
                lines.append("  Interpretation: feature placement pitch is correctly scaled; no XY calibration correction required.")
            else:
                lines.append(
                    f"Geometric scale (motion calibration): multiply X by {xm:.6f} "
                    f"({float(x_err):+0.3f}% spacing error)."
                )
                lines.append(
                    f"Geometric scale (motion calibration): multiply Y by {ym:.6f} "
                    f"({float(y_err):+0.3f}% spacing error)."
                )
                lines.append(
                    "  Interpretation: this corrects kinematic placement (steps/mm, encoder scaling, toolpath units)."
                )

    if not geom_available:
        lines.append("Geometric scale (motion calibration): unavailable (dot spacing not analyzed).")

    # --- B) Morphological scale (dot size compensation) from dot diameter ---
    morph_available = False
    if dot:
        d_err = dot.get("diameter_error_pct")
        if _finite(d_err):
            morph_available = True
            md = abs(float(d_err))

            def _mult_from_pct(err_pct: float) -> float:
                return 1.0 / (1.0 + (float(err_pct) / 100.0))

            dm = _mult_from_pct(float(d_err))

            if md < SCALE_PCT_THRESH:
                lines.append("Morphological scale (dot size compensation): no significant dot-size bias detected.")
                lines.append(
                    "  Interpretation: average dot diameter matches nominal; drop volume + wetting appear well-tuned."
                )
            else:
                # If dots are undersized, err is negative and dm > 1.0 (scale up).
                lines.append(
                    f"Morphological scale (dot size compensation): dots are {float(d_err):+0.3f}% vs nominal."
                )
                lines.append(
                    f"  Recommendation: multiply XY by {dm:.6f} *if compensating for dot-size bias*."
                )
                lines.append(
                    "  Interpretation: this compensates deposition physics (drop volume, wetting/absorption, "
                    "jetting frequency vs motion speed, standoff). It is not a true motion calibration."
                )
                lines.append(
                    "  Note: use this when printed feature size matters more than absolute placement pitch. "
                    "If centroid spacing is already correct, consider process tuning instead of XY scaling."
                )

    if not morph_available:
        lines.append("Morphological scale (dot size compensation): unavailable (dot diameter not analyzed).")

    # If both are available, explicitly flag disagreement as a diagnostic.
    if geom_available and morph_available:
        x_err = float(dot.get("spacing_x_error_pct"))
        y_err = float(dot.get("spacing_y_error_pct"))
        d_err = float(dot.get("diameter_error_pct"))
        if (abs(x_err) < SCALE_PCT_THRESH and abs(y_err) < SCALE_PCT_THRESH) and (abs(d_err) >= SCALE_PCT_THRESH):
            lines.append(
                "  Cross-check: spacing is calibrated but dot diameter is biased. "
                "This strongly suggests morphology-driven size error (not kinematic scaling)."
            )

    # Yaw (angular) compensation: checkerboard is the authoritative signal.
    if cb:
        ang_err = cb.get("checkerboard_angle_error_deg", cb.get("angle_deg"))
        if _finite(ang_err) and abs(float(ang_err)) > _CFG["health_report"]["yaw_threshold_deg"]:
            direction = "clockwise" if float(ang_err) > 0 else "counter-clockwise"
            lines.append(
                f"Yaw (printhead/stage rotation): adjust {direction} by about {abs(float(ang_err)):.3f}° "
                f"(checkerboard angle error)."
            )
        else:
            lines.append("Yaw: no significant checkboard-based rotation detected (or below threshold).")
    else:
        lines.append("Yaw: checkerboard not analyzed.")

    lines.append("")

    # ------------------------------------------------------------------
    # 2) Dot array diagnostics (health signals, not direct compensation)
    # ------------------------------------------------------------------
    lines.append("Dot array diagnostics")
    lines.append("-------------------")
    if not dot:
        lines.append("Dot array not analyzed.")
        lines.append("")
    else:
        n = dot.get("num_blobs")
        if _finite(n):
            lines.append(f"Detected dots: {int(round(float(n)))}")

        # Repeatability (droplet-to-droplet consistency)
        mean_d = dot.get("avg_diameter_mm")
        std_d = dot.get("std_diameter_mm")
        if _finite(mean_d) and _finite(std_d) and float(mean_d) != 0:
            cv = 100.0 * float(std_d) / abs(float(mean_d))
            lines.append(f"Diameter repeatability (CV): {cv:.2f}% (std {float(std_d):.4f} mm).")
            if cv <= _CFG["health_report"]["cv_threshold_very_stable"]:
                lines.append("  Interpretation: very stable jetting. This suggests consistent drop volume and good nozzle health.")
            elif cv <= _CFG["health_report"]["cv_threshold_moderate"]:
                lines.append("  Interpretation: moderate dot-to-dot variation. Watch ink pressure/temperature drift and occasional weak nozzles.")
            else:
                lines.append("  Interpretation: high dot-to-dot variation. This often points to nozzle dropouts, unstable pressure regulation, or thresholding/segmentation failure.")
        elif _finite(std_d):
            lines.append(f"Diameter std dev: {float(std_d):.4f} mm")        # Dot size bias (diagnostic): diameter error reflects deposition + spreading, not motion scale.
        diam_err_pct = dot.get("diameter_error_pct")
        diam_mult = dot.get("scale_xy_from_diameter")
        if _finite(diam_err_pct) and _finite(diam_mult):
            de = float(diam_err_pct)
            dm = float(diam_mult)
            sense = "undersized" if de < 0 else "oversized"
            lines.append(f"Dot size bias (diameter error): { _pct(de) } ({sense} vs nominal).")
            lines.append(f"Diameter-based scale cross-check: multiply XY by {dm:.6f} (diagnostic only).")
            if geom_available:
                lines.append(
                    "  Interpretation: dot spacing calibrates the motion frame. If spacing looks calibrated but dots are "
                    f"{sense}, the dominant error is deposition morphology (drop volume, wetting, wicking), not XY motion scale."
                )
            else:
                lines.append(
                    "  Interpretation: dot diameter is sensitive to spreading and drop volume. Prefer dot spacing for motion scale when available."
                )

            if abs(de) >= _CFG["health_report"]["diameter_error_pct_threshold"]:
                if de < 0:
                    lines.append(
                        "  Watch-outs: under-deposition or limited spreading. Check jetting waveform/drive, nozzle health, ink supply pressure, "
                        "stand-off height, and gantry speed vs firing rate (phase error)."
                    )
                else:
                    lines.append(
                        "  Watch-outs: over-deposition or excessive spreading/coalescence. Check drop volume, substrate wetting/porosity, "
                        "ink viscosity, and jetting frequency vs motion speed."
                    )

        # Circularity (process health: shape integrity beyond pixel-lattice bias)
        c_norm = dot.get("avg_circularity_norm")
        if _finite(c_norm):
            cn = float(c_norm)
            lines.append(f"Normalized circularity (mean): {cn:.3f} (1.0 is ideal for this imaging pipeline).")
            if cn >= _CFG["health_report"]["circularity_threshold_high"]:
                lines.append("  Interpretation: dots are compact with clean edges. Spreading/coalescence is low under current conditions.")
            elif cn >= _CFG["health_report"]["circularity_threshold_med"]:
                lines.append("  Interpretation: mild edge growth or roughness. Watch binder spread, substrate absorption, and scan contrast.")
            else:
                lines.append("  Interpretation: significant spreading/coalescence or rough edges. Scaling and yaw compensation will not fix this. Check binder formulation/viscosity, droplet volume, substrate wetting, and jetting frequency vs motion speed.")

        # Anisotropy (directional distortion): eccentricity / aspect ratio / orientation
        ecc = dot.get("mean_eccentricity", dot.get("halo_eccentricity"))
        ar = dot.get("mean_aspect_ratio")
        ang = dot.get("mean_major_axis_angle_deg")
        if _finite(ecc):
            lines.append(f"Mean eccentricity: {float(ecc):.3f} (0 is circular).")
        if _finite(ar):
            lines.append(f"Mean aspect ratio (major/minor): {float(ar):.3f}.")
        if _finite(ang):
            lines.append(f"Mean ellipse orientation: {float(ang):.1f}° (diagnostic only).")

        # Provide a single, explicit physical interpretation of anisotropy.
        if (_finite(ar) and float(ar) > _CFG["health_report"]["aspect_ratio_threshold"]) or (_finite(ecc) and float(ecc) > _CFG["health_report"]["eccentricity_threshold"]):
            lines.append("  Interpretation: consistent elongation indicates directional spreading or timing mismatch between gantry velocity and jetting (phase error).")
            lines.append("  What to check: jetting trigger timing vs motion, raster direction effects, paper fiber orientation, and any airflow/recoater interaction that biases wetting.")
        else:
            if _finite(ar) or _finite(ecc):
                lines.append("  Interpretation: low anisotropy. Jetting appears well-synchronized with motion and spreading is approximately isotropic.")

        # Dot-grid rotation: explicitly de-emphasized for compensation

        dg = dot.get("grid_rotation_deg")
        if _finite(dg) and abs(float(dg)) > _CFG["health_report"]["grid_rotation_threshold_deg"]:
            lines.append(f"Dot-grid rotation (diagnostic): {float(dg):+.2f}° (not used for yaw compensation).")

        lines.append("")

    # ------------------------------------------------------------------
    # 3) Checkerboard diagnostics (scale cross-check + yaw confidence)
    # ------------------------------------------------------------------
    lines.append("Checkerboard diagnostics")
    lines.append("----------------------")
    if not cb:
        lines.append("Checkerboard not analyzed.")
        lines.append("")
    else:
        mean_sq = cb.get("mean_square_mm")
        sq_err_pct = cb.get("square_error_pct")
        if _finite(mean_sq):
            lines.append(f"Mean square size: {float(mean_sq):.4f} mm")
            lines.append("  Interpretation: average printed square pitch. Use as a sanity-check against dot-derived scale, since dots can change size with spreading.")
        if _finite(sq_err_pct):
            lines.append(
                f"Square size error: {float(sq_err_pct):+.3f}% (diagnostic cross-check; primary scale comes from dot spacing)."
            )
            if abs(float(sq_err_pct)) <= _CFG["health_report"]["square_error_tolerance_pct"]:
                lines.append("  Interpretation: checkerboard agrees with dot-based calibration. Scale is likely well-captured.")
            else:
                lines.append("  Interpretation: mismatch suggests either dot morphology effects (spreading) or local distortion/segmentation. Trust dot spacing for calibration; treat checkerboard scale as a warning flag.")
        nsq = cb.get("num_squares")
        if _finite(nsq):
            lines.append(f"Detected squares: {int(round(float(nsq)))}")
            lines.append("  Interpretation: low counts can make rotation/size less stable. Ensure ROI fully contains the checkerboard and contrast is high.")
        lines.append("")

    # ------------------------------------------------------------------
    # 4) Concentric rings diagnostics (edge fidelity stress test)
    # ------------------------------------------------------------------
    lines.append("Concentric rings diagnostics")
    lines.append("---------------------------")
    if not rings:
        lines.append("Concentric rings not analyzed.")
        lines.append("")
    else:
        lw = rings.get("mean_line_width_mm")
        lw_std = rings.get("std_line_width_mm")
        sp = rings.get("mean_spacing_mm")
        sp_std = rings.get("std_spacing_mm")
        npeaks = rings.get("num_peaks")

        if _finite(lw):
            lines.append(f"Mean line width: {float(lw):.4f} mm")
            lines.append("  Interpretation: average edge growth of a thin, high-curvature feature. Bias here is a strong indicator of spreading/over-deposition.")
        if _finite(lw_std):
            lines.append(f"Line width std dev: {float(lw_std):.4f} mm")
            lines.append("  Interpretation: edge roughness and stability. High variability suggests unstable wetting, contrast loss, or segmentation instability.")
        if _finite(sp):
            lines.append(f"Mean spacing: {float(sp):.4f} mm")
            lines.append("  Interpretation: fidelity of alternating structures. Bias implies adjacent lines are merging (spread) or opening (under-deposition/contrast thresholding).")
        if _finite(sp_std):
            lines.append(f"Spacing std dev: {float(sp_std):.4f} mm")
            lines.append("  Interpretation: local non-uniformity. High values indicate intermittent merging, broken edges, or inconsistent thresholding across the ROI.")
        if _finite(npeaks):
            lines.append(f"Detected peak count: {int(round(float(npeaks)))}")
            lines.append("  Interpretation: fragmentation/contrast complexity. Higher counts often mean noisy edges and over-segmentation; very low counts can indicate washed-out contrast or merged rings.")

        # If nominal targets were provided, report bias explicitly.
        nom_lw = rings.get("nominal_line_width_mm", rings.get("nominal_ring_line_mm"))
        nom_sp = rings.get("nominal_spacing_mm", rings.get("nominal_ring_gap_mm"))
        if _finite(nom_lw) and _finite(lw):
            lw_bias = float(lw) - float(nom_lw)
            lines.append(f"  Line width bias vs nominal ({float(nom_lw):.3f} mm): {lw_bias:+.4f} mm.")
        if _finite(nom_sp) and _finite(sp):
            sp_bias = float(sp) - float(nom_sp)
            lines.append(f"  Spacing bias vs nominal ({float(nom_sp):.3f} mm): {sp_bias:+.4f} mm.")

        lines.append("  Note: rings are a process-window stress test, not a direct calibration knob. Use them to spot edge-quality drift before it shows up in bulk dimensions.")
        lines.append("")

    # ------------------------------------------------------------------
    # 5) Pitch ruler diagnostics (resolution limit + accuracy at that limit)
    # ------------------------------------------------------------------
    lines.append("Pitch ruler diagnostics")
    lines.append("----------------------")

    def _pitch_block(label: str, p: Optional[Dict[str, float]]) -> List[str]:
        out: List[str] = []
        if not p:
            return out

        # Smallest nominal width that produced any finite measurement
        mn = p.get("min_resolvable_nominal_mm")
        me = p.get("min_resolvable_measured_mm")
        ep = p.get("min_resolvable_error_pct")
        em = p.get("min_resolvable_error_mm")

        if _finite(mn):
            msg = f"{label}: minimum resolvable nominal width ≈ {float(mn):.3f} mm"
            if _finite(ep):
                msg += f" (error {float(ep):+.2f}%"
                if _finite(em):
                    msg += f", {float(em):+.4f} mm"
                msg += ")."
            else:
                msg += "."
            out.append(msg)

        # Smallest nominal width that is also accurate (|error| <= 10%)
        try:
            nom_s = str(p.get("nominal_widths_mm", ""))
            meas_s = str(p.get("measured_widths_mm", ""))
            err_s = str(p.get("percent_errors", ""))
            noms = [float(x) for x in nom_s.split(",") if x.strip() != ""]
            meas = [float(x) for x in meas_s.split(",") if x.strip() != ""]
            errs = [float(x) for x in err_s.split(",") if x.strip() != ""]
            triples = []
            for nom, mval, e in zip(noms, meas, errs):
                if math.isnan(nom) or math.isnan(mval) or math.isnan(e):
                    continue
                triples.append((nom, mval, e))
            _pitch_acc_thresh = _CFG["health_report"]["pitch_accuracy_threshold_pct"]
            good = [(nom, mval, e) for (nom, mval, e) in triples if abs(e) <= _pitch_acc_thresh]
            if good:
                nom_g, m_g, e_g = min(good, key=lambda t: t[0])
                out.append(
                    f"{label}: minimum *accurate* nominal width (|error|<={_pitch_acc_thresh}%) ≈ {nom_g:.3f} mm "
                    f"(error {e_g:+.2f}%, {m_g - nom_g:+.4f} mm)."
                )
        except Exception:
            pass

        out.append("  Interpretation: pitch limits are process + imaging dependent. Error typically increases as features approach the resolution floor (spreading, contrast loss, and pixel quantization).")
        return out
        mn = p.get("min_resolvable_nominal_mm")
        me = p.get("min_resolvable_measured_mm")
        ep = p.get("min_resolvable_error_pct")
        em = p.get("min_resolvable_error_mm")
        if _finite(mn):
            msg = f"{label}: minimum resolvable nominal width ≈ {float(mn):.3f} mm"
            if _finite(ep):
                msg += f" (error {float(ep):+.2f}%"
                if _finite(em):
                    msg += f", {float(em):+.4f} mm"
                msg += ")."
            else:
                msg += "."
            out.append(msg)
            out.append("  Interpretation: this is process + imaging condition dependent, not an absolute machine limit.")
        return out

    pitch_lines: List[str] = []
    pitch_lines += _pitch_block("Pitch X", pitch_x)
    pitch_lines += _pitch_block("Pitch Y", pitch_y)

    if not pitch_lines:
        lines.append("Pitch ruler not analyzed.")
    else:
        lines.extend(pitch_lines)

    lines.append("")

    # If everything is missing, return empty string so GUI doesn't write a file.
    meaningful = any(s.strip() for s in lines[2:])  # ignore title lines
    return "\n".join(lines).strip() if meaningful else ""
