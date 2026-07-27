"""Default de-identification profile (DICOM-PS3.15E-Basic).

Full PS3.15E de-identification with UID hashing, date jitter,
and PHI removal.
"""

from typing import cast

from pydicom.dataset import Dataset
from pydicom.tag import BaseTag
from pydicom.tag import Tag

from dicom_dre.actions import TagAction
from dicom_dre.actions import append_value
from dicom_dre.actions import cap_age
from dicom_dre.actions import empty
from dicom_dre.actions import hash_uid
from dicom_dre.actions import if_exists
from dicom_dre.actions import jitter_date
from dicom_dre.actions import keep
from dicom_dre.actions import process
from dicom_dre.actions import remove
from dicom_dre.actions import set_param
from dicom_dre.actions import set_value
from dicom_dre.parameters import DEFAULT_STUDY_ID
from dicom_dre.parameters import IDENTIFIER_PLACEHOLDER
from dicom_dre.parameters import DeidParameters
from dicom_dre.profile import DeidProfile
from dicom_dre.text_redactor import get_text_redactor


UIDROOT = "1.2.840.4267.32."


# 214 tags removed during de-identification because they may carry PHI.
PHI_REMOVE_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0000, 0x1000),  # AffectedSOPInstanceUID
        Tag(0x0008, 0x0080),  # InstitutionName
        Tag(0x0008, 0x0081),  # InstitutionAddress
        Tag(0x0008, 0x0082),  # InstitutionCodeSeq
        Tag(0x0008, 0x0092),  # ReferringPhysicianAddress
        Tag(0x0008, 0x0094),  # ReferringPhysicianPhoneNumbers
        Tag(0x0008, 0x0096),  # ReferringPhysiciansIDSeq
        Tag(0x0008, 0x009C),  # ConsultingPhysicianName
        Tag(0x0008, 0x009D),  # ConsultingPhysicianIdentificationSequence
        Tag(0x0008, 0x0201),  # TimezoneOffsetFromUTC
        Tag(0x0008, 0x1010),  # StationName
        Tag(0x0008, 0x1040),  # InstitutionalDepartmentName
        Tag(0x0008, 0x1048),  # PhysicianOfRecord
        Tag(0x0008, 0x1049),  # PhysicianOfRecordIdSeq
        Tag(0x0008, 0x1050),  # PerformingPhysicianName
        Tag(0x0008, 0x1052),  # PerformingPhysicianIdSeq
        Tag(0x0008, 0x1060),  # NameOfPhysicianReadingStudy
        Tag(0x0008, 0x1062),  # PhysicianReadingStudyIdSeq
        Tag(0x0008, 0x1070),  # OperatorName
        Tag(0x0008, 0x1072),  # OperatorsIdentificationSeq
        Tag(0x0008, 0x1080),  # AdmittingDiagnosisDescription
        Tag(0x0008, 0x1084),  # AdmittingDiagnosisCodeSeq
        Tag(0x0008, 0x1110),  # RefStudySeq
        Tag(0x0008, 0x1111),  # RefPPSSeq
        Tag(0x0008, 0x1120),  # RefPatientSeq
        Tag(0x0008, 0x1140),  # RefImageSeq
        Tag(0x0008, 0x1250),  # RelatedSeriesSequence
        Tag(0x0008, 0x2111),  # DerivationDescription
        Tag(0x0008, 0x2112),  # SourceImageSeq
        Tag(0x0008, 0x2218),  # AnatomicRegionSeq
        Tag(0x0008, 0x3010),  # IrradiationEventUID
        Tag(0x0008, 0x4000),  # IdentifyingComments
        Tag(0x0010, 0x0021),  # IssuerOfPatientID
        Tag(0x0010, 0x0032),  # PatientBirthTime
        Tag(0x0010, 0x0050),  # PatientInsurancePlanCodeSeq
        Tag(0x0010, 0x0101),  # PatientPrimaryLanguageCodeSeq
        Tag(0x0010, 0x0102),  # PatientPrimaryLanguageModifierCodeSeq
        Tag(0x0010, 0x1000),  # OtherPatientIDs
        Tag(0x0010, 0x1001),  # OtherPatientNames
        Tag(0x0010, 0x1002),  # OtherPatientIDsSeq
        Tag(0x0010, 0x1005),  # PatientBirthName
        Tag(0x0010, 0x1020),  # PatientSize
        Tag(0x0010, 0x1030),  # PatientWeight
        Tag(0x0010, 0x1040),  # PatientAddress
        Tag(0x0010, 0x1050),  # InsurancePlanIdentification
        Tag(0x0010, 0x1060),  # PatientMotherBirthName
        Tag(0x0010, 0x1080),  # MilitaryRank
        Tag(0x0010, 0x1081),  # BranchOfService
        Tag(0x0010, 0x1090),  # MedicalRecordLocator
        Tag(0x0010, 0x1100),  # ReferencedPatientPhotoSequence
        Tag(0x0010, 0x2000),  # MedicalAlerts
        Tag(0x0010, 0x2110),  # ContrastAllergies
        Tag(0x0010, 0x2150),  # CountryOfResidence
        Tag(0x0010, 0x2152),  # RegionOfResidence
        Tag(0x0010, 0x2154),  # PatientPhoneNumbers
        Tag(0x0010, 0x2155),  # PatientTelecomInformation
        Tag(0x0010, 0x2160),  # EthnicGroup
        Tag(0x0010, 0x2180),  # Occupation
        Tag(0x0010, 0x21A0),  # SmokingStatus
        Tag(0x0010, 0x21B0),  # AdditionalPatientHistory
        Tag(0x0010, 0x21C0),  # PregnancyStatus
        Tag(0x0010, 0x21F0),  # PatientReligiousPreference
        Tag(0x0010, 0x2203),  # PatientSexNeutered
        Tag(0x0010, 0x2297),  # ResponsiblePerson
        Tag(0x0010, 0x2299),  # ResponsibleOrganization
        Tag(0x0010, 0x4000),  # PatientComments
        Tag(0x0018, 0x1000),  # DeviceSerialNumber
        Tag(0x0018, 0x1004),  # PlateID
        Tag(0x0018, 0x1005),  # GeneratorID
        Tag(0x0018, 0x1007),  # CassetteID
        Tag(0x0018, 0x1008),  # GantryID
        Tag(0x0018, 0x1078),  # RadiopharmaceuticalStartDateTime
        Tag(0x0018, 0x1079),  # RadiopharmaceuticalStopDateTime
        Tag(0x0018, 0x1200),  # DateOfLastCalibration
        Tag(0x0018, 0x1400),  # AcquisitionDeviceProcessingDescription
        Tag(0x0018, 0x4000),  # AcquisitionComments
        Tag(0x0018, 0x700A),  # DetectorID
        Tag(0x0018, 0x700C),  # DateOfLastDetectorCalibration
        Tag(0x0018, 0x9074),  # FrameAcquisitionDatetime
        Tag(0x0018, 0x9151),  # FrameReferenceDatetime
        Tag(0x0018, 0x9424),  # AcquisitionProtocolDescription
        Tag(0x0018, 0x9506),  # ContributingSourcesSequence
        Tag(0x0018, 0xA003),  # ContributionDescription
        Tag(0x0020, 0x3401),  # ModifyingDeviceID
        Tag(0x0020, 0x3404),  # ModifyingDeviceManufacturer
        Tag(0x0020, 0x3406),  # ModifiedImageDescription
        Tag(0x0020, 0x4000),  # ImageComments
        Tag(0x0020, 0x9158),  # FrameComments
        Tag(0x0028, 0x4000),  # ImagePresentationComments
        Tag(0x0032, 0x0012),  # StudyIDIssuer
        Tag(0x0032, 0x0032),  # StudyVerifiedDate
        Tag(0x0032, 0x0034),  # StudyReadDate
        Tag(0x0032, 0x1000),  # ScheduledStudyStartDate
        Tag(0x0032, 0x1010),  # ScheduledStudyStopDate
        Tag(0x0032, 0x1020),  # ScheduledStudyLocation
        Tag(0x0032, 0x1021),  # ScheduledStudyLocationAET
        Tag(0x0032, 0x1030),  # ReasonforStudy
        Tag(0x0032, 0x1032),  # RequestingPhysician
        Tag(0x0032, 0x1033),  # RequestingService
        Tag(0x0032, 0x1040),  # StudyArrivalDate
        Tag(0x0032, 0x1050),  # StudyCompletionDate
        Tag(0x0032, 0x1060),  # RequestedProcedureDescription
        Tag(0x0032, 0x1070),  # RequestedContrastAgent
        Tag(0x0032, 0x4000),  # StudyComments
        Tag(0x0038, 0x0004),  # RefPatientAliasSeq
        Tag(0x0038, 0x0010),  # AdmissionID
        Tag(0x0038, 0x0011),  # IssuerOfAdmissionID
        Tag(0x0038, 0x001A),  # ScheduledAdmissionDate
        Tag(0x0038, 0x001C),  # ScheduledDischargeDate
        Tag(0x0038, 0x001E),  # ScheduledPatientInstitutionResidence
        Tag(0x0038, 0x0040),  # DischargeDiagnosisDescription
        Tag(0x0038, 0x0050),  # SpecialNeeds
        Tag(0x0038, 0x0060),  # ServiceEpisodeID
        Tag(0x0038, 0x0061),  # IssuerOfServiceEpisodeId
        Tag(0x0038, 0x0062),  # ServiceEpisodeDescription
        Tag(0x0038, 0x0300),  # CurrentPatientLocation
        Tag(0x0038, 0x0400),  # PatientInstitutionResidence
        Tag(0x0038, 0x0500),  # PatientState
        Tag(0x0038, 0x1234),  # ReferencedPatientAliasSeq
        Tag(0x0038, 0x4000),  # VisitComments
        Tag(0x0040, 0x0001),  # ScheduledStationAET
        Tag(0x0040, 0x0006),  # ScheduledPerformingPhysicianName
        Tag(0x0040, 0x0007),  # SPSDescription
        Tag(0x0040, 0x000B),  # ScheduledPerformingPhysicianIDSeq
        Tag(0x0040, 0x0010),  # ScheduledStationName
        Tag(0x0040, 0x0011),  # SPSLocation
        Tag(0x0040, 0x0012),  # PreMedication
        Tag(0x0040, 0x0241),  # PerformedStationAET
        Tag(0x0040, 0x0242),  # PerformedStationName
        Tag(0x0040, 0x0243),  # PerformedLocation
        Tag(0x0040, 0x0248),  # PerformedStationNameCodeSeq
        Tag(0x0040, 0x0253),  # PPSID
        Tag(0x0040, 0x0254),  # PPSDescription
        Tag(0x0040, 0x0275),  # RequestAttributesSeq
        Tag(0x0040, 0x0280),  # PPSComments
        Tag(0x0040, 0x0555),  # AcquisitionContextSeq
        Tag(0x0040, 0x1001),  # RequestedProcedureID
        Tag(0x0040, 0x1004),  # PatientTransportArrangements
        Tag(0x0040, 0x1005),  # RequestedProcedureLocation
        Tag(0x0040, 0x1010),  # NamesOfIntendedRecipientsOfResults
        Tag(0x0040, 0x1011),  # IntendedRecipientsOfResultsIDSequence
        Tag(0x0040, 0x1102),  # PersonAddress
        Tag(0x0040, 0x1103),  # PersonTelephoneNumbers
        Tag(0x0040, 0x1104),  # PersonTelecomInformation
        Tag(0x0040, 0x1400),  # RequestedProcedureComments
        Tag(0x0040, 0x2001),  # ReasonForTheImagingServiceRequest
        Tag(0x0040, 0x2004),  # IssueDateOfImagingServiceRequest
        Tag(0x0040, 0x2008),  # OrderEnteredBy
        Tag(0x0040, 0x2009),  # OrderEntererLocation
        Tag(0x0040, 0x2010),  # OrderCallbackPhoneNumber
        Tag(0x0040, 0x2011),  # OrderCallbackTelecomInformation
        Tag(0x0040, 0x2400),  # ImagingServiceRequestComments
        Tag(0x0040, 0x3001),  # ConfidentialityPatientData
        Tag(0x0040, 0x4025),  # ScheduledStationNameCodeSeq
        Tag(0x0040, 0x4027),  # ScheduledStationGeographicLocCodeSeq
        Tag(0x0040, 0x4028),  # PerformedStationNameCodeSequence
        Tag(0x0040, 0x4030),  # PerformedStationGeoLocCodeSeq
        Tag(0x0040, 0x4034),  # ScheduledHumanPerformersSeq
        Tag(0x0040, 0x4035),  # ActualHumanPerformersSequence
        Tag(0x0040, 0x4036),  # HumanPerformersOrganization
        Tag(0x0040, 0x4037),  # HumanPerformersName
        Tag(0x0040, 0xA027),  # VerifyingOrganization
        Tag(0x0040, 0xA030),  # VerificationDateTime
        Tag(0x0040, 0xA032),  # ObservationDateTime
        Tag(0x0040, 0xA078),  # AuthorObserverSequence
        Tag(0x0040, 0xA07A),  # ParticipantSequence
        Tag(0x0040, 0xA07C),  # CustodialOrganizationSeq
        Tag(0x0040, 0xA120),  # DateTime
        Tag(0x0040, 0xA121),  # Date
        Tag(0x0040, 0xA13A),  # RefDatetime
        Tag(0x0040, 0xA307),  # TrialCurrentObserver
        Tag(0x0040, 0xA352),  # TrialVerbalSource
        Tag(0x0040, 0xA353),  # TrialAddress
        Tag(0x0040, 0xA354),  # TrialTelephoneNumber
        Tag(0x0040, 0xA358),  # TrialVerbalSourceIdentifierCodeSequence
        Tag(0x0040, 0xA730),  # ContentSeq
        Tag(0x0060, 0x3000),  # OverlayData
        Tag(0x0060, 0x4000),  # OverlayComments
        Tag(0x0070, 0x0001),  # GraphicAnnotationSequence
        Tag(0x0070, 0x0086),  # ContentCreatorsIdCodeSeq
        Tag(0x0088, 0x0200),  # IconImageSequence
        Tag(0x0088, 0x0904),  # TopicTitle
        Tag(0x0088, 0x0906),  # TopicSubject
        Tag(0x0088, 0x0910),  # TopicAuthor
        Tag(0x0088, 0x0912),  # TopicKeyWords
        Tag(0x0400, 0x0100),  # DigitalSignatureUID
        Tag(0x0400, 0x0402),  # RefDigitalSignatureSeq
        Tag(0x0400, 0x0403),  # RefSOPInstanceMACSeq
        Tag(0x0400, 0x0404),  # MAC
        Tag(0x0400, 0x0550),  # ModifiedAttributesSequence
        Tag(0x0400, 0x0561),  # OriginalAttributesSequence
        Tag(0x0400, 0x0600),  # InstanceOriginStatus
        Tag(0x2030, 0x0020),  # TextString
        Tag(0x3008, 0x0105),  # SourceSerialNumber
        Tag(0x300C, 0x0113),  # ReasonForOmissionDescription
        Tag(0x300E, 0x0008),  # ReviewerName
        Tag(0x4000, 0x0010),  # Arbitrary
        Tag(0x4000, 0x4000),  # TextComments
        Tag(0x4008, 0x0042),  # ResultsIDIssuer
        Tag(0x4008, 0x0102),  # InterpretationRecorder
        Tag(0x4008, 0x010A),  # InterpretationTranscriber
        Tag(0x4008, 0x010B),  # InterpretationText
        Tag(0x4008, 0x010C),  # InterpretationAuthor
        Tag(0x4008, 0x0111),  # InterpretationApproverSequence
        Tag(0x4008, 0x0114),  # PhysicianApprovingInterpretation
        Tag(0x4008, 0x0115),  # InterpretationDiagnosisDescription
        Tag(0x4008, 0x0118),  # ResultsDistributionListSeq
        Tag(0x4008, 0x0119),  # DistributionName
        Tag(0x4008, 0x011A),  # DistributionAddress
        Tag(0x4008, 0x0202),  # InterpretationIdIssuer
        Tag(0x4008, 0x0300),  # Impressions
        Tag(0x4008, 0x4000),  # ResultComments
        Tag(0xFFFA, 0xFFFA),  # DigitalSignaturesSeq
        Tag(0xFFFC, 0xFFFC),  # DataSetTrailingPadding
    }
)

