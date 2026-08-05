"""Unit tests for the ``dicom-dre`` command-line interface.

Exercises the ``deidentify`` subcommand end to end against the synthetic GE
SIGNA Premier MR fixture, plus parameter parsing and error handling.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from dicom_dre.cli import _parse_parameters
from dicom_dre.cli import cli
from dicom_dre.salt import default_salt_path


if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def test_parse_parameters_valid() -> None:
    """KEY=VALUE pairs parse into a dict, preserving empty values."""
    result = _parse_parameters(("PATIENT_ID=TEST", "JITTER=10", "STUDY_DESCRIPTION="))
    assert result == {"PATIENT_ID": "TEST", "JITTER": "10", "STUDY_DESCRIPTION": ""}, (
        f"KEY=VALUE pairs should parse into a dict preserving empty values, got: {result!r}"
    )


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
            "--uid-root",
            "1.2.3",
            "--no-rename-to-sop-uid",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DEIDENTIFIED" in result.output, f"Expected a DEIDENTIFIED line, got: {result.output!r}"
    output = out / signa_premier_file.name
    assert output.exists(), f"A de-identified file should be written to {output}"

    ds = pydicom.dcmread(output, force=True)
    assert ds[Tag(0x0010, 0x0020)].value != "MRN123456", "PatientID should be scrubbed"


def test_deidentify_unknown_profile(signa_premier_file: Path, tmp_path: Path) -> None:
    """An unknown profile name is rejected by the Choice option."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(signa_premier_file), "-o", str(out), "--profile", "nope"],
    )

    assert result.exit_code != 0, f"An unknown profile should fail, got exit {result.exit_code}: {result.output!r}"
    assert "nope" in result.output, f"Expected the rejected profile name in the error, got: {result.output!r}"


