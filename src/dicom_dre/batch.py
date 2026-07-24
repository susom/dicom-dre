"""Batch de-identification over files and directories.

Provides :func:`deidentify_paths`, a generator that de-identifies every DICOM
file discovered under a set of source paths, mirroring each source directory
tree under a single output directory. The pipeline entry point
(:func:`dicom_dre.pipeline.deidentify_file`) is reused unchanged per input.

Execution is sequential by default (``workers=1``). Passing ``workers`` greater
than one dispatches each file to a :class:`concurrent.futures.ProcessPoolExecutor`
worker pool. Because a bound :class:`~dicom_dre.profile.DeidProfile` holds
closures that cannot be pickled, parallel runs build the profile once inside
each worker from a picklable :class:`ProfileSpec` rather than in the parent;
callers must supply that spec when ``workers`` exceeds one. Sequential runs use
a caller-supplied ``profile`` or, when omitted, build one from the spec.
"""

from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed
from dataclasses import dataclass
from dataclasses import field
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from dicom_dre.pipeline import deidentify_file
from dicom_dre.profiles.builder import build_profile
from dicom_dre.result import BatchItemResult
from dicom_dre.result import DeidentifyResult
from dicom_dre.result import Outcome


if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from collections.abc import Sequence

    from dicom_dre.catalog import DeviceCatalog
    from dicom_dre.profile import DeidProfile


DEFAULT_PATTERNS: tuple[str, ...] = ("*.dcm", "*.dicom")


@dataclass(frozen=True)
class ProfileSpec:
    """Picklable description of a de-identification profile.

    A bound :class:`~dicom_dre.profile.DeidProfile` cannot cross a process
    boundary because its tag rules are closures. This spec carries the profile
    name and runtime parameters instead, so each worker process can rebuild the
    profile with :func:`dicom_dre.build_profile`.

    Attributes:
        name: Profile name accepted by :func:`dicom_dre.build_profile`.
        parameters: Runtime parameter mapping consumed as-is.
    """

    name: str
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _BatchOptions:
    """Picklable per-file processing options shared across a batch run."""

    decompress: bool
    rename_to_sop_uid: bool
    highlight_blanked_pixels: bool


class OutputPathCollisionError(ValueError):
    """Two discovered inputs would be written to the same output path.

    Raised before any file is written when ``rename_to_sop_uid`` is disabled and
    the derived output paths are not unique (for example, two explicitly listed
    files that share a basename). With SOP-UID renaming the output names are
    unique by construction, so this is never raised.
    """


def _matches_any(name: str, patterns: Iterable[str]) -> bool:
    """Return whether ``name`` matches any pattern case-insensitively."""
    lowered = name.lower()
    return any(fnmatch(lowered, pattern.lower()) for pattern in patterns)


def _discover_inputs(
    sources: Sequence[Path],
    *,
    recursive: bool,
    patterns: Sequence[str],
) -> Iterator[tuple[Path, Path]]:
    """Yield ``(input_path, relative_output_subpath)`` pairs for the sources.

    Explicit file arguments are always included with a flat filename subpath and
    are not subject to the extension filter. Directory arguments are walked and
    every candidate file is filtered by ``patterns`` (case-insensitively); the
    subpath is the file path relative to that directory root. Results are
    de-duplicated while preserving discovery order.

    Args:
        sources: The source files and/or directories to process.
        recursive: Whether to descend into subdirectories of directory sources.
        patterns: Filename glob patterns applied to directory-scan candidates.

    Yields:
        Tuples of the input path and its output subpath relative to the output
        directory root.
    """
    seen: set[Path] = set()
    for source in sources:
        if source.is_dir():
            candidates = source.rglob("*") if recursive else source.glob("*")
            for candidate in sorted(candidates):
                if not candidate.is_file():
                    continue
                if not _matches_any(candidate.name, patterns):
                    continue
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield candidate, candidate.relative_to(source)
        else:
            resolved = source.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield source, Path(source.name)


def _raise_on_output_collisions(discovered: Sequence[tuple[Path, Path]], output_dir: Path) -> None:
    """Raise if any two inputs map to the same output path.

    Args:
        discovered: The ``(input_path, relative_output_subpath)`` pairs to check.
        output_dir: Root directory the subpaths are resolved against, used only
            to render absolute output paths in the error message.

    Raises:
        OutputPathCollisionError: If two or more inputs share an output subpath.
    """
    by_output: dict[Path, list[Path]] = {}
    for input_file, subpath in discovered:
        by_output.setdefault(subpath, []).append(input_file)

    collisions = {subpath: inputs for subpath, inputs in by_output.items() if len(inputs) > 1}
    if not collisions:
        return

    lines = [
        f"  {', '.join(str(input_file) for input_file in inputs)} -> {output_dir / subpath}"
        for subpath, inputs in collisions.items()
    ]
    raise OutputPathCollisionError(
        "--no-rename-to-sop-uid would write multiple inputs to the same output path:\n" + "\n".join(lines)
    )


