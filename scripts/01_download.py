#!/usr/bin/env python
# coding: utf-8

import os
import requests
from datetime import datetime
import yaml
from utils.helpers import atomic_write_json, ensure_dir

# ===========================
# Load config
# ===========================
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

data_root = config["paths"]["data_root"]
raw_subfolder = config["paths"]["raw_subfolder"]
extracted_subfolder = config["paths"]["extracted_subfolder"]

# ===========================
# Dynamic publication date
# ===========================
publication_date = datetime.today().strftime("%Y-%m-%d")

# ===========================
# Zenodo API fetch
# ===========================
zenodo_record_id = "14887484"  # Aurora OpenAIRE dump
zenodo_url = f"https://zenodo.org/api/records/{zenodo_record_id}/versions/latest"

print(f"Fetching Zenodo metadata from {zenodo_url} ...")
resp = requests.get(zenodo_url)
resp.raise_for_status()
meta = resp.json()

files = meta.get("files", [])
if not files:
    raise RuntimeError("No files found in Zenodo record metadata.")

# ===========================
# Select Aurora .tar file
# ===========================
aurora_files = [f for f in files if "aurora" in f["key"].lower() and f["key"].endswith(".tar")]
if not aurora_files:
    raise RuntimeError("No Aurora .tar file found in Zenodo record!")

selected_file = aurora_files[0]
file_name = selected_file["key"]
download_url = selected_file["links"]["self"]
checksum = selected_file.get("checksum", None)

# ===========================
# Paths
# ===========================
download_path = os.path.join(data_root, publication_date, raw_subfolder, file_name)
folder_name = file_name.replace(".tar", "")
extraction_path = os.path.join(data_root, publication_date, extracted_subfolder, folder_name)

ensure_dir(os.path.dirname(download_path))
ensure_dir(extraction_path)

# ===========================
# Download file
# ===========================
if os.path.exists(download_path):
    print(f"File already exists: {download_path}")
else:
    print(f"Downloading {file_name} → {download_path}")
    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(download_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Saved: {download_path}")

# ===========================
# Checksum verification (optional)
# ===========================
if checksum:
    from utils.helpers import calculate_checksum
    algorithm, expected = checksum.split(":", 1)
    actual = calculate_checksum(download_path, algorithm=algorithm)
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch! {actual} != {expected}")
    print("Checksum verified.")

print(f"Download complete. File ready at: {download_path}")
print(f"Extraction folder: {extraction_path}")
