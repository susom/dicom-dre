"""Command-line interface for the DICOM De-identification & Redaction Engine.

Exposes the batch engine entry point (:func:`dicom_dre.deidentify_paths`)
as a ``dicom-dre`` console script. The CLI performs no hashing, settings lookups,
or free-text redaction: de-identification parameters are consumed as-is, mirroring
the library contract.
"""

from __future__ import annotations

import csv
import importlib.resources as pkg_resources
import os
from pathlib import Path

import click

from dicom_dre import __version__
from dicom_dre import deidentify_paths
from dicom_dre.batch import OutputPathCollisionError
from dicom_dre.batch import ProfileSpec
from dicom_dre.parameters import DeidParameters
from dicom_dre.profiles.builder import BUILD_CONFIG_KEYS
from dicom_dre.profiles.builder import list_profiles
from dicom_dre.result import Outcome
from dicom_dre.text_redactor import TextRedactor
from dicom_dre.text_redactor import extract_unique_tokens
from dicom_dre.text_redactor import interactive_quality_check_csv_file
from dicom_dre.text_redactor import print_redacted_tokens
from dicom_dre.text_redactor import process_csv_file
from dicom_dre.text_redactor import quality_check_csv_file
from dicom_dre.text_redactor import save_allowlist_to_csv


def _parse_parameters(pairs: tuple[str, ...]) -> dict[str, str]:
    """Parse ``KEY=VALUE`` strings into a parameter dict.

    Args:
        pairs: The raw ``KEY=VALUE`` strings collected from ``--param``.

    Returns:
        A mapping of parameter name to value.

    Raises:
        click.BadParameter: If any entry is not of the form ``KEY=VALUE`` or
            has an empty key.
    """
    parameters: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise click.BadParameter(
                f"expected KEY=VALUE, got {pair!r}",
                param_hint="--param",
            )
        parameters[key] = value
    return parameters


@click.group(context_settings={"max_content_width": 120})
@click.version_option(version=__version__, prog_name="dicom-dre")
def cli() -> None:
    """DICOM De-identification & Redaction Engine."""


@cli.command(
    short_help="De-identify DICOM files and directories into an output directory.",
    epilog=(
        "Examples:\n\n"
        "  dicom-dre deidentify scan.dcm -o out/\n\n"
        "  dicom-dre deidentify studies/ -o out/ -r\n\n"
        "  dicom-dre deidentify a.dcm b.dcm dir/ -o out/\n\n"
        "Each source is read but never modified. Directory trees are mirrored "
        "under the output directory; explicitly listed files land flat. Output "
        "filenames are the new SOP Instance UID by default; with "
        "--no-rename-to-sop-uid the input basename is kept, and the command "
        "fails before writing anything if two inputs would resolve to the same "
        "output path."
    ),
)
@click.argument(
    "sources",
    metavar="SOURCES...",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to write de-identified files into (created if needed).",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Recurse into subdirectories of directory sources.",
)
@click.option(
    "--glob",
    "globs",
    multiple=True,
    default=("*.dcm", "*.dicom"),
    show_default=True,
    metavar="PATTERN",
    help="Filename pattern for directory scans (repeatable, case-insensitive).",
)
@click.option(
    "--profile",
    "profile_name",
    type=click.Choice(list_profiles()),
    default="default",
    show_default=True,
    help="De-identification profile to apply.",
)
@click.option(
    "--param",
    "-p",
    "params",
    multiple=True,
    metavar="KEY=VALUE",
    help="A de-identification parameter (repeatable), e.g. -p PATIENT_ID=TEST.",
)
@click.option(
    "--decompress/--no-decompress",
    default=False,
    show_default=True,
    help="Decompress encapsulated pixel data on output.",
)
@click.option(
    "--rename-to-sop-uid/--no-rename-to-sop-uid",
    default=True,
    show_default=True,
    help="Rename each output file to its new SOP Instance UID.",
)
@click.option(
    "--highlight-blanked-pixels",
    is_flag=True,
    default=False,
    help="Fill scrubbed pixel regions with a visible color.",
)
@click.option(
    "--workers",
    "-j",
    type=click.IntRange(min=1),
    default=lambda: os.cpu_count() or 1,
    show_default="number of CPUs",
    metavar="N",
    help="Number of worker processes; 1 runs sequentially in-process.",
)
def deidentify(
    sources: tuple[Path, ...],
    output_dir: Path,
    recursive: bool,
    globs: tuple[str, ...],
    profile_name: str,
    params: tuple[str, ...],
    decompress: bool,
    rename_to_sop_uid: bool,
    highlight_blanked_pixels: bool,
    workers: int,
) -> None:
    """De-identify one or more DICOM files or directories.

    \b
    SOURCES is one or more files and/or directories, all read unchanged.
    Directory trees are mirrored under OUTPUT_DIR; explicitly listed files land
    flat. One line is printed per processed file, followed by a summary. With
    --workers greater than 1 files are processed across worker processes and
    lines are printed as each file completes rather than in discovery order. The
    command exits with status 1 if any file was QUARANTINED; FILTERED files are
    a normal outcome and do not affect the exit code.
    """
    parameters = _parse_parameters(params)
    config = {key: value for key, value in parameters.items() if key in BUILD_CONFIG_KEYS}
    profile_spec = ProfileSpec(name=profile_name, config=config)
    try:
        deid_parameters = DeidParameters.from_mapping(parameters)
    except ValueError as error:
        raise click.BadParameter(str(error), param_hint="--param") from error

    counts = {Outcome.DEIDENTIFIED: 0, Outcome.FILTERED: 0, Outcome.QUARANTINED: 0}
    items = deidentify_paths(
        sources=list(sources),
        output_dir=output_dir,
        parameters=deid_parameters,
        recursive=recursive,
        patterns=globs,
        decompress=decompress,
        rename_to_sop_uid=rename_to_sop_uid,
        highlight_blanked_pixels=highlight_blanked_pixels,
        workers=workers,
        profile_spec=profile_spec,
    )
    try:
        for item in items:
            result = item.result
            counts[result.outcome] += 1
            if result.outcome is Outcome.DEIDENTIFIED:
                click.echo(f"DEIDENTIFIED: {item.input_file} -> {result.output_file}")
            elif result.outcome is Outcome.FILTERED:
                click.echo(f"FILTERED: {item.input_file} ({result.filter_reason})")
            else:
                click.echo(f"QUARANTINED: {item.input_file} ({result.error})", err=True)
    except OutputPathCollisionError as error:
        raise click.UsageError(str(error)) from error

    total = sum(counts.values())
    click.echo(
        f"Summary: {total} processed, "
        f"{counts[Outcome.DEIDENTIFIED]} deidentified, "
        f"{counts[Outcome.FILTERED]} filtered, "
        f"{counts[Outcome.QUARANTINED]} quarantined."
    )
    if counts[Outcome.QUARANTINED] > 0:
        raise SystemExit(1)


