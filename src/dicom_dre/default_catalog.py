"""Default device catalog data for DICOM filtering and pixel scrubbing.

Each device() entry combines a filter decision (allow/deny) with the pixel
scrub regions to blank for that device. Exclusion rules define the deny-list.
"""

from __future__ import annotations

from dicom_dre.catalog import DeviceCatalog
from dicom_dre.catalog import DeviceRule
from dicom_dre.catalog import ExclusionRule
from dicom_dre.catalog import deny_modalities
from dicom_dre.catalog import deny_when
from dicom_dre.catalog import device
from dicom_dre.catalog import variant


# Helper: SOP class prefixes used for US devices
_US_SOP_SINGLE = "1.2.840.10008.5.1.4.1.1.6"
_US_SOP_MULTI = "1.2.840.10008.5.1.4.1.1.3"
_US_SOP_SC = "1.2.840.10008.5.1.4.1.1.7"


# Device rules — allow-list

_cr_dx_devices: list[DeviceRule] = [
    # 1. KONICA 0402 CR -- SCRUBBED
    device(
        "KONICA 0402 CR",
        "allow",
        manufacturer="KONICA",
        modality="^CR",
        manufacturer_model_name="0402",
        variants=[
            variant(software_versions="^6.", rows=2446, cols=2446, scrub=[(0, 2308, 2446, 137)]),
            variant(software_versions="^2.", rows=2010, cols=2446, scrub=[(0, 0, 2446, 115)]),
        ],
    ),
    # 2. MedicaTechUSA KrystalRad 660 -- SCRUBBED
    device(
        "MedicaTechUSA KrystalRad 660",
        "allow",
        manufacturer="Medicatechusa",
        modality=["^CR", "^DX"],
        manufacturer_model_name="^KrystalRad 660",
        software_versions="^1.",
        scrub=[(0, 0, 10000, 70)],
    ),
    # 3. CANON/SHIMADZU AXIOM / CXDI -- SCRUBBED
    # Canon AXIOM V6 uses a different scrub height (115) than CXDI (104) per rule REG-XR02.
    device(
        "Canon AXIOM V6 CR",
        "allow",
        manufacturer="Canon",
        modality=["^CR", "^DX"],
        manufacturer_model_name="^AXIOM",
        software_versions="^V6",
        scrub=[(0, 0, 10000, 115)],
    ),
    device(
        "Shimadzu CXDI CR",
        "allow",
        manufacturer="^Shimadzu",
        modality=["^CR", "^DX"],
        manufacturer_model_name="^CXDI",
        software_versions="^2.",
        scrub=[(0, 0, 10000, 90)],
    ),
    device(
        "Canon/Shimadzu AXIOM/CXDI CR",
        "allow",
        manufacturer=["Shimadzu", "Canon"],
        modality=["^CR", "^DX"],
        manufacturer_model_name=["^AXIOM", "^CXDI"],
        software_versions=["^V6", "^V4", "^2."],
        scrub=[(0, 0, 10000, 104)],
    ),
    # 4. Cuattro CloudDR -- SCRUBBED
    device(
        "Cuattro CloudDR",
        "allow",
        manufacturer="^Cuattro",
        modality="^DX",
        manufacturer_model_name="^CloudDR",
        software_versions="^3.",
        rows=3072,
        cols=3072,
        scrub=[(2500, 0, 572, 400)],
    ),
    # 5. Medlink Imaging AltoDR -- SCRUBBED
    device(
        "Medlink Imaging AltoDR",
        "allow",
        manufacturer="^Medlink Imaging",
        modality="^DX",
        manufacturer_model_name="^AltoDR",
        software_versions="^1.",
        rows=2922,
        cols=1936,
        scrub=[(0, 0, 1936, 50)],
    ),
]


