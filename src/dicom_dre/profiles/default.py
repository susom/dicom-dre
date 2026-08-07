"""Default de-identification profile (DICOM-PS3.15E-Basic).

Full PS3.15E de-identification with UID hashing, date jitter,
and PHI removal.
"""

from typing import cast

from pydicom.datadict import dictionary_VR
from pydicom.dataset import Dataset
from pydicom.tag import BaseTag
from pydicom.tag import Tag

from dicom_dre.actions import TagAction
from dicom_dre.actions import append_value
from dicom_dre.actions import cap_age
from dicom_dre.actions import dummy_for_vr
from dicom_dre.actions import empty
from dicom_dre.actions import hash_identifier_param
from dicom_dre.actions import hash_uid
from dicom_dre.actions import hash_value_identifier
from dicom_dre.actions import if_exists
from dicom_dre.actions import jitter_date
from dicom_dre.actions import keep
from dicom_dre.actions import remove
from dicom_dre.actions import set_param
from dicom_dre.actions import set_value
from dicom_dre.parameters import DEFAULT_STUDY_ID
from dicom_dre.parameters import DeidParameters
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles.config import ProfileSettings
from dicom_dre.text_redactor import get_text_redactor


# 365 tags removed during de-identification because they may carry PHI.
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
        Tag(0x0008, 0x0051),  # IssuerOfAccessionNumberSeq
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
        Tag(0x0008, 0x1250),  # RelatedSeriesSequence
        Tag(0x0008, 0x2111),  # DerivationDescription
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
        Tag(0x0060, 0x3000),  # OverlayData
        Tag(0x0060, 0x4000),  # OverlayComments
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
        # PS3.15 Basic Profile X attributes (2024b confidentiality table).
        Tag(0x0008, 0x0054),  # Retrieve AE Title
        Tag(0x0008, 0x0055),  # Station AE Title
        Tag(0x0008, 0x1000),  # Network ID
        Tag(0x0008, 0x1030),  # Study Description
        Tag(0x0008, 0x103E),  # Series Description
        Tag(0x0008, 0x1041),  # Institutional Department Type Code Sequence
        Tag(0x0008, 0x1088),  # Pyramid Description
        Tag(0x0010, 0x1010),  # Patient's Age
        Tag(0x0012, 0x0022),  # Issuer of Clinical Trial Protocol ID
        Tag(0x0012, 0x0023),  # Other Clinical Trial Protocol IDs Sequence
        Tag(0x0012, 0x0032),  # Issuer of Clinical Trial Site ID
        Tag(0x0012, 0x0041),  # Issuer of Clinical Trial Subject ID
        Tag(0x0012, 0x0043),  # Issuer of Clinical Trial Subject Reading ID
        Tag(0x0012, 0x0051),  # Clinical Trial Time Point Description
        Tag(0x0012, 0x0055),  # Issuer of Clinical Trial Time Point ID
        Tag(0x0012, 0x0071),  # Clinical Trial Series ID
        Tag(0x0012, 0x0072),  # Clinical Trial Series Description
        Tag(0x0012, 0x0073),  # Issuer of Clinical Trial Series ID
        Tag(0x0012, 0x0082),  # Clinical Trial Protocol Ethics Committee Approval Number
        Tag(0x0016, 0x002B),  # Maker Note
        Tag(0x0016, 0x004B),  # Device Setting Description
        Tag(0x0016, 0x004D),  # Camera Owner Name
        Tag(0x0016, 0x004E),  # Lens Specification
        Tag(0x0016, 0x004F),  # Lens Make
        Tag(0x0016, 0x0050),  # Lens Model
        Tag(0x0016, 0x0051),  # Lens Serial Number
        Tag(0x0016, 0x0070),  # GPS Version ID
        Tag(0x0016, 0x0071),  # GPS Latitude Ref
        Tag(0x0016, 0x0072),  # GPS Latitude
        Tag(0x0016, 0x0073),  # GPS Longitude Ref
        Tag(0x0016, 0x0074),  # GPS Longitude
        Tag(0x0016, 0x0075),  # GPS Altitude Ref
        Tag(0x0016, 0x0076),  # GPS Altitude
        Tag(0x0016, 0x0077),  # GPS Time Stamp
        Tag(0x0016, 0x0078),  # GPS Satellites
        Tag(0x0016, 0x0079),  # GPS Status
        Tag(0x0016, 0x007A),  # GPS Measure Mode
        Tag(0x0016, 0x007B),  # GPS DOP
        Tag(0x0016, 0x007C),  # GPS Speed Ref
        Tag(0x0016, 0x007D),  # GPS Speed
        Tag(0x0016, 0x007E),  # GPS Track Ref
        Tag(0x0016, 0x007F),  # GPS Track
        Tag(0x0016, 0x0080),  # GPS Img Direction Ref
        Tag(0x0016, 0x0081),  # GPS Img Direction
        Tag(0x0016, 0x0082),  # GPS Map Datum
        Tag(0x0016, 0x0083),  # GPS Dest Latitude Ref
        Tag(0x0016, 0x0084),  # GPS Dest Latitude
        Tag(0x0016, 0x0085),  # GPS Dest Longitude Ref
        Tag(0x0016, 0x0086),  # GPS Dest Longitude
        Tag(0x0016, 0x0087),  # GPS Dest Bearing Ref
        Tag(0x0016, 0x0088),  # GPS Dest Bearing
        Tag(0x0016, 0x0089),  # GPS Dest Distance Ref
        Tag(0x0016, 0x008A),  # GPS Dest Distance
        Tag(0x0016, 0x008B),  # GPS Processing Method
        Tag(0x0016, 0x008C),  # GPS Area Information
        Tag(0x0016, 0x008E),  # GPS Differential
        Tag(0x0018, 0x1009),  # Unique Device Identifier
        Tag(0x0018, 0x100A),  # UDI Sequence
        Tag(0x0018, 0x5011),  # Transducer Identification Sequence
        Tag(0x0018, 0x9185),  # Respiratory Motion Compensation Technique Description
        Tag(0x0018, 0x9373),  # X-Ray Detector Label
        Tag(0x0018, 0x937B),  # Multi-energy Acquisition Description
        Tag(0x0018, 0x937F),  # Decomposition Description
        Tag(0x0018, 0x9937),  # Requested Series Description
        Tag(0x0020, 0x0027),  # Pyramid Label
        Tag(0x0032, 0x1066),  # Reason for Visit
        Tag(0x0032, 0x1067),  # Reason for Visit Code Sequence
        Tag(0x0038, 0x0014),  # Issuer of Admission ID Sequence
        Tag(0x0038, 0x0064),  # Issuer of Service Episode ID Sequence
        Tag(0x003A, 0x0329),  # Waveform Filter Description
        Tag(0x003A, 0x032B),  # Filter Lookup Table Description
        Tag(0x0040, 0x0009),  # Scheduled Procedure Step ID
        Tag(0x0040, 0x0310),  # Comments on Radiation Dose
        Tag(0x0040, 0x050A),  # Specimen Accession Number
        Tag(0x0040, 0x051A),  # Container Description
        Tag(0x0040, 0x0600),  # Specimen Short Description
        Tag(0x0040, 0x0602),  # Specimen Detailed Description
        Tag(0x0040, 0x06FA),  # Slide Identifier
        Tag(0x0040, 0x1002),  # Reason for the Requested Procedure
        Tag(0x0040, 0x100A),  # Reason for Requested Procedure Code Sequence
        Tag(0x0050, 0x001B),  # Container Component ID
        Tag(0x0050, 0x0020),  # Device Description
        Tag(0x0050, 0x0021),  # Long Device Description
        Tag(0x006A, 0x0006),  # Annotation Group Description
        Tag(0x0074, 0x1234),  # Receiving AE
        Tag(0x0074, 0x1236),  # Requesting AE
        Tag(0x0400, 0x0310),  # Certified Timestamp
        Tag(0x0400, 0x0551),  # Nonconforming Modified Attributes Sequence
        Tag(0x0400, 0x0552),  # Nonconforming Data Element Value
        Tag(0x2100, 0x0070),  # Originator
        Tag(0x3002, 0x0121),  # Position Acquisition Template Name
        Tag(0x3002, 0x0123),  # Position Acquisition Template Description
        Tag(0x3006, 0x0004),  # Structure Set Name
        Tag(0x3006, 0x0006),  # Structure Set Description
        Tag(0x3006, 0x0028),  # ROI Description
        Tag(0x3006, 0x0038),  # ROI Generation Description
        Tag(0x3006, 0x004D),  # ROI Creator Sequence
        Tag(0x3006, 0x004E),  # ROI Interpreter Sequence
        Tag(0x3006, 0x0085),  # ROI Observation Label
        Tag(0x3006, 0x0088),  # ROI Observation Description
        Tag(0x300A, 0x0003),  # RT Plan Name
        Tag(0x300A, 0x0004),  # RT Plan Description
        Tag(0x300A, 0x000B),  # Treatment Sites
        Tag(0x300A, 0x000E),  # Prescription Description
        Tag(0x300A, 0x0016),  # Dose Reference Description
        Tag(0x300A, 0x0072),  # Fraction Group Description
        Tag(0x300A, 0x00C3),  # Beam Description
        Tag(0x300A, 0x00DD),  # Bolus Description
        Tag(0x300A, 0x0196),  # Fixation Device Description
        Tag(0x300A, 0x01A6),  # Shielding Device Description
        Tag(0x300A, 0x01B2),  # Setup Technique Description
        Tag(0x300A, 0x0216),  # Source Manufacturer
        Tag(0x300A, 0x02EB),  # Compensator Description
        Tag(0x300A, 0x0676),  # Equipment Frame of Reference Description
        Tag(0x300A, 0x078E),  # Patient Treatment Preparation Procedure Parameter Description
        Tag(0x300A, 0x0792),  # Patient Treatment Preparation Method Description
        Tag(0x300A, 0x0794),  # Patient Setup Photo Description
        Tag(0x300A, 0x079A),  # Displacement Reference Label
        Tag(0x3010, 0x0036),  # Entity Name
        Tag(0x3010, 0x0037),  # Entity Description
        Tag(0x3010, 0x0061),  # Prior Treatment Dose Description
        Tag(0x4008, 0x0040),  # Results ID
        Tag(0x4008, 0x0200),  # Interpretation ID
        # PS3.15 2026c Basic Profile X additions (post-2024b).
        Tag(0x0008, 0x1301),  # Principal Diagnosis Code Sequence
        Tag(0x0008, 0x1302),  # Primary Diagnosis Code Sequence
        Tag(0x0008, 0x1303),  # Secondary Diagnoses Code Sequence
        Tag(0x0008, 0x1304),  # Histological Diagnoses Code Sequence
        Tag(0x0010, 0x0011),  # Person Names to Use Sequence
        Tag(0x0010, 0x0012),  # Name to Use
        Tag(0x0010, 0x0013),  # Name to Use Comment
        Tag(0x0010, 0x0014),  # Third Person Pronouns Sequence
        Tag(0x0010, 0x0015),  # Pronoun Code Sequence
        Tag(0x0010, 0x0016),  # Pronoun Comment
        Tag(0x0010, 0x0041),  # Gender Identity Sequence
        Tag(0x0010, 0x0042),  # Sex Parameters for Clinical Use Category Comment
        Tag(0x0010, 0x0043),  # Sex Parameters for Clinical Use Category Sequence
        Tag(0x0010, 0x0044),  # Gender Identity Code Sequence
        Tag(0x0010, 0x0045),  # Gender Identity Comment
        Tag(0x0010, 0x0046),  # Sex Parameters for Clinical Use Category Code Sequence
        Tag(0x0010, 0x0047),  # Sex Parameters for Clinical Use Category Reference
        Tag(0x0010, 0x2161),  # Ethnic Group Code Sequence
        Tag(0x0010, 0x2162),  # Ethnic Groups
        Tag(0x0018, 0x1010),  # Secondary Capture Device ID
        Tag(0x0018, 0x1011),  # Hardcopy Creation Device ID
        Tag(0x003A, 0x0020),  # Multiplex Group Label
        Tag(0x003A, 0x0203),  # Channel Label
        Tag(0x003A, 0x020C),  # Channel Derivation Description
        Tag(0x0040, 0x0556),  # Acquisition Context Description
        Tag(0x0040, 0xA034),  # Effective Start DateTime
        Tag(0x0040, 0xA035),  # Effective Stop DateTime
        Tag(0x0040, 0xB034),  # Annotation DateTime
        Tag(0x0040, 0xB036),  # Segment Definition DateTime
        Tag(0x0040, 0xB03B),  # Montage Name
        Tag(0x0040, 0xB03F),  # Montage Channel Label
        Tag(0x0040, 0xE012),  # Display URI
    }
)

