---
description: Writing documentation in docs/
applyTo: "docs/**/*.md, README.md"
---

# Writing Documentation in dicom-dre

Rules for writing and editing Markdown documentation under `docs/`. Favor the
reader: a clear page is more likely to be correct, cheaper to change, and safe
to reuse. Clarity is the primary goal; the rules below serve it.

## Voice and Style

- Write as dry as an IEEE or NIST specification: factual, declarative, and
  impersonal. State facts and requirements; omit motivation, praise, and asides.
- Use present tense and the active voice ("The engine hashes the value", not
  "The value is hashed by the engine").
- Prefer verbs and concrete nouns over adjectives.
- Omit marketing and promotional words (for example efficient, powerful, robust,
  seamless, comprehensive, advanced).
- Omit claims you cannot verify from the code or tests.

## What to Include

- State what a component does, not what it does not do. Avoid negative-space
  descriptions that contrast with an alternative or a prior design (for example
  "handled here rather than in the parent", "not passed to X"); these are
  usually refactoring artifacts. Keep a negative statement only when it conveys
  critical information the reader cannot infer, such as a safety constraint.
- Omit self-evident or trivially true statements. Do not state facts the reader
  can infer or that hold by construction (for example "this module has no
  dependencies so it avoids an import cycle"). Write only what is non-obvious
  and consequential.

## Terminology and Verbs

- Name the actual mechanism, not an analogy. Do not use metaphor or
  anthropomorphism: data does not "travel", "live", "ship", "flow", or get
  "baked in"; objects do not "carry", "own", "want", or "know" anything.
- Use precise verbs for the operation:
  - storage or location: "is stored in", "is held in", "resides in".
  - fixed at construction: "is fixed at construction", "is set once at
    construction time".
  - cross-process transfer: "is serialized to", "is pickled and sent to", "is
    passed to". State that it crosses the process boundary when relevant.
  - occurrence or scope: "occurs", "is performed", "is scoped to".
- Prefer terms of art already used in the codebase: serialization,
  immutability, process boundary, construction time, apply time, deterministic
  derivation, closure.
- Prohibited terms and replacements: "baked" -> "fixed"/"set at construction";
  "knobs" -> "settings"/"options"/"parameters"; "lives" -> "is stored"/
  "resides"/"occurs"; "travel"/"ship" -> "is serialized"/"is sent"/"is passed";
  "carries" -> "holds"/"contains".

## Punctuation

- Do not use em-dashes (`--` or the Unicode em-dash). Rephrase into separate
  sentences, or use a colon, comma, or parentheses.
- Do not use en-dashes for ranges in prose. Write "10 to 30", not "10-30".

## Conciseness

- Keep sentences short. Prefer several plain sentences over one long clause.
- Cut filler and hedging (for example "in order to", "it is important to note
  that", "basically", "simply").
- Make each point once. One idea per sentence; one topic per paragraph.

## Formatting

- Wrap prose at roughly 88 columns to match the source line length.
- Wrap element names, keywords, parameters, and file paths in backticks
  (`PatientID`, `HASH_SALT`, `~/.config/dicom-dre/salt`).
- Use fenced code blocks with a language hint for commands and code.
- Use relative Markdown links between docs pages
  (`[Reproducibility](reproducibility.md)`).
- Do not use emoji.

## Accuracy

- Keep documentation synchronized with the code. When behavior changes, update
  the affected pages in the same change.
- Verify CLI flags, parameter names, and defaults against the actual source and
  `--help` output before documenting them.
- When adding a new page, add it to the `nav`/`toctree` so it is reachable.
