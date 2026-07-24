#!/usr/bin/env python3
"""Text redaction module for PII and sensitive information protection.

This module provides functionality to redact text based on an allowlist of
permitted words and predefined regex patterns to identify sensitive information.
"""

import csv
import functools
import importlib.resources as pkg_resources
import re
from pathlib import Path
from typing import cast

import click
import readchar


@functools.lru_cache(maxsize=32)
def get_text_redactor(allowlist_csv: str, preserve_dates: bool = False) -> "TextRedactor":
    """Get or create a cached TextRedactor instance for the given allowlist.

    Args:
        allowlist_csv: Filename of the allowlist CSV (e.g. "default.csv") under allow_lists/.
        preserve_dates: If True, dates and times in free text are kept intact.
            Used for HIPAA limited datasets where date elements are permitted.

    Returns:
        TextRedactor: A cached TextRedactor instance configured with the allowlist

    Raises:
        ValueError: If the allowlist CSV file does not exist at the specified path
    """
    from dicom_dre.resources import allow_lists

    allow_list_path = Path(str(pkg_resources.files(allow_lists))) / allowlist_csv
    if not allow_list_path.exists():
        raise ValueError(f"Allow list file {allow_list_path} does not exist")

    redactor = TextRedactor(preserve_dates=preserve_dates)
    redactor.load_allowlist_from_csv(allow_list_path)
    return redactor