# 37 UID tags re-hashed to deterministic replacement UIDs.
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
        Tag(0x0008, 0x3010),  # IrradiationEventUID (std U: hash and retain reference)
        Tag(0x300A, 0x0054),  # TableTopPositionAlignmentUID (2026c, std U)
    }
)

# 89 date/datetime tags shifted by the jitter amount, each only when present.
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
        Tag(0x0070, 0x0082),  # PresentationCreationDate
        Tag(0x3006, 0x0008),  # StructureSetDate
        # PS3.15 Basic Profile date/datetime attributes shifted by the jitter.
        Tag(0x0012, 0x0086),  # Ethics Committee Approval Effectiveness Start Date
        Tag(0x0012, 0x0087),  # Ethics Committee Approval Effectiveness End Date
        Tag(0x0014, 0x407E),  # Calibration Date
        Tag(0x0016, 0x008D),  # GPS Date Stamp
        Tag(0x0018, 0x1202),  # DateTime of Last Calibration
        Tag(0x0018, 0x1203),  # Calibration DateTime
        Tag(0x0018, 0x1204),  # Date of Manufacture
        Tag(0x0018, 0x1205),  # Date of Installation
        Tag(0x0018, 0x9369),  # Source Start DateTime
        Tag(0x0018, 0x936A),  # Source End DateTime
        Tag(0x0018, 0x9623),  # Functional Sync Pulse
        Tag(0x0018, 0x9701),  # Decay Correction DateTime
        Tag(0x0018, 0x9804),  # Exclusion Start DateTime
        Tag(0x0018, 0x9919),  # Instruction Performed DateTime
        Tag(0x0018, 0xA002),  # Contribution DateTime
        Tag(0x0020, 0x3403),  # Modified Image Date
        Tag(0x0038, 0x0030),  # Discharge Date
        Tag(0x003A, 0x0314),  # Impedance Measurement DateTime
        Tag(0x0040, 0xA023),  # Findings Group Recording Date (Trial)
        Tag(0x0040, 0xA033),  # Observation Start DateTime
        Tag(0x0040, 0xA082),  # Participation DateTime
        Tag(0x0040, 0xA110),  # Date of Document or Verbal Transaction (Trial)
        Tag(0x0040, 0xDB06),  # Template Version
        Tag(0x0040, 0xDB07),  # Template Local Version
        Tag(0x0040, 0xE004),  # HL7 Document Effective Time
        Tag(0x0044, 0x0004),  # Approval Status DateTime
        Tag(0x0044, 0x000B),  # Product Expiration DateTime
        Tag(0x0044, 0x0010),  # Substance Administration DateTime
        Tag(0x0044, 0x0104),  # Assertion DateTime
        Tag(0x0044, 0x0105),  # Assertion Expiration DateTime
        Tag(0x0068, 0x6226),  # Effective DateTime
        Tag(0x0068, 0x6270),  # Information Issue DateTime
        Tag(0x0072, 0x000A),  # Hanging Protocol Creation DateTime
        Tag(0x0072, 0x0061),  # Selector DA Value
        Tag(0x0072, 0x0063),  # Selector DT Value
        Tag(0x0100, 0x0420),  # SOP Authorization DateTime
        Tag(0x0400, 0x0105),  # Digital Signature DateTime
        Tag(0x0400, 0x0562),  # Attribute Modification DateTime
        Tag(0x2100, 0x0040),  # Creation Date
        Tag(0x3006, 0x002D),  # ROI DateTime
        Tag(0x3006, 0x002E),  # ROI Observation DateTime
        Tag(0x3008, 0x0024),  # Treatment Control Point Date
        Tag(0x3008, 0x0054),  # First Treatment Date
        Tag(0x3008, 0x0056),  # Most Recent Treatment Date
        Tag(0x3008, 0x0162),  # Safe Position Exit Date
        Tag(0x3008, 0x0166),  # Safe Position Return Date
        Tag(0x3008, 0x0250),  # Treatment Date
        Tag(0x300A, 0x0006),  # RT Plan Date
        Tag(0x300A, 0x022C),  # Source Strength Reference Date
        Tag(0x300A, 0x0736),  # Treatment Tolerance Violation DateTime
        Tag(0x300A, 0x073A),  # Recorded RT Control Point DateTime
        Tag(0x300A, 0x0741),  # Interlock DateTime
        Tag(0x300A, 0x0760),  # Override DateTime
        Tag(0x300C, 0x0127),  # Beam Hold Transition DateTime
        Tag(0x300E, 0x0004),  # Review Date
        Tag(0x3010, 0x004C),  # Intended Phase Start Date
        Tag(0x3010, 0x004D),  # Intended Phase End Date
        Tag(0x4008, 0x0100),  # Interpretation Recorded Date
        Tag(0x4008, 0x0108),  # Interpretation Transcription Date
        Tag(0x4008, 0x0112),  # Interpretation Approval Date
    }
)

