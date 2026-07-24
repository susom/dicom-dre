# Redactor Commands

The `dicom-dre redactor` command group provides free-text redaction operations
for description fields. Tokens absent from the allowlist are replaced with a
redaction marker. Dates, times, emails, URLs, and hexadecimal numbers are
redacted regardless of the allowlist; use `--preserve-dates` to keep date and
time values intact, as required for HIPAA limited datasets. See
[Text Redaction](../concepts/text-redaction.md) for the underlying model.

```bash
dicom-dre redactor [OPTIONS] COMMAND [ARGS]...
```

Commands:

- `redact` — Redact free text from an input CSV and write the result.
- `quality-check` — Preview redaction of a CSV of free text side by side.
- `show-tokens` — Extract and display all unique tokens from an input.
- `allow-token` — Add one or more tokens to the allowlist file.

## redact

Redact free text from an input CSV and write the result to an output CSV. Every
cell of every row is treated as an independent piece of text; no header row is
required and the column layout does not matter. The output CSV mirrors the
input, with tokens absent from the allowlist replaced by a redaction marker.

```bash
dicom-dre redactor redact [OPTIONS]
```

**Options:**

- `--track-redacted` — Also write the distinct tokens that were redacted.
- `--allowlist TEXT` — Allowlist filename (for example `default.csv`) or absolute
  path to an allowlist CSV. Default: `default.csv`.
- `--preserve-dates` — Keep dates and times in text, for HIPAA limited datasets.
- `--input TEXT` — Path to the input CSV file. Default: `input.csv`.
- `--output TEXT` — Path to the output CSV file. Default: `output.csv`.

**Examples:**

Redact using the default allowlist:

```bash
dicom-dre redactor redact --input samples.csv --output redacted.csv
```

Also record which tokens were redacted:

```bash
dicom-dre redactor redact --input samples.csv --output redacted.csv --track-redacted
```

Use a custom allowlist:

```bash
dicom-dre redactor redact --input samples.csv --allowlist /path/to/custom_list.csv
```

## quality-check

Display original and redacted text side by side for an input CSV. Use it to
identify false positives (valid words being redacted) and false negatives (PHI
not being redacted) before relying on the allowlist.

```bash
dicom-dre redactor quality-check [OPTIONS] INPUT
```

`INPUT` is a CSV file. Every cell of every row is treated as an independent
piece of free text; no header row is required and the column layout does not
matter.

**Options:**

- `--allowlist TEXT` — Allowlist filename (for example `default.csv`) or absolute
  path to an allowlist CSV. Default: `default.csv`.
- `--preserve-dates` — Keep dates and times in text, for HIPAA limited datasets.
- `--redacted-only` — Only display cells that were redacted.
- `--simple` — Only print tokens that would be redacted, sorted and de-duplicated.
- `--interactive` — Interactively review and add tokens to the allowlist.

**Examples:**

Show all text with side-by-side comparison:

```bash
dicom-dre redactor quality-check samples.csv
```

Show only cells with redactions:

```bash
dicom-dre redactor quality-check samples.csv --redacted-only
```

Print a simple list of redacted tokens:

```bash
dicom-dre redactor quality-check samples.csv --simple
```

Review and update the allowlist interactively:

```bash
dicom-dre redactor quality-check samples.csv --interactive
```

### Interactive mode

With `--interactive`, the command enters a keyboard-driven review mode that
displays each redacted token with its context and allows you to queue additions
to the allowlist.

For each redacted token, the display shows the row number, the original cell
text, the redacted version, the current token, and its status. Keyboard
shortcuts:

- `a` — Add the token to the allowlist (queue for addition).
- `s` — Skip the token (no action).
- `q` — Quit review early.
- `ESC` — Quit review early.

After the review reaches the end of the file or is quit, the command displays a
summary of queued additions, prompts for confirmation, and atomically updates
the allowlist file if confirmed.

## show-tokens

Extract and display all unique tokens from an input CSV. Every cell of every row
is split into tokens; no header row is required and the column layout does not
matter. The distinct tokens are printed sorted, one per line. Use this to
discover candidate terms to add to an allowlist.

```bash
dicom-dre redactor show-tokens [OPTIONS]
```

**Options:**

- `--input TEXT` — Path to the input CSV file. Default: `input.csv`.

**Example:**

```bash
dicom-dre redactor show-tokens --input samples.csv
```

## allow-token

Add one or more tokens to the allowlist file. Tokens are stripped of whitespace
and inserted in sorted order; duplicates are skipped.

```bash
dicom-dre redactor allow-token [OPTIONS] TOKENS...
```

`TOKENS` is one or more tokens to add to the allowlist.

**Options:**

- `--allowlist TEXT` — Allowlist filename (for example `default.csv`) or absolute
  path to an allowlist CSV. Default: `default.csv`.

**Examples:**

Add a single token:

```bash
dicom-dre redactor allow-token bicuspid
```

Add multiple tokens:

```bash
dicom-dre redactor allow-token spoonful bicuspid
```

Add a token to a custom allowlist:

```bash
dicom-dre redactor allow-token mytoken --allowlist /path/to/custom_list.csv
```