# 35 UID tags re-hashed to deterministic replacement UIDs.
UID_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0000, 0x1001),  # RequestedSOPInstanceUID
        Tag(0x0002, 0x0003),  # MediaStorageSOPInstanceUID
        Tag(0x0004, 0x1511),  # RefSOPInstanceUIDinFile
        Tag(0x0008, 0x0014),  # InstanceCreatorUID
        Tag(0x0008, 0x0018),  # SOPInstanceUID
        Tag(0x0008, 0x0058),  # FailedSOPInstanceUIDList
        Tag(0x0008, 0x010C),  # PrivateCodingSchemeCreatorUID
        Tag(0x0008, 0x010D),  # CodeSetExtensionCreatorUID
        Tag(0x0008, 0x1155),  # ReferencedSOPInstanceUID
        Tag(0x0008, 0x1195),  # TransactionUID
        Tag(0x0008, 0x9123),  # CreatorVersionUID
        Tag(0x0018, 0x1002),  # DeviceUID
        Tag(0x0020, 0x000D),  # StudyInstanceUID
        Tag(0x0020, 0x000E),  # SeriesInstanceUID
        Tag(0x0020, 0x0052),  # FrameOfReferenceUID
        Tag(0x0020, 0x0200),  # SynchronizationFrameOfReferenceUID
        Tag(0x0020, 0x9161),  # ConcatenationUID
        Tag(0x0020, 0x9164),  # DimensionOrganizationUID
        Tag(0x0028, 0x1199),  # PaletteColorLUTUID
        Tag(0x0028, 0x1214),  # LargePaletteColorLUTUid
        Tag(0x0040, 0x4023),  # RefGenPurposeSchedProcStepTransUID
        Tag(0x0040, 0xA124),  # UID
        Tag(0x0040, 0xA171),  # TrialObservationUID
        Tag(0x0040, 0xA172),  # TrialReferencedObservationUID
        Tag(0x0040, 0xA402),  # TrialObservationSubjectUID
        Tag(0x0040, 0xDB0C),  # TemplateExtensionOrganizationUID
        Tag(0x0040, 0xDB0D),  # TemplateExtensionCreatorUID
        Tag(0x0062, 0x0021),  # TrackingUID
        Tag(0x0070, 0x031A),  # FiducialUID
        Tag(0x0070, 0x1101),  # PresentationDisplayCollectionUID
        Tag(0x0070, 0x1102),  # PresentationSequenceCollectionUID
        Tag(0x0088, 0x0140),  # StorageMediaFilesetUID
        Tag(0x3006, 0x0024),  # ReferencedFrameOfReferenceUID
        Tag(0x3006, 0x00C2),  # RelatedFrameOfReferenceUID
        Tag(0x300A, 0x0013),  # DoseReferenceUID
    }
)