# 74 tags preserved unchanged during de-identification. Membership in a
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
        Tag(0x0040, 0x0003),  # SPSStartTime
        Tag(0x0040, 0x0005),  # SPSEndTime
        Tag(0x0040, 0x0245),  # PPSStartTime
        Tag(0x0040, 0x0251),  # PPSEndTime
        Tag(0x0040, 0xA122),  # Time
        Tag(0x0040, 0xA193),  # TrialObservationTime
        Tag(0x0054, 0x0070),  # TimeSlotVector
        Tag(0x0054, 0x0100),  # TimeSliceVector
        Tag(0x0054, 0x1300),  # FrameReferenceTime
        Tag(0x0070, 0x0083),  # PresentationCreationTime
        # PS3.15 Basic Profile time-of-day attributes retained (day granularity).
        Tag(0x0014, 0x407C),  # Calibration Time
        Tag(0x0018, 0x1014),  # Time of Secondary Capture
        Tag(0x0018, 0x700E),  # Time of Last Detector Calibration
        Tag(0x0020, 0x3405),  # Modified Image Time
        Tag(0x0038, 0x0032),  # Discharge Time
        Tag(0x0040, 0x2005),  # Issue Time of Imaging Service Request
        Tag(0x0040, 0xA024),  # Findings Group Recording Time (Trial)
        Tag(0x0040, 0xA112),  # Time of Document Creation or Verbal Transaction (Trial)
        Tag(0x0072, 0x006B),  # Selector TM Value
        Tag(0x2100, 0x0050),  # Creation Time
        Tag(0x3006, 0x0009),  # Structure Set Time
        Tag(0x3008, 0x0025),  # Treatment Control Point Time
        Tag(0x3008, 0x0164),  # Safe Position Exit Time
        Tag(0x3008, 0x0168),  # Safe Position Return Time
        Tag(0x3008, 0x0251),  # Treatment Time
        Tag(0x300A, 0x0007),  # RT Plan Time
        Tag(0x300A, 0x022E),  # Source Strength Reference Time
        Tag(0x300E, 0x0005),  # Review Time
        Tag(0x3010, 0x0085),  # Intended Fraction Start Time
        Tag(0x4008, 0x0101),  # Interpretation Recorded Time
        Tag(0x4008, 0x0109),  # Interpretation Transcription Time
        Tag(0x4008, 0x0113),  # Interpretation Approval Time
    }
)

