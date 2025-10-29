# utils/duckdb_helpers.py
import duckdb
import pandas as pd
from typing import Optional

def connect_duckdb(db_path: str = ":memory:"):
    """Return a DuckDB connection object."""
    return duckdb.connect(database=db_path, read_only=False)

def run_query(con, query: str, return_df: bool = True):
    res = con.execute(query)
    if return_df:
        return res.df()
    return res

def parquet_to_duckdb_table(con, parquet_path: str, table_name: str, replace: bool = True):
    """Create table from parquet file."""
    rep = "OR REPLACE" if replace else ""
    sql = f"CREATE {rep} TABLE {table_name} AS SELECT * FROM read_parquet('{parquet_path}');"
    con.execute(sql)

def duckdb_query_to_parquet(con, query: str, output_path: str):
    """Write the result of a query to Parquet using DuckDB COPY."""
    con.execute(f"COPY ({query}) TO '{output_path}' (FORMAT PARQUET);")
