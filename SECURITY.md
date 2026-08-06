# Security Policy

## Supported Versions

Security updates are applied to the most recent release of `dicom-dre`. Users
are advised to run the latest version to receive fixes.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| Older   | :x:                |

## What Constitutes a Vulnerability

A possible security vulnerability is any defect that could allow unauthorized
access to, disclosure of, or modification of data, or that could compromise the
confidentiality, integrity, or availability of the software or the systems on
which it runs. Because `dicom-dre` processes medical imaging data that may
contain Protected Health Information (PHI), issues that could lead to the
unintended retention or disclosure of PHI are treated as possible security
vulnerabilities.

What constitutes an acceptable level of risk varies between institutions, and
what may be acceptable to one institution may not be acceptable to another. For
this reason, we evaluate reported issues on a case-by-case basis, taking into
account the reporter's context and the range of environments in which the
software is deployed. If you are unsure whether an issue qualifies as a security
vulnerability, please report it and we will assess it with you.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately. Do not open a public issue,
pull request, or discussion for security reports, as this can expose details of
the vulnerability before a fix is available.

Use one of the following private channels:

- Use GitHub's private vulnerability reporting for this
  repository: https://github.com/susom/dicom-dre/security/advisories/new

When reporting, please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce or a proof of concept.
- Affected version(s) and environment details.
- Any suggested remediation, if known.

Do not include real PHI in your report. Use synthetic or de-identified data to
demonstrate the issue.

## Disclosure Process and Timelines

We follow a coordinated vulnerability disclosure process. As a volunteer-driven
open-source project, we cannot guarantee fixed response times, but we aim to:

- Acknowledge receipt of your report within a few days.
- Provide an initial assessment and an expected remediation timeline once the
  report has been triaged.
- Release a fix and coordinate public disclosure, typically within 90 days of
  the initial report. Complex issues may take longer, and we will keep you
  informed of progress.

We ask that you keep the details of any reported vulnerability confidential
until a fix has been released and a coordinated disclosure has been made. We
will credit reporters who wish to be acknowledged once the issue is resolved.