# 40 tags emptied (set to a zero-length value) during de-identification.
# Present elements are set to a zero-length value; absent elements are not
# created.
EMPTY_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0090),  # ReferringPhysicianName
        Tag(0x0018, 0x1065),  # FrameTimeVector
        Tag(0x0020, 0x0010),  # StudyID
        Tag(0x0040, 0x0550),  # SpecimenSeq
        Tag(0x0040, 0x0551),  # SpecimenIdentifier
        Tag(0x0040, 0x1003),  # RequestedProcedurePriority
        Tag(0x0040, 0x1101),  # PersonIdentificationCodeSequence
        Tag(0x0040, 0x2016),  # PlacerOrderNumber
        Tag(0x0040, 0x2017),  # FillerOrderNumber
        Tag(0x0040, 0xA073),  # VerifyingObserverSeq
        Tag(0x0040, 0xA088),  # VerifyingObserverIdentificationCodeSeq
        Tag(0x0040, 0xA123),  # PersonName
        Tag(0x0070, 0x0084),  # ContentCreatorsName
        # PS3.15 Basic Profile Z attributes emptied when present. AccessionNumber
        # (0008,0050), Patient's Name (0010,0010), and Patient's Birth Date
        # (0010,0030) are also Z, but the default profile de-identifies them by
        # hashing/jitter, so they are not listed here.
        Tag(0x0012, 0x0021),  # Clinical Trial Protocol Name
        Tag(0x0012, 0x0030),  # Clinical Trial Site ID
        Tag(0x0012, 0x0031),  # Clinical Trial Site Name
        Tag(0x0012, 0x0050),  # Clinical Trial Time Point ID
        Tag(0x0012, 0x0060),  # Clinical Trial Coordinating Center Name
        Tag(0x0040, 0x0513),  # Issuer of the Container Identifier Sequence
        Tag(0x0040, 0x0562),  # Issuer of the Specimen Identifier Sequence
        Tag(0x0040, 0x0610),  # Specimen Preparation Sequence
        Tag(0x0400, 0x0564),  # Source of Previous Values
        Tag(0x2200, 0x0002),  # Label Text
        Tag(0x2200, 0x0005),  # Barcode Value
        Tag(0x3006, 0x0026),  # ROI Name
        Tag(0x3006, 0x00A6),  # ROI Interpreter
        Tag(0x300A, 0x00B2),  # Treatment Machine Name
        Tag(0x300A, 0x0611),  # RT Accessory Holder Slot ID
        Tag(0x300A, 0x0615),  # RT Accessory Device Slot ID
        Tag(0x300A, 0x067D),  # Radiation Generation Mode Description
        Tag(0x3010, 0x000F),  # Conceptual Volume Combination Description
        Tag(0x3010, 0x0017),  # Conceptual Volume Description
        Tag(0x3010, 0x001B),  # Device Alternate Identifier
        Tag(0x3010, 0x0043),  # Manufacturer's Device Identifier
        Tag(0x3010, 0x005A),  # RT Physician Intent Narrative
        Tag(0x3010, 0x005C),  # Reason for Superseding
        Tag(0x3010, 0x007A),  # Treatment Technique Notes
        Tag(0x3010, 0x007B),  # Prescription Notes
        Tag(0x3010, 0x007F),  # Fractionation Notes
        Tag(0x3010, 0x0081),  # Prescription Notes Sequence
    }
)