# 28 date/datetime tags shifted by the jitter amount, each only when present.
DATE_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0012),  # InstanceCreationDate
        Tag(0x0008, 0x0015),  # InstanceCoercionDateTime
        Tag(0x0008, 0x0020),  # StudyDate
        Tag(0x0008, 0x0021),  # SeriesDate
        Tag(0x0008, 0x0022),  # AcquisitionDate
        Tag(0x0008, 0x0023),  # ContentDate
        Tag(0x0008, 0x0024),  # OverlayDate
        Tag(0x0008, 0x0025),  # CurveDate
        Tag(0x0008, 0x002A),  # AcquisitionDatetime
        Tag(0x0010, 0x0030),  # PatientBirthDate
        Tag(0x0010, 0x21D0),  # LastMenstrualDate
        Tag(0x0018, 0x1012),  # DateOfSecondaryCapture
        Tag(0x0018, 0x9516),  # StartAcquisitionDateTime
        Tag(0x0018, 0x9517),  # EndAcquisitionDateTime
        Tag(0x0038, 0x0020),  # AdmittingDate
        Tag(0x0040, 0x0002),  # SPSStartDate
        Tag(0x0040, 0x0004),  # SPSEndDate
        Tag(0x0040, 0x0244),  # PPSStartDate
        Tag(0x0040, 0x0250),  # PPSEndDate
        Tag(0x0040, 0x4005),  # ScheduledProcedureStepStartDateTime
        Tag(0x0040, 0x4008),  # ScheduledProcedureStepExpirationDateTime
        Tag(0x0040, 0x4010),  # ScheduledProcedureStepModificationDateTime
        Tag(0x0040, 0x4011),  # ExpectedCompletionDateTime
        Tag(0x0040, 0x4050),  # PerformedProcedureStepStartDateTime
        Tag(0x0040, 0x4051),  # PerformedProcedureStepEndDateTime
        Tag(0x0040, 0x4052),  # ProcedureStepCancellationDateTime
        Tag(0x0040, 0xA192),  # TrialObservationDate
        Tag(0x3006, 0x0008),  # StructureSetDate
    }
)