class TextRedactor:
    """Text redaction tool for PII and sensitive information.

    This class provides functionality to redact words not present in an allowlist
    and text matching specific regex patterns that may contain sensitive information.

    Attributes:
        allowlist: Set of words that should not be redacted.
        delimiters: List of characters used to split text into tokens.
        regex_patterns: List of regex patterns to identify sensitive information.
        allowlist_regex_patterns: List of regex patterns for tokens that should not be redacted.
    """

    @staticmethod
    def create_month_regex() -> re.Pattern[str]:
        """Create a regex pattern to match month names (full and abbreviated)."""
        months = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"  # noqa B950
        return re.compile(f"^{months}$", re.IGNORECASE)

    TIMEZONE_ABBREVIATIONS = [
        "UTC",
        "GMT",
        "EST",
        "EDT",
        "CST",
        "CDT",
        "MST",
        "MDT",
        "PST",
        "PDT",
        "AKST",
        "AKDT",
        "HST",
        "HAST",
        "HADT",
        "AST",
        "ADT",
        "NST",
        "NDT",
        "BST",
        "CET",
        "CEST",
        "EET",
        "EEST",
        "WET",
        "WEST",
        "IST",
        "JST",
        "KST",
        "CST",
        "HKT",
        "SGT",
        "ICT",
        "WIB",
        "AEST",
        "AEDT",
        "ACST",
        "ACDT",
        "AWST",
        "NZST",
        "NZDT",
        "SAST",
        "EAT",
        "WAT",
        "CAT",
    ]

    @staticmethod
    def create_timezone_regex() -> re.Pattern[str]:
        """Create a regex pattern to match timezone abbreviations."""
        tz_alts = "|".join(TextRedactor.TIMEZONE_ABBREVIATIONS)
        return re.compile(rf"^(?:{tz_alts})$", re.IGNORECASE)

    @staticmethod
    def create_year_regex() -> re.Pattern[str]:
        """Create a regex pattern to match 4-digit years."""
        return re.compile(r"^(?:19\d{2}|20\d{2}|21[0-2][0-5])$")

    @staticmethod
    def create_date_regex() -> re.Pattern[str]:
        """Create a regex pattern to match various date formats. Must include year."""
        # Month names (full and abbreviated)
        months = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"  # noqa B950

        # Basic components
        day = r"(?:0?[1-9]|[12][0-9]|3[01])"
        month_num = r"(?:0?[1-9]|1[0-2])"
        year_2 = r"(?:\d{2})"
        year_4 = r"(?:19\d{2}|20\d{2}|21[0-2][0-5])"
        year = f"(?:{year_4}|{year_2})"

        # Time component (optional)
        time = r"(?:\s+(?:[01]?[0-9]|2[0-3])[:.\-](?:[0-5][0-9])(?:[:.\-](?:[0-5][0-9]))?(?:\s*[AaPp][Mm])?)?"

        # Timezone abbreviations (3-4 letter codes)
        timezone = r"(?:\s+[A-Z]{3,4})?"

        # Date patterns
        patterns = [
            # Numeric formats with non-period separators
            f"{month_num}[/\\-\\s]{day}[/\\-\\s]{year}{time}{timezone}",
            f"{day}[/\\-\\s]{month_num}[/\\-\\s]{year}{time}{timezone}",
            f"{year}[/\\-\\s]{month_num}[/\\-\\s]{day}{time}{timezone}",
            # Period and ~ delimited formats (4-digit years only)
            f"{month_num}[\\.~]{day}[\\.~]{year_4}{time}{timezone}",
            f"{day}[\\.~]{month_num}[\\.~]{year_4}{time}{timezone}",
            f"{year_4}[\\.~]{month_num}[\\.~]{day}{time}{timezone}",
            # Month name formats
            f"{day}[\\-\\s]{months}[\\-\\s]{year}{time}{timezone}",
            f"{year}[\\-\\s]{months}[\\-\\s]{day}{time}{timezone}",
            f"{day}\\.{months}\\.{year_4}{time}{timezone}",
            f"{year_4}\\.{months}\\.{day}{time}{timezone}",
            f"{months}\\s+{day},?\\s+{year}{time}{timezone}",
            f"{day}\\s+{months}\\s+{year}{time}{timezone}",
        ]

        combined_pattern = "|".join(f"(?:{p})" for p in patterns)
        # Use negative lookbehind/lookahead to prevent matching within longer numeric/separator sequences
        return re.compile(f"(?<![\\d/\\-])(?:{combined_pattern})(?![\\d/\\-])", re.IGNORECASE)

    # US state abbreviations and full names for ZIP code detection
    US_STATES = [
        "AL",
        "Alabama",
        "AK",
        "Alaska",
        "AZ",
        "Arizona",
        "AR",
        "Arkansas",
        "CA",
        "California",
        "CO",
        "Colorado",
        "CT",
        "Connecticut",
        "DE",
        "Delaware",
        "FL",
        "Florida",
        "GA",
        "Georgia",
        "HI",
        "Hawaii",
        "ID",
        "Idaho",
        "IL",
        "Illinois",
        "IN",
        "Indiana",
        "IA",
        "Iowa",
        "KS",
        "Kansas",
        "KY",
        "Kentucky",
        "LA",
        "Louisiana",
        "ME",
        "Maine",
        "MD",
        "Maryland",
        "MA",
        "Massachusetts",
        "MI",
        "Michigan",
        "MN",
        "Minnesota",
        "MS",
        "Mississippi",
        "MO",
        "Missouri",
        "MT",
        "Montana",
        "NE",
        "Nebraska",
        "NV",
        "Nevada",
        "NH",
        "New Hampshire",
        "NJ",
        "New Jersey",
        "NM",
        "New Mexico",
        "NY",
        "New York",
        "NC",
        "North Carolina",
        "ND",
        "North Dakota",
        "OH",
        "Ohio",
        "OK",
        "Oklahoma",
        "OR",
        "Oregon",
        "PA",
        "Pennsylvania",
        "RI",
        "Rhode Island",
        "SC",
        "South Carolina",
        "SD",
        "South Dakota",
        "TN",
        "Tennessee",
        "TX",
        "Texas",
        "UT",
        "Utah",
        "VT",
        "Vermont",
        "VA",
        "Virginia",
        "WA",
        "Washington",
        "WV",
        "West Virginia",
        "WI",
        "Wisconsin",
        "WY",
        "Wyoming",
        "DC",
        "District of Columbia",
        "PR",
        "Puerto Rico",
        "VI",
        "Virgin Islands",
        "GU",
        "Guam",
        "AS",
        "American Samoa",
        "MP",
        "Northern Mariana Islands",
    ]

    # PII prefixes that should be redacted when followed by 4+ digits
    DEFAULT_PII_PREFIXES = ["NRP", "MRN", "SSN"]

    # Deny patterns for standalone time formats (before tokenization).
    # Separated from DEFAULT_DENY_REGEX_PATTERNS so they can be skipped
    # when preserve_dates is True (HIPAA limited datasets).
    DEFAULT_TIME_DENY_REGEX_PATTERNS = [
        r"(\b(?:(?:2[0-3]|[01]?[0-9]):(?:[0-5][0-9])(?::(?:[0-5][0-9]))?\s*(?:[AaPp][Mm])?)\b)",  # time format optional AM/PM
        r"(\b\d{1,2}H\d{1,2}M\b)",  # time format 12H01M
    ]

    # Default regex patterns for sensitive information (before tokenization)
    DEFAULT_DENY_REGEX_PATTERNS = [
        r"(\b(?=.*[A-Fa-f])[0-9A-Fa-f]{6,}\b)",  # hexadecimal numbers 6 chars or longer are removed
        r"(\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b)",  # email addresses
        r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/$.?#].[^\s]*\b)",  # URLs
        r"(\b\d{3}-?\d{2}-?\d{4}\b)",  # SSN format (XXX-XX-XXXX or XXXXXXXXX)
        r"(\b\d{5}-\d{4}\b)",  # US zip codes (strictly 5+4 format only)
        r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b)",  # US phone numbers (various formats)
        # ZIP code with state context (state name or abbreviation followed by 5-digit ZIP)
        # Matches: "IL 62704", "Illinois 62704", "Springfield, IL 62704", "IL, 62704"
        # Case-insensitive matching with (?i) flag. It's only a zip# if it has a state, that is the compromise.
        rf"(?i)(\b(?:{'|'.join(US_STATES)})(?:,)?\s+\d{{5}}\b)",
    ]

    DEFAULT_ALLOW_REGEX_PATTERNS = [
        r"^(?:[0]*\d{1,5})$",  # 1-5 digit numbers, any # leading zero. Note the hex version above.
    ]

    # Default delimiters for tokenization
    # Do NOT change these unless you can justify it. It will affect ALL pipelines.
    DEFAULT_DELIMITERS = [
        " ",
        "<",
        ">",
        "(",
        ")",
        "{",
        "}",
        "|",
        "!",
        ";",
        ",",
        "'",
        '"',
        "*",
        "&",
        "?",
        "+",
        "/",
        ":",
        "=",
        "@",
        ".",
        "-",
        "$",
        "%",
        "\\",
        "_",
        "\n",
        "\r",
        "\t",
        "]",
        "[",
        "^",
        "#",
        "~",
        "`",
    ]

    def __init__(
        self,
        allowlist: set[str] | None = None,
        delimiters: list[str] | None = None,
        deny_regex_patterns: list[str] | None = None,
        allow_regex_patterns: list[str] | None = None,
        pii_prefixes: list[str] | None = None,
        preserve_dates: bool = False,
    ):
        """Initialize the TextRedactor with an allowlist and optional patterns.

        Args:
            allowlist: Set of words that should not be redacted.
            delimiters: List of delimiter characters to use for tokenization.
                If None, uses the DEFAULT_DELIMITERS class constant.
            deny_regex_patterns: List of regex patterns to mask. If None, uses
                the DEFAULT_DENY_REGEX_PATTERNS class constant.
            allow_regex_patterns: List of regex patterns for tokens that
                should not be redacted.
            pii_prefixes: List of prefixes that should be redacted when followed by 4+ digits.
                If None, uses the DEFAULT_PII_PREFIXES class constant.
            preserve_dates: If True, skip date and time redaction. Used for
                HIPAA limited datasets where date elements are permitted.
        """
        self.allowlist = allowlist or set()
        self.delimiters = delimiters or self.DEFAULT_DELIMITERS
        self.preserve_dates = preserve_dates

        prefixes = pii_prefixes or self.DEFAULT_PII_PREFIXES
        generated_pii_patterns = [rf"(\b{prefix}[0-9]{{4,}}\b)" for prefix in prefixes]

        deny_patterns = deny_regex_patterns or self.DEFAULT_DENY_REGEX_PATTERNS
        all_deny_patterns = generated_pii_patterns + deny_patterns

        # Time patterns are kept separate so they can be skipped when preserving dates
        if not preserve_dates:
            time_patterns = self.DEFAULT_TIME_DENY_REGEX_PATTERNS
            all_deny_patterns = generated_pii_patterns + time_patterns + deny_patterns

        allow_patterns = list(allow_regex_patterns or self.DEFAULT_ALLOW_REGEX_PATTERNS)
        compiled_allow_patterns = [re.compile(pattern) for pattern in allow_patterns]

        # When preserving dates, allow month names, years, and timezone tokens
        # so they survive the tokenization pass without being redacted.
        if preserve_dates:
            compiled_allow_patterns.append(self.create_month_regex())
            compiled_allow_patterns.append(self.create_year_regex())
            compiled_allow_patterns.append(self.create_timezone_regex())

        self.compiled_deny_regex_patterns = [re.compile(pattern) for pattern in all_deny_patterns]
        self.compiled_allow_regex_patterns = compiled_allow_patterns
        pattern = "|".join(map(re.escape, self.delimiters))
        self.tokenization_pattern = re.compile(
            f"({pattern}|"
            f"(?<=[a-zA-Z])(?=\\d)|"  # Letters followed by digits
            f"(?<=\\d)(?=[a-zA-Z]))"  # Digits followed by letters
        )
        # Compile the date pattern once; it is otherwise rebuilt on every
        # redact_text call.
        self._date_regex = self.create_date_regex()
        # Per-instance memoization of the plain-string redaction path. Bounded to
        # cap memory across many distinct inputs while capturing intra-series
        # reuse of identical description values.
        self._cached_redact_plain = functools.lru_cache(maxsize=1024)(self._redact_plain)

    def redact_text(
        self, text: str, track_redacted: bool = False, return_token_pairs: bool = False
    ) -> str | tuple[str, set[str]] | tuple[str, list[tuple[str, str]]]:
        """Redact words not in the allowlist and mask regex patterns.

        Args:
            text: The input text to redact.
            track_redacted: If True, return set of redacted tokens. Default is False.
            return_token_pairs: If True, return list of (original_token, redacted_token) pairs.

        Returns:
            If track_redacted is False and return_token_pairs is False, returns redacted text.
            If track_redacted is True, returns tuple of (redacted text, set of redacted tokens).
            If return_token_pairs is True, returns tuple of (redacted text, list of token pairs).
        """
        if return_token_pairs:
            original_tokens = self.tokenization_pattern.split(text)
            original_tokens = [token for token in original_tokens if token]

            result_tokens = []
            token_pairs_list = []

            for token in original_tokens:
                if self._date_regex.fullmatch(token):
                    if self.preserve_dates:
                        result_tokens.append(token)
                        token_pairs_list.append((token, token))
                    else:
                        redacted_token = self._date_regex.sub(lambda m: re.sub(r"[^/\-\.\s]", "X", m.group(0)), token)
                        result_tokens.append(redacted_token)
                        token_pairs_list.append((token, redacted_token))
                    continue

                matches_deny_pattern = False
                for pattern in self.compiled_deny_regex_patterns:
                    if pattern.fullmatch(token):
                        redacted_token = pattern.sub(lambda m: re.sub(r"[^/\:\.\-\s]", "X", m.group(0)), token)
                        result_tokens.append(redacted_token)
                        token_pairs_list.append((token, redacted_token))
                        matches_deny_pattern = True
                        break

                if matches_deny_pattern:
                    continue

                if token in self.delimiters:
                    result_tokens.append(token)
                    token_pairs_list.append((token, token))
                elif token and token[0] == "X" and token.count("X") == len(token):
                    result_tokens.append(token)
                    token_pairs_list.append((token, token))
                elif token.lower() in self.allowlist or any(
                    pattern.fullmatch(token) for pattern in self.compiled_allow_regex_patterns
                ):
                    result_tokens.append(token)
                    token_pairs_list.append((token, token))
                else:
                    redacted = "X" * len(token)
                    result_tokens.append(redacted)
                    token_pairs_list.append((token, redacted))

            result_text = "".join(result_tokens)
            return (result_text, token_pairs_list)

        # Standard processing (non-token-pairs mode). The plain-string path is
        # memoized per instance; the tracked path returns the redacted token set
        # and is not cached.
        if track_redacted:
            result_text, redacted_tokens = self._compute_redaction(text, track_redacted=True)
            return (result_text, redacted_tokens)  # type: ignore

        return self._cached_redact_plain(text)

    def _compute_redaction(self, text: str, track_redacted: bool) -> tuple[str, set[str] | None]:
        """Run the standard (non token-pair) redaction pass.

        Returns the redacted text and, when track_redacted is True, the set of
        redacted source tokens.
        """
        processed_text = text
        if not self.preserve_dates:
            processed_text = self._date_regex.sub(lambda m: re.sub(r"[^/\-\.\s]", "X", m.group(0)), processed_text)

        masked_text = processed_text
        for pattern in self.compiled_deny_regex_patterns:
            masked_text = pattern.sub(lambda m: re.sub(r"[^/\:\.\-\s]", "X", m.group(0)), masked_text)

        tokens = self.tokenization_pattern.split(masked_text)
        tokens = [token for token in tokens if token]

        result = []
        redacted_tokens: set[str] | None = set() if track_redacted else None

        for token in tokens:
            if token in self.delimiters:
                result.append(token)
            elif token and token[0] == "X" and token.count("X") == len(token):
                result.append(token)
            elif token.lower() in self.allowlist or any(
                pattern.fullmatch(token) for pattern in self.compiled_allow_regex_patterns
            ):
                result.append(token)
            else:
                redacted = "X" * len(token)
                result.append(redacted)
                if track_redacted and token.strip():
                    redacted_tokens.add(token)  # type: ignore

        return "".join(result), redacted_tokens

    def _redact_plain(self, text: str) -> str:
        """Return the redacted string for text without token tracking.

        Memoized per instance via ``_cached_redact_plain`` so repeated identical
        inputs (for example the same SeriesDescription across every instance in
        a series) are redacted only once.
        """
        return self._compute_redaction(text, track_redacted=False)[0]

    def load_allowlist_from_csv(self, allowlist_file: str | Path) -> None:
        """Load allowlist words from a CSV file.

        Args:
            allowlist_file: Path to the CSV file containing allowed words.

        Raises:
            ValueError: If the file cannot be read or is not in the expected format.
        """
        try:
            with open(allowlist_file, newline="", encoding="utf-8") as file:
                reader = csv.reader(file)
                self.allowlist = {word.strip().lower() for row in reader for word in row if word.strip()}
        except (OSError, csv.Error) as e:
            raise ValueError(f"Failed to load allowlist from {allowlist_file}: {e}") from e
        # The allowlist changed, so any memoized redactions are stale.
        self._cached_redact_plain.cache_clear()


