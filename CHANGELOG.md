# CHANGELOG

<!-- version list -->

## v1.2.0 (2026-08-14)

### Bug Fixes

- Add DeviceId and DeviceSerialNumber to default profile (hashed)
  ([`f801cb6`](https://github.com/susom/dicom-dre/commit/f801cb653726359a185027d5606fd95da8eb5477))

- Hash_identifier always uses default salt and study_id when either is None
  ([`54e780e`](https://github.com/susom/dicom-dre/commit/54e780e8bfac0f9d688e2103efda5e3f95120846))

- Private attribute preservation no longer requires a device match (STAR-12198)
  ([#13](https://github.com/susom/dicom-dre/pull/13),
  [`5f35e79`](https://github.com/susom/dicom-dre/commit/5f35e7921a3fbc9a5815372f40012dcf9542465f))

### Features

- Add additional attributes to default rules, including PatientSize and PatientWeight (rounded)
  ([#12](https://github.com/susom/dicom-dre/pull/12),
  [`edeaa5a`](https://github.com/susom/dicom-dre/commit/edeaa5aa8c8300cd4001ce8186c0f08ef9e8948e))


## v1.1.2 (2026-08-10)

### Bug Fixes

- Reject truncated JPEG entropy streams in the DCT accelerator instead of hanging
  ([#10](https://github.com/susom/dicom-dre/pull/10),
  [`50bfd9b`](https://github.com/susom/dicom-dre/commit/50bfd9b0f26cad1cafe4579b8df04e8577cb9547))


## v1.1.1 (2026-08-07)

### Bug Fixes

- Harden JPEG DCT scrubber against malformed input and add fuzzing suite
  ([#8](https://github.com/susom/dicom-dre/pull/8),
  [`e7c1d84`](https://github.com/susom/dicom-dre/commit/e7c1d84ff44ee8e4d0c80d7bf058c73203698a73))


## v1.1.0 (2026-08-07)

### Features

- Admit annotated presentation states and KO key object selections, align profiles with PS3.15 Basic
  Profile (STAR-12623) ([#1](https://github.com/susom/dicom-dre/pull/1),
  [`257ac8d`](https://github.com/susom/dicom-dre/commit/257ac8db5a930b30e24e0030cb48ceba6ff48c31))

### Bug Fixes

- Upgrade gitpython to resolve known vulnerabilities
  ([`313ec2a`](https://github.com/susom/dicom-dre/commit/313ec2aeffbb10fc6a8900055c9e6c6df5bfbebc))


## v1.0.1 (2026-07-31)

### Bug Fixes

- Clarification in the README
  ([`20a84e1`](https://github.com/susom/dicom-dre/commit/20a84e13bca1ee43250bd0e7acc4405561a67e38))


## v1.0.0 (2026-07-31)

### Documentation

- Initial release
  ([`5da3648`](https://github.com/susom/dicom-dre/commit/5da36481a061b081e97d44c9baf804ba50f18329))