# 51 tags preserved unchanged during de-identification. Membership in a
# profile's rules exempts these from global removal, which matters for
# profiles that set remove_unspecified=True.
KEEP_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0005),  # SpecificCharacterSet
        Tag(0x0008, 0x0013),  # InstanceCreationTime
        Tag(0x0008, 0x0016),  # SOPClassUID
        Tag(0x0008, 0x0030),  # StudyTime
        Tag(0x0008, 0x0031),  # SeriesTime
        Tag(0x0008, 0x0032),  # AcquisitionTime
        Tag(0x0008, 0x0033),  # ContentTime
        Tag(0x0008, 0x0034),  # OverlayTime
        Tag(0x0008, 0x0035),  # CurveTime
        Tag(0x0008, 0x0060),  # Modality
        Tag(0x0008, 0x1150),  # RefSOPClassUID
        Tag(0x0008, 0x2130),  # EventElapsedTime
        Tag(0x0010, 0x0040),  # PatientSex
        Tag(0x0018, 0x0010),  # ContrastBolusAgent
        Tag(0x0018, 0x0015),  # BodyPartExamined
        Tag(0x0018, 0x0027),  # InterventionDrugStopTime
        Tag(0x0018, 0x0035),  # InterventionDrugStartTime
        Tag(0x0018, 0x0080),  # RepetitionTime
        Tag(0x0018, 0x0081),  # EchoTime
        Tag(0x0018, 0x0082),  # InversionTime
        Tag(0x0018, 0x1042),  # ContrastBolusStartTime
        Tag(0x0018, 0x1043),  # ContrastBolusStopTime
        Tag(0x0018, 0x1060),  # TriggerTime
        Tag(0x0018, 0x1063),  # FrameTime
        Tag(0x0018, 0x1072),  # RadiopharmaceuticalStartTime
        Tag(0x0018, 0x1073),  # RadiopharmaceuticalStopTime
        Tag(0x0018, 0x1150),  # ExposureTime
        Tag(0x0018, 0x1201),  # TimeOfLastCalibration
        Tag(0x0018, 0x1480),  # TomoTime
        Tag(0x0018, 0x7014),  # DetectorActiveTime
        Tag(0x0018, 0x9079),  # InversionTimes
        Tag(0x0018, 0x9082),  # EffectiveEchoTime
        Tag(0x0020, 0x9153),  # TriggerDelayTime
        Tag(0x0032, 0x0033),  # StudyVerifiedTime
        Tag(0x0032, 0x0035),  # StudyReadTime
        Tag(0x0032, 0x1001),  # ScheduledStudyStartTime
        Tag(0x0032, 0x1011),  # ScheduledStudyStopTime
        Tag(0x0032, 0x1041),  # StudyArrivalTime
        Tag(0x0032, 0x1051),  # StudyCompletionTime
        Tag(0x0038, 0x001B),  # ScheduledAdmissionTime
        Tag(0x0038, 0x001D),  # ScheduledDischargeTime
        Tag(0x0038, 0x0021),  # AdmittingTime
        Tag(0x0038, 0x0030),  # DischargeDate
        Tag(0x0040, 0x0003),  # SPSStartTime
        Tag(0x0040, 0x0005),  # SPSEndTime
        Tag(0x0040, 0x0245),  # PPSStartTime
        Tag(0x0040, 0x0251),  # PPSEndTime
        Tag(0x0040, 0xA122),  # Time
        Tag(0x0040, 0xA193),  # TrialObservationTime
        Tag(0x0054, 0x0070),  # TimeSlotVector
        Tag(0x0054, 0x0100),  # TimeSliceVector
        Tag(0x0054, 0x1300),  # FrameReferenceTime
    }
)