def process_csv_file(
    redactor: TextRedactor, input_file: str, output_file: str, track_redacted: bool = False
) -> set[str] | None:
    """Process a CSV file and write redacted content to output file.

    Args:
        redactor: TextRedactor instance to use for redaction.
        input_file: Path to input CSV file.
        output_file: Path to output CSV file.
        track_redacted: If True, track and return redacted tokens. Default is False.

    Returns:
        Set of redacted tokens if track_redacted is True, otherwise None.

    Raises:
        ValueError: If the input or output file cannot be processed.
    """
    all_redacted_tokens: set[str] | None = set() if track_redacted else None

    try:
        with (
            open(input_file, newline="", encoding="utf-8") as in_file,
            open(output_file, "w", newline="", encoding="utf-8") as out_file,
        ):
            reader = csv.reader(in_file)
            writer = csv.writer(out_file)

            for row in reader:
                if track_redacted:
                    results = [
                        cast("tuple[str, set[str]]", redactor.redact_text(cell, track_redacted=True)) for cell in row
                    ]
                    writer.writerow([text for text, _ in results])
                    for _, tokens in results:
                        all_redacted_tokens.update(tokens)  # type: ignore
                else:
                    writer.writerow([redactor.redact_text(cell) for cell in row])

        return all_redacted_tokens
    except (OSError, csv.Error) as e:
        raise ValueError(f"Error processing CSV file: {e}") from e