# PS3.15 Basic Profile D (dummy) attributes replaced with a VR-valid non-empty
# value when present, via dummy_for_vr(). Graphic Annotation Sequence (0070,0001)
# is intentionally excluded: the Clean Graphics handling recurses into it and
# redacts nested text rather than clearing the sequence.
DUMMY_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0018, 0x11BB),  # Acquisition Field Of View Label
        Tag(0x0018, 0x9367),  # X-Ray Source ID
        Tag(0x0018, 0x9371),  # X-Ray Detector ID
        Tag(0x0034, 0x0001),  # Flow Identifier Sequence
        Tag(0x0034, 0x0002),  # Flow Identifier
        Tag(0x0034, 0x0005),  # Source Identifier
        Tag(0x0034, 0x0007),  # Frame Origin Timestamp
        Tag(0x0040, 0xB020),  # Waveform Annotation Sequence (2026c)
        Tag(0x0042, 0x0011),  # Encapsulated Document
        Tag(0x006A, 0x0005),  # Annotation Group Label
        Tag(0x0072, 0x005E),  # Selector AE Value
        Tag(0x0072, 0x005F),  # Selector AS Value
        Tag(0x0072, 0x0065),  # Selector OB Value
        Tag(0x0072, 0x0066),  # Selector LO Value
        Tag(0x0072, 0x0068),  # Selector LT Value
        Tag(0x0072, 0x006A),  # Selector PN Value
        Tag(0x0072, 0x006C),  # Selector SH Value
        Tag(0x0072, 0x006D),  # Selector UN Value
        Tag(0x0072, 0x006E),  # Selector ST Value
        Tag(0x0072, 0x0070),  # Selector UT Value
        Tag(0x0072, 0x0071),  # Selector UR Value
        Tag(0x0400, 0x0115),  # Certificate of Signer
        Tag(0x0400, 0x0563),  # Modifying System
        Tag(0x0400, 0x0565),  # Reason for the Attribute Modification
        Tag(0x2100, 0x0140),  # Destination AE
        Tag(0x3006, 0x0002),  # Structure Set Label
        Tag(0x300A, 0x0002),  # RT Plan Label
        Tag(0x300A, 0x0608),  # Treatment Position Group Label
        Tag(0x300A, 0x0619),  # Radiation Dose Identification Label
        Tag(0x300A, 0x0623),  # Radiation Dose In-Vivo Measurement Label
        Tag(0x300A, 0x062A),  # RT Tolerance Set Label
        Tag(0x300A, 0x067C),  # Radiation Generation Mode Label
        Tag(0x300A, 0x0734),  # Treatment Tolerance Violation Description
        Tag(0x300A, 0x0742),  # Interlock Description
        Tag(0x300A, 0x0783),  # Interlock Origin Description
        Tag(0x3010, 0x002D),  # Device Label
        Tag(0x3010, 0x0033),  # User Content Label
        Tag(0x3010, 0x0034),  # User Content Long Label
        Tag(0x3010, 0x0035),  # Entity Label
        Tag(0x3010, 0x0038),  # Entity Long Label
        Tag(0x3010, 0x0054),  # RT Prescription Label
        Tag(0x3010, 0x0056),  # RT Treatment Approach Label
        Tag(0x3010, 0x0077),  # Treatment Site
    }
)


