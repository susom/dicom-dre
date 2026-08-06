"""Pixels-Only de-identification profile.

The most aggressive redaction that still yields a DICOM file that opens in most
DICOM viewers and libraries. Use only when the pixel data is the sole item of
interest and study demographics or other metadata can be discarded. No UID
salt, no date jitter, minimal retained elements; all unspecified elements are
removed.

Key Object Selection (KO) and Presentation State (PR) objects carry no pixel
data but hold clinician-curated labels. Their structured-content and
graphic-annotation subtrees are retained through ``content_root_tags`` so the
labels survive, while the shared PHI-removal, date-removal, and free-text
redaction rules de-identify every element inside those subtrees.

The resulting file is likely not conformant to the DICOM specification, since
required elements may be removed; it is intended only for pixel-data use, not
for interchange with systems that enforce conformance.
"""

from pydicom.tag import BaseTag
from pydicom.tag import Tag

from dicom_dre.actions import TagAction
from dicom_dre.actions import hash_identifier_param
from dicom_dre.actions import hash_uid
from dicom_dre.actions import hash_value_identifier
from dicom_dre.actions import keep
from dicom_dre.actions import remove
from dicom_dre.actions import set_value
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles.config import ProfileSettings
from dicom_dre.profiles.default import DATE_TAGS
from dicom_dre.profiles.default import EMPTY_TAGS
from dicom_dre.profiles.default import PHI_REMOVE_TAGS
from dicom_dre.profiles.default import redact_description
from dicom_dre.profiles.default import redact_free_text


# 15 UID tags re-hashed in the pixels-only profile, without a salt.
PIXELS_ONLY_UID_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0002, 0x0003),  # MediaStorageSOPInstanceUID
        Tag(0x0008, 0x0018),  # SOPInstanceUID
        Tag(0x0008, 0x1155),  # ReferencedSOPInstanceUID
        Tag(0x0020, 0x000D),  # StudyInstanceUID
        Tag(0x0020, 0x000E),  # SeriesInstanceUID
        Tag(0x0020, 0x0052),  # FrameOfReferenceUID
        Tag(0x0020, 0x0200),  # SynchronizationFrameOfReferenceUID
        Tag(0x0028, 0x1199),  # PaletteColorLookupTableUID
        Tag(0x0028, 0x1214),  # LargePaletteColorLookupTableUID
        Tag(0x0040, 0xA124),  # UID
        Tag(0x0070, 0x1101),  # PresentationDisplayCollectionUID
        Tag(0x0070, 0x1102),  # PresentationSequenceCollectionUID
        Tag(0x0088, 0x0140),  # StorageMediaFileSetUID
        Tag(0x3006, 0x0024),  # ReferencedFrameOfReferenceUID
        Tag(0x3006, 0x00C2),  # RelatedFrameOfReferenceUID
    }
)