def deidentify_paths(
    sources: Sequence[Path],
    output_dir: Path,
    *,
    profile: DeidProfile | None = None,
    catalog: DeviceCatalog | None = None,
    recursive: bool = False,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
    decompress: bool = False,
    rename_to_sop_uid: bool = True,
    highlight_blanked_pixels: bool = False,
    workers: int = 1,
    profile_spec: ProfileSpec | None = None,
) -> Iterator[BatchItemResult]:
    """De-identify every DICOM file discovered under ``sources``.

    Mirrors each source directory tree under ``output_dir``; explicitly listed
    files land flat in ``output_dir``. Discovery and output-directory creation
    errors are turned into ``QUARANTINED`` results so processing continues; the
    pipeline itself already quarantines its own internal errors.

    With ``workers == 1`` (default) inputs are processed sequentially in
    discovery order. The profile is taken from ``profile`` if given, otherwise
    built once in this process from ``profile_spec``. With ``workers`` greater
    than one, inputs are dispatched to a
    :class:`concurrent.futures.ProcessPoolExecutor` and results are yielded as
    each worker completes (not in discovery order). A bound profile cannot be
    pickled, so parallel runs require ``profile_spec`` and build the profile
    once per worker; ``profile`` is not built or used in that case.

    Because ``profile_spec`` is limited to what :func:`dicom_dre.build_profile`
    can construct (the registered named profiles), parallel runs support only
    those profiles. An arbitrary hand-built :class:`~dicom_dre.profile.DeidProfile`
    that no ``profile_spec`` can describe must be passed as ``profile`` and run
    sequentially (``workers == 1``), since its rules cannot cross a process
    boundary.

    When ``rename_to_sop_uid`` is disabled the derived output paths must be
    unique; if two inputs would be written to the same path the run fails fast
    with :class:`OutputPathCollisionError` before any file is written.

    Args:
        sources: The source files and/or directories to process.
        output_dir: Root directory under which de-identified files are written.
        profile: The bound de-identification profile to apply. Optional; for a
            sequential run it is built from ``profile_spec`` when omitted, and it
            is ignored entirely for parallel runs.
        catalog: Device catalog for filtering and pixel-scrub decisions.
            Defaults to :func:`dicom_dre.get_default_catalog`.
        recursive: Whether to descend into subdirectories of directory sources.
        patterns: Filename glob patterns applied to directory-scan candidates.
        decompress: Whether to decompress encapsulated pixel data on output.
        rename_to_sop_uid: Rename each output file to its new SOP Instance UID.
        highlight_blanked_pixels: Fill scrubbed regions with a visible color.
        workers: Number of worker processes. ``1`` runs sequentially in-process.
        profile_spec: Picklable profile description used to rebuild the profile
            in each worker. Required when ``workers`` is greater than one, and
            used to build the sequential profile when ``profile`` is omitted.

    Yields:
        One :class:`BatchItemResult` per discovered input. Ordered by discovery
        when ``workers == 1``; ordered by completion when ``workers > 1``.

    Raises:
        ValueError: If ``workers`` is less than one, if neither ``profile`` nor
            ``profile_spec`` is provided for a sequential run, or if ``workers``
            is greater than one without a ``profile_spec``.
        OutputPathCollisionError: If ``rename_to_sop_uid`` is disabled and two
            inputs map to the same output path.
    """
    if workers < 1:
        raise ValueError("workers must be >= 1")

    discovered: Iterable[tuple[Path, Path]] = _discover_inputs(
        sources,
        recursive=recursive,
        patterns=patterns,
    )
    if not rename_to_sop_uid:
        discovered = list(discovered)
        _raise_on_output_collisions(discovered, output_dir)

    options = _BatchOptions(
        decompress=decompress,
        rename_to_sop_uid=rename_to_sop_uid,
        highlight_blanked_pixels=highlight_blanked_pixels,
    )

    if workers == 1:
        if profile is None:
            if profile_spec is None:
                raise ValueError("deidentify_paths requires either profile or profile_spec")
            profile = build_profile(profile_spec.name, profile_spec.parameters)
        yield from _run_sequential(discovered, output_dir, profile=profile, catalog=catalog, options=options)
        return

    if profile_spec is None:
        raise ValueError("workers > 1 requires profile_spec to rebuild the profile in worker processes")

    yield from _run_parallel(
        discovered,
        output_dir,
        profile_spec=profile_spec,
        catalog=catalog,
        workers=workers,
        options=options,
    )


