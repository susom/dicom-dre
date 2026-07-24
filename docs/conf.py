"""Sphinx configuration for the dicom-dre documentation."""

from __future__ import annotations

import importlib.metadata
import os
import sys


# Make the ``src`` layout importable so autodoc can resolve ``dicom_dre``
# without requiring the package to be installed.
sys.path.insert(0, os.path.abspath("../src"))


# -- Project information ------------------------------------------------------

project = "dicom-dre"
author = "Stanford"
copyright = "2026, Stanford"

try:
    release = importlib.metadata.version("dicom-dre")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    release = "0.0.0.dev0"
version = release


# -- General configuration ----------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
    "sphinxcontrib.mermaid",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}


# -- Autodoc / autosummary ----------------------------------------------------

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}


# -- Napoleon (Google-style docstrings) --------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_ivar = True


# -- Intersphinx --------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pydicom": ("https://pydicom.github.io/pydicom/stable/", None),
}


# -- MyST ---------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]


# -- HTML output --------------------------------------------------------------

html_theme = "furo"
html_title = f"dicom-dre {version}"
html_static_path = ["_static"]
