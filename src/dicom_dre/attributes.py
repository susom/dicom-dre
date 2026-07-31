"""Typed DICOM attribute snapshot for indexing.

``IndexAttributes`` is an immutable, hashable snapshot of the standard DICOM
attributes most commonly needed after de-identification. It is read once from a
dataset so callers can index or record those attributes without re-opening the
DICOM file.

Only standard DICOM keywords are captured. Every field follows the
present-vs-absent convention used elsewhere in the library: ``None`` means the
element is absent (or present with an empty value). Multi-valued attributes are
represented as ``tuple[str, ...]`` so the frozen snapshot stays hashable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pydicom
from pydicom.multival import MultiValue

import dicom_dre.pydicom_config  # noqa: F401  applies process-wide pydicom config


if TYPE_CHECKING:
    from pathlib import Path


def _get_str(ds: pydicom.Dataset, keyword: str) -> str | None:
    """Return the scalar value of *keyword* as a string, or None if absent/empty."""
    value = ds.get(keyword, None)
    if value is None or value == "":
        return None
    return str(value)


def _get_int(ds: pydicom.Dataset, keyword: str) -> int | None:
    """Return the scalar value of *keyword* as an int, or None if absent/non-numeric."""
    value = ds.get(keyword, None)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_tuple(ds: pydicom.Dataset, keyword: str) -> tuple[str, ...] | None:
    """Return a multi-valued *keyword* as a tuple of strings, or None if absent/empty."""
    value = ds.get(keyword, None)
    if value is None:
        return None
    if isinstance(value, (list, MultiValue)):
        parts = tuple(str(v) for v in value)
        return parts or None
    text = str(value)
    if text == "":
        return None
    return (text,)


def _get_transfer_syntax_uid(ds: pydicom.Dataset) -> str | None:
    """Return the Transfer Syntax UID from the File Meta group, or None if absent.

    The Transfer Syntax UID is stored in the File Meta Information group (0002), not
    the main dataset, so it is read from ``ds.file_meta`` rather than ``ds``. A
    bare in-memory dataset with no ``file_meta`` yields None.
    """
    file_meta = getattr(ds, "file_meta", None)
    if file_meta is None:
        return None
    return _get_str(file_meta, "TransferSyntaxUID")


def _get_procedure_code_value(ds: pydicom.Dataset) -> str | None:
    """Return the CodeValue of the first ProcedureCodeSequence item, or None.

    ProcedureCodeSequence (0008,1032) is a sequence with no scalar VR, so it is
    handled specially: the CodeValue (0008,0100) of the first sequence item is
    extracted. Returns None when the sequence is absent or empty.
    """
    sequence = ds.get("ProcedureCodeSequence", None)
    if not sequence:
        return None
    return _get_str(sequence[0], "CodeValue")


@dataclass(frozen=True, slots=True)
class IndexAttributes:
    """Typed snapshot of standard DICOM attributes read from a dataset.

    All fields are standard DICOM keywords. ``None`` means the element is absent.
    Multi-valued attributes are ``tuple[str, ...]`` so the snapshot is hashable.
    """

    # UIDs / identifiers
    sop_instance_uid: str | None = None
    study_instance_uid: str | None = None
    series_instance_uid: str | None = None
    sop_class_uid: str | None = None
    accession_number: str | None = None
    patient_id: str | None = None
    study_id: str | None = None
    # Sourced from ds.file_meta (File Meta group), not the main dataset.
    transfer_syntax_uid: str | None = None

    # Descriptors
    modality: str | None = None
    modalities_in_study: tuple[str, ...] | None = None
    manufacturer: str | None = None
    manufacturer_model_name: str | None = None
    secondary_capture_device_manufacturer_model_name: str | None = None
    station_name: str | None = None
    institution_name: str | None = None
    institutional_department_name: str | None = None
    study_description: str | None = None
    series_description: str | None = None
    protocol_name: str | None = None
    derivation_description: str | None = None
    body_part_examined: str | None = None
    laterality: str | None = None
    patient_position: str | None = None
    conversion_type: str | None = None
    image_type: tuple[str, ...] | None = None
    software_versions: tuple[str, ...] | None = None

    # Patient demographics
    patient_name: str | None = None
    patient_birth_date: str | None = None
    patient_age: str | None = None
    patient_sex: str | None = None
    patient_size: str | None = None
    patient_weight: str | None = None
    ethnic_group: str | None = None
    patient_identity_removed: str | None = None
    confidentiality_code: str | None = None

    # Physicians
    referring_physician_name: str | None = None
    requesting_physician: str | None = None
    performing_physician_name: str | None = None

    # Dates / times
    study_date: str | None = None
    study_time: str | None = None
    series_date: str | None = None
    series_time: str | None = None
    content_date: str | None = None
    content_time: str | None = None

    # Numbering / counts
    instance_number: int | None = None
    series_number: int | None = None
    number_of_frames: int | None = None
    number_of_series_related_instances: int | None = None
    number_of_study_related_instances: int | None = None
    number_of_study_related_series: int | None = None

    # Pixel / technical
    rows: int | None = None
    columns: int | None = None
    bits_allocated: int | None = None
    bits_stored: int | None = None
    high_bit: int | None = None
    samples_per_pixel: int | None = None
    pixel_representation: int | None = None
    photometric_interpretation: str | None = None
    burned_in_annotation: str | None = None
    lossy_image_compression: str | None = None

    # Other
    # CodeValue of the first ProcedureCodeSequence item (non-scalar extraction).
    procedure_code_sequence: str | None = None
    retrieve_url: str | None = None

    @classmethod
    def from_dataset(cls, ds: pydicom.Dataset) -> IndexAttributes:
        """Extract a snapshot from an in-memory dataset (no I/O)."""
        return cls(
            sop_instance_uid=_get_str(ds, "SOPInstanceUID"),
            study_instance_uid=_get_str(ds, "StudyInstanceUID"),
            series_instance_uid=_get_str(ds, "SeriesInstanceUID"),
            sop_class_uid=_get_str(ds, "SOPClassUID"),
            accession_number=_get_str(ds, "AccessionNumber"),
            patient_id=_get_str(ds, "PatientID"),
            study_id=_get_str(ds, "StudyID"),
            transfer_syntax_uid=_get_transfer_syntax_uid(ds),
            modality=_get_str(ds, "Modality"),
            modalities_in_study=_get_tuple(ds, "ModalitiesInStudy"),
            manufacturer=_get_str(ds, "Manufacturer"),
            manufacturer_model_name=_get_str(ds, "ManufacturerModelName"),
            secondary_capture_device_manufacturer_model_name=_get_str(
                ds, "SecondaryCaptureDeviceManufacturerModelName"
            ),
            station_name=_get_str(ds, "StationName"),
            institution_name=_get_str(ds, "InstitutionName"),
            institutional_department_name=_get_str(ds, "InstitutionalDepartmentName"),
            study_description=_get_str(ds, "StudyDescription"),
            series_description=_get_str(ds, "SeriesDescription"),
            protocol_name=_get_str(ds, "ProtocolName"),
            derivation_description=_get_str(ds, "DerivationDescription"),
            body_part_examined=_get_str(ds, "BodyPartExamined"),
            laterality=_get_str(ds, "Laterality"),
            patient_position=_get_str(ds, "PatientPosition"),
            conversion_type=_get_str(ds, "ConversionType"),
            image_type=_get_tuple(ds, "ImageType"),
            software_versions=_get_tuple(ds, "SoftwareVersions"),
            patient_name=_get_str(ds, "PatientName"),
            patient_birth_date=_get_str(ds, "PatientBirthDate"),
            patient_age=_get_str(ds, "PatientAge"),
            patient_sex=_get_str(ds, "PatientSex"),
            patient_size=_get_str(ds, "PatientSize"),
            patient_weight=_get_str(ds, "PatientWeight"),
            ethnic_group=_get_str(ds, "EthnicGroup"),
            patient_identity_removed=_get_str(ds, "PatientIdentityRemoved"),
            confidentiality_code=_get_str(ds, "ConfidentialityCode"),
            referring_physician_name=_get_str(ds, "ReferringPhysicianName"),
            requesting_physician=_get_str(ds, "RequestingPhysician"),
            performing_physician_name=_get_str(ds, "PerformingPhysicianName"),
            study_date=_get_str(ds, "StudyDate"),
            study_time=_get_str(ds, "StudyTime"),
            series_date=_get_str(ds, "SeriesDate"),
            series_time=_get_str(ds, "SeriesTime"),
            content_date=_get_str(ds, "ContentDate"),
            content_time=_get_str(ds, "ContentTime"),
            instance_number=_get_int(ds, "InstanceNumber"),
            series_number=_get_int(ds, "SeriesNumber"),
            number_of_frames=_get_int(ds, "NumberOfFrames"),
            number_of_series_related_instances=_get_int(ds, "NumberOfSeriesRelatedInstances"),
            number_of_study_related_instances=_get_int(ds, "NumberOfStudyRelatedInstances"),
            number_of_study_related_series=_get_int(ds, "NumberOfStudyRelatedSeries"),
            rows=_get_int(ds, "Rows"),
            columns=_get_int(ds, "Columns"),
            bits_allocated=_get_int(ds, "BitsAllocated"),
            bits_stored=_get_int(ds, "BitsStored"),
            high_bit=_get_int(ds, "HighBit"),
            samples_per_pixel=_get_int(ds, "SamplesPerPixel"),
            pixel_representation=_get_int(ds, "PixelRepresentation"),
            photometric_interpretation=_get_str(ds, "PhotometricInterpretation"),
            burned_in_annotation=_get_str(ds, "BurnedInAnnotation"),
            lossy_image_compression=_get_str(ds, "LossyImageCompression"),
            procedure_code_sequence=_get_procedure_code_value(ds),
            retrieve_url=_get_str(ds, "RetrieveURL"),
        )

    @classmethod
    def from_file(cls, path: Path) -> IndexAttributes:
        """Read a DICOM file and extract a snapshot.

        Uses ``stop_before_pixels=True`` because none of the captured attributes
        require pixel data.
        """
        ds = pydicom.dcmread(str(path), stop_before_pixels=True)
        return cls.from_dataset(ds)
