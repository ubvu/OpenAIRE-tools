#!/usr/bin/env python
# coding: utf-8

import os
import tarfile
import random
import yaml
from utils.helpers import ensure_dir

# ==============================
# Load config
# ==============================
with open("config/config.yaml") as f:
    config = yaml.safe_load(f)

testing_mode = config['general'].get('testing_mode', False)
data_root = config['paths']['data_root']
raw_subfolder = config['paths']['raw_subfolder']
extracted_subfolder = config['paths']['extracted_subfolder']

# ==============================
# Find latest publication folder
# ==============================
pub_folders = sorted(
    [f for f in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, f))],
    reverse=True
)

if not pub_folders:
    raise RuntimeError(f"No publication folders found in {data_root}")

latest_pub = pub_folders[0]
raw_folder = os.path.join(data_root, latest_pub, raw_subfolder)

# Find latest tar file
tar_files = [f for f in os.listdir(raw_folder) if f.endswith('.tar')]
if not tar_files:
    raise RuntimeError(f"No tar files found in {raw_folder}")

# Prefer "aurora" tar
aurora_files = [f for f in tar_files if "aurora" in f.lower()]
if aurora_files:
    tar_file = aurora_files[0]
else:
    tar_file = tar_files[0]

download_path = os.path.join(raw_folder, tar_file)
folder_name = tar_file.replace('.tar', '')
extraction_path = os.path.join(data_root, latest_pub, extracted_subfolder, folder_name)

ensure_dir(extraction_path)

print(f"Extracting {download_path} -> {extraction_path} ...")

# ==============================
# Safe extraction to prevent path traversal
# ==============================
def safe_extract(tar, path=".", members=None):
    for member in tar.getmembers():
        member_path = os.path.join(path, member.name)
        if not os.path.abspath(member_path).startswith(os.path.abspath(path)):
            raise Exception(f"Unsafe path in tar file: {member.name}")
    tar.extractall(path, members)

with tarfile.open(download_path, 'r') as tar:
    if testing_mode:
        members = tar.getmembers()[:10]
        safe_extract(tar, path=extraction_path, members=members)
        print("Extracted first 10 files (testing mode).")
    else:
        safe_extract(tar, path=extraction_path)
        print("Extraction complete.")

# List extracted files
extracted_files = os.listdir(extraction_path)
if testing_mode:
    extracted_files = extracted_files[:10]

extracted_files_with_path = [os.path.join(extraction_path, f) for f in extracted_files]
print(f"Number of extracted files: {len(extracted_files)}")
print("Sample files:", random.sample(extracted_files_with_path, min(5, len(extracted_files_with_path))))