def quality_check_csv_file(redactor: TextRedactor, input_file: str, redacted_only: bool = False) -> None:
    """Process a CSV file and display original text with redacted version for quality checking.

    Args:
        redactor: TextRedactor instance to use for redaction.
        input_file: Path to input CSV file.
        redacted_only: If True, only display cells that have been redacted. Default is False.

    Raises:
        ValueError: If the input file cannot be processed.
    """
    try:
        with open(input_file, newline="", encoding="utf-8") as in_file:
            reader = csv.reader(in_file)

            for row_num, row in enumerate(reader, 1):
                row_printed = False  # Track if we've printed the row number

                for _col_num, cell in enumerate(row, 1):
                    if cell.strip():
                        redacted_text = redactor.redact_text(cell)

                        if not redacted_only or redacted_text != cell:
                            if not row_printed:
                                print(f"{row_num:06}:", end=" ")
                                row_printed = True

                            print(f"{cell}")
                            if redacted_text != cell:
                                print(f"        {redacted_text}\n")

    except (OSError, csv.Error) as e:
        raise ValueError(f"Error processing CSV file for quality check: {e}") from e


def print_redacted_tokens(redactor: TextRedactor, input_file: str) -> None:
    """Process a CSV file and print only the tokens that would be redacted, excluding regex patterns.

    Args:
        redactor: TextRedactor instance to use for redaction.
        input_file: Path to input CSV file.

    Raises:
        ValueError: If the input file cannot be processed.
    """
    redacted_tokens = set()

    try:
        with open(input_file, newline="", encoding="utf-8") as in_file:
            reader = csv.reader(in_file)
            for row in reader:
                for cell in row:
                    if cell.strip():
                        result = redactor.redact_text(cell, track_redacted=True)
                        _, tokens_set = cast(tuple[str, set[str]], result)
                        for token in tokens_set:
                            should_add = True
                            for pattern in redactor.compiled_deny_regex_patterns:
                                if pattern.fullmatch(token):
                                    should_add = False
                                    break
                            if should_add:
                                redacted_tokens.add(token)

        if redacted_tokens:
            for token in sorted(redacted_tokens):
                print(token)
        else:
            print("No tokens were redacted.")

    except (OSError, csv.Error) as e:
        raise ValueError(f"Error processing CSV file for redacted tokens: {e}") from e


