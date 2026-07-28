"""Unit tests for the ``dicom-dre`` command-line interface.

Exercises the ``deidentify`` subcommand end to end against the synthetic GE
SIGNA Premier MR fixture, plus parameter parsing and error handling.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from dicom_dre.cli import _parse_parameters
from dicom_dre.cli import cli


if TYPE_CHECKING:
    from pathlib import Path


def test_parse_parameters_valid() -> None:
    """KEY=VALUE pairs parse into a dict, preserving empty values."""
    result = _parse_parameters(("PATIENT_ID=TEST", "JITTER=10", "STUDY_DESCRIPTION="))
    assert result == {"PATIENT_ID": "TEST", "JITTER": "10", "STUDY_DESCRIPTION": ""}


@pytest.mark.parametrize("bad", ["PATIENT_ID", "=TEST", ""])
def test_parse_parameters_invalid(bad: str) -> None:
    """Entries without a key or ``=`` separator are rejected."""
    import click

    with pytest.raises(click.BadParameter):
        _parse_parameters((bad,))


def test_deidentify_command_success(signa_premier_file: Path, tmp_path: Path) -> None:
    """The deidentify command scrubs PHI and writes a de-identified file."""
    import pydicom
    from pydicom.tag import Tag

    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deidentify",
            str(signa_premier_file),
            "-o",
            str(out),
            "--profile",
            "default",
            "-p",
            "PATIENT_ID=TEST",
            "-p",
            "ACCESSION_NUMBER=TEST",
            "-p",
            "STUDY_ID=TEST",
            "-p",
            "JITTER=10",
            "-p",
            "UIDROOT=1.2.3",
            "--no-rename-to-sop-uid",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DEIDENTIFIED" in result.output
    output = out / signa_premier_file.name
    assert output.exists()

    ds = pydicom.dcmread(output, force=True)
    assert ds[Tag(0x0010, 0x0020)].value != "MRN123456"  # PatientID scrubbed


def test_deidentify_unknown_profile(signa_premier_file: Path, tmp_path: Path) -> None:
    """An unknown profile name is rejected by the Choice option."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(signa_premier_file), "-o", str(out), "--profile", "nope"],
    )

    assert result.exit_code != 0
    assert "nope" in result.output


def test_deidentify_bad_parameter(signa_premier_file: Path, tmp_path: Path) -> None:
    """A malformed ``--param`` entry fails with a usage error."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(signa_premier_file), "-o", str(out), "-p", "PATIENT_ID"],
    )

    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output


_BATCH_PARAMS = [
    "-p",
    "PATIENT_ID=TEST",
    "-p",
    "ACCESSION_NUMBER=TEST",
    "-p",
    "STUDY_ID=TEST",
    "-p",
    "JITTER=10",
    "-p",
    "UIDROOT=1.2.3",
]


def test_deidentify_batch_directory_recursive(signa_premier_file: Path, tmp_path: Path) -> None:
    """Batch mode with -r mirrors the source subtree under the output dir."""
    import shutil

    source = tmp_path / "src"
    (source / "sub").mkdir(parents=True)
    shutil.copy2(signa_premier_file, source / "top.dcm")
    shutil.copy2(signa_premier_file, source / "sub" / "nested.dcm")
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(source), "-o", str(out), "-r", "--no-rename-to-sop-uid", *_BATCH_PARAMS],
    )

    assert result.exit_code == 0, result.output
    assert (out / "top.dcm").exists(), "Top-level file should be mirrored"
    assert (out / "sub" / "nested.dcm").exists(), "Nested file should be mirrored"


def test_deidentify_batch_glob_case_insensitive(signa_premier_file: Path, tmp_path: Path) -> None:
    """A --glob pattern matches uppercase extensions case-insensitively."""
    import shutil

    source = tmp_path / "src"
    source.mkdir()
    shutil.copy2(signa_premier_file, source / "upper.DCM")
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(source), "-o", str(out), "--glob", "*.dcm", "--no-rename-to-sop-uid", *_BATCH_PARAMS],
    )

    assert result.exit_code == 0, result.output
    assert (out / "upper.DCM").exists(), "*.DCM should match the *.dcm glob case-insensitively"


def test_deidentify_batch_quarantine_exit_code(signa_premier_file: Path, tmp_path: Path) -> None:
    """A quarantined file yields exit 1 while valid files still process."""
    import shutil

    source = tmp_path / "src"
    source.mkdir()
    shutil.copy2(signa_premier_file, source / "good.dcm")
    (source / "bad.dcm").write_bytes(b"not a dicom file")
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(source), "-o", str(out), "--no-rename-to-sop-uid", *_BATCH_PARAMS],
    )

    assert result.exit_code == 1, result.output
    assert "QUARANTINED" in result.output
    assert (out / "good.dcm").exists(), "Valid file should still be written"


def test_deidentify_basename_collision_is_usage_error(signa_premier_file: Path, tmp_path: Path) -> None:
    """Two explicit files sharing a basename fail under --no-rename-to-sop-uid."""
    import shutil

    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    shutil.copy2(signa_premier_file, a_dir / "scan.dcm")
    shutil.copy2(signa_premier_file, b_dir / "scan.dcm")
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deidentify",
            str(a_dir / "scan.dcm"),
            str(b_dir / "scan.dcm"),
            "-o",
            str(out),
            "--no-rename-to-sop-uid",
            *_BATCH_PARAMS,
        ],
    )

    assert result.exit_code != 0, result.output
    assert "same output path" in result.output
    assert not out.exists() or not any(out.iterdir()), "No output should be written on collision"


def test_deidentify_no_sources_is_usage_error(tmp_path: Path) -> None:
    """Invoking with --output-dir but no sources is a usage error."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(cli, ["deidentify", "-o", str(out)])

    assert result.exit_code != 0
    assert "source" in result.output.lower()


