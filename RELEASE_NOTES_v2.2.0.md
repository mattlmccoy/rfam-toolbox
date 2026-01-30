# bjam-toolbox v2.2.0 Release Notes

**Release Date:** January 2026
**Previous Version:** 2.1.0

---

## Highlights

- **Bayesian GMM Classifier** — New production-ready classifier achieving 98.9% accuracy on petroleum concentration discrimination and 99.4% on unified 3-class material classification, with built-in uncertainty quantification
- **GP Concentration Estimator** — Gaussian Process regression for continuous concentration estimation with calibrated confidence intervals (MAE = 0.68 wt%)
- **Seaborn Plotting Overhaul** — All plotting across the entire ink concentration suite upgraded to publication-quality seaborn visuals
- **Standalone Plotting Mode** — New dedicated plotting workflow accessible from the IC menu
- **Bundled Sample Data** — Training and test datasets ship inside the package for immediate use

---

## New Features

### Bayesian GMM Classifier (`bayesian_classifier.py`)
- **`BayesianGMMClassifier`** class: per-class Bayesian Gaussian Mixture Model with posterior inference via Bayes' rule
  - Optimal config: `n_components=1`, `covariance_type="full"` (simplest config that achieves best accuracy)
  - `predict_proba()` — calibrated posterior class probabilities via numerically-stable softmax
  - `predict_with_uncertainty()` — returns predictions, probabilities, and normalized entropy uncertainty in [0, 1]
  - Validated against 7 alternative methods (kNN, LR, QDA, GP) in the exploratory notebook
- **GP Regressor** for continuous concentration estimation
  - Matern-2.5 kernel + WhiteKernel, `normalize_y=True`
  - Leave-one-out MAE = 0.68 wt%, RMSE = 2.26 wt%
  - Calibrated uncertainty bands (82.7% within 1-sigma, 90.8% within 2-sigma)
- **Tkinter GUI** (`BayesianClassifierDialog`) with options for GP regression, decision boundaries, and calibration plots
- **6 publication-quality plot functions:**
  - Decision boundary with posterior probability contours
  - Uncertainty heatmap over feature space
  - Calibration curve (predicted probability vs observed frequency)
  - GP regression: predicted vs actual with 2-sigma error bars
  - Confusion matrix (seaborn heatmap)
  - Per-sample posterior probability strip plots
  - Session prediction confidence bar chart

### Standalone Plotting Mode (`plotting.py`)
- New dedicated plotting workflow accessible from the IC menu (no longer a stub)
- Tkinter dialog with file selection, grouping options, and per-plot toggles
- Generates: boxplot, bar chart, swarm plot, histogram-metric charts, and feature pairplot
- All plots use consistent seaborn theming

### Bundled Sample Data (`sample_data/`)
- Training and test CSVs ship inside the package at `bjam_toolbox/ink_concentration/sample_data/`
- **`chroma_training_data.csv`** — 175 chroma paper samples (63x 5wt% petro, 35x 25wt% petro, 77x 25wt% IPA)
- **`test_bayesian_3class.csv`** — 15 hold-out samples (5 per class)
- **`test_5petro_25IPA.csv`** — 10 hold-out samples (5x 5wt% petro + 5x IPA)
- **`test_concentration.csv`** — 6 petroleum-only samples for concentration estimation
- Programmatic access: `from bjam_toolbox.ink_concentration.sample_data import get_path`

### Exploratory Notebook
- `notebooks/bayesian_concentration_classifier.ipynb` — Full model comparison and development notebook with all results that informed the production implementation

---

## Improvements

### Seaborn Plotting Overhaul
All plotting across the ink concentration suite has been upgraded from raw matplotlib to seaborn with consistent theming:

- **`plots.py`** — Complete rewrite: all 12 plot functions now use `sns.barplot()`, `sns.histplot()`, `sns.boxplot()`, `sns.stripplot()`, `sns.scatterplot()` with whitegrid theme and muted palette. Automatic ink-type colour coding via `INK_PALETTE`.
- **`classification.py`** — Decision-region plots updated with consistent colour palette. Grouped intensity section replaced: raw boxplot -> `sns.boxplot()` + `sns.stripplot()` overlay, raw bar chart -> `sns.barplot()`, manual jitter scatter -> `sns.swarmplot()`.
- **`concentration_estimator.py`** — Calibration curve plot redesigned with seaborn palette and proper legend elements.

### IC Menu Updates
- Added "Bayesian Classification" button (mode 3)
- Replaced plotting stub with functional "Plotting" button
- Menu now has 5 working modes: Data Collection, Classification, Bayesian Classification, Plotting, Concentration Estimation

---

## Bug Fixes

- **k-fold CV crash in Bayesian classifier** — `np.bincount()` on non-zero-based ink_keys (1,2,3) included an empty bin-0, producing `n_splits=0` and crashing `StratifiedKFold`. Fixed to use `np.unique(return_counts=True)`.
- **Concentration estimator NaN crash** — When the consolidated training CSV (containing all 3 classes) was used, IPA samples (ink_key=3) mapped to NaN concentration targets, crashing `IsotonicRegression`. Fixed by automatically filtering to petroleum-only samples before fitting.

---

## Dependencies

- **Added:** `seaborn>=0.12.0` as a core dependency
- **Existing:** opencv-python, numpy, matplotlib, pandas, scikit-image, scikit-learn, scipy, pdf2image

---

## Upgrade Instructions

```bash
pip install --upgrade bjam-toolbox
```

Or from source:
```bash
git pull origin main
pip install -e .
```

---

## Testing the New Features

### Bayesian Classification
1. `bjam-toolbox` -> Bayesian Classification
2. Training CSVs: navigate to `bjam_toolbox/ink_concentration/sample_data/chroma_training_data.csv`
3. Session CSVs: select `test_bayesian_3class.csv` from the same directory

### Concentration Estimation
1. `bjam-toolbox` -> Concentration Estimation
2. Training CSVs: `chroma_training_data.csv` (IPA samples are automatically filtered)
3. Session CSVs: `test_concentration.csv`

### Standalone Plotting
1. `bjam-toolbox` -> Plotting
2. Select any CSV(s) -> choose grouping -> Generate Plots

### Programmatic Data Access
```python
from bjam_toolbox.ink_concentration.sample_data import get_path, list_files
print(list_files())
training = get_path("chroma_training_data.csv")
```
