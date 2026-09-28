"""Pytest configuration and environment initialization for Windows Conda environments."""

import os
import sys
from pathlib import Path

# On Windows under Conda environments, ensure Library/bin is in DLL search path
if sys.platform == "win32":
    library_bin = Path(sys.prefix) / "Library" / "bin"
    if library_bin.exists():
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(library_bin))
            except Exception:
                pass
        os.environ["PATH"] = str(library_bin) + os.pathsep + os.environ.get("PATH", "")

    gdal_data = Path(sys.prefix) / "Library" / "share" / "gdal"
    if gdal_data.exists() and "GDAL_DATA" not in os.environ:
        os.environ["GDAL_DATA"] = str(gdal_data)

    proj_lib = Path(sys.prefix) / "Library" / "share" / "proj"
    if proj_lib.exists() and "PROJ_LIB" not in os.environ:
        os.environ["PROJ_LIB"] = str(proj_lib)
