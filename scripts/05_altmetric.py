#!/usr/bin/env python
# coding: utf-8

import os
import yaml
import json
import time
import requests
import pandas as pd
import duckdb
from tqdm import tqdm
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.helpers import atomic_write_json, print_header

# ------------------------
# Load config
# ------------------------
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

testing_mode = config['general'].get('testing_mode', False)
data_root = config['paths']['data_root']
identifiers_subfolder = config['paths']['identifiers_subfolder']
altmetric_subfolder = config['paths']['altmetric_subfolder']

# ------------------------
# Detect latest publication folder
# ------------------------
available_dates = sorted(
    [d for d in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, d))],
    reverse=True
)
if not available_dates:
    raise FileNotFoundError(f"No folders found in {data_root}")
latest_date = available_dates[0]
print_header(f"Using latest folder: {latest_date}")

# ------------------------
# Paths
# ------------------------
identifiers_root = os.path.join(data_root, latest_date, identifiers_subfolder)
if not os.path.exists(identifiers_root):
    raise FileNotFoundError(f"Identifiers folder does not exist: {identifiers_root}")
combined_path = os.path.join(identifiers_root, "combined_id_pid.parquet")
if not os.path.exists(combined_path):
    raise FileNotFoundError(f"Combined PID parquet not found at: {combined_path}")

altmetric_root = os.path.join(data_root, latest_date, altmetric_subfolder)
os.makedirs(altmetric_root, exist_ok=True)

# ------------------------
# Load identifiers
# ------------------------
print_header(f"Loading combined identifiers from: {combined_path}")
df = pd.read_parquet(combined_path)

supported_schemes = set(config.get('altmetric', {}).get('supported_schemes', ['doi', 'handle', 'pmid']))
df = df[df['pid_scheme'].isin(supported_schemes)]
if testing_mode:
    df = df.head(10000)
print(f"Total identifiers to process: {len(df)}")

# ------------------------
# Endpoint mapping
# ------------------------
endpoint_map = {
    'doi': 'doi', 'handle': 'handle', 'pmid': 'pmid', 'arxiv': 'arxiv',
    'ads': 'ads', 'ssrn': 'ssrn', 'repec': 'repec', 'isbn': 'isbn',
    'id': 'id', 'nct_id': 'nct', 'urn': 'urn'
}

# ------------------------
# Output paths
# ------------------------
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
json_path = os.path.join(altmetric_root, f"altmetric_results_{timestamp}.json")
parquet_path = os.path.join(altmetric_root, f"altmetric_results_{timestamp}.parquet")
schema_path = os.path.join(altmetric_root, f"schema_altmetric_{timestamp}.sql")

# ------------------------
# Resume checkpoint if exists
# ------------------------
results = []
if os.path.exists(json_path):
    print(f"Resuming from {json_path}")
    with open(json_path, 'r', encoding='utf-8') as fh:
        results = json.load(f)

processed_keys = {(r.get('pid_scheme'), r.get('pid_value')) for r in results}
df_to_process = df[~df.apply(lambda row: (row['pid_scheme'], row['pid_value']) in processed_keys, axis=1)]
df_to_process = df_to_process.reset_index(drop=True)
total = len(df_to_process)
print(f"Remaining to process: {total}")

# ------------------------
# Configs
# ------------------------
batch_size = config.get('altmetric', {}).get('batch_size', 100)
sleep_sec = config.get('altmetric', {}).get('sleep_sec', 1.0)
max_workers = config.get('altmetric', {}).get('max_workers', 20)

# ------------------------
# Helper to safely convert nested objects to JSON strings
# ------------------------
def sanitize_record(rec: dict) -> dict:
    sanitized = {}
    for k, v in rec.items():
        if isinstance(v, (dict, list)):
            try:
                sanitized[k] = json.dumps(v)
            except Exception:
                sanitized[k] = None
        else:
            sanitized[k] = v
    return sanitized

# ------------------------
# Function to fetch a single Altmetric record
# ------------------------
def fetch_altmetric(record):
    pid_scheme = record['pid_scheme'].lower()
    pid_value = record['pid_value']
    endpoint = endpoint_map.get(pid_scheme)
    if not endpoint:
        return None
    url = f"https://api.altmetric.com/v1/{endpoint}/{pid_value}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            data.update(record)
            return sanitize_record(data)
        elif r.status_code == 404:
            return {**record, 'status': 404}
        elif r.status_code == 403:
            print(f"403 Forbidden for {pid_scheme}:{pid_value}")
            return {**record, 'status': 403}
        elif r.status_code == 429:
            print("Rate limited (429). Sleeping 60s.")
            time.sleep(60)
            return fetch_altmetric(record)  # retry after sleep
        else:
            return {**record, 'status': r.status_code}
    except Exception as e:
        print(f"Exception fetching {pid_scheme}:{pid_value} -> {e}")
        return {**record, 'status': 'error'}

# ------------------------
# Main loop: process in chunks with ETA
# ------------------------
start_time = time.time()

for start in range(0, total, batch_size):
    chunk_start_time = time.time()
    end = min(start + batch_size, total)
    chunk = df_to_process.iloc[start:end]

    chunk_records = [row._asdict() for row in chunk.itertuples(index=False)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_altmetric, rec): rec for rec in chunk_records}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)

    # Save after each chunk
    atomic_write_json(results, json_path)
    df_parquet = pd.json_normalize(results)

    # Sanitize all columns to strings to avoid PyArrow conversion errors
    for c in df_parquet.columns:
        df_parquet[c] = df_parquet[c].apply(lambda x: json.dumps(x) if isinstance(x, (dict, list))
                                            else str(x) if x is not None else None)
    df_parquet.to_parquet(parquet_path, index=False)

    # ------------------------
    # ETA calculation
    # ------------------------
    elapsed = time.time() - start_time
    chunks_done = end // batch_size
    total_chunks = (total + batch_size - 1) // batch_size
    avg_time_per_chunk = elapsed / max(chunks_done, 1)
    remaining_chunks = total_chunks - chunks_done
    est_remaining = remaining_chunks * avg_time_per_chunk
    print(f"Chunk {start} → {end} done in {time.time() - chunk_start_time:.2f}s, "
          f"estimated remaining: {est_remaining/60:.1f} min")

print_header(f"Altmetric enrichment completed. Total results: {len(results)}")
print(f"Saved JSON: {json_path}")
print(f"Saved Parquet: {parquet_path}")

# ------------------------
# Extract schema from parquet
# ------------------------
con = duckdb.connect()
con.execute(f"DESCRIBE SELECT * FROM parquet_scan('{os.path.abspath(parquet_path)}')")
schema_df = con.fetchdf()
with open(schema_path, "w", encoding='utf-8') as fh:
    for _, row in schema_df.iterrows():
        fh.write(f"{row['column_name']} {row['column_type']}\n")
con.close()
print(f"Schema file written to: {schema_path}")