def test_deidentify_bad_parameter(signa_premier_file: Path, tmp_path: Path) -> None:
    """A malformed ``--param`` entry fails with a usage error."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deidentify", str(signa_premier_file), "-o", str(out), "-p", "PATIENT_ID"],
    )

    assert result.exit_code != 0, f"A malformed --param should fail, got exit {result.exit_code}: {result.output!r}"
    assert "KEY=VALUE" in result.output, f"Expected the KEY=VALUE usage hint, got: {result.output!r}"


@pytest.mark.parametrize("profile_name", ["lds", "lds-no-dob", "pixels-only"])
def test_deidentify_jitter_rejected_for_date_preserving_profile(
    signa_premier_file: Path, tmp_path: Path, profile_name: str
) -> None:
    """JITTER combined with a date-preserving profile fails with a usage error."""
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
            profile_name,
            "-p",
            "JITTER=10",
        ],
    )

    assert result.exit_code != 0, (
        f"JITTER with the {profile_name} profile should fail, got exit {result.exit_code}: {result.output!r}"
    )
    assert "JITTER" in result.output, f"Expected the error to mention JITTER, got: {result.output!r}"
    assert not out.exists(), f"No output should be written when the combination is rejected: {out}"


def test_deidentify_zero_jitter_rejected_for_date_shifting_profile(signa_premier_file: Path, tmp_path: Path) -> None:
    """JITTER=0 with a date-shifting profile fails with a usage error."""
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
            "JITTER=0",
        ],
    )

    assert result.exit_code != 0, (
        f"JITTER=0 with the default profile should fail, got exit {result.exit_code}: {result.output!r}"
    )
    assert "JITTER" in result.output, f"Expected the error to mention JITTER, got: {result.output!r}"
    assert not out.exists(), f"No output should be written when the combination is rejected: {out}"


@pytest.mark.parametrize("profile_name", ["lds", "lds-no-dob", "pixels-only"])
def test_deidentify_zero_jitter_accepted_for_date_preserving_profile(
    signa_premier_file: Path, tmp_path: Path, profile_name: str
) -> None:
    """JITTER=0 with a date-preserving profile is accepted and inert."""
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
            profile_name,
            "-p",
            "JITTER=0",
            "--uid-root",
            "1.2.3",
            "--no-rename-to-sop-uid",
        ],
    )

    assert result.exit_code == 0, (
        f"JITTER=0 with the {profile_name} profile should succeed, got exit {result.exit_code}: {result.output!r}"
    )
    assert "DEIDENTIFIED" in result.output, f"Expected a DEIDENTIFIED line, got: {result.output!r}"


_BATCH_PARAMS = [
    "-p",
    "PATIENT_ID=TEST",
    "-p",
    "ACCESSION_NUMBER=TEST",
    "-p",
    "STUDY_ID=TEST",
    "-p",
    "JITTER=10",
    "--uid-root",
    "1.2.3",
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
    assert "QUARANTINED" in result.output, f"Expected a QUARANTINED line, got: {result.output!r}"
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
    assert "same output path" in result.output, f"Expected a basename-collision message, got: {result.output!r}"
    assert not out.exists() or not any(out.iterdir()), "No output should be written on collision"


def test_deidentify_no_sources_is_usage_error(tmp_path: Path) -> None:
    """Invoking with --output-dir but no sources is a usage error."""
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(cli, ["deidentify", "-o", str(out)])

    assert result.exit_code != 0, f"Missing sources should fail, got exit {result.exit_code}: {result.output!r}"
    assert "source" in result.output.lower(), f"Expected a missing-source message, got: {result.output!r}"


def test_deidentify_missing_output_dir_is_usage_error(signa_premier_file: Path) -> None:
    """The --output-dir option is required."""
    runner = CliRunner()
    result = runner.invoke(cli, ["deidentify", str(signa_premier_file)])

    assert result.exit_code != 0, f"Missing --output-dir should fail, got exit {result.exit_code}: {result.output!r}"
    assert "output-dir" in result.output.lower(), f"Expected an output-dir requirement message, got: {result.output!r}"


class TestSaltResolution:
    """The deidentify command loads, generates, or bypasses the persisted salt."""

    def test_generates_and_persists_salt_when_absent(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """With no salt supplied a salt file is generated and a notice is printed."""
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["deidentify", str(signa_premier_file), "-o", str(out), "--no-rename-to-sop-uid", *_BATCH_PARAMS],
        )

        assert result.exit_code == 0, result.output
        assert default_salt_path().exists(), "A salt file should be generated when none is supplied"
        assert "generated one and saved it" in result.output, f"Expected a generation notice, got: {result.output!r}"

    def test_reuses_persisted_salt_on_second_run(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A second run reuses the persisted salt and prints no generation notice."""
        runner = CliRunner()
        first = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(tmp_path / "out1"),
                "--no-rename-to-sop-uid",
                *_BATCH_PARAMS,
            ],
        )
        second = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(tmp_path / "out2"),
                "--no-rename-to-sop-uid",
                *_BATCH_PARAMS,
            ],
        )

        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        assert "generated one and saved it" not in second.output, (
            f"The second run should reuse the salt, got: {second.output!r}"
        )

    def test_explicit_hash_salt_skips_generation(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """An explicit --hash-salt suppresses salt-file generation."""
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(out),
                "--no-rename-to-sop-uid",
                "--hash-salt",
                "fixed-salt",
                *_BATCH_PARAMS,
            ],
        )

        assert result.exit_code == 0, result.output
        assert not default_salt_path().exists(), "No salt file should be written when --hash-salt is supplied"
        assert "generated one and saved it" not in result.output, f"No notice should be printed, got: {result.output!r}"

    def test_env_var_salt_skips_generation(
        self, signa_premier_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DICOM_DRE_HASH_SALT is used and no salt file is generated."""
        monkeypatch.setenv("DICOM_DRE_HASH_SALT", "env-provided-salt")
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["deidentify", str(signa_premier_file), "-o", str(out), "--no-rename-to-sop-uid", *_BATCH_PARAMS],
        )

        assert result.exit_code == 0, result.output
        assert not default_salt_path().exists(), "No salt file should be written when the env var supplies a salt"
        assert "generated one and saved it" not in result.output, f"No notice should be printed, got: {result.output!r}"

    def test_no_generate_salt_errors_when_absent(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """--no-generate-salt errors when no salt is available anywhere."""
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["deidentify", str(signa_premier_file), "-o", str(out), "--no-generate-salt", *_BATCH_PARAMS],
        )

        assert result.exit_code != 0, result.output
        assert "no-generate-salt" in result.output, f"Expected the strict-mode message, got: {result.output!r}"
        assert not default_salt_path().exists(), "No salt file should be written in strict mode"

    def test_no_generate_salt_uses_existing_file(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """--no-generate-salt reuses an existing persisted salt without error."""
        default_salt_path().parent.mkdir(parents=True)
        default_salt_path().write_text("preset-salt\n", encoding="utf-8")
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(out),
                "--no-rename-to-sop-uid",
                "--no-generate-salt",
                *_BATCH_PARAMS,
            ],
        )

        assert result.exit_code == 0, result.output

    def test_quiet_suppresses_generation_notice(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """--quiet suppresses the generation notice while still persisting the salt."""
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(out),
                "--no-rename-to-sop-uid",
                "--quiet",
                *_BATCH_PARAMS,
            ],
        )

        assert result.exit_code == 0, result.output
        assert default_salt_path().exists(), "The salt file should still be generated under --quiet"
        assert "generated one and saved it" not in result.output, (
            f"The notice should be suppressed, got: {result.output!r}"
        )


class TestIdentifierParameterConflicts:
    """Dedicated identity options conflict with the same key given via --param."""

    def test_study_id_conflict_raises(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Supplying STUDY_ID via both --study-id and --param is an error."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["deidentify", str(signa_premier_file), "-o", str(tmp_path / "out"), "--study-id", "A", "-p", "STUDY_ID=B"],
        )

        assert result.exit_code != 0, result.output
        assert "STUDY_ID" in result.output, f"Expected the conflict to name STUDY_ID, got: {result.output!r}"
        assert "only once" in result.output, f"Expected a single-source message, got: {result.output!r}"

    def test_build_setting_via_param_rejected(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A build setting passed through --param is rejected as an unknown parameter."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "deidentify",
                str(signa_premier_file),
                "-o",
                str(tmp_path / "out"),
                "-p",
                "UIDROOT=1.2.3",
            ],
        )

        assert result.exit_code != 0, result.output
        assert "UIDROOT" in result.output, f"Expected the error to name UIDROOT, got: {result.output!r}"


@pytest.fixture()
def reset_root_logging() -> Iterator[None]:
    """Snapshot and restore logging state so --verbose configures deterministically.

    pytest attaches handlers to the root logger, which would make the command's
    ``logging.basicConfig`` a no-op. Root handlers are cleared and the root,
    ``dicom_dre``, and ``py.warnings`` logger state plus the warnings-capture
    hook are reset before the test, then restored, so the ``--verbose`` changes
    neither depend on nor leak into other tests.
    """
    root = logging.getLogger()
    pkg = logging.getLogger("dicom_dre")
    warnings_logger = logging.getLogger("py.warnings")
    root_level = root.level
    root_handlers = root.handlers[:]
    pkg_level = pkg.level
    warn_propagate = warnings_logger.propagate
    warn_handlers = warnings_logger.handlers[:]
    show_warning = warnings.showwarning
    root.handlers[:] = []
    root.setLevel(logging.WARNING)
    pkg.setLevel(logging.NOTSET)
    yield
    root.setLevel(root_level)
    root.handlers[:] = root_handlers
    pkg.setLevel(pkg_level)
    warnings_logger.propagate = warn_propagate
    warnings_logger.handlers[:] = warn_handlers
    warnings.showwarning = show_warning


class TestQuarantineLogging:
    """A file that fails to process is quarantined without leaking a traceback."""

    def _write_malformed_dicom(self, path: Path) -> None:
        """Write a file that is not valid DICOM so the pipeline quarantines it."""
        path.write_text("not a dicom file", encoding="utf-8")

    def test_quarantine_prints_no_traceback_by_default(self, tmp_path: Path) -> None:
        """A quarantined file reports its reason but no traceback on stderr."""
        bad = tmp_path / "bad.dcm"
        self._write_malformed_dicom(bad)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(cli, ["deidentify", str(bad), "-o", str(out), "--hash-salt", "s"])

        assert result.exit_code == 1, result.output
        assert "QUARANTINED" in result.output, f"Expected a QUARANTINED line, got: {result.output!r}"
        assert "Traceback" not in result.output, f"No traceback should print by default, got: {result.output!r}"

    def test_verbose_enables_debug_logging(self, tmp_path: Path, reset_root_logging: object) -> None:
        """The --verbose flag raises logging to DEBUG so tracebacks are emitted."""
        bad = tmp_path / "bad.dcm"
        self._write_malformed_dicom(bad)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(cli, ["deidentify", str(bad), "-o", str(out), "--hash-salt", "s", "-v"])

        assert result.exit_code == 1, result.output
        assert logging.getLogger("dicom_dre.pipeline").isEnabledFor(logging.DEBUG), (
            "--verbose should enable DEBUG logging for the pipeline"
        )

    def test_default_does_not_enable_debug_logging(self, tmp_path: Path, reset_root_logging: object) -> None:
        """Without --verbose the pipeline logger stays above DEBUG."""
        bad = tmp_path / "bad.dcm"
        self._write_malformed_dicom(bad)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(cli, ["deidentify", str(bad), "-o", str(out), "--hash-salt", "s"])

        assert result.exit_code == 1, result.output
        assert not logging.getLogger("dicom_dre.pipeline").isEnabledFor(logging.DEBUG), (
            "DEBUG logging should stay off without --verbose"
        )

    def test_warnings_suppressed_by_default(self, tmp_path: Path, reset_root_logging: object) -> None:
        """Captured Python warnings are kept off the console without --verbose."""
        bad = tmp_path / "bad.dcm"
        self._write_malformed_dicom(bad)
        out = tmp_path / "out"
        runner = CliRunner()
        runner.invoke(cli, ["deidentify", str(bad), "-o", str(out), "--hash-salt", "s"])

        warnings_logger = logging.getLogger("py.warnings")
        assert warnings_logger.propagate is False, "Captured warnings should not propagate by default"
        assert any(isinstance(h, logging.NullHandler) for h in warnings_logger.handlers), (
            "A NullHandler should absorb captured warnings by default"
        )

    def test_warnings_enabled_under_verbose(self, tmp_path: Path, reset_root_logging: object) -> None:
        """The --verbose flag lets captured Python warnings reach the console."""
        bad = tmp_path / "bad.dcm"
        self._write_malformed_dicom(bad)
        out = tmp_path / "out"
        runner = CliRunner()
        runner.invoke(cli, ["deidentify", str(bad), "-o", str(out), "--hash-salt", "s", "-v"])

        assert logging.getLogger("py.warnings").propagate is True, (
            "--verbose should let captured warnings propagate to the console"
        )


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
    assert "Chest" in result.output, f"Expected the token Chest to be listed, got: {result.output!r}"
    assert "Abdomen" in result.output, f"Expected the token Abdomen to be listed, got: {result.output!r}"


def test_redactor_allow_token(tmp_path: Path) -> None:
    """The allow-token subcommand adds new tokens to the allowlist file."""
    allowlist = tmp_path / "allow.csv"
    _write_allowlist(allowlist, ["chest"])

    runner = CliRunner()
    result = runner.invoke(cli, ["redactor", "allow-token", "--allowlist", str(allowlist), "abdomen"])

    assert result.exit_code == 0, result.output
    assert "Added 1 token" in result.output, f"Expected a single-token addition notice, got: {result.output!r}"
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