_ct_pet_devices: list[DeviceRule] = [
    # 6. GE CT+PET Discovery -- SCRUBBED
    device(
        "GE CT+PET Discovery",
        "allow",
        manufacturer=["^GE MEDICAL", "^GEMS"],
        modality=["=PT", "=OT", "=CT"],
        manufacturer_model_name="^Discovery",
        secondary_capture_device_manufacturer_model_name=["^Volume Viewer", "^Xeleris 4"],
        software_versions=["^5", "^4", "^pet_columbia"],
        variants=[
            variant(
                rows=512, cols=512, scrub=[(0, 0, 500, 80), (256, 0, 256, 22), (300, 22, 212, 80), (10, 478, 100, 10)]
            ),
            variant(
                rows=512, cols=256, scrub=[(0, 0, 500, 80), (256, 0, 256, 22), (300, 22, 212, 80), (10, 478, 100, 10)]
            ),
            variant(rows=256, cols=256, scrub=[(0, 0, 500, 80)]),
            variant(rows=1024, cols=1024, scrub=[(0, 0, 500, 80)]),
            variant(rows=1878, cols=835, scrub=[(0, 0, 500, 80)]),
            variant(rows=541, cols=328, scrub=[(0, 0, 500, 80)]),
        ],
    ),
    # 7. GE CT+PET SIGNA PET/MR - SIGNA_LX1.MP1
    device(
        "GE SIGNA PET/MR - MP1",
        "allow",
        manufacturer=["^GE MEDICAL", "^GEMS"],
        modality=["=PT", "=OT", "=CT"],
        manufacturer_model_name="^SIGNA PET/MR",
        secondary_capture_device_manufacturer_model_name="^Volume Viewer",
        software_versions="^SIGNA_LX1.MP1",
        rows=456,
        cols=456,
        scrub=[(0, 0, 456, 60), (300, 60, 456, 95), (0, 425, 456, 500)],
    ),
    # 8. GE CT+PET SIGNA PET/MR - SIGNA_LX1.MR30
    device(
        "GE SIGNA PET/MR - MR30",
        "allow",
        manufacturer=["^GE MEDICAL", "^GEMS"],
        modality=["=PT", "=OT", "=CT"],
        manufacturer_model_name="^SIGNA PET/MR",
        secondary_capture_device_manufacturer_model_name="^Volume Viewer",
        software_versions="SIGNA_LX1.MR30.1_R02_2332.a",
        rows=568,
        cols=568,
        scrub=[(0, 0, 568, 110)],
    ),
    # 9. GE CT REVOLUTION CT
    device(
        "GE REVOLUTION CT",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=CT",
        manufacturer_model_name="=REVOLUTION CT",
        software_versions=["=REVO_CT_22BC.50", "=REVO_CT_21B.32"],
        rows=512,
        cols=512,
    ),
    # 10. GE CT DISCOVERY CT750 HD - ORIGINAL
    device(
        "GE DISCOVERY CT750 HD",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=CT",
        manufacturer_model_name="=DISCOVERY CT750 HD",
        software_versions="=SLES_HDE.198",
        image_type="ORIGINAL",
        rows=512,
        cols=512,
    ),
    # 11. GE CT LIGHTSPEED VCT
    device(
        "GE LIGHTSPEED VCT",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=CT",
        manufacturer_model_name="=LIGHTSPEED VCT",
        secondary_capture_device_manufacturer_model_name="=VOLUME VIEWER",
        software_versions="=CORELOAD.118",
        rows=512,
        cols=512,
    ),
    # 12. MIMvista standalone
    device(
        "MIMvista standalone",
        "allow",
        manufacturer="=MIMvista Corp",
        modality="=CT",
        software_versions="=",
        rows=512,
        cols=512,
    ),
    # 13. MIMvista + Manufacturer
    device(
        "MIMvista + Manufacturer",
        "allow",
        manufacturer="/ MIM",
        modality=["=CT", "=PT"],
        image_type="DERIVED\\PRIMARY",
        software_versions="=",
    ),
    # 14. Toshiba CT AQUILION - V6.06ER011
    device(
        "Toshiba AQUILION V6.06ER011",
        "allow",
        manufacturer="=TOSHIBA",
        modality="=CT",
        manufacturer_model_name="=AQUILION",
        software_versions="=V6.06ER011",
        image_type=["DERIVED", "MPR"],
        variants=[
            variant(rows=r, cols=c)
            for r, c in [
                (512, 512),
                (520, 520),
                (528, 528),
                (552, 552),
                (560, 560),
                (568, 568),
                (592, 592),
                (600, 600),
                (616, 616),
                (632, 632),
                (640, 640),
                (656, 656),
                (664, 664),
            ]
        ],
    ),
    # 15. NEUSOFT CT - NEUVIZ 16
    device(
        "NEUSOFT NEUVIZ 16",
        "allow",
        manufacturer="/(?i)^Neusoft$/",
        modality="=CT",
        secondary_capture_device_manufacturer_model_name="/(?i)^Neuviz 16$/",
        image_type=["SECONDARY", "DERIVED", "MPR"],
        image_type_exclude="DOSE_INFO",
        variants=[
            variant(rows=r, cols=c)
            for r, c in [
                (364, 512),
                (376, 512),
                (388, 512),
                (428, 512),
                (512, 512),
            ]
        ],
    ),
    # 16. CANON MEDICAL SYSTEMS CT - AQUILION ONE / Aquilion Prime SP
    device(
        "Canon AQUILION ONE/Prime SP",
        "allow",
        manufacturer="CANON MEDICAL SYSTEMS",
        modality="=CT",
        manufacturer_model_name=["AQUILION ONE", "Aquilion Prime SP"],
        software_versions="^V10",
        image_type=["DERIVED", "PRIMARY", "MPR"],
        rows=512,
        cols=512,
    ),
    # 17. Siemens CT - Biograph 6 / Somaris/5 3D / SOMATOM Definition AS / Emotion / Sensation
    device(
        "Siemens CT Biograph/Somaris/SOMATOM/Emotion/Sensation",
        "allow",
        manufacturer="^SIEMENS",
        modality=["=CT", "=PT"],
        image_type_exclude=["PROT", "SCREEN"],
        burned_in_annotation="/^(?!YES$)/",
        manufacturer_model_name=[
            "Biograph 6",
            "Somaris/5 3D",
            "SOMATOM Definition AS",
            "^Emotion",
            "Sensation",
        ],
    ),
    # 18. Siemens SOMATOM Definition Edge / AS+ / FORCE - VB20A
    device(
        "Siemens SOMATOM Edge/AS+/FORCE VB20A",
        "allow",
        manufacturer="^SIEMENS",
        modality="=CT",
        image_type="DERIVED",
        image_type_any=["CT_SOM5 MIP", "CT_SOM5 MPR"],
        manufacturer_model_name=[
            "SOMATOM Definition Edge",
            "SOMATOM DEFINITION AS+",
            "SOMATOM FORCE",
        ],
        software_versions="SYNGO CT VB20A",
    ),
    # 19. Siemens SOMATOM DEFINITION AS+ - VA48A
    device(
        "Siemens SOMATOM AS+ VA48A",
        "allow",
        manufacturer="^SIEMENS",
        modality="=CT",
        image_type="DERIVED",
        image_type_any=["CT_SOM5 MIP", "CT_SOM5 MPR"],
        manufacturer_model_name="SOMATOM DEFINITION AS+",
        software_versions="SYNGO CT VA48A",
    ),
    # 20. Siemens SOMATOM DEFINITION FLASH - VB20A
    device(
        "Siemens SOMATOM FLASH VB20A",
        "allow",
        manufacturer="^SIEMENS",
        modality="=CT",
        image_type="DERIVED",
        image_type_any=["CT_SOM5 MIP", "CT_SOM5 MPR"],
        manufacturer_model_name="SOMATOM DEFINITION FLASH",
        software_versions="syngo CT VB20A",
        secondary_capture_device_manufacturer_model_name=["Volume Viewer", "="],
    ),
    # 21. Siemens Healthineers SYNGO.VIA.VB30A
    device(
        "Siemens Healthineers VB30A",
        "allow",
        manufacturer="^Siemens Healthineers",
        modality="=CT",
        burned_in_annotation="/^(?!YES$)/",
        image_type="DERIVED",
        image_type_any=["MPR FUSION", "MPR THICK"],
        manufacturer_model_name="SYNGO.VIA.VB30A",
    ),
    # 22. Siemens Healthineers SYNGO.VIA.VB60A
    device(
        "Siemens Healthineers VB60A",
        "allow",
        manufacturer="^Siemens Healthineers",
        modality="=CT",
        image_type=["DERIVED", "AXIAL"],
        image_type_any=["CT_SOM8 DEOC", "MPR FUSION", "MPR THICK"],
        manufacturer_model_name="SYNGO.VIA.VB60A",
        software_versions="VB60A",
    ),
    # 23. Philips PT/CT fusion - Guardian
    device(
        "Philips Guardian PT/CT",
        "allow",
        manufacturer="^Philips",
        modality="=PT",
        manufacturer_model_name="^Guardian",
        secondary_capture_device_manufacturer_model_name="^EBW",
        software_versions="^9.3.1",
        variants=[
            variant(rows=839, cols=638, scrub=[(0, 0, 638, 80)]),
            variant(rows=918, cols=453, scrub=[(0, 0, 453, 100)]),
            variant(rows=918, cols=546, scrub=[(0, 0, 546, 100)]),
            variant(rows=907, cols=638, scrub=[(0, 0, 638, 110)]),
        ],
    ),
    # 23a. GE SIGNA PET/MR Static 3D MAC -- PT, DERIVED, SECONDARY, 192x192
    device(
        "GE SIGNA PET/MR Static 3D MAC PT",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=PT",
        manufacturer_model_name="^SIGNA PET/MR",
        series_description="/(?i)^Static 3D MAC$/",
        image_type=["DERIVED", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
        rows=192,
        cols=192,
        study_description="/(?i)^PET/MR BRAIN METABOLISM$/",
    ),
]


_nm_devices: list[DeviceRule] = [
    # 24. Segami Mirage
    device(
        "Segami Mirage NM",
        "allow",
        manufacturer="=Segami",
        modality="=NM",
        manufacturer_model_name="=Mirage",
        variants=[
            variant(rows=192, cols=192),
            variant(rows=512, cols=512),
        ],
    ),
    # 25. GE MEDICAL SYSTEMS, NUCLEAR - Xeleris 4
    device(
        "GE Nuclear Xeleris 4 NM",
        "allow",
        manufacturer="^GE MEDICAL SYSTEMS, NUCLEAR",
        modality="=NM",
        secondary_capture_device_manufacturer_model_name="^Xeleris 4",
        variants=[
            variant(rows=541, cols=328, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=552, cols=547, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=540, cols=409, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=1092, cols=409, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=192, cols=128, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=536, cols=328, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
            variant(rows=339, cols=328, scrub=[(0, 0, 550, 50), (675, 505, 780, 535)]),
        ],
    ),
    # 26. GE MEDICAL SYSTEMS, NUCLEAR - Stargate_StarGuide
    device(
        "GE Nuclear Stargate_StarGuide NM",
        "allow",
        manufacturer="^GE MEDICAL SYSTEMS, NUCLEAR",
        modality="=NM",
        manufacturer_model_name="=Stargate_StarGuide",
        rows=192,
        cols=128,
    ),
    # 27. GE MEDICAL SYSTEMS, NUCLEAR - Xeleris 5
    device(
        "GE Nuclear Xeleris 5 NM",
        "allow",
        manufacturer="^GE MEDICAL SYSTEMS, NUCLEAR",
        modality="=NM",
        secondary_capture_device_manufacturer_model_name="^Xeleris 5",
        variants=[
            variant(rows=536, cols=328, scrub=[(0, 0, 330, 50)]),
            variant(rows=339, cols=328, scrub=[(0, 0, 330, 50)]),
        ],
    ),
    # 28. Neurologica CereTom dose reports
    device(
        "Neurologica CereTom",
        "allow",
        manufacturer="=Neurologica",
        modality="=CT",
        manufacturer_model_name="=CereTom",
        image_type="=ORIGINAL\\PRIMARY\\DOSE",
        rows=512,
        cols=512,
    ),
]


_mammo_devices: list[DeviceRule] = [
    # 29. Mammography composite rule
    # Each manufacturer/model pair is a separate device entry for clarity.
    device(
        "Mammography CARESTREAM CLASSIC CR",
        "allow",
        manufacturer="=CARESTREAM",
        modality="=MG",
        manufacturer_model_name="=CLASSIC CR",
        image_type_exclude=["SCREEN"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography Hologic Selenia",
        "allow",
        manufacturer="Hologic",
        modality="=MG",
        manufacturer_model_name="Selenia",
        image_type_exclude=["SCREEN"],
        burned_in_annotation="/^(?!YES$)/",
        # Hologic Selenia allows SECONDARY
    ),
    device(
        "Mammography Lorad Selenia",
        "allow",
        manufacturer="Lorad",
        modality="=MG",
        manufacturer_model_name="Selenia",
        image_type_exclude=["SCREEN"],
        burned_in_annotation="/^(?!YES$)/",
        # Lorad Selenia allows SECONDARY
    ),
    device(
        "Mammography Lorad DSM",
        "allow",
        manufacturer="Lorad",
        modality="=MG",
        manufacturer_model_name="DSM",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography GE Senographe",
        "allow",
        manufacturer="^GE",
        modality="=MG",
        manufacturer_model_name="Senographe",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography GE ADS_",
        "allow",
        manufacturer="^GE",
        modality="=MG",
        manufacturer_model_name="ADS_",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography MPTronic Senographe",
        "allow",
        manufacturer="MPTronic",
        modality="=MG",
        manufacturer_model_name="Senographe",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography FUJI Clearview CSm",
        "allow",
        manufacturer="FUJI",
        modality="=MG",
        manufacturer_model_name="Clearview CSm",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography FUJI FDR",
        "allow",
        manufacturer="FUJI",
        modality="=MG",
        manufacturer_model_name="FDR",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography Fischer SenoScan",
        "allow",
        manufacturer="Fischer",
        modality="=MG",
        manufacturer_model_name="SenoScan",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography IMS GIOTTO",
        "allow",
        manufacturer="IMS",
        modality="=MG",
        manufacturer_model_name="GIOTTO",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography KODAK ELITE CR",
        "allow",
        manufacturer="KODAK",
        modality="=MG",
        manufacturer_model_name="=ELITE CR",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography KODAK CLASSIC CR",
        "allow",
        manufacturer="KODAK",
        modality="=MG",
        manufacturer_model_name="=CLASSIC CR",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography Philips L30",
        "allow",
        manufacturer="Philips",
        modality="=MG",
        manufacturer_model_name="=L30",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography SIEMENS Mammomat",
        "allow",
        manufacturer="SIEMENS",
        modality="=MG",
        manufacturer_model_name="Mammomat",
        image_type_exclude=["SCREEN", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
    ),
    device(
        "Mammography TMSC MGU-1000D",
        "allow",
        manufacturer="TMSC",
        modality="=MG",
        manufacturer_model_name="=MGU-1000D",
        image_type_exclude=["SCREEN"],
        burned_in_annotation="/^(?!YES$)/",
        # TMSC allows SECONDARY
    ),
]


_breast_mri_devices: list[DeviceRule] = [
    # 30. GE DISCOVERY DIXON
    device(
        "GE Breast MRI DISCOVERY DIXON",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=MR",
        manufacturer_model_name="DISCOVERY",
        image_type="DERIVED\\PRIMARY\\DIXON\\WATER",
    ),
    # 30a. GE MR Ax T1 IR FSPGR - DERIVED SECONDARY, 512x512
    device(
        "GE MR Ax T1 IR FSPGR",
        "allow",
        manufacturer="=GE MEDICAL SYSTEMS",
        modality="=MR",
        manufacturer_model_name=[
            "/(?i)^SIGNA Architect$/",
            "/(?i)^SIGNA PET\\/MR$/",
            "/(?i)^SIGNA Premier$/",
            "/(?i)^DISCOVERY MR750$/",
            "/(?i)^SIGNA Explorer$/",
        ],
        series_description="Ax T1 IR FSPGR",
        image_type=["DERIVED", "SECONDARY"],
        burned_in_annotation="/^(?!YES$)/",
        rows=512,
        cols=512,
    ),
]


_us_devices: list[DeviceRule] = [
    # 31. ACUSON SEQUOIA
    device(
        "ACUSON SEQUOIA US",
        "allow",
        manufacturer="=ACUSON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        image_type_exclude=["ORIGINAL\\PRIMARY\\\\0000", "DERIVED\\SECONDARY\\\\0000"],
        manufacturer_model_name="SEQUOIA",
        variants=[
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 40)]),
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 30), (553, 30, 87, 16)]),
            variant(rows=576, cols=768, scrub=[(0, 0, 768, 40), (672, 40, 96, 16)]),
            variant(rows=456, cols=576, scrub=[(0, 0, 576, 31), (493, 31, 83, 17)]),
        ],
    ),
    # 32. ACUSON Cypress
    device(
        "ACUSON Cypress US",
        "allow",
        manufacturer="/(?i)^ACUSON$/",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        image_type_exclude=["ORIGINAL\\PRIMARY\\\\0000", "DERIVED\\SECONDARY\\\\0000"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="Cypress",
        rows=480,
        cols=640,
        scrub=[(0, 0, 640, 32), (560, 48, 80, 36)],
    ),
    # 33. Aloka Alpha series
    device(
        "Aloka Alpha/SSD-5500 US",
        "allow",
        manufacturer="Aloka",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name=[
            "SSD-ALPHA5",
            "SSD-ALPHA6",
            "SSD-ALPHA7",
            "SSD-ALPHA10",
            "SSD-5500",
        ],
        variants=[
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 56)]),
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 25)]),
            variant(rows=420, cols=608, scrub=[(0, 0, 608, 24)]),
            variant(rows=480, cols=686, scrub=[(0, 0, 686, 48)]),
        ],
    ),
    # 34. Aloka Noblus
    device(
        "Aloka Noblus US",
        "allow",
        manufacturer="Aloka",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="Noblus",
        rows=600,
        cols=800,
        scrub=[(0, 0, 800, 48)],
    ),
    # 35. Aloka ProSound F75
    device(
        "Aloka ProSound F75 US",
        "allow",
        manufacturer="Aloka",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="ProSound F75",
        variants=[
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 40)]),
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 56)]),
        ],
    ),
    # 36-38. B-K Medical
    device(
        "B-K Medical 2202 US",
        "allow",
        manufacturer=["=B-K Medical", "=BK Medical"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=2202",
        variants=[
            variant(rows=818, cols=1020, scrub=[(200, 0, 696, 56)]),
            variant(rows=480, cols=640, scrub=[(128, 0, 420, 32)]),
        ],
    ),
    device(
        "B-K Medical 1202 US",
        "allow",
        manufacturer=["=B-K Medical", "=BK Medical"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=1202",
        variants=[
            variant(rows=1072, cols=1024, scrub=[(0, 0, 1024, 147), (905, 168, 117, 730)]),
            variant(rows=780, cols=800),
        ],
    ),
    device(
        "B-K Medical 2300 US",
        "allow",
        manufacturer=["=B-K Medical", "=BK Medical"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=2300",
        variants=[
            variant(rows=1072, cols=1024, scrub=[(0, 0, 1024, 147), (905, 168, 117, 730)]),
            variant(rows=802, cols=992, scrub=[(888, 0, 104, 802)]),
        ],
    ),
    # 39. Philips US - iU22 / iE33
    device(
        "Philips iU22/iE33 US",
        "allow",
        manufacturer="Philips",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="INVALID",
        requires_ultrasound_regions=True,
        manufacturer_model_name=["=iU22", "=iE33"],
        variants=[
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 72)]),
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 56)]),
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 47)]),
        ],
    ),
    # 40. Philips US - EPIQ / Affiniti
    device(
        "Philips EPIQ/Affiniti US",
        "allow",
        manufacturer="Philips",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="INVALID",
        requires_ultrasound_regions=True,
        manufacturer_model_name=["EPIQ", "Affiniti"],
        variants=[
            variant(rows=1080, cols=1920, scrub=[(0, 0, 1920, 32)]),
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 24)]),
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 16)]),
        ],
    ),
    # 41. Philips US - CX50 / CX30 / Sparq / HD15 / ClearVue 550
    device(
        "Philips CX50/CX30/Sparq/HD15/ClearVue US",
        "allow",
        manufacturer="Philips",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="INVALID",
        requires_ultrasound_regions=True,
        manufacturer_model_name=["=CX50", "=CX30", "=Sparq", "=HD15", "=ClearVue 550"],
        rows=600,
        cols=800,
        scrub=[(0, 0, 800, 56)],
    ),
    # 42. Philips US - Lumify / VT
    device(
        "Philips Lumify/VT US",
        "allow",
        manufacturer="Philips",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="INVALID",
        requires_ultrasound_regions=True,
        manufacturer_model_name=["=Lumify", "=VT"],
        rows=768,
        cols=1024,
    ),
    # 43. Toshiba US - A500 / A300 / A400 / TUS-X200 / SSH-880CV
    device(
        "Toshiba A-series/SSH-880CV US",
        "allow",
        manufacturer="Toshiba",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name=["A500", "A300", "A400", "TUS-X200", "SSH-880CV"],
        rows=720,
        cols=960,
        scrub=[(0, 0, 960, 60)],
    ),
    # 44. Toshiba US - AI700
    device(
        "Toshiba AI700 US",
        "allow",
        manufacturer="Toshiba",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="AI700",
        rows=960,
        cols=1280,
        scrub=[(0, 0, 1280, 72)],
    ),
    # 45. Toshiba US - Aplio / Xario
    device(
        "Toshiba Aplio/Xario US",
        "allow",
        manufacturer="Toshiba",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name=["Aplio", "Xario"],
        variants=[
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 40)]),
            variant(rows=537, cols=716, scrub=[(0, 0, 716, 40)]),
        ],
    ),
    # 46. Toshiba US - Viamo
    device(
        "Toshiba Viamo US",
        "allow",
        manufacturer="Toshiba",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="Viamo",
        rows=600,
        cols=800,
        scrub=[(0, 0, 800, 56)],
    ),
    # 47. SonoSite US - Turbo / MicroMAXX / Nano / Edge II
    device(
        "SonoSite Turbo/MicroMAXX/Nano/Edge II US",
        "allow",
        manufacturer="SonoSite",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name=["Turbo", "MicroMAXX", "Nano", "Edge II"],
        rows=480,
        cols=640,
        scrub=[(0, 0, 640, 24)],
    ),
    # 47b. SonoSite US - Titan (no ultrasound regions requirement)
    device(
        "SonoSite Titan US",
        "allow",
        manufacturer="SonoSite",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="Titan",
        rows=480,
        cols=640,
        scrub=[(0, 0, 640, 24)],
    ),
    # 48. SonoSite US - X-Porte
    device(
        "SonoSite X-Porte US",
        "allow",
        manufacturer="SonoSite",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="X-Porte",
        rows=720,
        cols=960,
        scrub=[(0, 0, 960, 32)],
    ),
    # 49. Zonare US - Z_ONE / ZS3
    device(
        "Zonare Z_ONE/ZS3 US",
        "allow",
        manufacturer="Zonare",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        image_type_exclude="PATIENTINFO",
        manufacturer_model_name=["Z_ONE", "ZS3"],
        variants=[
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 40)]),
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 40)]),
        ],
    ),
    # 50. SIEMENS US
    # 50a. S1000
    # Note: some S1000 images are mis-tagged with Modality=CT; the scrub rule omits the modality check.
    device(
        "Siemens S1000 US",
        "allow",
        manufacturer="SIEMENS",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=S1000",
        rows=768,
        cols=1024,
        scrub=[(0, 0, 1024, 56)],
    ),
    # 50b. S2000
    device(
        "Siemens S2000 US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=S2000",
        variants=[
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 56)]),
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 19), (0, 19, 160, 55)]),
            variant(rows=463, cols=707),
            variant(rows=183, cols=162),
        ],
    ),
    # 50c. S3000
    device(
        "Siemens S3000 US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=S3000",
        rows=768,
        cols=1024,
        scrub=[(0, 0, 1024, 56)],
    ),
    # 50d. Antares
    device(
        "Siemens Antares US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=Antares",
        variants=[
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 56)]),
            # 600x800 scrub is restricted to single-frame SOP only
            variant(rows=600, cols=800, sop_class_uid=f"^{_US_SOP_SINGLE}", scrub=[(0, 0, 800, 19), (0, 19, 160, 55)]),
            variant(rows=600, cols=800, sop_class_uid=f"^{_US_SOP_MULTI}"),
            # 547x692 only validated for multi-frame; no scrub rule defined
            variant(rows=547, cols=692, sop_class_uid=f"^{_US_SOP_MULTI}"),
        ],
    ),
    # 50e. X150 / Acuson X300 / Acuson X700 / Acuson P500
    device(
        "Siemens X150/X300/X700/P500 US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude=["0000", "=ORIGINAL\\PRIMARY", "=DERIVED\\PRIMARY"],
        manufacturer_model_name=[
            "/(?i)^X150$/",
            "/(?i)^Acuson X300$/",
            "/(?i)^Acuson X700$/",
            "/(?i)^Acuson P500$/",
        ],
        variants=[
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 40)]),
            variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 56)]),
        ],
    ),
    # 50f. ACUSON SC2000
    device(
        "Siemens ACUSON SC2000 US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        image_type_exclude="0000",
        manufacturer_model_name="=ACUSON SC2000",
        rows=768,
        cols=1024,
        scrub=[(0, 0, 712, 40)],
    ),
    # 50g. ACUSON Freestyle
    device(
        "Siemens ACUSON Freestyle US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=ACUSON Freestyle",
        variants=[
            variant(rows=656, cols=800, scrub=[(0, 0, 800, 56)]),
            variant(rows=664, cols=800, scrub=[(0, 0, 800, 56)]),
        ],
    ),
    # 50h. ELEGRA
    device(
        "Siemens ELEGRA US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=ELEGRA",
        rows=666,
        cols=888,
        scrub=[(0, 0, 888, 48)],
    ),
    # 50i. G60 S / G50 S
    # Note: this rule requires PixelSpacing to be present to exclude screenshots.
    device(
        "Siemens G60 S/G50 S US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name=["=G60 S", "=G50 S"],
        pixel_spacing="/^.+$/",
        variants=[
            variant(rows=547, cols=692, scrub=[(0, 0, 692, 40)]),
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 42)]),
        ],
    ),
    # 50j. G40
    device(
        "Siemens G40 US",
        "allow",
        manufacturer="SIEMENS",
        modality="US",
        sop_class_uid=[
            f"^{_US_SOP_SINGLE}",
            f"^{_US_SOP_MULTI}",
            f"^{_US_SOP_SC}",
        ],
        image_type_exclude="0000",
        manufacturer_model_name="=G40",
        rows=600,
        cols=800,
        scrub=[(0, 0, 800, 40)],
    ),
    # 51. SuperSonic Imagine - Aixplorer
    device(
        "SuperSonic Aixplorer US",
        "allow",
        manufacturer="SuperSonic",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="=Aixplorer",
        variants=[
            variant(rows=1080, cols=1440, scrub=[(0, 0, 1440, 90)]),
            variant(rows=1050, cols=1400, scrub=[(0, 0, 1400, 90)]),
            variant(rows=930, cols=1240, scrub=[(0, 0, 1240, 70)]),
            variant(rows=900, cols=1200, scrub=[(0, 0, 1080, 64)]),
            variant(rows=894, cols=1192, scrub=[(0, 0, 1080, 64)]),
            variant(rows=819, cols=1092, scrub=[(0, 0, 980, 56)]),
            variant(rows=816, cols=1088, scrub=[(0, 0, 1088, 56)]),
            variant(rows=812, cols=1082, scrub=[(0, 0, 980, 56)]),
            variant(rows=810, cols=1080, scrub=[(0, 0, 1080, 70)]),
            variant(rows=788, cols=1050, scrub=[(0, 0, 1050, 70)]),
            variant(rows=782, cols=1042, scrub=[(0, 0, 1042, 56)]),
            variant(rows=776, cols=1035, scrub=[(0, 0, 900, 56)]),
            variant(rows=638, cols=851, scrub=[(0, 0, 851, 48)]),
            variant(rows=525, cols=700, scrub=[(0, 0, 700, 48)]),
        ],
    ),
    # 52. Samsung/Medison
    # 52a. RS80A
    device(
        "Samsung RS80A US",
        "allow",
        manufacturer="MEDISON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="=RS80A",
        variants=[
            variant(rows=872, cols=1280, scrub=[(0, 0, 1280, 72)]),
            variant(rows=872, cols=1152, scrub=[(0, 0, 1152, 72)]),
        ],
    ),
    # 52b. ACCUVIX
    device(
        "Samsung ACCUVIX US",
        "allow",
        manufacturer="MEDISON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="=ACCUVIX",
        rows=480,
        cols=640,
        scrub=[(0, 0, 640, 40)],
    ),
    # 52c. H60
    device(
        "Samsung H60 US",
        "allow",
        manufacturer="MEDISON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name="=H60",
        rows=720,
        cols=960,
        scrub=[(0, 0, 960, 64)],
    ),
    # 52d. Accuvix V10 / V20 / XG
    device(
        "Samsung Accuvix V10/V20/XG US",
        "allow",
        manufacturer="MEDISON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name=["=Accuvix V10", "=Accuvix V20", "=Accuvix XG"],
        rows=768,
        cols=1024,
        scrub=[(0, 0, 1024, 56)],
    ),
    # 52e. SonoAce R7 / X8
    device(
        "Samsung SonoAce R7/X8 US",
        "allow",
        manufacturer="MEDISON",
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        requires_ultrasound_regions=True,
        manufacturer_model_name=["=SonoAce R7", "=SonoAce X8"],
        rows=768,
        cols=1024,
        scrub=[(0, 0, 1024, 56)],
    ),
    # 53. GE US
    # 53a. Invenia
    device(
        "GE Invenia US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Invenia",
        rows=482,
        cols=841,
    ),
    # 53a2. Invenia ABUS 2.0 -- Automated Breast Ultrasound System
    device(
        "GE Invenia ABUS 2.0 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="/(?i)^Invenia ABUS 2\\.0$/",
        image_type=["ORIGINAL", "PRIMARY"],
        rows=546,
        cols=843,
        body_part_examined="/(?i)^BREAST$/",
    ),
    # 53b. Vivide
    device(
        "GE Vivide US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivide",
        rows=614,
        cols=820,
        scrub=[(0, 0, 568, 55)],
    ),
    # 53c. Vivid i
    device(
        "GE Vivid i US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid i",
        variants=[
            variant(rows=422, cols=636, scrub=[(0, 0, 220, 25)]),
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
        ],
    ),
    # 53d. Vivid S5
    device(
        "GE Vivid S5 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid S5",
        rows=422,
        cols=636,
        scrub=[(0, 0, 220, 25)],
    ),
    # 53e. Vivid S6
    device(
        "GE Vivid S6 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid S6",
        variants=[
            variant(rows=422, cols=636, scrub=[(0, 0, 220, 25)]),
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
        ],
    ),
    # 53f. Vivid7
    device(
        "GE Vivid7 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid7",
        variants=[
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
            variant(rows=434, cols=640),
            variant(rows=484, cols=636, scrub=[(0, 0, 584, 48)]),
        ],
    ),
    # 53g. Vivid E9
    device(
        "GE Vivid E9 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid E9",
        variants=[
            variant(rows=759, cols=1020, scrub=[(0, 0, 800, 48)]),
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
            variant(rows=484, cols=636, scrub=[(0, 0, 584, 48)]),
            variant(rows=709, cols=1020),
        ],
    ),
    # 53h. Vivid E95
    device(
        "GE Vivid E95 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid E95",
        rows=708,
        cols=1016,
        scrub=[(0, 0, 400, 56)],
    ),
    # 53i. Vivid 3
    device(
        "GE Vivid 3 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid 3",
        variants=[
            variant(rows=480, cols=640, scrub=[(0, 0, 392, 32)]),
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
        ],
    ),
    # 53j. Voluson P
    device(
        "GE Voluson P US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Voluson P",
        rows=600,
        cols=800,
        scrub=[(0, 0, 800, 56)],
    ),
    # 53k. Voluson S
    device(
        "GE Voluson S US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Voluson S",
        rows=743,
        cols=975,
        scrub=[(0, 0, 975, 72)],
    ),
    # 53l. Voluson E8
    device(
        "GE Voluson E8 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Voluson E8",
        rows=852,
        cols=1136,
        scrub=[(0, 0, 1136, 64)],
    ),
    # 53m. Vivid q
    device(
        "GE Vivid q US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=Vivid q",
        variants=[
            variant(rows=422, cols=636, scrub=[(0, 0, 220, 25)]),
            variant(rows=434, cols=636, scrub=[(0, 0, 280, 24)]),
        ],
    ),
    # 53n. LOGIQworksE9
    device(
        "GE LOGIQworksE9 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQworksE9",
        rows=434,
        cols=532,
    ),
    # 53o. LOGIQe
    device(
        "GE LOGIQe US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQe",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=590, cols=819, scrub=[(0, 0, 570, 55)]),
            variant(rows=614, cols=820, scrub=[(0, 0, 570, 55)]),
        ],
    ),
    # 53p. LOGIQi
    device(
        "GE LOGIQi US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQi",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=600, cols=800, scrub=[(0, 0, 554, 57)]),
        ],
    ),
    # 53q. LOGIQE9
    device(
        "GE LOGIQE9 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        image_type_exclude="DERIVED\\PRIMARY\\\\0000",
        manufacturer_model_name="=LOGIQE9",
        variants=[
            variant(rows=970, cols=1552, scrub=[(0, 0, 1174, 68)]),
            variant(rows=873, cols=1552, scrub=[(0, 0, 1196, 68)]),
            variant(rows=899, cols=1442, scrub=[(0, 0, 1000, 32)]),
            variant(rows=819, cols=1456, scrub=[(0, 0, 1122, 70)]),
            variant(rows=802, cols=1442, scrub=[(0, 0, 1000, 32)]),
            variant(rows=748, cols=1346, scrub=[(0, 0, 1000, 24)]),
            variant(rows=768, cols=1280, scrub=[(0, 0, 826, 92)]),
            variant(rows=720, cols=1280, scrub=[(0, 0, 968, 70)]),
            variant(rows=649, cols=1170, scrub=[(0, 0, 880, 24)]),
            variant(rows=873, cols=1164, scrub=[(0, 0, 808, 70)]),
            variant(rows=819, cols=1092, scrub=[(0, 0, 758, 68)]),
            variant(rows=802, cols=1054, scrub=[(0, 0, 700, 30)]),
            variant(rows=748, cols=982, scrub=[(0, 0, 670, 28)]),
            variant(rows=720, cols=960, scrub=[(0, 0, 666, 68)]),
            variant(rows=519, cols=936),
            variant(rows=697, cols=914),
            variant(rows=649, cols=852, scrub=[(0, 0, 595, 26)]),
            variant(rows=649, cols=850, scrub=[(0, 0, 595, 26)]),
            variant(rows=614, cols=820, scrub=[(0, 0, 568, 55)]),
            variant(rows=421, cols=760),
            variant(rows=519, cols=680),
            variant(rows=421, cols=552),
        ],
    ),
    # 53r. LOGIQ S6 (or LOGIQ7 with LOGIQ S6 software)
    device(
        "GE LOGIQ S6 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name=["=LOGIQ S6"],
        variants=[
            variant(rows=434, cols=532),
            variant(rows=768, cols=1024, scrub=[(0, 0, 712, 67)]),
        ],
    ),
    # 53s. LOGIQS7
    device(
        "GE LOGIQS7 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQS7",
        variants=[
            variant(rows=421, cols=552),
            variant(rows=649, cols=850, scrub=[(0, 0, 592, 26)]),
            variant(rows=720, cols=960, scrub=[(0, 0, 666, 68)]),
            variant(rows=720, cols=1280, scrub=[(0, 0, 968, 70)]),
        ],
    ),
    # 53t. LOGIQS8
    device(
        "GE LOGIQS8 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQS8",
        variants=[
            variant(rows=421, cols=552),
            variant(rows=600, cols=600),
            variant(rows=649, cols=850, scrub=[(0, 0, 584, 20)]),
            variant(rows=720, cols=960, scrub=[(0, 0, 666, 68)]),
            variant(rows=819, cols=1092, scrub=[(0, 0, 758, 68)]),
            variant(rows=802, cols=1054, scrub=[(0, 0, 754, 26)]),
            variant(rows=873, cols=1164, scrub=[(0, 0, 808, 70)]),
            variant(rows=649, cols=1170, scrub=[(0, 0, 880, 24)]),
            variant(rows=720, cols=1280, scrub=[(0, 0, 968, 70)]),
            variant(rows=748, cols=1346, scrub=[(0, 0, 1000, 24)]),
            variant(rows=802, cols=1442, scrub=[(0, 0, 1000, 32)]),
            variant(rows=819, cols=1456, scrub=[(0, 0, 1122, 70)]),
            variant(rows=873, cols=1552, scrub=[(0, 0, 1195, 68)]),
            variant(rows=970, cols=1552, scrub=[(0, 0, 1174, 68)]),
        ],
    ),
    # 53u. LOGIQP5
    device(
        "GE LOGIQP5 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQP5",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=614, cols=816, scrub=[(0, 0, 566, 60)]),
        ],
    ),
    # 53v. LOGIQP6
    device(
        "GE LOGIQP6 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQP6",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=614, cols=816, scrub=[(0, 0, 566, 60)]),
        ],
    ),
    # 53w. LOGIQP9
    device(
        "GE LOGIQP9 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQP9",
        variants=[
            variant(rows=856, cols=1142, scrub=[(0, 0, 794, 68)]),
            variant(rows=912, cols=1216),
        ],
    ),
    # 53x. LOGIQ 400
    device(
        "GE LOGIQ 400 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQ 400",
        rows=462,
        cols=608,
        scrub=[(0, 0, 608, 31)],
    ),
    # 53y. LOGIQ5
    device(
        "GE LOGIQ5 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQ5",
        rows=480,
        cols=640,
        scrub=[(0, 0, 444, 44)],
    ),
    # 53z. LOGIQ 700
    device(
        "GE LOGIQ 700 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQ 700",
        rows=480,
        cols=640,
        scrub=[(0, 0, 640, 41)],
    ),
    # 53aa. LOGIQ7
    device(
        "GE LOGIQ7 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQ7",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=480, cols=640, scrub=[(0, 0, 444, 44)]),
            variant(rows=768, cols=1024, scrub=[(0, 0, 712, 70)]),
        ],
    ),
    # 53ab. LOGIQ9
    device(
        "GE LOGIQ9 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQ9",
        variants=[
            variant(rows=434, cols=532),
            variant(rows=480, cols=640, scrub=[(0, 0, 444, 44)]),
            variant(rows=697, cols=854),
            variant(rows=697, cols=856),
            variant(rows=600, cols=800, scrub=[(0, 0, 605, 44)]),
            variant(rows=768, cols=1024, scrub=[(0, 0, 712, 67)]),
        ],
    ),
    # 53ac. LOGIQBook
    device(
        "GE LOGIQBook US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=LOGIQBook",
        rows=434,
        cols=532,
    ),
    # 53ad. V830
    device(
        "GE V830 US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=V830",
        variants=[
            variant(rows=480, cols=640, scrub=[(0, 0, 640, 48)]),
            variant(rows=600, cols=800, scrub=[(0, 0, 800, 56)]),
            variant(rows=650, cols=868, scrub=[(0, 0, 868, 48)]),
            variant(rows=662, cols=930, scrub=[(0, 0, 930, 64)]),
            variant(rows=720, cols=960, scrub=[(0, 0, 960, 56)]),
            variant(rows=735, cols=960, scrub=[(0, 0, 960, 72)]),
            variant(rows=735, cols=975, scrub=[(0, 0, 975, 72)]),
            variant(rows=743, cols=975, scrub=[(0, 0, 975, 72)]),
            variant(rows=682, cols=1134, scrub=[(0, 0, 1134, 56)]),
            variant(rows=852, cols=1136, scrub=[(0, 0, 1136, 64)]),
        ],
    ),
    # 53ae. EchoPAC PC
    device(
        "GE EchoPAC PC US",
        "allow",
        manufacturer=["^GE", "^G.E.", "^GEMS"],
        modality="US",
        sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
        manufacturer_model_name="=EchoPAC PC",
        variants=[
            variant(rows=434, cols=636),
            variant(rows=850, cols=1081),
        ],
    ),
]