def extract_unique_tokens(redactor: TextRedactor, input_file: str) -> set[str]:
    """Process a CSV file and extract all unique tokens.

    Args:
        redactor: TextRedactor instance to use for tokenization.
        input_file: Path to input CSV file.

    Returns:
        Set of unique tokens found in the file.

    Raises:
        ValueError: If the input file cannot be processed.
    """
    unique_tokens = set()

    try:
        with open(input_file, newline="", encoding="utf-8") as in_file:
            reader = csv.reader(in_file)
            for row in reader:
                for cell in row:
                    if cell.strip():
                        tokens = redactor.tokenization_pattern.split(cell)
                        tokens = [t for t in tokens if t and t not in redactor.delimiters]
                        unique_tokens.update(tokens)

        return unique_tokens

    except (OSError, csv.Error) as e:
        raise ValueError(f"Error extracting tokens from CSV file: {e}") from e


def interactive_quality_check_csv_file(redactor: TextRedactor, input_file: str, allowlist_path: Path) -> list[str]:
    """Interactive quality check that allows reviewing and managing tokens.

    Args:
        redactor: TextRedactor instance to use for redaction.
        input_file: Path to input CSV file.
        allowlist_path: Path to allowlist file for saving updates.

    Returns:
        List of tokens_to_add based on user review.

    Raises:
        ValueError: If the input file cannot be processed.
    """
    tokens_to_add = set()
    processed_tokens = set()  # Track tokens we've already reviewed
    date_regex = redactor.create_date_regex()
    month_regex = redactor.create_month_regex()
    timezone_regex = redactor.create_timezone_regex()
    year_regex = redactor.create_year_regex()

    try:
        with open(input_file, newline="", encoding="utf-8") as in_file:
            reader = csv.reader(in_file)
            row_num = 0

            for row in reader:
                row_num += 1
                for cell in row:
                    if not cell.strip():
                        continue

                    redacted_text, token_pairs = cast(
                        "tuple[str, list[tuple[str, str]]]",
                        redactor.redact_text(cell, return_token_pairs=True),
                    )

                    for original, redacted in token_pairs:
                        if original in redactor.delimiters or original in processed_tokens:
                            continue

                        if original == redacted:
                            continue

                        if original.isdigit():
                            continue

                        if month_regex.fullmatch(original):
                            continue

                        if timezone_regex.fullmatch(original):
                            continue

                        if year_regex.fullmatch(original):
                            continue

                        if date_regex.fullmatch(original):
                            continue

                        matches_deny_pattern = False
                        for pattern in redactor.compiled_deny_regex_patterns:
                            if pattern.fullmatch(original):
                                matches_deny_pattern = True
                                break
                        if matches_deny_pattern:
                            continue

                        processed_tokens.add(original)

                        click.echo(f"\n{click.style('Row ' + str(row_num), fg='cyan', bold=True)}")
                        click.echo(f"Original: {cell}")
                        click.echo(f"Redacted: {redacted_text}")
                        click.echo()

                        click.echo(
                            f"Token: {click.style(original, fg='yellow', bold=True)} → "
                            f"{click.style(redacted, fg='red', bold=True)}"
                        )

                        in_add_queue = original in tokens_to_add
                        is_allowlisted = original.lower() in redactor.allowlist

                        status_parts = []
                        if is_allowlisted:
                            status_parts.append(click.style("in allowlist", fg="green"))
                        if in_add_queue:
                            status_parts.append(click.style("queued to add", fg="blue"))

                        if status_parts:
                            click.echo(f"Status: {', '.join(status_parts)}")

                        click.echo(
                            f"\n{click.style('[a]', fg='green')}dd to allowlist  "
                            f"{click.style('[s]', fg='white')}kip  "
                            f"{click.style('[q]', fg='yellow')}uit"
                        )

                        while True:
                            try:
                                key = readchar.readkey()

                                if key.lower() == "a":
                                    tokens_to_add.add(original)
                                    click.echo(click.style(f"✓ Queued '{original}' to add", fg="green"))
                                    break
                                elif key.lower() == "s":
                                    click.echo("Skipped")
                                    break
                                elif key.lower() == "q":
                                    click.echo("\nQuitting...")
                                    return list(tokens_to_add)
                                elif key == readchar.key.ESC:
                                    click.echo("\nQuitting...")
                                    return list(tokens_to_add)

                            except KeyboardInterrupt:
                                click.echo("\n\nInterrupted by user")
                                return list(tokens_to_add)

        click.echo("\n" + click.style("✓ Reached end of file", fg="green", bold=True))
        return list(tokens_to_add)

    except (OSError, csv.Error) as e:
        raise ValueError(f"Error processing CSV file for interactive quality check: {e}") from e


def save_allowlist_to_csv(allowlist_path: Path, tokens_to_add: list[str]) -> None:
    """Update allowlist file by adding tokens atomically.

    Args:
        allowlist_path: Path to the allowlist CSV file.
        tokens_to_add: List of tokens to add to allowlist.

    Raises:
        ValueError: If the file cannot be read or written.
    """
    try:
        existing_tokens = set()
        with open(allowlist_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    existing_tokens.add(row[0])

        updated_tokens = existing_tokens.copy()
        for token in tokens_to_add:
            updated_tokens.add(token.strip())

        sorted_tokens = sorted(updated_tokens, key=str.lower)

        # Write to temp file, then atomic rename
        temp_path = allowlist_path.with_suffix(".tmp")
        with open(temp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for token in sorted_tokens:
                writer.writerow([token])

        temp_path.replace(allowlist_path)

    except (OSError, csv.Error) as e:
        raise ValueError(f"Failed to save allowlist to {allowlist_path}: {e}") from e