def test_deidentify_missing_output_dir_is_usage_error(signa_premier_file: Path) -> None:
    """The --output-dir option is required."""
    runner = CliRunner()
    result = runner.invoke(cli, ["deidentify", str(signa_premier_file)])

    assert result.exit_code != 0
    assert "output-dir" in result.output.lower()


def _write_allowlist(path: Path, tokens: list[str]) -> None:
    """Write a one-token-per-row allowlist CSV."""
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for token in tokens:
            writer.writerow([token])


def test_redactor_redact_command(tmp_path: Path) -> None:
    """The redact subcommand masks unlisted tokens and keeps allowlisted ones."""
    allowlist = tmp_path / "allow.csv"
    _write_allowlist(allowlist, ["chest"])
    input_csv = tmp_path / "in.csv"
    input_csv.write_text("Chest Zzytkiewicz\n", encoding="utf-8")
    output_csv = tmp_path / "out.csv"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "redactor",
            "redact",
            "--allowlist",
            str(allowlist),
            "--input",
            str(input_csv),
            "--output",
            str(output_csv),
        ],
    )

    assert result.exit_code == 0, result.output
    redacted = output_csv.read_text(encoding="utf-8")
    assert "Chest" in redacted, f"Allowlisted token should survive, got {redacted!r}"
    assert "Zzytkiewicz" not in redacted, f"Unlisted token should be masked, got {redacted!r}"


def test_redactor_quality_check_simple(tmp_path: Path) -> None:
    """The quality-check --simple subcommand lists tokens that would be redacted."""
    allowlist = tmp_path / "allow.csv"
    _write_allowlist(allowlist, ["chest"])
    input_csv = tmp_path / "in.csv"
    input_csv.write_text("Chest Zzytkiewicz\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["redactor", "quality-check", "--allowlist", str(allowlist), "--simple", str(input_csv)],
    )

    assert result.exit_code == 0, result.output
    assert "Zzytkiewicz" in result.output, "Unlisted token should be reported"


def test_redactor_show_tokens(tmp_path: Path) -> None:
    """The show-tokens subcommand lists unique tokens from the input."""
    input_csv = tmp_path / "in.csv"
    input_csv.write_text("Chest Abdomen\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["redactor", "show-tokens", "--input", str(input_csv)])

    assert result.exit_code == 0, result.output
    assert "Chest" in result.output
    assert "Abdomen" in result.output


def test_redactor_allow_token(tmp_path: Path) -> None:
    """The allow-token subcommand adds new tokens to the allowlist file."""
    allowlist = tmp_path / "allow.csv"
    _write_allowlist(allowlist, ["chest"])

    runner = CliRunner()
    result = runner.invoke(cli, ["redactor", "allow-token", "--allowlist", str(allowlist), "abdomen"])

    assert result.exit_code == 0, result.output
    assert "Added 1 token" in result.output
    contents = allowlist.read_text(encoding="utf-8")
    assert "abdomen" in contents, "New token should be written to the allowlist"


def test_accelerator_status_active(monkeypatch) -> None:
    """The command reports ACTIVE and exits 0 when the accelerator is present."""
    from dicom_dre import cli as cli_module

    monkeypatch.setattr(cli_module, "jpeg_dct_accelerator_available", lambda: True)
    runner = CliRunner()
    result = runner.invoke(cli, ["accelerator-status"])

    assert result.exit_code == 0, f"Expected exit code 0 when active, got {result.exit_code}: {result.output}"
    assert "JPEG DCT C accelerator: ACTIVE" in result.output, f"Expected ACTIVE line, got: {result.output!r}"


def test_accelerator_status_fallback(monkeypatch) -> None:
    """The command reports the fallback and exits non-zero when absent."""
    from dicom_dre import cli as cli_module

    monkeypatch.setattr(cli_module, "jpeg_dct_accelerator_available", lambda: False)
    runner = CliRunner()
    result = runner.invoke(cli, ["accelerator-status"])

    assert result.exit_code == 1, f"Expected exit code 1 on fallback, got {result.exit_code}: {result.output}"
    assert "NOT AVAILABLE" in result.output, f"Expected NOT AVAILABLE, got: {result.output!r}"
    assert "pure-Python fallback" in result.output, f"Expected fallback note, got: {result.output!r}"
