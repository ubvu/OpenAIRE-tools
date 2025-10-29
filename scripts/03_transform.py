#!/usr/bin/env python
# coding: utf-8

import os
import glob
import yaml
import gzip
import random
from utils.helpers import (
    duckdb_jsons_to_parquet,
    extract_parquet_schema,
    print_header
)

# Load config
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

testing_mode = config['general'].get('testing_mode', False)
data_root = config['paths']['data_root']
extracted_subfolder = config['paths']['extracted_subfolder']
processed_subfolder = config['paths']['processed_subfolder']

# Find latest publication folder dynamically
if not os.path.exists(data_root):
    raise RuntimeError(f"data_root not found: {data_root}")

pub_folders = sorted([d for d in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, d))], reverse=True)
if not pub_folders:
    raise RuntimeError("No publication date folders found in data_root.")

latest_pub = pub_folders[0]
extracted_root = os.path.join(data_root, latest_pub, extracted_subfolder)

# Find latest extraction subfolder (e.g., aurora)
extracted_subdirs = sorted([d for d in os.listdir(extracted_root) if os.path.isdir(os.path.join(extracted_root, d))], reverse=True)
if not extracted_subdirs:
    raise RuntimeError(f"No extracted subfolders found in {extracted_root}")

latest_extraction = extracted_subdirs[0]
extraction_path = os.path.join(extracted_root, latest_extraction)

# List JSON/JSON.GZ files
all_files = glob.glob(os.path.join(extraction_path, '**', '*.json*'), recursive=True)
if testing_mode:
    all_files = all_files[:10]

print_header(f"Processing {len(all_files)} JSON files from {extraction_path}")

# Ensure processed folder exists
processed_path = os.path.join(data_root, latest_pub, processed_subfolder)
os.makedirs(processed_path, exist_ok=True)

master_parquet = os.path.join(processed_path, f"{latest_extraction}-master.parquet")
schema_file = os.path.join(processed_path, f"{latest_extraction}-schema.sql")

# Use DuckDB to read JSON files and write Parquet
if all_files:
    print("Converting JSON files to Parquet (DuckDB)...")
    duckdb_jsons_to_parquet(all_files, master_parquet, union_by_name=True, sample_size=-1, compression='gzip')
    print(f"Master Parquet created at {master_parquet}")
    # Extract schema
    extract_parquet_schema(master_parquet, schema_file)
    print(f"Schema saved to {schema_file}")
else:
    print("No JSON files found to process.")