def redact_description(field_name: str, allowlist_csv: str, preserve_dates: bool) -> TagAction:
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


def redact_free_text(allowlist_csv: str, preserve_dates: bool) -> TagAction:
    """Return an action that redacts a free-text element against the allowlist.

    Present-only: a missing element is left absent. Raw bytes from an implicit-VR
    (UN/OB) element are decoded and the element VR is set to its dictionary VR so
    Phase 5 does not re-decode it, making redaction independent of encoding.
    """
    redactor = get_text_redactor(allowlist_csv, preserve_dates)

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag not in ds:
            return
        elem = ds[tag]
        value = elem.value
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="replace").strip().rstrip("\x00")
            try:
                elem.VR = dictionary_VR(tag)
            except KeyError:
                pass
        if not value:
            return
        elem.value = cast(str, redactor.redact_text(text=str(value), track_redacted=False))

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
    rules[Tag(0x0028, 0x0303)] = set_value(  # LongitudinalTemporalInformationModified
        "MODIFIED", create_if_missing=True
    )
    rules[Tag(0x0010, 0x1010)] = cap_age(89, "090Y")  # PatientAge
    rules[Tag(0x0040, 0xA075)] = remove_action  # VerifyingObserverName

    # Dummy-value attributes (PS3.15 Table E.1-1 action code D): replaced with a
    # fixed, VR-valid non-empty value when present. create_if_missing is left at
    # its default (False), since D applies only to existing elements.
    rules[Tag(0x0012, 0x0010)] = set_value("REMOVED")  # ClinicalTrialSponsorName (LO)
    rules[Tag(0x0012, 0x0081)] = set_value("REMOVED")  # ClinicalTrialProtocolEthicsCommitteeName (LO)
    # ContextGroupVersion/LocalVersion are code-system version stamps, not patient
    # events, so a fixed dummy DT is used rather than the patient-scoped jitter.
    rules[Tag(0x0008, 0x0106)] = set_value("20000101000000")  # ContextGroupVersion (DT)
    rules[Tag(0x0008, 0x0107)] = set_value("20000101000000")  # ContextGroupLocalVersion (DT)

    # Sequences absent from the removal set above (Radiopharmaceutical Information
    # (0054,0016), Referenced Series/Image/Instance) are retained. The engine
    # recurses into every sequence and hashes nested UIDs (RefSOPInstanceUID)
    # while keeping the class UID, preserving cross-object references with hashed
    # identifiers.
    return rules