# 15 tags emptied (set to a zero-length value) during de-identification.
# Present elements are set to a zero-length value; absent elements are not
# created.
EMPTY_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0090),  # ReferringPhysicianName
        Tag(0x0018, 0x1065),  # FrameTimeVector
        Tag(0x0020, 0x0010),  # StudyID
        Tag(0x0040, 0x050A),  # SpecimenAccessionNumber
        Tag(0x0040, 0x0550),  # SpecimenSeq
        Tag(0x0040, 0x0551),  # SpecimenIdentifier
        Tag(0x0040, 0x1002),  # ReasonForTheRequestedProcedure
        Tag(0x0040, 0x1003),  # RequestedProcedurePriority
        Tag(0x0040, 0x1101),  # PersonIdentificationCodeSequence
        Tag(0x0040, 0x2016),  # PlacerOrderNumber
        Tag(0x0040, 0x2017),  # FillerOrderNumber
        Tag(0x0040, 0xA073),  # VerifyingObserverSeq
        Tag(0x0040, 0xA088),  # VerifyingObserverIdentificationCodeSeq
        Tag(0x0040, 0xA123),  # PersonName
        Tag(0x0070, 0x0084),  # ContentCreatorsName
    }
)


def description_action(field_name: str, allowlist_csv: str, preserve_dates: bool) -> TagAction:
    """Return the tag action for a free-text description element.

    A per-patient value supplied on ``params.<field_name>`` takes precedence and
    is written verbatim. When it is ``None`` the element is redacted using the
    allowlist redactor, so PHI in SeriesDescription, StudyDescription, and
    ProtocolName is removed while allowlisted tokens are preserved. The action is
    present-only: a missing element is left absent.
    """
    redactor = get_text_redactor(allowlist_csv, preserve_dates)

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        override = getattr(params, field_name)
        if override is not None:
            if tag in ds:
                ds[tag].value = override
            return
        if tag not in ds:
            return
        value = ds[tag].value
        if value:
            ds[tag].value = cast(str, redactor.redact_text(text=str(value), track_redacted=False))
        else:
            ds[tag].value = ""

    return action