def _run_sequential(
    discovered: Iterable[tuple[Path, Path]],
    output_dir: Path,
    *,
    profile: DeidProfile,
    catalog: DeviceCatalog | None,
    options: _BatchOptions,
) -> Iterator[BatchItemResult]:
    """De-identify each discovered input in-process, in discovery order."""
    for input_file, relative_subpath in discovered:
        output_file = output_dir / relative_subpath
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            yield BatchItemResult(
                input_file=input_file,
                result=DeidentifyResult.quarantined(error=str(error)),
            )
            continue

        result = deidentify_file(
            input_file=input_file,
            output_file=output_file,
            profile=profile,
            catalog=catalog,
            decompress=options.decompress,
            rename_to_sop_uid=options.rename_to_sop_uid,
            highlight_blanked_pixels=options.highlight_blanked_pixels,
        )

        if result.outcome is not Outcome.DEIDENTIFIED:
            _remove_empty_dir(output_file.parent, output_dir)

        yield BatchItemResult(input_file=input_file, result=result)


def _run_parallel(
    discovered: Iterable[tuple[Path, Path]],
    output_dir: Path,
    *,
    profile_spec: ProfileSpec,
    catalog: DeviceCatalog | None,
    workers: int,
    options: _BatchOptions,
) -> Iterator[BatchItemResult]:
    """De-identify discovered inputs across a process pool, yielding as completed.

    Output directories are created in the parent before a task is submitted so a
    creation failure becomes a ``QUARANTINED`` result without starting a worker.
    A worker that dies (for example a native crash) surfaces as a
    ``QUARANTINED`` result for the affected input rather than aborting the run.
    """
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(profile_spec, catalog, options),
    ) as executor:
        futures: dict[Future[DeidentifyResult], tuple[Path, Path]] = {}
        for input_file, relative_subpath in discovered:
            output_file = output_dir / relative_subpath
            try:
                output_file.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                yield BatchItemResult(
                    input_file=input_file,
                    result=DeidentifyResult.quarantined(error=str(error)),
                )
                continue
            future = executor.submit(_process_one, input_file, output_file)
            futures[future] = (input_file, output_file)

        for future in as_completed(futures):
            input_file, output_file = futures[future]
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001  worker crash is a process boundary
                result = DeidentifyResult.quarantined(error=str(error))

            if result.outcome is not Outcome.DEIDENTIFIED:
                _remove_empty_dir(output_file.parent, output_dir)

            yield BatchItemResult(input_file=input_file, result=result)


_WORKER_PROFILE: DeidProfile | None = None
_WORKER_CATALOG: DeviceCatalog | None = None
_WORKER_OPTIONS: _BatchOptions | None = None


def _init_worker(
    profile_spec: ProfileSpec,
    catalog: DeviceCatalog | None,
    options: _BatchOptions,
) -> None:
    """Initialize per-process worker state for a parallel batch run.

    Rebuilds the bound profile from ``profile_spec`` once per worker (a bound
    profile is not picklable) and stashes the catalog and options in module
    globals so :func:`_process_one` can reuse them across tasks.
    """
    global _WORKER_PROFILE, _WORKER_CATALOG, _WORKER_OPTIONS
    _WORKER_PROFILE = build_profile(profile_spec.name, profile_spec.parameters)
    _WORKER_CATALOG = catalog
    _WORKER_OPTIONS = options


def _process_one(input_file: Path, output_file: Path) -> DeidentifyResult:
    """De-identify one input in a worker process using initialized state."""
    if _WORKER_PROFILE is None or _WORKER_OPTIONS is None:
        raise RuntimeError("worker state was not initialized")
    return deidentify_file(
        input_file=input_file,
        output_file=output_file,
        profile=_WORKER_PROFILE,
        catalog=_WORKER_CATALOG,
        decompress=_WORKER_OPTIONS.decompress,
        rename_to_sop_uid=_WORKER_OPTIONS.rename_to_sop_uid,
        highlight_blanked_pixels=_WORKER_OPTIONS.highlight_blanked_pixels,
    )


def _remove_empty_dir(directory: Path, stop_at: Path) -> None:
    """Remove ``directory`` and empty parents up to (but excluding) ``stop_at``.

    Used to avoid leaving stray mirrored directories when an input did not
    produce an output file (FILTERED or QUARANTINED outcomes).
    """
    try:
        stop_resolved = stop_at.resolve()
        current = directory.resolve()
    except OSError:
        return
    while current != stop_resolved and stop_resolved in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
