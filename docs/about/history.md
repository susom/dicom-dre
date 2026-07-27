# History

`dicom-dre` grew out of a de-identification workflow built on the MIRC CTP
(Clinical Trial Processor) engine. This page records that background. It is not
a reference for configuring the engine; the device catalog and profiles
documented elsewhere in these docs have replaced the behavior described here.

## From CTP scripts to a device catalog

The original workflow controlled DICOM image handling with two CTP script files
and an XML metadata template:

- **filter.script** decided which images to accept for processing. Images
  matching a filter rule passed through; the engine quarantined images matching
  no rule.
- **pixel.script** defined rectangular regions to blank for images with
  burned-in PHI annotations.

Both scripts used a Java boolean expression syntax over DICOM attributes. Filter
rules keyed on manufacturer, model, modality, software version, and image
dimensions. Pixel rules paired a matching signature with one or more
`(x, y, width, height)` scrub regions.

Two problems motivated the rewrite:

- The filter and pixel scripts encoded the same device signatures twice, once to
  decide acceptance and again to place scrub regions, so the two files drifted
  apart as maintainers added devices.
- The expression syntax was code rather than data, which made the rule set hard
  to inspect, test, and validate.

`dicom-dre` replaces both script files with a single Python device catalog. Each
catalog entry describes one device and binds its acquisition variants directly
to the pixel regions to blank, so each device defines its filter decision and
its scrub regions together. See [Device catalog](../concepts/device-catalog.md).

## From an XML template to profiles

De-identification profiles now express the metadata handling that a CTP
anonymizer template previously expressed. See
[Profiles](../concepts/profiles.md) for the profiles shipped in this repository.

## Acknowledgement

This project would not have been possible without years of working with and
learning from the MIRC CTP engine.