def _build_constant_rules() -> dict[BaseTag, TagAction]:
    """Build the patient-invariant rule mapping shared by every profile.

    The action objects are stateless closures, so one instance is shared across
    all tags in each category: ``dict.fromkeys`` assigns a single value to every
    key, and ``remove_action`` is reused for the lone VerifyingObserverName rule.
    """
    remove_action = remove()
    rules: dict[BaseTag, TagAction] = {}
    rules.update(dict.fromkeys(PHI_REMOVE_TAGS, remove_action))
    rules.update(dict.fromkeys(KEEP_TAGS, keep()))
    rules.update(dict.fromkeys(EMPTY_TAGS, empty()))
    # Mandatory evidence attributes with literal values
    rules[Tag(0x0012, 0x0062)] = set_value("YES", create_if_missing=True)  # PatientIdentityRemoved
    rules[Tag(0x0028, 0x0303)] = set_value(
        "MODIFIED", create_if_missing=True
    )  # LongitudinalTemporalInformationModified
    rules[Tag(0x0010, 0x1010)] = cap_age(89, "090Y")  # PatientAge
    rules[Tag(0x0040, 0xA075)] = remove_action  # VerifyingObserverName
    # process() marks a sequence for recursion; DeidProfile applies its own
    # rules to the sequence items, so derived profiles inherit the rule set.
    rules[Tag(0x0054, 0x0016)] = process()  # RadiopharmaceuticalInformationSequence
    return rules


