"""Unit tests for batch de-identification over files and directories.

Exercises :func:`dicom_dre.batch.deidentify_paths` and the private
``_discover_inputs`` helper against the synthetic GE SIGNA Premier MR fixture.
Directory trees are built by copying the fixture so mirroring, recursion, glob
filtering, and continue-on-error behavior can be validated.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from dicom_dre import ProfileSettings
from dicom_dre import build_profile
from dicom_dre.batch import OutputPathCollisionError
from dicom_dre.batch import ProfileSpec
from dicom_dre.batch import _discover_inputs
from dicom_dre.batch import deidentify_paths
from dicom_dre.result import Outcome


if TYPE_CHECKING:
    from pathlib import Path


_BATCH_SETTINGS = ProfileSettings(uid_root="1.2.3")


def _profile():
    """Build a default profile bound with a deterministic UID root."""
    return build_profile("default", _BATCH_SETTINGS)


class TestDiscoverInputs:
    """Test input discovery, filtering, and subpath computation."""

    def test_explicit_files_bypass_extension_filter(self, tmp_path: Path) -> None:
        """Explicit file arguments are always included regardless of extension."""
        odd = tmp_path / "scan.foo"
        odd.write_bytes(b"data")
        pairs = list(_discover_inputs([odd], recursive=False, patterns=("*.dcm",)))
        assert len(pairs) == 1, "Explicit file should be included despite the filter"
        assert pairs[0][1].as_posix() == "scan.foo", "Explicit file lands flat by name"

    def test_directory_non_recursive_skips_subdirs(self, tmp_path: Path) -> None:
        """A non-recursive directory scan ignores files in subdirectories."""
        (tmp_path / "top.dcm").write_bytes(b"a")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.dcm").write_bytes(b"b")
        names = {p[1].as_posix() for p in _discover_inputs([tmp_path], recursive=False, patterns=("*.dcm",))}
        assert names == {"top.dcm"}, "Non-recursive scan should only find top-level files"

    def test_directory_recursive_finds_nested(self, tmp_path: Path) -> None:
        """A recursive directory scan yields nested files with mirrored subpaths."""
        (tmp_path / "top.dcm").write_bytes(b"a")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.dcm").write_bytes(b"b")
        names = {p[1].as_posix() for p in _discover_inputs([tmp_path], recursive=True, patterns=("*.dcm",))}
        assert names == {"top.dcm", "sub/nested.dcm"}, "Recursive scan should mirror subpaths"

    def test_glob_is_case_insensitive(self, tmp_path: Path) -> None:
        """Directory-scan patterns match filenames case-insensitively."""
        (tmp_path / "upper.DCM").write_bytes(b"a")
        names = {p[1].as_posix() for p in _discover_inputs([tmp_path], recursive=False, patterns=("*.dcm",))}
        assert names == {"upper.DCM"}, "*.DCM should match a *.dcm pattern case-insensitively"

    def test_deduplicates_repeated_sources(self, tmp_path: Path) -> None:
        """The same file listed twice is only yielded once."""
        f = tmp_path / "one.dcm"
        f.write_bytes(b"a")
        pairs = list(_discover_inputs([f, f], recursive=False, patterns=("*.dcm",)))
        assert len(pairs) == 1, "Repeated source should be de-duplicated"


class TestDeidentifyPaths:
    """Test the sequential batch generator end to end."""

    def test_directory_tree_mirrored(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A recursive batch mirrors the source subtree under the output dir."""
        source = tmp_path / "src"
        (source / "a").mkdir(parents=True)
        (source / "b").mkdir(parents=True)
        shutil.copy2(signa_premier_file, source / "a" / "one.dcm")
        shutil.copy2(signa_premier_file, source / "b" / "two.dcm")
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [source],
                out,
                profile=_profile(),
                recursive=True,
                rename_to_sop_uid=False,
            )
        )

        assert len(results) == 2, "Both nested files should be processed"
        assert all(r.result.outcome is Outcome.DEIDENTIFIED for r in results), "Both should deidentify"
        assert (out / "a" / "one.dcm").exists(), "Subtree 'a' should be mirrored"
        assert (out / "b" / "two.dcm").exists(), "Subtree 'b' should be mirrored"

    def test_sop_uid_rename_within_mirrored_subdir(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """SOP-UID rename composes with mirroring, keeping the output subdir."""
        source = tmp_path / "src"
        (source / "study").mkdir(parents=True)
        shutil.copy2(signa_premier_file, source / "study" / "img.dcm")
        out = tmp_path / "out"

        results = list(deidentify_paths([source], out, profile=_profile(), recursive=True))

        assert len(results) == 1, "One file should be processed"
        output_file = results[0].result.output_file
        assert output_file is not None, "Deidentified result carries an output file"
        assert output_file.parent == out / "study", "Renamed file stays in the mirrored subdir"
        assert output_file.suffix == ".dcm", "Renamed file keeps the .dcm suffix"

    def test_explicit_files_land_flat(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Explicit file arguments are written flat into the output directory."""
        a = tmp_path / "a.dcm"
        b = tmp_path / "b.dcm"
        shutil.copy2(signa_premier_file, a)
        shutil.copy2(signa_premier_file, b)
        out = tmp_path / "out"

        results = list(deidentify_paths([a, b], out, profile=_profile(), rename_to_sop_uid=False))

        assert len(results) == 2, "Both explicit files should be processed"
        assert (out / "a.dcm").exists(), "Explicit file a lands flat"
        assert (out / "b.dcm").exists(), "Explicit file b lands flat"

    def test_continue_on_error_quarantines_non_dicom(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A non-DICOM file is quarantined while valid files still process."""
        source = tmp_path / "src"
        source.mkdir()
        shutil.copy2(signa_premier_file, source / "good.dcm")
        (source / "bad.dcm").write_bytes(b"not a dicom file")
        out = tmp_path / "out"

        results = list(deidentify_paths([source], out, profile=_profile(), rename_to_sop_uid=False))
        by_name = {r.input_file.name: r.result.outcome for r in results}

        assert by_name["good.dcm"] is Outcome.DEIDENTIFIED, "Valid file should deidentify"
        assert by_name["bad.dcm"] is Outcome.QUARANTINED, "Invalid file should be quarantined"

    def test_no_empty_dir_for_quarantined(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A quarantined nested input leaves no empty mirrored directory."""
        source = tmp_path / "src"
        (source / "nested").mkdir(parents=True)
        (source / "nested" / "bad.dcm").write_bytes(b"not a dicom file")
        out = tmp_path / "out"

        list(deidentify_paths([source], out, profile=_profile(), recursive=True))

        assert not (out / "nested").exists(), "No empty mirrored dir should remain for a quarantined input"


class TestOutputCollisions:
    """Test fail-fast detection of colliding output paths."""

    def test_basename_collision_raises_without_rename(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Two explicit files sharing a basename raise before any file is written."""
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        a = a_dir / "scan.dcm"
        b = b_dir / "scan.dcm"
        shutil.copy2(signa_premier_file, a)
        shutil.copy2(signa_premier_file, b)
        out = tmp_path / "out"

        with pytest.raises(OutputPathCollisionError):
            list(deidentify_paths([a, b], out, profile=_profile(), rename_to_sop_uid=False))

        assert not out.exists() or not any(out.iterdir()), "No output should be written when a collision is detected"

    def test_collision_check_runs_before_processing(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """The collision error is raised on first iteration, before writing outputs."""
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        shutil.copy2(signa_premier_file, a_dir / "scan.dcm")
        shutil.copy2(signa_premier_file, b_dir / "scan.dcm")
        out = tmp_path / "out"

        generator = deidentify_paths(
            [a_dir / "scan.dcm", b_dir / "scan.dcm"],
            out,
            profile=_profile(),
            rename_to_sop_uid=False,
        )
        with pytest.raises(OutputPathCollisionError):
            next(generator)

    def test_no_collision_with_sop_uid_rename(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """SOP-UID renaming makes shared basenames unique, so no error is raised."""
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        shutil.copy2(signa_premier_file, a_dir / "scan.dcm")
        shutil.copy2(signa_premier_file, b_dir / "scan.dcm")
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [a_dir / "scan.dcm", b_dir / "scan.dcm"],
                out,
                profile=_profile(),
                rename_to_sop_uid=True,
            )
        )

        assert len(results) == 2, "Both files should process under SOP-UID rename"
        assert all(r.result.outcome is Outcome.DEIDENTIFIED for r in results), "Both should deidentify"

    def test_distinct_basenames_do_not_collide(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Different basenames without rename produce distinct outputs, no error."""
        a = tmp_path / "a.dcm"
        b = tmp_path / "b.dcm"
        shutil.copy2(signa_premier_file, a)
        shutil.copy2(signa_premier_file, b)
        out = tmp_path / "out"

        results = list(deidentify_paths([a, b], out, profile=_profile(), rename_to_sop_uid=False))

        assert len(results) == 2, "Both distinct files should process"
        assert (out / "a.dcm").exists() and (out / "b.dcm").exists(), "Distinct basenames land separately"


def _spec() -> ProfileSpec:
    """Build the picklable profile spec matching the sequential test profile."""
    return ProfileSpec(name="default", settings=ProfileSettings(uid_root="1.2.3"))


class TestParallelDeidentifyPaths:
    """Test the multiprocessing batch path (workers > 1)."""

    def test_workers_below_one_raises(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A worker count below one raises before any file is processed."""
        with pytest.raises(ValueError, match="workers must be >= 1"):
            list(deidentify_paths([signa_premier_file], tmp_path / "out", profile=_profile(), workers=0))

    def test_parallel_requires_profile_spec(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Parallel execution without a profile spec raises a descriptive error."""
        with pytest.raises(ValueError, match="profile_spec"):
            list(deidentify_paths([signa_premier_file], tmp_path / "out", profile=_profile(), workers=2))

    def test_parallel_builds_profile_from_spec_only(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Parallel runs work with only a profile spec and no prebuilt profile."""
        source = tmp_path / "src"
        source.mkdir()
        shutil.copy2(signa_premier_file, source / "one.dcm")
        shutil.copy2(signa_premier_file, source / "two.dcm")
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [source],
                out,
                profile_spec=_spec(),
                workers=2,
                rename_to_sop_uid=False,
            )
        )

        assert len(results) == 2, "Both inputs should process from the spec alone"
        assert all(r.result.outcome is Outcome.DEIDENTIFIED for r in results), "Both inputs should deidentify"

    def test_parallel_processes_all_inputs(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Every discovered input is de-identified and written under the output dir."""
        source = tmp_path / "src"
        source.mkdir()
        for name in ("one.dcm", "two.dcm", "three.dcm"):
            shutil.copy2(signa_premier_file, source / name)
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [source],
                out,
                profile=_profile(),
                profile_spec=_spec(),
                workers=2,
                rename_to_sop_uid=False,
            )
        )

        assert len(results) == 3, "All three inputs should produce a result"
        assert all(r.result.outcome is Outcome.DEIDENTIFIED for r in results), "All inputs should deidentify"
        written = {p.name for p in out.iterdir()}
        assert written == {"one.dcm", "two.dcm", "three.dcm"}, "All outputs should be written"

    def test_parallel_mirrors_directory_tree(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Parallel runs mirror source subtrees like the sequential path does."""
        source = tmp_path / "src"
        (source / "a").mkdir(parents=True)
        (source / "b").mkdir(parents=True)
        shutil.copy2(signa_premier_file, source / "a" / "one.dcm")
        shutil.copy2(signa_premier_file, source / "b" / "two.dcm")
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [source],
                out,
                profile=_profile(),
                profile_spec=_spec(),
                workers=2,
                recursive=True,
                rename_to_sop_uid=False,
            )
        )

        assert len(results) == 2, "Both nested files should be processed"
        assert (out / "a" / "one.dcm").exists(), "Subtree 'a' should be mirrored"
        assert (out / "b" / "two.dcm").exists(), "Subtree 'b' should be mirrored"

    def test_parallel_quarantines_non_dicom(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A non-DICOM input is quarantined while valid inputs still process."""
        source = tmp_path / "src"
        source.mkdir()
        shutil.copy2(signa_premier_file, source / "good.dcm")
        (source / "bad.dcm").write_bytes(b"not a dicom file")
        out = tmp_path / "out"

        results = list(
            deidentify_paths(
                [source],
                out,
                profile=_profile(),
                profile_spec=_spec(),
                workers=2,
                rename_to_sop_uid=False,
            )
        )
        by_name = {r.input_file.name: r.result.outcome for r in results}

        assert by_name["good.dcm"] is Outcome.DEIDENTIFIED, "Valid file should deidentify"
        assert by_name["bad.dcm"] is Outcome.QUARANTINED, "Invalid file should be quarantined"

    def test_parallel_no_empty_dir_for_quarantined(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A quarantined nested input leaves no empty mirrored directory."""
        source = tmp_path / "src"
        (source / "nested").mkdir(parents=True)
        (source / "nested" / "bad.dcm").write_bytes(b"not a dicom file")
        out = tmp_path / "out"

        list(
            deidentify_paths(
                [source],
                out,
                profile=_profile(),
                profile_spec=_spec(),
                workers=2,
                recursive=True,
            )
        )

        assert not (out / "nested").exists(), "No empty mirrored dir should remain for a quarantined input"

    def test_parallel_collision_check_still_applies(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """Colliding outputs fail fast even when parallel workers are requested."""
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        shutil.copy2(signa_premier_file, a_dir / "scan.dcm")
        shutil.copy2(signa_premier_file, b_dir / "scan.dcm")
        out = tmp_path / "out"

        with pytest.raises(OutputPathCollisionError):
            list(
                deidentify_paths(
                    [a_dir / "scan.dcm", b_dir / "scan.dcm"],
                    out,
                    profile=_profile(),
                    profile_spec=_spec(),
                    workers=2,
                    rename_to_sop_uid=False,
                )
            )


class TestProfileSpec:
    """Test the picklable profile specification used for worker processes."""

    def test_profile_spec_is_picklable(self) -> None:
        """A profile spec round-trips through pickle so it can cross processes."""
        import pickle

        spec = _spec()
        restored = pickle.loads(pickle.dumps(spec))  # noqa: S301  round-trip of trusted local data
        assert restored == spec, "ProfileSpec should survive a pickle round-trip"

    def test_sequential_builds_profile_from_spec_only(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A sequential run builds the profile from the spec when none is passed."""
        a = tmp_path / "a.dcm"
        shutil.copy2(signa_premier_file, a)
        out = tmp_path / "out"

        results = list(deidentify_paths([a], out, profile_spec=_spec(), rename_to_sop_uid=False))

        assert len(results) == 1, "The input should be processed from the spec alone"
        assert results[0].result.outcome is Outcome.DEIDENTIFIED, "The input should deidentify"

    def test_missing_profile_and_spec_raises(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A sequential run needs either a profile or a spec to build one."""
        with pytest.raises(ValueError, match="either profile or profile_spec"):
            list(deidentify_paths([signa_premier_file], tmp_path / "out"))


class TestDeidParametersInBatch:
    """DeidParameters travel with the batch and reach worker processes."""

    def test_deid_parameters_hashable_and_picklable(self) -> None:
        """DeidParameters can be hashed and pickled for cross-process transport."""
        import pickle

        from dicom_dre import DeidParameters

        params = DeidParameters(patient_id="P", accession_number="A", study_id="S", jitter=4)
        assert hash(params) == hash(params), "DeidParameters should be hashable"
        restored = pickle.loads(pickle.dumps(params))  # noqa: S301  round-trip of trusted local data
        assert restored == params, "DeidParameters should survive a pickle round-trip"

    def test_from_mapping_reads_identity_keys_and_parses_jitter(self) -> None:
        """from_mapping reads identity keys and parses JITTER to an int."""
        from dicom_dre import DeidParameters

        params = DeidParameters.from_mapping({"PATIENT_ID": "P", "JITTER": "12"})
        assert params.patient_id == "P", "PATIENT_ID should be read"
        assert params.jitter == 12, "JITTER should be parsed to an int"

    def test_from_mapping_rejects_unknown_key(self) -> None:
        """from_mapping rejects build settings and other non-identity keys."""
        from dicom_dre import DeidParameters

        with pytest.raises(ValueError, match="Unknown de-identification parameter"):
            DeidParameters.from_mapping({"PATIENT_ID": "P", "UIDROOT": "1.2.3"})

    def test_from_mapping_rejects_non_integer_jitter(self) -> None:
        """from_mapping raises when JITTER is not an integer."""
        from dicom_dre import DeidParameters

        with pytest.raises(ValueError, match="JITTER"):
            DeidParameters.from_mapping({"JITTER": "soon"})

    def test_parallel_applies_parameters(self, signa_premier_file: Path, tmp_path: Path) -> None:
        """A parallel run applies the supplied parameters in worker processes."""
        import pydicom
        from pydicom.tag import Tag

        from dicom_dre import DeidParameters

        source = tmp_path / "src"
        source.mkdir()
        shutil.copy2(signa_premier_file, source / "one.dcm")
        out = tmp_path / "out"

        params = DeidParameters(patient_id="WORKER_ID", accession_number="WORKER_ACC")
        results = list(
            deidentify_paths(
                [source],
                out,
                parameters=params,
                profile_spec=_spec(),
                workers=2,
                rename_to_sop_uid=False,
            )
        )

        assert len(results) == 1, "The single input should be processed"
        assert results[0].result.parameters == params, "The result should carry the supplied parameters"
        ds = pydicom.dcmread(out / "one.dcm", force=True)
        assert str(ds[Tag(0x0010, 0x0020)].value) == "WORKER_ID", "worker should apply the supplied PatientID"