# 311 tags preserved unchanged in the pixels-only profile.
PIXELS_ONLY_KEEP_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0005),  # SpecificCharacterSet
        Tag(0x0008, 0x0008),  # ImageType
        Tag(0x0008, 0x0013),  # InstanceCreationTime
        Tag(0x0008, 0x0016),  # SOPClassUID
        Tag(0x0008, 0x0030),  # StudyTime
        Tag(0x0008, 0x0031),  # SeriesTime
        Tag(0x0008, 0x0032),  # AcquisitionTime
        Tag(0x0008, 0x0033),  # ContentTime
        Tag(0x0008, 0x0034),  # OverlayTime
        Tag(0x0008, 0x0035),  # CurveTime
        Tag(0x0008, 0x0060),  # Modality
        Tag(0x0008, 0x0070),  # Manufacturer
        Tag(0x0008, 0x1090),  # ManufacturerModelName
        Tag(0x0008, 0x2111),  # DerivationDescription
        Tag(0x0008, 0x2130),  # EventElapsedTime
        Tag(0x0008, 0x9092),  # ReferencedImageEvidenceSequence
        Tag(0x0010, 0x0040),  # PatientSex
        Tag(0x0018, 0x0010),  # ContrastBolusAgent
        Tag(0x0018, 0x0015),  # BodyPartExamined
        Tag(0x0018, 0x0020),  # ScanningSequence
        Tag(0x0018, 0x0021),  # SequenceVariant
        Tag(0x0018, 0x0022),  # ScanOptions
        Tag(0x0018, 0x0023),  # MRAcquisitionType
        Tag(0x0018, 0x0026),  # InterventionDrugInformationSequence
        Tag(0x0018, 0x0027),  # InterventionDrugStopTime
        Tag(0x0018, 0x0031),  # Radiopharmaceutical
        Tag(0x0018, 0x0032),  # EnergyWindowCenterline
        Tag(0x0018, 0x0035),  # InterventionDrugStartTime
        Tag(0x0018, 0x0040),  # CineRate
        Tag(0x0018, 0x0050),  # SliceThickness
        Tag(0x0018, 0x0060),  # KVP
        Tag(0x0018, 0x0070),  # CountsAccumulated
        Tag(0x0018, 0x0071),  # AcquisitionTerminationCondition
        Tag(0x0018, 0x0073),  # AcquisitionStartCondition
        Tag(0x0018, 0x0075),  # AcquisitionTerminationConditionData
        Tag(0x0018, 0x0080),  # RepetitionTime
        Tag(0x0018, 0x0081),  # EchoTime
        Tag(0x0018, 0x0082),  # InversionTime
        Tag(0x0018, 0x0083),  # NumberOfAverages
        Tag(0x0018, 0x0084),  # ImagingFrequency
        Tag(0x0018, 0x0085),  # ImagedNucleus
        Tag(0x0018, 0x0086),  # EchoNumbers
        Tag(0x0018, 0x0087),  # MagneticFieldStrength
        Tag(0x0018, 0x0088),  # SpacingBetweenSlices
        Tag(0x0018, 0x0090),  # DataCollectionDiameter
        Tag(0x0018, 0x0091),  # EchoTrainLength
        Tag(0x0018, 0x0095),  # PixelBandwidth
        Tag(0x0018, 0x1000),  # DeviceSerialNumber
        Tag(0x0018, 0x1020),  # SoftwareVersions
        Tag(0x0018, 0x1040),  # ContrastBolusRoute
        Tag(0x0018, 0x1041),  # ContrastBolusVolume
        Tag(0x0018, 0x1042),  # ContrastBolusStartTime
        Tag(0x0018, 0x1043),  # ContrastBolusStopTime
        Tag(0x0018, 0x1050),  # SpatialResolution
        Tag(0x0018, 0x1060),  # TriggerTime
        Tag(0x0018, 0x1063),  # FrameTime
        Tag(0x0018, 0x1065),  # FrameTimeVector
        Tag(0x0018, 0x1066),  # FrameDelay
        Tag(0x0018, 0x106E),  # TriggerSamplePosition
        Tag(0x0018, 0x1072),  # RadiopharmaceuticalStartTime
        Tag(0x0018, 0x1073),  # RadiopharmaceuticalStopTime
        Tag(0x0018, 0x1074),  # RadionuclideTotalDose
        Tag(0x0018, 0x1075),  # RadionuclideHalfLife
        Tag(0x0018, 0x1088),  # HeartRate
        Tag(0x0018, 0x1090),  # CardiacNumberOfImages
        Tag(0x0018, 0x1100),  # ReconstructionDiameter
        Tag(0x0018, 0x1110),  # DistanceSourceToDetector
        Tag(0x0018, 0x1111),  # DistanceSourceToPatient
        Tag(0x0018, 0x1114),  # EstimatedRadiographicMagnificationFactor
        Tag(0x0018, 0x1120),  # GantryDetectorTilt
        Tag(0x0018, 0x1130),  # TableHeight
        Tag(0x0018, 0x1140),  # RotationDirection
        Tag(0x0018, 0x1147),  # FieldOfViewShape
        Tag(0x0018, 0x1149),  # FieldOfViewDimensions
        Tag(0x0018, 0x1150),  # ExposureTime
        Tag(0x0018, 0x1151),  # XRayTubeCurrent
        Tag(0x0018, 0x1152),  # Exposure
        Tag(0x0018, 0x1153),  # ExposureInuAs
        Tag(0x0018, 0x1155),  # RadiationSetting
        Tag(0x0018, 0x1160),  # FilterType
        Tag(0x0018, 0x1164),  # ImagerPixelSpacing
        Tag(0x0018, 0x1166),  # Grid
        Tag(0x0018, 0x1170),  # GeneratorPower
        Tag(0x0018, 0x1180),  # CollimatorGridName
        Tag(0x0018, 0x1190),  # FocalSpots
        Tag(0x0018, 0x1191),  # AnodeTargetMaterial
        Tag(0x0018, 0x1201),  # TimeOfLastCalibration
        Tag(0x0018, 0x1210),  # ConvolutionKernel
        Tag(0x0018, 0x1242),  # ActualFrameDuration
        Tag(0x0018, 0x1243),  # CountRate
        Tag(0x0018, 0x1250),  # ReceiveCoilName
        Tag(0x0018, 0x1300),  # ScanVelocity
        Tag(0x0018, 0x1301),  # WholeBodyTechnique
        Tag(0x0018, 0x1302),  # ScanLength
        Tag(0x0018, 0x1310),  # AcquisitionMatrix
        Tag(0x0018, 0x1312),  # InPlanePhaseEncodingDirection
        Tag(0x0018, 0x1314),  # FlipAngle
        Tag(0x0018, 0x1320),  # B1rms
        Tag(0x0018, 0x1400),  # AcquisitionDeviceProcessingDescription
        Tag(0x0018, 0x1401),  # AcquisitionDeviceProcessingCode
        Tag(0x0018, 0x1405),  # RelativeXRayExposure
        Tag(0x0018, 0x1450),  # ColumnAngulation
        Tag(0x0018, 0x1470),  # TomoAngle
        Tag(0x0018, 0x1480),  # TomoTime
        Tag(0x0018, 0x1500),  # PositionerMotion
        Tag(0x0018, 0x1508),  # PositionerType
        Tag(0x0018, 0x1510),  # PositionerPrimaryAngle
        Tag(0x0018, 0x1511),  # PositionerSecondaryAngle
        Tag(0x0018, 0x1530),  # DetectorPrimaryAngle
        Tag(0x0018, 0x1531),  # DetectorSecondaryAngle
        Tag(0x0018, 0x1600),  # ShutterShape
        Tag(0x0018, 0x1620),  # VerticesOfThePolygonalShutter
        Tag(0x0018, 0x1622),  # ShutterPresentationValue
        Tag(0x0018, 0x1624),  # ShutterPresentationColorCIELabValue
        Tag(0x0018, 0x1700),  # CollimatorShape
        Tag(0x0018, 0x1702),  # CollimatorLeftVerticalEdge
        Tag(0x0018, 0x1704),  # CollimatorRightVerticalEdge
        Tag(0x0018, 0x1710),  # CenterOfCircularCollimator
        Tag(0x0018, 0x1720),  # VerticesOfThePolygonalCollimator
        Tag(0x0018, 0x2001),  # PageNumberVector
        Tag(0x0018, 0x5010),  # TransducerData
        Tag(0x0018, 0x5012),  # FocusDepth
        Tag(0x0018, 0x5020),  # ProcessingFunction
        Tag(0x0018, 0x5021),  # PostprocessingFunction
        Tag(0x0018, 0x5022),  # MechanicalIndex
        Tag(0x0018, 0x5024),  # BoneThermalIndex
        Tag(0x0018, 0x5026),  # CranialThermalIndex
        Tag(0x0018, 0x5027),  # SoftTissueThermalIndex
        Tag(0x0018, 0x5028),  # SoftTissueFocusThermalIndex
        Tag(0x0018, 0x5029),  # SoftTissueSurfaceThermalIndex
        Tag(0x0018, 0x5030),  # DynamicRange
        Tag(0x0018, 0x5040),  # TotalGain
        Tag(0x0018, 0x5050),  # DepthOfScanField
        Tag(0x0018, 0x5100),  # PatientPosition
        Tag(0x0018, 0x6000),  # Sensitivity
        Tag(0x0018, 0x6011),  # SequenceOfUltrasoundRegions
        Tag(0x0018, 0x6020),  # ReferencePixelX0
        Tag(0x0018, 0x6031),  # TransducerType
        Tag(0x0018, 0x6032),  # PulseRepetitionFrequency
        Tag(0x0018, 0x6040),  # TMLinePositionX1Retired
        Tag(0x0018, 0x7000),  # DetectorConditionsNominalFlag
        Tag(0x0018, 0x7001),  # DetectorTemperature
        Tag(0x0018, 0x7004),  # DetectorType
        Tag(0x0018, 0x7014),  # DetectorActiveTime
        Tag(0x0018, 0x7020),  # DetectorElementPhysicalSize
        Tag(0x0018, 0x7022),  # DetectorElementSpacing
        Tag(0x0018, 0x7030),  # FieldOfViewOrigin
        Tag(0x0018, 0x7032),  # FieldOfViewRotation
        Tag(0x0018, 0x7034),  # FieldOfViewHorizontalFlip
        Tag(0x0018, 0x7040),  # GridAbsorbingMaterial
        Tag(0x0018, 0x7041),  # GridSpacingMaterial
        Tag(0x0018, 0x7042),  # GridThickness
        Tag(0x0018, 0x7044),  # GridPitch
        Tag(0x0018, 0x7046),  # GridAspectRatio
        Tag(0x0018, 0x7050),  # FilterMaterial
        Tag(0x0018, 0x7052),  # FilterThicknessMinimum
        Tag(0x0018, 0x7054),  # FilterThicknessMaximum
        Tag(0x0018, 0x7060),  # ExposureControlMode
        Tag(0x0018, 0x7062),  # ExposureControlModeDescription
        Tag(0x0018, 0x9005),  # PulseSequenceName
        Tag(0x0018, 0x9070),  # CardiacRRIntervalSpecified
        Tag(0x0018, 0x9073),  # AcquisitionDuration
        Tag(0x0018, 0x9075),  # DiffusionDirectionality
        Tag(0x0018, 0x9076),  # DiffusionGradientDirectionSequence
        Tag(0x0018, 0x9077),  # ParallelAcquisition
        Tag(0x0018, 0x9082),  # EffectiveEchoTime
        Tag(0x0018, 0x9087),  # DiffusionBValue
        Tag(0x0018, 0x9371),  # XRayDetectorID
        Tag(0x0018, 0x9417),  # FrameAcquisitionSequence
        Tag(0x0018, 0x9434),  # ExposureControlSensingRegionsSequence
        Tag(0x0018, 0x9435),  # ExposureControlSensingRegionShape
        Tag(0x0018, 0x9436),  # ExposureControlSensingRegionLeftVerticalEdge
        Tag(0x0018, 0x9438),  # ExposureControlSensingRegionUpperHorizontalEdge
        Tag(0x0018, 0x9461),  # FieldOfViewDimensionsInFloat
        Tag(0x0018, 0x9462),  # IsocenterReferenceSystemSequence
        Tag(0x0018, 0x9476),  # XRayGeometrySequence
        Tag(0x0018, 0x9477),  # IrradiationEventIdentificationSequence
        Tag(0x0018, 0x9504),  # XRay3DFrameTypeSequence
        Tag(0x0018, 0x9506),  # ContributingSourcesSequence
        Tag(0x0018, 0x9507),  # XRay3DAcquisitionSequence
        Tag(0x0018, 0x9508),  # PrimaryPositionerScanArc
        Tag(0x0018, 0x9528),  # AlgorithmDescription
        Tag(0x0018, 0x9530),  # XRay3DReconstructionSequence
        Tag(0x0018, 0x9531),  # ReconstructionDescription
        Tag(0x0018, 0x9538),  # PerProjectionAcquisitionSequence
        Tag(0x0018, 0x9732),  # PETFrameAcquisitionSequence
        Tag(0x0018, 0x9733),  # PETDetectorMotionDetailsSequence
        Tag(0x0018, 0x9736),  # PETFrameCorrectionFactorsSequence
        Tag(0x0018, 0x9737),  # RadiopharmaceuticalUsageSequence
        Tag(0x0018, 0x9738),  # AttenuationCorrectionSource
        Tag(0x0018, 0x9749),  # PETReconstructionSequence
        Tag(0x0018, 0x9751),  # PETFrameTypeSequence
        Tag(0x0018, 0x9810),  # ZeroVelocityPixelValue
        Tag(0x0020, 0x0011),  # SeriesNumber
        Tag(0x0020, 0x0012),  # AcquisitionNumber
        Tag(0x0020, 0x0013),  # InstanceNumber
        Tag(0x0020, 0x0032),  # ImagePositionPatient
        Tag(0x0020, 0x0037),  # ImageOrientationPatient
        Tag(0x0020, 0x0060),  # Laterality
        Tag(0x0020, 0x1002),  # ImagesInAcquisition
        Tag(0x0020, 0x1040),  # PositionReferenceIndicator
        Tag(0x0020, 0x1041),  # SliceLocation
        Tag(0x0020, 0x9116),  # PlaneOrientationSequence
        Tag(0x0020, 0x9153),  # TriggerDelayTime
        Tag(0x0022, 0x0001),  # LightPathFilterPassThroughWavelength
        Tag(0x0022, 0x0002),  # LightPathFilterPassBand
        Tag(0x0022, 0x0003),  # ImagePathFilterPassThroughWavelength
        Tag(0x0022, 0x0005),  # PatientEyeMovementCommanded
        Tag(0x0022, 0x0006),  # PatientEyeMovementCommandCodeSequence
        Tag(0x0022, 0x0007),  # SphericalLensPower
        Tag(0x0022, 0x0008),  # CylinderLensPower
        Tag(0x0022, 0x0009),  # CylinderAxis
        Tag(0x0022, 0x1007),  # OphthalmicAxialMeasurementsRightEyeSequence
        Tag(0x0022, 0x1019),  # OphthalmicAxialLength
        Tag(0x0022, 0x1050),  # OphthalmicAxialLengthMeasurementsSequence
        Tag(0x0028, 0x0002),  # SamplesPerPixel
        Tag(0x0028, 0x0004),  # PhotometricInterpretation
        Tag(0x0028, 0x0006),  # PlanarConfiguration
        Tag(0x0028, 0x0008),  # NumberOfFrames
        Tag(0x0028, 0x0009),  # FrameIncrementPointer
        Tag(0x0028, 0x000A),  # FrameDimensionPointer
        Tag(0x0028, 0x0010),  # Rows
        Tag(0x0028, 0x0011),  # Columns
        Tag(0x0028, 0x0012),  # Planes
        Tag(0x0028, 0x0030),  # PixelSpacing
        Tag(0x0028, 0x0034),  # PixelAspectRatio
        Tag(0x0028, 0x0100),  # BitsAllocated
        Tag(0x0028, 0x0101),  # BitsStored
        Tag(0x0028, 0x0102),  # HighBit
        Tag(0x0028, 0x0103),  # PixelRepresentation
        Tag(0x0028, 0x0106),  # SmallestImagePixelValue
        Tag(0x0028, 0x0107),  # LargestImagePixelValue
        Tag(0x0028, 0x0120),  # PixelPaddingValue
        Tag(0x0028, 0x0121),  # PixelPaddingRangeLimit
        Tag(0x0028, 0x0200),  # ImageLocation
        Tag(0x0028, 0x0300),  # QualityControlImage
        Tag(0x0028, 0x0A02),  # PixelSpacingCalibrationType
        Tag(0x0028, 0x0A04),  # PixelSpacingCalibrationDescription
        Tag(0x0028, 0x1050),  # WindowCenter
        Tag(0x0028, 0x1051),  # WindowWidth
        Tag(0x0028, 0x1052),  # RescaleIntercept
        Tag(0x0028, 0x1053),  # RescaleSlope
        Tag(0x0028, 0x1054),  # RescaleType
        Tag(0x0028, 0x1055),  # WindowCenterWidthExplanation
        Tag(0x0028, 0x1056),  # VOILUTFunction
        Tag(0x0028, 0x1090),  # RecommendedViewingMode
        Tag(0x0028, 0x1101),  # RedPaletteColorLookupTableDescriptor
        Tag(0x0028, 0x1102),  # GreenPaletteColorLookupTableDescriptor
        Tag(0x0028, 0x1103),  # BluePaletteColorLookupTableDescriptor
        Tag(0x0028, 0x1201),  # RedPaletteColorLookupTableData
        Tag(0x0028, 0x1202),  # GreenPaletteColorLookupTableData
        Tag(0x0028, 0x1203),  # BluePaletteColorLookupTableData
        Tag(0x0028, 0x2000),  # ICCProfile
        Tag(0x0028, 0x2110),  # LossyImageCompression
        Tag(0x0028, 0x2112),  # LossyImageCompressionRatio
        Tag(0x0028, 0x2114),  # LossyImageCompressionMethod
        Tag(0x0028, 0x6010),  # RepresentativeFrameNumber
        Tag(0x0028, 0x9001),  # DataPointRows
        Tag(0x0028, 0x9002),  # DataPointColumns
        Tag(0x0028, 0x9108),  # DataRepresentation
        Tag(0x0032, 0x0033),  # StudyVerifiedTime
        Tag(0x0032, 0x0035),  # StudyReadTime
        Tag(0x0032, 0x1001),  # ScheduledStudyStartTime
        Tag(0x0032, 0x1011),  # ScheduledStudyStopTime
        Tag(0x0032, 0x1041),  # StudyArrivalTime
        Tag(0x0032, 0x1051),  # StudyCompletionTime
        Tag(0x0038, 0x001B),  # ScheduledAdmissionTime
        Tag(0x0038, 0x001D),  # ScheduledDischargeTime
        Tag(0x0038, 0x0021),  # AdmittingTime
        Tag(0x0038, 0x0032),  # DischargeTime
        Tag(0x0040, 0x0003),  # SPSStartTime
        Tag(0x0040, 0x0005),  # SPSEndTime
        Tag(0x0040, 0x0245),  # PPSStartTime
        Tag(0x0040, 0x0251),  # PPSEndTime
        Tag(0x0040, 0x0318),  # OrganExposed
        Tag(0x0040, 0x8302),  # EntranceDoseInmGy
        Tag(0x0040, 0xA122),  # Time
        Tag(0x0040, 0xA193),  # TrialObservationTime
        Tag(0x0054, 0x0011),  # NumberOfEnergyWindows
        Tag(0x0054, 0x0016),  # RadiopharmaceuticalInformationSequence
        Tag(0x0054, 0x0022),  # DetectorInformationSequence
        Tag(0x0054, 0x0050),  # RotationVector
        Tag(0x0054, 0x0051),  # NumberOfRotations
        Tag(0x0054, 0x0060),  # RRIntervalVector
        Tag(0x0054, 0x0061),  # NumberOfRRIntervals
        Tag(0x0054, 0x0070),  # TimeSlotVector
        Tag(0x0054, 0x0080),  # SliceVector
        Tag(0x0054, 0x0090),  # AngularViewVector
        Tag(0x0054, 0x0100),  # TimeSliceVector
        Tag(0x0054, 0x0202),  # TypeOfDetectorMotion
        Tag(0x0054, 0x0300),  # RadionuclideCodeSequence
        Tag(0x0054, 0x1000),  # SeriesType
        Tag(0x0054, 0x1001),  # Units
        Tag(0x0054, 0x1006),  # SUVType
        Tag(0x0054, 0x1102),  # DecayCorrection
        Tag(0x0054, 0x1300),  # FrameReferenceTime
        Tag(0x0054, 0x1323),  # ScatterFractionFactor
        Tag(0x0054, 0x1330),  # ImageIndex
        Tag(0x0054, 0x1400),  # CountsIncluded
        Tag(0x0054, 0x1401),  # DeadTimeCorrectionFlag
        Tag(0x0062, 0x0002),  # SegmentSequence
        Tag(0x7FE0, 0x0010),  # PixelData
    }
)