_scrub_only_devices: list[DeviceRule] = [
    # CT Dose scrub rules -- these are scrub-only entries
    device(
        "CT Dose IEC Body Dosimetry Phantom",
        "scrub",
        code_meaning="IEC Body Dosimetry Phantom",
        scrub=[(0, 0, 512, 200)],
    ),
    device(
        "GE CT Dose Report",
        "scrub",
        modality="CT",
        manufacturer="GE MEDICAL",
        series_description="Dose Report",
        image_type_exclude="SCREEN SAVE",
        scrub=[(0, 0, 512, 110)],
    ),
    device(
        "GE DLP Dose",
        "scrub",
        manufacturer="GE MEDICAL",
        comments_on_radiation_dose="DLP",
        image_type_exclude="SCREEN SAVE",
        scrub=[(0, 0, 512, 110)],
    ),
    device(
        "GE AW Workstation",
        "scrub",
        manufacturer="GE MEDICAL",
        burned_in_annotation="YES",
        series_description="AW electronic film",
        scrub=[(0, 0, 512, 80)],
    ),
    device(
        "GE AVA Report",
        "scrub",
        manufacturer="GE MEDICAL",
        burned_in_annotation="YES",
        series_description="AVA Report",
        rows=512,
        scrub=[(0, 0, 200, 250)],
    ),
    device(
        "Volume Rendering VOLREN",
        "scrub",
        image_type="VOLREN",
        rows=512,
        cols=512,
        scrub=[(350, 0, 162, 30), (390, 80, 122, 15)],
    ),
    device(
        "GE 1024 Screen Capture",
        "scrub",
        manufacturer="GE MEDICAL",
        burned_in_annotation="YES",
        rows=1024,
        scrub=[(0, 0, 300, 150), (724, 0, 300, 150)],
    ),
    device(
        "VITREA Stent Planning",
        "scrub",
        manufacturer="VITAL Images",
        series_description=["AAA", "Report"],
        rows=1041,
        scrub=[(0, 0, 795, 150)],
    ),
    device(
        "Siemens CT Dose Secondary",
        "scrub",
        modality="CT",
        manufacturer="SIEMENS",
        image_type="SECONDARY",
        rows=860,
        scrub=[(0, 0, 1132, 60)],
    ),
    device(
        "Philips CT Dose",
        "scrub",
        manufacturer="PHILIPS",
        image_type="DOSE",
        sop_class_uid="/^(?!1.2.840.10008.5.1.4.1.1.7$)/",
        scrub=[(0, 0, 512, 135)],
    ),
    device(
        "Toshiba Aquilion One CT Dose",
        "scrub",
        modality="=CT",
        manufacturer="TOSHIBA",
        manufacturer_model_name="Aquilion ONE",
        image_type="SECONDARY",
        rows=512,
        cols=512,
        scrub=[(0, 0, 410, 240)],
    ),
    # NM scrub rules
    device(
        "Siemens NM Secondary",
        "scrub",
        modality="NM",
        manufacturer="SIEMENS",
        image_type="SECONDARY",
        rows=860,
        scrub=[(0, 0, 1132, 82), (0, 780, 1132, 80)],
    ),
    # Other scrub rules
    device(
        "ADAC NM",
        "scrub",
        manufacturer="ADAC",
        rows=832,
        cols=1024,
        sop_class_uid="/^(?!1.2.840.10008.5.1.4.1.1.7$)/",
        scrub=[(0, 0, 1024, 60), (0, 762, 1024, 80)],
    ),
    device(
        "MEDRAD Injection Profile",
        "scrub",
        series_description="MEDRAD",
        rows=1077,
        cols=750,
        scrub=[(0, 0, 750, 230)],
    ),
    # Canon CXDI additional scrub (different from CR entry)
    device(
        "Canon CXDI 2592 scrub",
        "scrub",
        manufacturer="Canon",
        manufacturer_model_name="CXDI",
        rows=2592,
        scrub=[(0, 0, 2208, 80), (0, 2512, 2208, 80)],
    ),
]


