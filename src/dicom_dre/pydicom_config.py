"""Process-wide pydicom configuration.

Applies global pydicom settings that make DICOM reading tolerant of malformed
production data. The settings are process-global, so one import applies them
everywhere; the only requirement is that the import runs before the first
DICOM read or write in the process.

Import it for its side effects from any module that reads or writes DICOM
without already routing through one that does.
"""

from pydicom import config


# Ignore non-conformant value representations on read rather than raising.
config.settings.reading_validation_mode = config.IGNORE

# Coerce elements whose declared length is invalid (for example a UL value whose
# byte length is not a multiple of 4) to UN instead of raising BytesLengthException.
config.convert_wrong_length_to_UN = True
