# utils/helpers.py
import os
import json
import shutil
import tempfile
from datetime import datetime
import hashlib
import gzip
from typing import List
import duckdb

# -------------------------
# Small utilities
# -------------------------
def calculate_checksum(file_path: str, algorithm: str = "md5", chunk_size: int = 8192) -> str:
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def atomic_write_json(data, path: str):
    dirpath = os.path.dirname(path)
    ensure_dir(dirpath)
    with tempfile.NamedTemporaryFile('w', delete=False, dir=dirpath, encoding='utf-8') as tf:
        json.dump(data, tf)
        tempname = tf.name
    shutil.move(tempname, path)

def timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def file_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024**2)

def print_header(msg: str):
    print("\n" + "="*80)
    print(msg)
    print("="*80 + "\n")


# -------------------------
# JSON(.gz) -> Parquet via DuckDB
# -------------------------
def duckdb_jsons_to_parquet(file_list: List[str], output_path: str, union_by_name: bool = True, sample_size: int = -1, compression: str = "gzip"):
    """
    Use DuckDB's read_json over a list of files and COPY the result to a single Parquet file.
    This avoids pandas append problems and is fast for large JSONL(.gz).
    """
    if not file_list:
        raise ValueError("file_list is empty")

    # build file list SQL literal array
    # ensure absolute paths
    file_list_abs = [os.path.abspath(p) for p in file_list]
    paths_sql = ", ".join(f"'{p}'" for p in file_list_abs)

    union_flag = "union_by_name=true" if union_by_name else ""
    sample_clause = f"sample_size={sample_size}" if sample_size is not None else ""

    con = duckdb.connect()
    # DuckDB read_json supports an array literal of files
    sql = f"""
    COPY (
      SELECT *
      FROM read_json([{paths_sql}], {sample_clause}, {union_flag})
    ) TO '{os.path.abspath(output_path)}' (FORMAT PARQUET, COMPRESSION {compression});
    """
    # remove double commas or empty params if sample_size == -1 etc -- simpler: call read_json with only file list and flags explicitly
    # Build a safer SQL string:
    extra_args = []
    if sample_size is not None and sample_size >= 0:
        extra_args.append(f"sample_size={sample_size}")
    if union_by_name:
        extra_args.append("union_by_name=true")
    extra_args_str = ", ".join(extra_args)
    if extra_args_str:
        read_json_call = f"read_json([{paths_sql}], {extra_args_str})"
    else:
        read_json_call = f"read_json([{paths_sql}])"

    sql = f"""
    COPY (
      SELECT *
      FROM {read_json_call}
    ) TO '{os.path.abspath(output_path)}' (FORMAT PARQUET, COMPRESSION {compression});
    """

    con.execute(sql)
    con.close()
    return os.path.abspath(output_path)


def extract_parquet_schema(parquet_path: str, schema_file: str):
    """
    Extract column name + type from Parquet via DuckDB DESCRIBE parquet_scan() and write to schema_file.
    """
    con = duckdb.connect()
    # DESCRIBE SELECT * FROM parquet_scan
    q = f"DESCRIBE SELECT * FROM parquet_scan('{os.path.abspath(parquet_path)}')"
    con.execute(q)
    df = con.fetchdf()  # columns: column_name, column_type
    ensure_dir(os.path.dirname(schema_file))
    with open(schema_file, "w", encoding="utf-8") as fh:
        for _, row in df.iterrows():
            fh.write(f"{row['column_name']} {row['column_type']}\n")
    con.close()
    return os.path.abspath(schema_file)