def _resolve_allowlist_path(allowlist: str) -> Path:
    """Resolve an allowlist filename or absolute path to a concrete Path.

    Args:
        allowlist: Either a filename such as ``"default.csv"`` resolved against
            the packaged ``dicom_dre.resources.allow_lists`` data, or an
            absolute path to a CSV file.

    Returns:
        The resolved path to the allowlist CSV.

    Raises:
        ValueError: If the allowlist cannot be located.
    """
    allowlist_path = Path(allowlist)
    if allowlist_path.is_absolute() and allowlist_path.exists():
        return allowlist_path

    from dicom_dre.resources import allow_lists

    resources_path = Path(str(pkg_resources.files(allow_lists))) / allowlist
    if not resources_path.exists():
        raise ValueError(f"Allowlist not found: {resources_path}")
    return resources_path


def _add_tokens_to_allowlist(allowlist_path: Path, tokens: list[str]) -> int:
    """Add tokens to an allowlist CSV, writing atomically.

    Args:
        allowlist_path: Path to the allowlist CSV file.
        tokens: Tokens to add; whitespace is stripped and duplicates skipped.

    Returns:
        The number of new tokens added.
    """
    existing_tokens: set[str] = set()
    with open(allowlist_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                existing_tokens.add(row[0])

    tokens_to_add = [token.strip() for token in tokens if token.strip() and token.strip() not in existing_tokens]
    if not tokens_to_add:
        return 0

    all_tokens = sorted(existing_tokens.union(tokens_to_add), key=str.lower)
    temp_path = allowlist_path.with_suffix(".tmp")
    with open(temp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for token in all_tokens:
            writer.writerow([token])
    temp_path.replace(allowlist_path)
    return len(tokens_to_add)


@cli.group()
def redactor() -> None:
    """Free-text redaction operations for description fields."""


@redactor.command("redact")
@click.option("--track-redacted", is_flag=True, help="Also write the distinct tokens that were redacted.")
@click.option(
    "--allowlist",
    default="default.csv",
    show_default=True,
    help="Allowlist filename (e.g. 'default.csv') or absolute path to an allowlist CSV.",
)
@click.option("--preserve-dates", is_flag=True, help="Keep dates and times in text (for HIPAA limited datasets).")
@click.option(
    "--input",
    "input_",
    default="input.csv",
    show_default=True,
    help="Path to the input CSV file. Every cell of every row is redacted; no header row required.",
)
@click.option("--output", default="output.csv", show_default=True, help="Path to the output CSV file.")
def redact_command(track_redacted: bool, allowlist: str, preserve_dates: bool, input_: str, output: str) -> None:
    """Redact free text from an input CSV and write the result to OUTPUT.

    \b
    The input CSV holds free text to de-identify. Every cell of every row is
    treated as an independent piece of text; no header row is required and the
    column layout does not matter. The output CSV mirrors the input, with
    tokens absent from the allowlist replaced by a redaction marker.
    """
    allowlist_path = _resolve_allowlist_path(allowlist)
    redactor_instance = TextRedactor(preserve_dates=preserve_dates)
    redactor_instance.load_allowlist_from_csv(allowlist_path)

    all_redacted_tokens = process_csv_file(redactor_instance, input_, output, track_redacted)
    click.echo(f"Redacted text has been written to {output}")

    if track_redacted and all_redacted_tokens:
        redacted_tokens_file = f"{output.rsplit('.', 1)[0]}_redacted_tokens.csv"
        with open(redacted_tokens_file, "w", newline="", encoding="utf-8") as token_file:
            writer = csv.writer(token_file)
            writer.writerow(["Redacted Tokens"])
            for token in sorted(all_redacted_tokens, key=str.lower):
                writer.writerow([token])
        click.echo(f"Redacted tokens have been written to {redacted_tokens_file}")


@redactor.command(
    "quality-check",
    short_help="Preview redaction of a CSV of free text side by side.",
)
@click.option(
    "--allowlist",
    default="default.csv",
    show_default=True,
    help="Allowlist filename (e.g. 'default.csv') or absolute path to an allowlist CSV.",
)
@click.option("--preserve-dates", is_flag=True, help="Keep dates and times in text (for HIPAA limited datasets).")
@click.option("--redacted-only", is_flag=True, help="Only display cells that were redacted.")
@click.option("--simple", is_flag=True, help="Only print tokens that would be redacted (sorted, de-duplicated).")
@click.option("--interactive", is_flag=True, help="Interactively review and add tokens to the allowlist.")
@click.argument("input_", metavar="INPUT", default="input.csv")
def quality_check_command(
    allowlist: str,
    preserve_dates: bool,
    redacted_only: bool,
    simple: bool,
    interactive: bool,
    input_: str,
) -> None:
    """Display original and redacted text side by side for INPUT.

    \b
    INPUT is a CSV file (default: input.csv). Every cell of every row is
    treated as an independent piece of free text to redact; no header row is
    required and the column layout does not matter. For example, a file with
    one description per line is valid:

    \b
        CHEST X-RAY, John Smith, MRN 12345
        CT ABDOMEN Dr. Jones 555-1234

    Tokens not present in the allowlist are replaced with a redaction marker.
    """
    allowlist_path = _resolve_allowlist_path(allowlist)
    redactor_instance = TextRedactor(preserve_dates=preserve_dates)
    redactor_instance.load_allowlist_from_csv(allowlist_path)

    if interactive:
        tokens_to_add = interactive_quality_check_csv_file(redactor_instance, input_, allowlist_path)
        click.echo("\n" + "=" * 60)
        click.echo(click.style("Review Summary", bold=True))
        click.echo("=" * 60)
        if not tokens_to_add:
            click.echo("\nNo changes queued.")
            return
        click.echo(f"\n{click.style('Tokens to add:', fg='green', bold=True)}")
        for token in sorted(tokens_to_add, key=str.lower):
            click.echo(f"  + {token}")
        click.echo()
        if click.confirm("Apply these changes to the allowlist?", default=True):
            save_allowlist_to_csv(allowlist_path, tokens_to_add)
            click.echo(click.style(f"Allowlist updated: {len(tokens_to_add)} added", fg="green", bold=True))
        else:
            click.echo("Changes cancelled.")
    elif simple:
        print_redacted_tokens(redactor_instance, input_)
    else:
        quality_check_csv_file(redactor_instance, input_, redacted_only)
        click.echo(f"Quality check completed for {input_}")


@redactor.command("show-tokens")
@click.option(
    "--input",
    "input_",
    default="input.csv",
    show_default=True,
    help="Path to the input CSV file. Every cell of every row is tokenized; no header row required.",
)
def show_tokens_command(input_: str) -> None:
    """Extract and display all unique tokens from INPUT.

    \b
    The input CSV holds free text. Every cell of every row is split into
    tokens; no header row is required and the column layout does not matter.
    The distinct tokens are printed sorted, one per line. Use this to discover
    candidate terms to add to an allowlist.
    """
    redactor_instance = TextRedactor()
    unique_tokens = extract_unique_tokens(redactor_instance, input_)
    if unique_tokens:
        for token in sorted(unique_tokens, key=str.lower):
            click.echo(token)
        click.echo(f"\nTotal unique tokens: {len(unique_tokens)}")
    else:
        click.echo("No tokens found in the file.")


@redactor.command("allow-token")
@click.option(
    "--allowlist",
    default="default.csv",
    show_default=True,
    help="Allowlist filename (e.g. 'default.csv') or absolute path to an allowlist CSV.",
)
@click.argument("tokens", nargs=-1, required=True)
def allow_token_command(allowlist: str, tokens: tuple[str, ...]) -> None:
    """Add one or more TOKENS to the allowlist file.

    Tokens are stripped of whitespace and inserted in sorted order; duplicates
    are skipped.
    """
    allowlist_path = _resolve_allowlist_path(allowlist)
    tokens_added = _add_tokens_to_allowlist(allowlist_path, list(tokens))
    if tokens_added == 0:
        click.echo("No new tokens to add (all tokens already in allowlist)")
    else:
        click.echo(f"Added {tokens_added} token(s) to {allowlist_path}")


if __name__ == "__main__":
    cli()
