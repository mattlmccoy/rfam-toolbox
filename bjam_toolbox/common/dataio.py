"""Data I/O for BJAM Image Analysis Tool."""
import pandas as pd
import datetime
import os


def build_dataframe(results_list, metadata):
    """Build pandas DataFrame from list of results dicts and metadata dict."""
    df = pd.DataFrame(results_list)
    # Prepend metadata columns
    for key, value in metadata.items():
        df[key] = value
    # Reorder columns: metadata first
    cols = list(metadata.keys()) + [c for c in df.columns if c not in metadata]
    df = df[cols]
    return df

def export_csv(df, output_dir):
    """Export DataFrame to CSV with timestamp."""
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'results_{timestamp}.csv'
    path = os.path.join(output_dir, filename)
    df.to_csv(path, index=False)
    return path