# Exclusion rules — deny-list

default_exclusions: list[ExclusionRule] = [
    # Deny 1: Unsupported modalities (substring match)
    deny_modalities(
        substring=["MG", "MA", "RF", "US", "XA"],
    ),
    # Deny 2: Unsupported modalities (exact match)
    deny_modalities(
        exact=[
            "AN",
            "AS",
            "BD",
            "BM",
            "BMA",
            "BMD",
            "CF",
            "CV",
            "DE",
            "DEXA",
            "DF",
            "DG",
            "DMA",
            "DOC",
            "EC",
            "ECG",
            "ES",
            "FILM_CT",
            "FL",
            "HC",
            "HD",
            "IO",
            "IR",
            "PN",
            "RAW",
            "REPORT",
            "REQUEST",
            "RG",
            "RTDOSE",
            "RTIMAGE",
            "RTPLAN",
            "RTSTRUCT",
            "SC",
            "SD",
            "SPL",
            "SR",
            "ST",
            "TG",
            "UNQ",
            "XD",
        ],
    ),
    # Deny 3: Encapsulated PDF
    deny_when(
        "Encapsulated PDF",
        sop_class="=1.2.840.10008.5.1.4.1.1.104.1",
    ),
    # Deny 4: the DiCOM box
    deny_when(
        "the DiCOM box",
        manufacturer_model_name="the DiCOM box",
    ),
    # Deny 5: Vidar film scanners
    deny_when(
        "Vidar film scanner (manufacturer)",
        manufacturer="vidar",
    ),
    deny_when(
        "Vidar film scanner (model)",
        manufacturer_model_name="vidar",
    ),
    # Deny 6: iCAD mammo scanners
    deny_when(
        "iCAD mammo scanner",
        manufacturer="icad",
    ),
    # Deny 7: Presentation state and SR SOP classes.
    # Admit Modality PR instances that are 2D softcopy presentation states
    # carrying a Graphic Annotation Sequence; deny volumetric/unknown PR classes
    # and admitted-class instances that carry no annotation. Admit Key Object
    # Selection (KO, .88.59) that references at least one instance; deny the rest
    # of the SR family and deny reference-free KO.
    deny_when(
        "unsupported presentation state",
        modality="=PR",
        sop_class_not=[
            "=1.2.840.10008.5.1.4.1.1.11.1",
            "=1.2.840.10008.5.1.4.1.1.11.2",
            "=1.2.840.10008.5.1.4.1.1.11.3",
            "=1.2.840.10008.5.1.4.1.1.11.4",
            "=1.2.840.10008.5.1.4.1.1.11.5",
            "=1.2.840.10008.5.1.4.1.1.11.12",
        ],
    ),
    deny_when(
        "no annotation data",
        modality="=PR",
        graphic_annotation_absent=True,
    ),
    deny_when(
        "unsupported structured report",
        sop_class="^1.2.840.10008.5.1.4.1.1.8",
        sop_class_not=["=1.2.840.10008.5.1.4.1.1.88.59"],
    ),
    deny_when(
        "no referenced instances",
        sop_class="=1.2.840.10008.5.1.4.1.1.88.59",
        referenced_instance_absent=True,
    ),
    # Deny 8: INFINITT PACS with high series number
    deny_when(
        "INFINITT PACS high series number",
        manufacturer="INFINITT",
        series_number="/[1-9]\\d{3,}/",
    ),
    # Deny 9: Biopsy/pathology vendors
    deny_when(
        "Bioptics manufacturer",
        manufacturer="Bioptics",
    ),
    deny_when(
        "Biovision model",
        manufacturer_model_name="Biovision",
    ),
    deny_when(
        "Faxitron manufacturer",
        manufacturer="Faxitron",
    ),
    deny_when(
        "KUBTEC manufacturer",
        manufacturer="KUBTEC",
    ),
    deny_when(
        "Hologic Trident",
        manufacturer="Hologic",
        manufacturer_model_name="Trident",
    ),
    # Deny 10: Secondary Capture SOP Class
    deny_when(
        "Secondary Capture SOP",
        sop_class="1.2.840.10008.5.1.4.1.1.7",
    ),
    # Deny 11: Empty ImageType (GSPS presentation states have no ImageType).
    deny_when(
        "Empty ImageType",
        image_type_empty=True,
        modality_not=["=PR", "=KO"],
    ),
    # Deny 12: BurnedInAnnotation YES
    deny_when(
        "BurnedInAnnotation YES",
        burned_in_annotation="=YES",
    ),
    # Deny 13: DERIVED/SECONDARY/ConversionType for non-CR/DR/DX
    deny_when(
        "Non-CR/DR/DX with ConversionType",
        modality_not=["=CR", "=DR", "=DX"],
        conversion_type_present=True,
    ),
    deny_when(
        "Non-CR/DR/DX/MR DERIVED",
        modality_not=["=CR", "=DR", "=DX", "=MR"],
        image_type_any="DERIVED",
    ),
    deny_when(
        "MR DERIVED without PRIMARY",
        modality="=MR",
        image_type_any="DERIVED",
        image_type_exclude="DERIVED\\PRIMARY",
    ),
    deny_when(
        "MR MRSC",
        modality="=MR",
        image_type_any="MRSC",
    ),
    deny_when(
        "Non-CR/DR/DX SECONDARY",
        modality_not=["=CR", "=DR", "=DX"],
        image_type_any="SECONDARY",
    ),
]


# Combined device list and factory

default_devices: list[DeviceRule] = (
    _cr_dx_devices
    + _ct_pet_devices
    + _nm_devices
    + _mammo_devices
    + _breast_mri_devices
    + _us_devices
    + _scrub_only_devices
)


def get_default_catalog() -> DeviceCatalog:
    """Return the default device catalog with all translated rules."""
    return DeviceCatalog(
        devices=default_devices,
        exclusions=default_exclusions,
        default_action="allow",
    )
