---
description: Reading and writing DICOM with pydicom
applyTo: "src/dicom_dre/**/*.py"
---

# DICOM I/O Conventions

## Process-wide pydicom config

Any module that reads or writes DICOM with pydicom (`dcmread`, `dcmwrite`,
`save_as`, `Dataset` I/O) depends on the global settings in
`dicom_dre.pydicom_config`, which make reads tolerant of malformed
production data.

- The settings are process-global: one import applies them everywhere, so the
  import only has to run before the first read or write in the process.
- Add the side-effect import to any new DICOM reader/writer whose module (or its
  import chain) does not already reach it:

  ```python
  import dicom_dre.pydicom_config  # noqa: F401  applies process-wide pydicom config
  ```

- Modules that import the pipeline (`dicom_dre.pipeline`) or an anonymizer entry
  module already inherit it transitively and do not need the direct import.