def default_profile(
    settings: ProfileSettings | None = None,
    *,
    deid_method: str = "DICOM-PS3.15E-Basic",
    preserve_dates: bool = False,
) -> DeidProfile:
    """Construct a full PS3.15E de-identification profile.

    The returned profile is a patient-invariant policy object. Per-patient
    identity values (PatientID, AccessionNumber, StudyID, PatientName, the
    free-text description overrides, and the date jitter) are supplied at apply
    time via :class:`DeidParameters`.

    When a caller supplies no PatientID, PatientName, or AccessionNumber, the
    original element value is hashed with ``settings.hash_salt`` and the study
    identifier; PatientName reuses the PatientID hash. A fail-safe placeholder is
    written only when there is no value to hash.

    The free-text description fields accept a per-patient value that takes
    precedence; when it is ``None`` the engine redacts the corresponding element
    from the dataset at apply time using ``settings.allowlist_csv``.
    ``preserve_dates`` selects a date-preserving redactor for the free-text
    fields and does not alter the profile's date-jitter behavior.
    """
    settings = settings or ProfileSettings()
    uid_action = hash_uid(settings.uid_root, use_study_salt=True)
    shift = if_exists(jitter_date())

    rules = _build_constant_rules()
    rules.update(dict.fromkeys(UID_TAGS, uid_action))
    rules.update(dict.fromkeys(DATE_TAGS, shift))
    rules.update(dict.fromkeys(DUMMY_TAGS, dummy_for_vr(settings.uid_root, use_study_salt=True)))

    # PatientName runs before the PatientID rule so it hashes the original
    # PatientID element, yielding the same hash the PatientID rule then writes.
    rules[Tag(0x0010, 0x0010)] = hash_identifier_param(  # PatientName
        "patient_name", salt=settings.hash_salt, fallback_field="patient_id", source_tag=Tag(0x0010, 0x0020)
    )
    rules[Tag(0x0010, 0x0020)] = hash_identifier_param("patient_id", salt=settings.hash_salt)  # PatientID
    rules[Tag(0x0008, 0x0050)] = hash_identifier_param("accession_number", salt=settings.hash_salt)  # AccessionNumber
    rules[Tag(0x0008, 0x103E)] = redact_description(  # SeriesDescription
        "series_description", settings.allowlist_csv, preserve_dates
    )
    rules[Tag(0x0008, 0x1030)] = redact_description(  # StudyDescription
        "study_description", settings.allowlist_csv, preserve_dates
    )
    rules[Tag(0x0018, 0x1030)] = redact_description(  # ProtocolName
        "protocol_name", settings.allowlist_csv, preserve_dates
    )

    # GSPS 2D annotation text
    redact = redact_free_text(settings.allowlist_csv, preserve_dates)
    rules[Tag(0x0070, 0x0006)] = redact  # UnformattedTextValue (ST)
    rules[Tag(0x0070, 0x0289)] = redact  # TickLabel (SH)
    rules[Tag(0x0040, 0xA160)] = redact  # TextValue (UT), KO/SR content free text
    rules[Tag(0x0062, 0x0020)] = hash_value_identifier(salt=settings.hash_salt)  # TrackingID (UT)

    # Dummy-value identifiers (PS3.15 Table E.1-1 action code D) that may recur
    # across a subject's instances: hashed rather than set to a constant, so
    # distinct subjects and containers stay distinguishable while the original
    # value is removed. The closure is stateless and shared across these tags.
    subject_hash = hash_value_identifier(salt=settings.hash_salt)
    rules[Tag(0x0012, 0x0040)] = subject_hash  # ClinicalTrialSubjectID (LO)
    rules[Tag(0x0012, 0x0042)] = subject_hash  # ClinicalTrialSubjectReadingID (LO)
    rules[Tag(0x0040, 0x0512)] = subject_hash  # ContainerIdentifier (LO)

    # Presentation State content identification (may embed dates and operator identifiers).
    # The text redactor preserves numeric tokens (measurements), so it cannot strip an
    # operator number from these fields; the standard actions are applied instead.
    rules[Tag(0x0070, 0x0080)] = set_value("DEIDENTIFIED")  # ContentLabel (CS), Type 1 -- dummy value
    rules[Tag(0x0070, 0x0081)] = empty()  # ContentDescription (LO), Type 2

    # Mandatory evidence attributes -- created if missing and then set here
    rules[Tag(0x0012, 0x0020)] = set_param(  # ClinicalTrialProtocolID
        "study_id", default=DEFAULT_STUDY_ID, create_if_missing=True
    )
    rules[Tag(0x0012, 0x0063)] = append_value(deid_method, create_if_missing=True)  # DeIdentificationMethod

    return DeidProfile(
        name="DICOM-PS3.15E-Basic",
        rules=rules,
        keep_groups=frozenset(),
        remove_private=True,
        remove_curves=True,
        remove_overlays=True,
        modifies_dates=True,
        allowlist_csv=settings.allowlist_csv,
        hash_salt=settings.hash_salt,
        uid_root=settings.uid_root,
        uid_use_study_salt=True,
        deid_options=frozenset({"113104", "113105", "113108"}),
    )
