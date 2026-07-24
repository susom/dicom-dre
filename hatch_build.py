"""Custom hatchling build hook.

Compiles the CFFI JPEG-DCT acceleration extension during wheel builds.
Falls back gracefully (pure-Python entropy codec) if the build script is absent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


_BUILD_SCRIPT = Path("src/dicom_dre/_jpeg_dct_accel_build.py")


class CFFIBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    """Compile the CFFI acceleration extension during wheel builds."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Compile the CFFI extension if its build script exists."""
        build_script = Path(self.root) / _BUILD_SCRIPT
        if not build_script.is_file():
            self.app.display_warning(
                "JPEG-DCT CFFI build script not found; building without native acceleration (pure-Python fallback)."
            )
            return

        spec = importlib.util.spec_from_file_location("_jpeg_dct_accel_build", build_script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load CFFI build script: {build_script}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        ffibuilder = getattr(module, "ffibuilder", None) or getattr(module, "ffi", None)
        if ffibuilder is None:
            raise RuntimeError(f"{build_script} does not define 'ffibuilder' or 'ffi'.")

        # The extension's module name is ``dicom_dre._jpeg_dct_accel``, so CFFI
        # writes its artifacts under ``<tmpdir>/dicom_dre/``. Point tmpdir at the
        # ``src`` root so the compiled ``.so`` lands at
        # ``src/dicom_dre/_jpeg_dct_accel.*.so`` rather than a nested package dir.
        src_dir = Path(self.root) / "src"
        ffibuilder.compile(tmpdir=str(src_dir), verbose=True)

        # Produced a compiled artifact: mark the wheel platform-specific.
        build_data["pure_python"] = False
        build_data["infer_tag"] = True