def default_profile(
    *,
    uid_root: str = UIDROOT,
    deid_method: str = "DICOM-PS3.15E-Basic",
    allowlist_csv: str = "default.csv",
    preserve_dates: bool = False,
) -> DeidProfile:
    """Construct a full PS3.15E de-identification profile.

    The returned profile is a patient-invariant policy object. Per-patient
    identity values (PatientID, AccessionNumber, StudyID, PatientName, the
    free-text description overrides, and the date jitter) are supplied at apply
    time via :class:`DeidParameters`.

    The free-text description fields accept a per-patient value that takes
    precedence; when it is ``None`` the engine redacts the corresponding element
    from the dataset at apply time using the ``allowlist_csv`` allowlist.
    ``preserve_dates`` selects a date-preserving redactor for the free-text
    fields and does not alter the profile's date-jitter behavior.
    """
    uid_action = hash_uid(uid_root, use_study_salt=True)
    shift = if_exists(jitter_date())

    rules = _build_constant_rules()
    rules.update(dict.fromkeys(UID_TAGS, uid_action))
    rules.update(dict.fromkeys(DATE_TAGS, shift))

    rules[Tag(0x0010, 0x0010)] = set_param(
        "patient_name", fallback_field="patient_id", default=IDENTIFIER_PLACEHOLDER
    )  # PatientName
    rules[Tag(0x0010, 0x0020)] = set_param("patient_id", default=IDENTIFIER_PLACEHOLDER)  # PatientID
    rules[Tag(0x0008, 0x0050)] = set_param("accession_number", default=IDENTIFIER_PLACEHOLDER)  # AccessionNumber
    rules[Tag(0x0008, 0x103E)] = description_action(
        "series_description", allowlist_csv, preserve_dates
    )  # SeriesDescription
    rules[Tag(0x0008, 0x1030)] = description_action(
        "study_description", allowlist_csv, preserve_dates
    )  # StudyDescription
    rules[Tag(0x0018, 0x1030)] = description_action("protocol_name", allowlist_csv, preserve_dates)  # ProtocolName

    # Mandatory evidence attributes -- created if missing and then set here
    rules[Tag(0x0012, 0x0020)] = set_param(
        "study_id", default=DEFAULT_STUDY_ID, create_if_missing=True
    )  # ClinicalTrialProtocolID
    rules[Tag(0x0012, 0x0063)] = append_value(deid_method, create_if_missing=True)  # DeIdentificationMethod

    return DeidProfile(
        name="DICOM-PS3.15E-Basic",
        rules=rules,
        keep_groups=frozenset(),
        remove_private=True,
        remove_curves=False,
        remove_overlays=True,
        modifies_dates=True,
        allowlist_csv=allowlist_csv,
    )
