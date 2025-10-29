#!/usr/bin/env python
# coding: utf-8

import os
import yaml
import glob
from utils.helpers import print_header
from utils.duckdb_helpers import connect_duckdb

# Load config
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

testing_mode = config['general'].get('testing_mode', False)
data_root = config['paths']['data_root']
processed_subfolder = config['paths']['processed_subfolder']
identifiers_subfolder = config['paths']['identifiers_subfolder']

# Find latest publication folder dynamically
pub_folders = sorted([d for d in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, d))], reverse=True)
if not pub_folders:
    raise FileNotFoundError(f"No publication folders found in {data_root}")
latest_pub = pub_folders[0]

processed_root = os.path.join(data_root, latest_pub, processed_subfolder)
if not os.path.exists(processed_root):
    raise FileNotFoundError(f"Processed folder not found: {processed_root}")

# Find master parquet file
master_files = glob.glob(os.path.join(processed_root, "*-master.parquet"))
if not master_files:
    raise FileNotFoundError(f"No master parquet files found in: {processed_root}")
master_parquet = master_files[0]
print_header(f"Using master parquet file: {master_parquet}")

# Output identifiers path
identifiers_root = os.path.join(data_root, latest_pub, identifiers_subfolder)
os.makedirs(identifiers_root, exist_ok=True)
combined_file = os.path.join(identifiers_root, "combined_id_pid.parquet")

# Extract identifiers using DuckDB and write Parquet through COPY
con = connect_duckdb()
sql = f"""
COPY (
  SELECT
    id AS record_id,
    unnest.scheme AS pid_scheme,
    unnest.value  AS pid_value
  FROM read_parquet('{os.path.abspath(master_parquet)}')
  CROSS JOIN UNNEST(pids) AS unnest
) TO '{os.path.abspath(combined_file)}' (FORMAT PARQUET);
"""
con.execute(sql)
con.close()

print(f"Identifiers extracted and saved: {combined_file}")
if testing_mode:
    print("Testing mode ON — showing head of combined identifiers:")
    import pandas as pd
    df = pd.read_parquet(combined_file).head(20)
    print(df)