# Pixels-only: 1 tag removed -- IrradiationEventUID.
PIXELS_ONLY_REMOVE_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x3010),  # IrradiationEventUID
    }
)

# Content-root sequences whose subtree is retained verbatim under
# remove_unspecified. These carry the KO/PR labels and cross-object references;
# the shared element rules (PHI removal, date removal, free-text redaction, UID
# hashing) still de-identify every element within them. Structural and coded
# members (Value Type, Concept Name/Code sequences, Graphic Data/Type, reference
# SOP sequences) carry no PHI and are preserved.
PIXELS_ONLY_CONTENT_ROOT_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x2218),  # AnatomicRegionSequence
        Tag(0x0040, 0xA043),  # ConceptNameCodeSequence (KO document title)
        Tag(0x0040, 0xA370),  # ReferencedRequestSequence
        Tag(0x0040, 0xA375),  # CurrentRequestedProcedureEvidenceSequence
        Tag(0x0040, 0xA525),  # IdenticalDocumentsSequence
        Tag(0x0040, 0xA730),  # ContentSequence
        Tag(0x0070, 0x0001),  # GraphicAnnotationSequence
    }
)


def pixels_only_profile(settings: ProfileSettings | None = None) -> DeidProfile:
    """Construct a pixels-only profile.

    No jitter, minimal metadata. Removes all unspecified elements. UIDs are
    re-derived without the study-ID salt. Per-patient identity values are
    supplied at apply time via :class:`DeidParameters`. When PatientID,
    PatientName, or AccessionNumber are not supplied, the original element value
    is hashed with ``settings.hash_salt`` and the study identifier;
    PatientName reuses the PatientID hash.

    The free-text description fields take a per-patient value verbatim; when it
    is ``None`` they are redacted from the dataset using
    ``settings.allowlist_csv`` at apply time.

    KO and PR label subtrees are retained through ``content_root_tags``. The
    shared PHI-removal, date-removal, and free-text redaction rules are applied
    so those retained subtrees are de-identified: dates are removed (not
    jittered, matching the profile's no-date posture), and the free-text label
    fields are redacted against the allowlist. Because the profile hashes UIDs
    without the study salt, references resolve within a single pixels-only
    export but not against objects de-identified by another profile.
    """
    settings = settings or ProfileSettings()
    uid_action = hash_uid(settings.uid_root)  # no study-ID salt

    rules: dict[BaseTag, TagAction] = {}

    # PHI removal shared with the default profile, applied first so the
    # image-technical keep rules below win on the few overlapping tags. These
    # remove PHI wherever it appears, including inside the retained KO/PR
    # content subtrees. Dates are removed rather than jittered.
    remove_action = remove()
    rules.update(dict.fromkeys(PHI_REMOVE_TAGS, remove_action))
    rules.update(dict.fromkeys(EMPTY_TAGS, remove_action))
    rules.update(dict.fromkeys(DATE_TAGS, remove_action))

    # Preserve tags unchanged
    rules.update({t: keep() for t in PIXELS_ONLY_KEEP_TAGS})

    # Hash UID tags -- no salt
    rules.update(dict.fromkeys(PIXELS_ONLY_UID_TAGS, uid_action))

    # Remove tags
    rules.update({t: remove() for t in PIXELS_ONLY_REMOVE_TAGS})

    # Identifier substitution -- caller value wins, else hash the original.
    # PatientName runs before the PatientID rule so it hashes the original
    # PatientID element and matches the value the PatientID rule then writes.
    rules[Tag(0x0010, 0x0010)] = hash_identifier_param(
        "patient_name", salt=settings.hash_salt, fallback_field="patient_id", source_tag=Tag(0x0010, 0x0020)
    )  # PatientName
    rules[Tag(0x0010, 0x0020)] = hash_identifier_param("patient_id", salt=settings.hash_salt)  # PatientID
    rules[Tag(0x0008, 0x0050)] = hash_identifier_param("accession_number", salt=settings.hash_salt)  # AccessionNumber
    rules[Tag(0x0008, 0x103E)] = redact_description(
        "series_description", settings.allowlist_csv, False
    )  # SeriesDescription
    rules[Tag(0x0008, 0x1030)] = redact_description(
        "study_description", settings.allowlist_csv, False
    )  # StudyDescription
    rules[Tag(0x0018, 0x1030)] = redact_description("protocol_name", settings.allowlist_csv, False)  # ProtocolName

    # KO/PR free-text label redaction and identifier hashing inside retained
    # content subtrees.
    redact = redact_free_text(settings.allowlist_csv, False)
    rules[Tag(0x0070, 0x0006)] = redact  # UnformattedTextValue (ST)
    rules[Tag(0x0070, 0x0289)] = redact  # TickLabel (SH)
    rules[Tag(0x0040, 0xA160)] = redact  # TextValue (UT), KO/SR content free text
    rules[Tag(0x0062, 0x0020)] = hash_value_identifier(salt=settings.hash_salt)  # TrackingID (UT)

    # PatientIdentityRemoved -- created if missing and set to YES
    rules[Tag(0x0012, 0x0062)] = set_value("YES", create_if_missing=True)

    return DeidProfile(
        name="Pixels-Only",
        rules=rules,
        keep_groups=frozenset(),
        remove_private=True,
        remove_curves=True,
        remove_overlays=True,
        remove_unspecified=True,
        allowlist_csv=settings.allowlist_csv,
        hash_salt=settings.hash_salt,
        uid_root=settings.uid_root,
        uid_use_study_salt=False,
        emits_basic_profile=False,
        deid_options=frozenset({"113103", "113104"}),
        content_root_tags=PIXELS_ONLY_CONTENT_ROOT_TAGS,
    )
