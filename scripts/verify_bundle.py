"""Move demo_bundle.zip into repo and verify manifest checksums."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

repo_root = Path(r"d:\Smart India Hackathon\Dam")
scratch_zip = Path(
    r"C:\Users\user\.gemini\antigravity-ide\brain\52a3517e-5742-40fc-acdc-77e6fcf88c50\scratch\demo_bundle.zip"
)
bundle_dir = repo_root / "demo_bundle"
bundle_dir.mkdir(parents=True, exist_ok=True)

target_zip = bundle_dir / "demo_bundle.zip"
manifest_file = bundle_dir / "MANIFEST.json"

# Move / copy zip
shutil.copy2(scratch_zip, target_zip)
print(f"Copied zip to: {target_zip.resolve()} ({target_zip.stat().st_size / (1024*1024):.2f} MB)")

# Extract MANIFEST.json
with zipfile.ZipFile(target_zip, "r") as zf:
    manifest_bytes = zf.read("MANIFEST.json")
    manifest_data = json.loads(manifest_bytes.decode("utf-8"))
    manifest_file.write_bytes(manifest_bytes)

print(f"Wrote manifest to: {manifest_file.resolve()}")

# Verify SHA256 of all files
all_ok = True
for rel_path, meta in manifest_data["files"].items():
    with zipfile.ZipFile(target_zip, "r") as zf:
        data = zf.read(rel_path)
    calc_sha = hashlib.sha256(data).hexdigest()
    exp_sha = meta["sha256"]
    if calc_sha != exp_sha:
        print(f"MISMATCH: {rel_path}")
        all_ok = False
    else:
        print(f"  [VERIFIED] {rel_path} : {calc_sha[:16]}... ({meta['size_bytes']:,} bytes)")

zip_sha = hashlib.sha256(target_zip.read_bytes()).hexdigest()
print(f"\nFinal Zip SHA256: {zip_sha}")
print(f"All files verified: {all_ok}")
print(f"Final Absolute Path: {target_zip.resolve()}")
