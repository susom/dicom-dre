#!/usr/bin/env python3
"""Unit tests for text_redactor module."""

import csv
import tempfile
from pathlib import Path

import pytest

from dicom_dre.text_redactor import TextRedactor
from dicom_dre.text_redactor import extract_unique_tokens
from dicom_dre.text_redactor import print_redacted_tokens
from dicom_dre.text_redactor import process_csv_file
from dicom_dre.text_redactor import quality_check_csv_file


class TestTextRedactor:
    """Tests for TextRedactor class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        import shutil

        shutil.rmtree(temp_path, ignore_errors=True)

    @pytest.fixture
    def basic_redactor(self):
        """Create a TextRedactor with empty allowlist."""
        return TextRedactor()

    @pytest.fixture
    def allowlist_redactor(self):
        """Create a TextRedactor with a basic allowlist."""
        allowlist = {"mint", "lesion", "report", "pi", "rev"}
        return TextRedactor(allowlist=allowlist)

    @pytest.fixture
    def full_allowlist_redactor(self):
        """Create a TextRedactor with the full default allowlist loaded."""
        import importlib.resources as pkg_resources
        from pathlib import Path

        from dicom_dre.resources import allow_lists

        redactor = TextRedactor()
        csv_path = Path(str(pkg_resources.files(allow_lists))) / "default.csv"
        redactor.load_allowlist_from_csv(csv_path)
        return redactor

    def test_initialization_default(self):
        """TextRedactor initializes with default settings."""
        redactor = TextRedactor()
        assert redactor.allowlist == set(), f"Expected empty allowlist, got {redactor.allowlist}"
        assert redactor.delimiters == TextRedactor.DEFAULT_DELIMITERS, (
            f"Expected default delimiters, got {redactor.delimiters}"
        )
        # Should have 3 generated PII patterns + 2 time patterns + 7 default deny patterns (including ZIP code with state)
        expected_pattern_count = (
            len(TextRedactor.DEFAULT_PII_PREFIXES)
            + len(TextRedactor.DEFAULT_TIME_DENY_REGEX_PATTERNS)
            + len(TextRedactor.DEFAULT_DENY_REGEX_PATTERNS)
        )
        assert len(redactor.compiled_deny_regex_patterns) == expected_pattern_count, (
            f"Expected {expected_pattern_count} deny patterns, got {len(redactor.compiled_deny_regex_patterns)}"
        )
        assert len(redactor.compiled_allow_regex_patterns) == len(TextRedactor.DEFAULT_ALLOW_REGEX_PATTERNS), (
            f"Expected {len(TextRedactor.DEFAULT_ALLOW_REGEX_PATTERNS)} allow patterns, got {len(redactor.compiled_allow_regex_patterns)}"
        )

    def test_initialization_custom_allowlist(self):
        """TextRedactor initializes with custom allowlist."""
        allowlist = {"hello", "world"}
        redactor = TextRedactor(allowlist=allowlist)
        assert redactor.allowlist == allowlist, f"Expected allowlist {allowlist!r}, got {redactor.allowlist!r}"

    def test_initialization_custom_delimiters(self):
        """TextRedactor initializes with custom delimiters."""
        delimiters = [" ", ",", "."]
        redactor = TextRedactor(delimiters=delimiters)
        assert redactor.delimiters == delimiters, f"Expected delimiters {delimiters!r}, got {redactor.delimiters!r}"

    def test_basic_redaction_no_allowlist(self, basic_redactor):
        """Redact all words when allowlist is empty."""
        text = "hello world"
        result = basic_redactor.redact_text(text)
        assert result == "XXXXX XXXXX", f"Expected 'XXXXX XXXXX', got {result!r}"

    def test_basic_redaction_with_allowlist(self, allowlist_redactor):
        """Keep allowlisted words, redact others."""
        text = "mint report secret"
        result = allowlist_redactor.redact_text(text)
        assert result == "mint report XXXXXX", f"Expected 'mint report XXXXXX', got {result!r}"

    def test_case_insensitive_allowlist(self, allowlist_redactor):
        """Allowlist matching is case-insensitive."""
        text = "MINT Mint mInT"
        result = allowlist_redactor.redact_text(text)
        assert result == "MINT Mint mInT", f"Expected 'MINT Mint mInT', got {result!r}"

    def test_user_example_redaction(self, allowlist_redactor):
        """User example: mint Lesion Report: PI: John Doe Rev-0 [2022-09-07]."""
        text = "mint Lesion Report: PI: John Doe Rev-0 [2022-09-07]"
        result = allowlist_redactor.redact_text(text)
        # mint, Lesion (lesion), Report, PI, Rev are in allowlist
        # John, Doe (patient names), and date should be redacted
        assert result == "mint Lesion Report: PI: XXXX XXX Rev-0 [XXXX-XX-XX]", f"Expected PII redacted, got {result!r}"

    def test_delimiter_preservation(self, basic_redactor):
        """Delimiters are preserved during redaction."""
        text = "hello,world.test"
        result = basic_redactor.redact_text(text)
        assert result == "XXXXX,XXXXX.XXXX", f"Expected 'XXXXX,XXXXX.XXXX', got {result!r}"

    def test_empty_string(self, basic_redactor):
        """Empty string returns empty string."""
        result = basic_redactor.redact_text("")
        assert result == "", f"Expected empty string, got {result!r}"

    def test_only_delimiters(self, basic_redactor):
        """String with only delimiters is preserved."""
        text = "   ,,,...   "
        result = basic_redactor.redact_text(text)
        assert result == text, f"Expected delimiters-only string to be preserved unchanged, got {result!r}"

    def test_track_redacted_tokens(self, allowlist_redactor):
        """Track redacted tokens when requested."""
        text = "mint Rodriguez report Johnson"
        result, redacted = allowlist_redactor.redact_text(text, track_redacted=True)
        assert isinstance(result, str), f"Expected result to be str, got {type(result)}"
        assert isinstance(redacted, set), f"Expected redacted to be set, got {type(redacted)}"
        assert "Rodriguez" in redacted or "rodriguez" in redacted, (
            f"Expected 'Rodriguez' in redacted set, got {redacted}"
        )
        assert "Johnson" in redacted or "johnson" in redacted, f"Expected 'Johnson' in redacted set, got {redacted}"
        assert "mint" not in redacted, f"Expected 'mint' not in redacted set, got {redacted}"
        assert "report" not in redacted, f"Expected 'report' not in redacted set, got {redacted}"

    def test_already_redacted_text(self, basic_redactor):
        """Already redacted text (all X's) is preserved."""
        text = "XXXXX XXXXX"
        result = basic_redactor.redact_text(text)
        assert result == text, f"Expected already-redacted text to be preserved, got {result!r}"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Date is 09/07/2022 today", "XXXX XX XX/XX/XXXX XXXXX"),
            ("Date is 2022-09-07 today", "XXXX XX XXXX-XX-XX XXXXX"),
            ("Date is 07/09/2022 today", "XXXX XX XX/XX/XXXX XXXXX"),
            ("Date is September 7, 2022 today", "XXXX XX XXXXXXXXX XX XXXX XXXXX"),
            ("Date is Sep 7, 2022 today", "XXXX XX XXX XX XXXX XXXXX"),
            ("Date is 07-Sep-2022 today", "XXXX XX XX-XXX-XXXX XXXXX"),
            ("Timestamp 2022-09-07 14:30:00", "XXXXXXXXX XXXX-XX-XX XXXXXXXX"),
            ("Date is 09/07/22 today", "XXXX XX XX/XX/XX XXXXX"),
            ("Date is 09.07.2022 today", "XXXX XX XX.XX.XXXX XXXXX"),
            ("Date is 2022~09~07 today", "XXXX XX XXXXXXXXXX XXXXX"),
        ],
        ids=[
            "slash_mdy",
            "dash_ymd",
            "slash_dmy",
            "full_month_name",
            "abbrev_month_name",
            "dash_day_month_year",
            "with_time",
            "two_digit_year",
            "period_delimiter",
            "tilde_delimiter",
        ],
    )
    def test_date_formats(self, basic_redactor, text, expected):
        """Various date formats are redacted to X-strings."""
        result = basic_redactor.redact_text(text)
        assert result == expected, f"Expected {expected!r}, got {result!r}"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Meeting at 2:30 PM today", "XXXXXXX XX X:XX XX XXXXX"),
            ("Time is 14:30:45 now", "XXXX XX XX:XX:XX XXX"),
            ("Departure 23:59 tonight", "XXXXXXXXX XX:XX XXXXXXX"),
            ("Duration 12H01M total", "XXXXXXXX XXXXXX XXXXX"),
        ],
        ids=["hhmm_am_pm", "hhmmss", "hhmm_24hour", "hhMmm"],
    )
    def test_time_formats(self, basic_redactor, text, expected):
        """Various time formats are redacted to X-strings."""
        result = basic_redactor.redact_text(text)
        assert result == expected, f"Expected {expected!r}, got {result!r}"

    @pytest.mark.parametrize(
        "redactor_fixture,text,expected_contains,expected_absent",
        [
            (
                "basic_redactor",
                "Contact john.doe@example.com for info",
                ["XXXX.XXXXXXXXXXX.XXX"],
                ["john.doe"],
            ),
            (
                "full_allowlist_redactor",
                "Contact john.doe@example.com for info",
                ["XXXX.XXXXXXXXXXX.XXX"],
                ["john.doe"],
            ),
            (
                "basic_redactor",
                "Visit http://example.com for details",
                ["XXXX://XXXXXXX.XXX"],
                ["example.com"],
            ),
            (
                "basic_redactor",
                "Visit https://secure.example.com for details",
                ["XXXXX://XXXXXX.XXXXXXX.XXX"],
                ["secure.example.com"],
            ),
        ],
        ids=["email_basic", "email_with_allowlist", "url_http", "url_https"],
    )
    def test_email_and_url_formats(self, request, redactor_fixture, text, expected_contains, expected_absent):
        """Email addresses and URLs are redacted."""
        redactor = request.getfixturevalue(redactor_fixture)
        result = redactor.redact_text(text)
        for fragment in expected_contains:
            assert fragment in result, f"Expected {fragment!r} in result, got {result!r}"
        for fragment in expected_absent:
            assert fragment not in result, f"Expected {fragment!r} absent from result, got {result!r}"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("SSN is 123-45-6789 here", "XXX XX XXX-XX-XXXX XXXX"),
            ("SSN is 123456789 here", "XXX XX XXXXXXXXX XXXX"),
            ("Patient SSN12345 record", "XXXXXXX XXXXXXXX XXXXXX"),
        ],
        ids=["ssn_with_dashes", "ssn_no_dashes", "ssn_prefix_with_digits"],
    )
    def test_ssn_formats(self, basic_redactor, text, expected):
        """SSN patterns (with dashes, without dashes, prefix) are redacted."""
        result = basic_redactor.redact_text(text)
        assert result == expected, f"Expected {expected!r}, got {result!r}"

    @pytest.mark.parametrize(
        "text,zip_code_redacted",
        [
            ("Address in IL 62704 area", True),
            ("Address in Illinois 62704 area", True),
            ("Springfield, IL 62704 address", True),
            ("Value 62704 measurement", False),
            ("Address in il 62704 or ILLINOIS 62705", True),
        ],
        ids=[
            "state_abbreviation",
            "full_state_name",
            "comma_separator",
            "standalone_allowed",
            "case_insensitive",
        ],
    )
    def test_zip_code_formats(self, basic_redactor, text, zip_code_redacted):
        """ZIP codes are redacted when preceded by a state name/abbreviation, allowed when standalone."""
        result = basic_redactor.redact_text(text)
        if zip_code_redacted:
            assert "62704" not in result, f"Expected ZIP code '62704' to be redacted, got {result!r}"
            if "62705" in text:
                assert "62705" not in result, f"Expected ZIP code '62705' to be redacted, got {result!r}"
        else:
            assert "62704" in result, f"Expected standalone ZIP code '62704' to be preserved, got {result!r}"

    def test_hexadecimal_long(self, basic_redactor):
        """Redact hexadecimal numbers 6+ characters."""
        text = "ID is ABCDEF123456 here"
        result = basic_redactor.redact_text(text)
        assert result == "XX XX XXXXXXXXXXXX XXXX", f"Expected long hex redacted, got {result!r}"

    def test_hexadecimal_short_preserved(self, basic_redactor):
        """Short hexadecimal (5 chars) not redacted by hex pattern."""
        # Note: This tests the 6+ char requirement
        redactor = TextRedactor(allowlist={"abcde"})
        text = "Code ABCDE ok"
        result = redactor.redact_text(text)
        assert result == "XXXX ABCDE XX", f"Expected short hex to be preserved, got {result!r}"

    def test_nrp_number(self, basic_redactor):
        """Redact NRP numbers with 4+ digits."""
        text = "Patient NRP12345 record"
        result = basic_redactor.redact_text(text)
        assert result == "XXXXXXX XXXXXXXX XXXXXX", f"Expected NRP number redacted, got {result!r}"

    def test_nrp_number_short(self, basic_redactor):
        """NRP with less than 4 digits not matched by NRP pattern."""
        text = "Code NRP123 value"
        result = basic_redactor.redact_text(text)
        # NRP123 has only 3 digits after NRP, not matched by NRP pattern
        # NRP is redacted, 123 is allowed by short number pattern
        assert result == "XXXX XXX123 XXXXX", f"Expected short NRP to leave number, got {result!r}"

    def test_mrn_number(self, basic_redactor):
        """Redact MRN numbers with 4+ digits."""
        text = "Patient MRN12345 record"
        result = basic_redactor.redact_text(text)
        assert result == "XXXXXXX XXXXXXXX XXXXXX", f"Expected MRN number redacted, got {result!r}"

    def test_mrn_number_short(self, basic_redactor):
        """MRN with less than 4 digits not matched by MRN pattern."""
        text = "Code MRN123 value"
        result = basic_redactor.redact_text(text)
        # MRN123 has only 3 digits after MRN, not matched by MRN pattern
        # MRN is redacted, 123 is allowed by short number pattern
        assert result == "XXXX XXX123 XXXXX", f"Expected short MRN to leave number, got {result!r}"

    def test_allow_regex_pattern_short_numbers(self, basic_redactor):
        """Short numbers (1-5 digits) allowed by default regex pattern."""
        text = "Value 12345 and 6 here"
        result = basic_redactor.redact_text(text)
        # These should be allowed by DEFAULT_ALLOW_REGEX_PATTERNS
        assert result == "XXXXX 12345 XXX 6 XXXX", f"Expected short numbers allowed, got {result!r}"

    def test_load_allowlist_from_csv(self, basic_redactor, temp_dir):
        """Load allowlist from CSV file."""
        csv_file = temp_dir / "allowlist.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["hello", "world"])
            writer.writerow(["test", "data"])

        basic_redactor.load_allowlist_from_csv(csv_file)
        assert "hello" in basic_redactor.allowlist, f"Expected 'hello' in allowlist, got {basic_redactor.allowlist}"
        assert "world" in basic_redactor.allowlist, f"Expected 'world' in allowlist, got {basic_redactor.allowlist}"
        assert "test" in basic_redactor.allowlist, f"Expected 'test' in allowlist, got {basic_redactor.allowlist}"
        assert "data" in basic_redactor.allowlist, f"Expected 'data' in allowlist, got {basic_redactor.allowlist}"

    def test_load_allowlist_csv_case_normalization(self, basic_redactor, temp_dir):
        """Allowlist from CSV is normalized to lowercase."""
        csv_file = temp_dir / "allowlist.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Hello", "WORLD"])

        basic_redactor.load_allowlist_from_csv(csv_file)
        assert "hello" in basic_redactor.allowlist, (
            f"Expected lowercase 'hello' in allowlist, got {basic_redactor.allowlist}"
        )
        assert "world" in basic_redactor.allowlist, (
            f"Expected lowercase 'world' in allowlist, got {basic_redactor.allowlist}"
        )
        assert "Hello" not in basic_redactor.allowlist, (
            f"Expected mixed-case 'Hello' not in allowlist, got {basic_redactor.allowlist}"
        )

    def test_load_allowlist_csv_strips_whitespace(self, basic_redactor, temp_dir):
        """Allowlist from CSV strips whitespace."""
        csv_file = temp_dir / "allowlist.csv"
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["  hello  ", " world "])

        basic_redactor.load_allowlist_from_csv(csv_file)
        assert "hello" in basic_redactor.allowlist, (
            f"Expected stripped 'hello' in allowlist, got {basic_redactor.allowlist}"
        )
        assert "world" in basic_redactor.allowlist, (
            f"Expected stripped 'world' in allowlist, got {basic_redactor.allowlist}"
        )

    def test_load_allowlist_csv_invalid_file(self, basic_redactor):
        """Loading from nonexistent file raises ValueError."""
        with pytest.raises(ValueError, match="Failed to load allowlist"):
            basic_redactor.load_allowlist_from_csv("/nonexistent/file.csv")

    def test_process_csv_file_basic(self, allowlist_redactor, temp_dir):
        """Process CSV file and write redacted output."""
        input_file = temp_dir / "input.csv"
        output_file = temp_dir / "output.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mint", "Rodriguez", "report"])
            writer.writerow(["Johnson", "lesion", "MRN123456"])

        process_csv_file(allowlist_redactor, str(input_file), str(output_file))

        with open(output_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert rows[0] == ["mint", "XXXXXXXXX", "report"], (
                f"Expected row 0 to be ['mint', 'XXXXXXXXX', 'report'], got {rows[0]}"
            )
            assert rows[1] == ["XXXXXXX", "lesion", "XXXXXXXXX"], (
                f"Expected row 1 to be ['XXXXXXX', 'lesion', 'XXXXXXXXX'], got {rows[1]}"
            )

    def test_process_csv_file_with_tracking(self, allowlist_redactor, temp_dir):
        """Process CSV file and track redacted tokens."""
        input_file = temp_dir / "input.csv"
        output_file = temp_dir / "output.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mint", "Rodriguez", "report"])
            writer.writerow(["Johnson", "Smith"])

        redacted_tokens = process_csv_file(allowlist_redactor, str(input_file), str(output_file), track_redacted=True)

        assert isinstance(redacted_tokens, set), f"Expected redacted_tokens to be set, got {type(redacted_tokens)}"
        assert "Rodriguez" in redacted_tokens or "rodriguez" in redacted_tokens, (
            f"Expected 'Rodriguez' in redacted_tokens, got {redacted_tokens}"
        )
        assert "Johnson" in redacted_tokens or "johnson" in redacted_tokens, (
            f"Expected 'Johnson' in redacted_tokens, got {redacted_tokens}"
        )
        assert "Smith" in redacted_tokens or "smith" in redacted_tokens, (
            f"Expected 'Smith' in redacted_tokens, got {redacted_tokens}"
        )
        assert "mint" not in redacted_tokens, f"Expected 'mint' not in redacted_tokens, got {redacted_tokens}"

    def test_process_csv_file_invalid_input(self, allowlist_redactor, temp_dir):
        """Processing nonexistent input file raises ValueError."""
        output_file = temp_dir / "output.csv"
        with pytest.raises(ValueError, match="Error processing CSV file"):
            process_csv_file(allowlist_redactor, "/nonexistent/input.csv", str(output_file))

    def test_quality_check_csv_file(self, allowlist_redactor, temp_dir, capsys):
        """Quality check CSV file displays original and redacted text."""
        input_file = temp_dir / "input.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mint Rodriguez"])

        quality_check_csv_file(allowlist_redactor, str(input_file))

        captured = capsys.readouterr()
        assert "mint Rodriguez" in captured.out or "mint rodriguez" in captured.out, (
            f"Expected original text in output, got {captured.out!r}"
        )
        assert "mint XXXXXXXXX" in captured.out, f"Expected redacted text in output, got {captured.out!r}"

    def test_quality_check_csv_file_redacted_only(self, allowlist_redactor, temp_dir, capsys):
        """Quality check with redacted_only flag shows only modified cells."""
        input_file = temp_dir / "input.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mint", "Rodriguez"])

        quality_check_csv_file(allowlist_redactor, str(input_file), redacted_only=True)

        captured = capsys.readouterr()
        # "mint" should not appear (not redacted)
        # "Rodriguez" should appear (redacted PII name)
        assert "Rodriguez" in captured.out or "rodriguez" in captured.out, (
            f"Expected 'Rodriguez' in redacted-only output, got {captured.out!r}"
        )

    def test_print_redacted_tokens(self, allowlist_redactor, temp_dir, capsys):
        """Print redacted tokens excludes regex pattern matches."""
        input_file = temp_dir / "input.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["mint", "Rodriguez", "test@example.com"])

        print_redacted_tokens(allowlist_redactor, str(input_file))

        captured = capsys.readouterr()
        # "Rodriguez" should be in output (not in allowlist, not regex match, actual PII name)
        assert "Rodriguez" in captured.out or "rodriguez" in captured.out, (
            f"Expected 'Rodriguez' in print output, got {captured.out!r}"
        )

    def test_extract_unique_tokens(self, allowlist_redactor, temp_dir):
        """Extract unique tokens from CSV file."""
        input_file = temp_dir / "input.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["hello world"])
            writer.writerow(["hello test"])

        tokens = extract_unique_tokens(allowlist_redactor, str(input_file))

        assert isinstance(tokens, set), f"Expected tokens to be set, got {type(tokens)}"
        assert "hello" in tokens, f"Expected 'hello' in tokens, got {tokens}"
        assert "world" in tokens, f"Expected 'world' in tokens, got {tokens}"
        assert "test" in tokens, f"Expected 'test' in tokens, got {tokens}"

    def test_extract_unique_tokens_excludes_delimiters(self, allowlist_redactor, temp_dir):
        """Extract unique tokens excludes delimiters."""
        input_file = temp_dir / "input.csv"

        with open(input_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["hello, world!"])

        tokens = extract_unique_tokens(allowlist_redactor, str(input_file))

        assert "hello" in tokens, f"Expected 'hello' in tokens, got {tokens}"
        assert "world" in tokens, f"Expected 'world' in tokens, got {tokens}"
        assert "," not in tokens, f"Expected ',' not in tokens, got {tokens}"
        assert "!" not in tokens, f"Expected '!' not in tokens, got {tokens}"

    def test_multiple_dates_in_text(self, basic_redactor):
        """Redact multiple dates in same text."""
        text = "From 2022-01-15 to 2022-12-31"
        result = basic_redactor.redact_text(text)
        assert result.count("XXXX") >= 2, (
            f"Expected at least two years redacted, got {result!r}"
        )  # At least two years redacted

    def test_mixed_content(self, allowlist_redactor):
        """Redact text with mixed content types."""
        text = "Report on 2022-09-07: Contact john@test.com at https://example.com"
        result = allowlist_redactor.redact_text(text)
        # Date should be redacted (PII)
        assert "XXXX-XX-XX" in result, f"Expected date to be redacted, got {result!r}"
        # Email and URL should be redacted (PII)
        assert "john@test.com" not in result, f"Expected email to be redacted, got {result!r}"
        assert "https://example.com" not in result, f"Expected URL to be redacted, got {result!r}"
        # "Report" should be preserved (medical term in allowlist, not PII)
        assert "Report" in result or "report" in result.lower(), f"Expected 'Report' to be preserved, got {result!r}"

    def test_user_example_with_full_allowlist(self, full_allowlist_redactor):
        """User example with full allowlist: mint Lesion Report: PI: John Doe Rev-0 [2022-09-07]."""
        text = "mint Lesion Report: PI: John Doe Rev-0 [2022-09-07]"
        result = full_allowlist_redactor.redact_text(text)
        # Medical terms are in allowlist (not PII)
        assert "mint" in result, f"Expected 'mint' to be preserved, got {result!r}"
        assert "Lesion" in result, f"Expected 'Lesion' to be preserved, got {result!r}"
        assert "Report" in result, f"Expected 'Report' to be preserved, got {result!r}"
        assert "PI" in result, f"Expected 'PI' to be preserved, got {result!r}"
        # Patient names should be redacted (PII)
        assert "XXXX" in result, f"Expected 'John' to be redacted as 'XXXX', got {result!r}"  # John
        assert "XXX" in result, f"Expected 'Doe' to be redacted as 'XXX', got {result!r}"  # Doe
        # Date should be redacted (PII)
        assert "XXXX-XX-XX" in result, f"Expected date to be redacted, got {result!r}"

    def test_full_allowlist_loaded(self, full_allowlist_redactor):
        """Full allowlist contains expected medical terms."""
        assert len(full_allowlist_redactor.allowlist) > 30000, (
            f"Expected allowlist > 30000 words, got {len(full_allowlist_redactor.allowlist)}"
        )
        assert "contact" in full_allowlist_redactor.allowlist, "Expected 'contact' in allowlist"
        assert "patient" in full_allowlist_redactor.allowlist, "Expected 'patient' in allowlist"
        assert "report" in full_allowlist_redactor.allowlist, "Expected 'report' in allowlist"

    def test_allowlist_excludes_lc(self, full_allowlist_redactor):
        """Allowlist must not contain 'lc' to ensure LC-prefixed accession numbers are redacted."""
        assert "lc" not in full_allowlist_redactor.allowlist, (
            "'lc' must not be in the allowlist; it is a hospital identifier prefix "
            "used in timestamp-based accession numbers (e.g. LC20260110100)"
        )

    def test_gauntlet(self, full_allowlist_redactor):
        """Gauntlet test with multiple PHI types."""
        text = (
            "NONE OF THE FOLLOWING IS REAL PHI: John A. Smith, a 58-year-old male "
            "(DOB: 03/14/1967), MRN 009874563, SSN 000-12-3456, residing at "
            "742 Evergreen Terrace, Springfield, IL 62704, presented to Mercy General "
            "Hospital on 11/22/2025 at 14:37 for evaluation of acute chest pain. "
            "CT angiography of the chest was performed per order of Dr. Emily Carter, MD "
            "(NPI 1234567890). Comparison was made to prior CT dated 06/18/2023. "
            "The patient's referring provider was Michael Thompson, MD, reachable at "
            "(217) 555-0198. Insurance on file includes BlueCross BlueShield of Illinois, "
            "Member ID BCBS-IL-45892177. Imaging demonstrates no evidence of pulmonary embolism. "
            "Results were discussed directly with the patient and his spouse, Laura Smith "
            "(emergency contact), at bedside at 15:42."
        )
        result = full_allowlist_redactor.redact_text(text)

        # Patient names should be redacted
        assert "John" not in result, f"Expected 'John' to be redacted, got {result!r}"
        assert "Smith" not in result, f"Expected 'Smith' to be redacted, got {result!r}"
        assert "Emily" not in result, f"Expected 'Emily' to be redacted, got {result!r}"
        assert "Carter" not in result, f"Expected 'Carter' to be redacted, got {result!r}"
        assert "Michael" not in result, f"Expected 'Michael' to be redacted, got {result!r}"
        assert "Thompson" not in result, f"Expected 'Thompson' to be redacted, got {result!r}"
        assert "Laura" not in result, f"Expected 'Laura' to be redacted, got {result!r}"

        # Dates should be redacted
        assert "03/14/1967" not in result, f"Expected DOB '03/14/1967' to be redacted, got {result!r}"
        assert "11/22/2025" not in result, f"Expected date '11/22/2025' to be redacted, got {result!r}"
        assert "06/18/2023" not in result, f"Expected date '06/18/2023' to be redacted, got {result!r}"

        # IDs should be redacted
        assert "009874563" not in result, f"Expected MRN '009874563' to be redacted, got {result!r}"
        assert "000-12-3456" not in result, f"Expected SSN '000-12-3456' to be redacted, got {result!r}"
        assert "1234567890" not in result, f"Expected NPI '1234567890' to be redacted, got {result!r}"
        assert "BCBS-IL-45892177" not in result, (
            f"Expected insurance ID 'BCBS-IL-45892177' to be redacted, got {result!r}"
        )

        # Addresses should be redacted
        assert "Evergreen" not in result, f"Expected address word 'Evergreen' to be redacted, got {result!r}"
        assert "Terrace" not in result, f"Expected address word 'Terrace' to be redacted, got {result!r}"
        assert "62704" not in result, f"Expected ZIP code '62704' to be redacted, got {result!r}"

        # Phone should be redacted
        assert "217) 555-0198" not in result, f"Expected phone number to be redacted, got {result!r}"

        # Time should be redacted
        assert "14:37" not in result, f"Expected time '14:37' to be redacted, got {result!r}"
        assert "15:42" not in result, f"Expected time '15:42' to be redacted, got {result!r}"

        # Medical terms should be preserved
        assert "chest" in result.lower(), f"Expected medical term 'chest' to be preserved, got {result!r}"
        assert "pain" in result.lower(), f"Expected medical term 'pain' to be preserved, got {result!r}"
        assert "patient" in result.lower(), f"Expected medical term 'patient' to be preserved, got {result!r}"
        assert "embolism" in result.lower(), f"Expected medical term 'embolism' to be preserved, got {result!r}"


class TestPreserveDates:
    """Tests for preserve_dates mode (HIPAA limited datasets)."""

    @pytest.fixture
    def lds_redactor(self):
        """Create a TextRedactor with preserve_dates=True and empty allowlist."""
        return TextRedactor(preserve_dates=True)

    @pytest.fixture
    def lds_allowlist_redactor(self):
        """Create a TextRedactor with preserve_dates=True and a basic allowlist."""
        allowlist = {"mint", "lesion", "report", "pi", "rev"}
        return TextRedactor(allowlist=allowlist, preserve_dates=True)

    @pytest.fixture
    def lds_full_allowlist_redactor(self):
        """Create a TextRedactor with preserve_dates=True and the full default allowlist."""
        import importlib.resources as pkg_resources

        from dicom_dre.resources import allow_lists

        redactor = TextRedactor(preserve_dates=True)
        csv_path = Path(str(pkg_resources.files(allow_lists))) / "default.csv"
        redactor.load_allowlist_from_csv(csv_path)
        return redactor

    def test_preserve_dates_flag_stored(self, lds_redactor):
        """preserve_dates flag is stored on the instance."""
        assert lds_redactor.preserve_dates is True, "preserve_dates should be True when set"
        default = TextRedactor()
        assert default.preserve_dates is False, "preserve_dates should default to False"

    @pytest.mark.parametrize(
        "text,expected_present",
        [
            ("Date is 2022-09-07 today", ["2022", "09", "07"]),
            ("Date is 09/07/2022 today", ["09", "07", "2022"]),
            ("Date is September 7, 2022 today", ["September", "2022"]),
            ("Timestamp 2022-09-07 14:30:00", ["2022", "14", "30"]),
        ],
        ids=["dash_ymd", "slash_mdy", "full_month_name", "with_time"],
    )
    def test_date_preserved_variants(self, lds_redactor, text, expected_present):
        """Dates are preserved when preserve_dates is True."""
        result = lds_redactor.redact_text(text)
        for fragment in expected_present:
            assert fragment in result, f"Expected {fragment!r} to be preserved, got: {result}"

    @pytest.mark.parametrize(
        "text,expected_present",
        [
            ("Time is 14:30:45 now", ["14", "30", "45"]),
            ("Meeting at 2:30 PM today", ["2", "30"]),
            ("Duration 12H01M total", ["12", "01"]),
        ],
        ids=["hhmmss", "hhmm_am_pm", "hhMmm"],
    )
    def test_time_preserved_variants(self, lds_redactor, text, expected_present):
        """Time values are preserved when preserve_dates is True."""
        result = lds_redactor.redact_text(text)
        for fragment in expected_present:
            assert fragment in result, f"Expected {fragment!r} to be preserved, got: {result}"

    def test_email_still_redacted(self, lds_redactor):
        """Email addresses are still redacted when preserve_dates is True."""
        text = "Contact john.doe@example.com for info"
        result = lds_redactor.redact_text(text)
        assert "john" not in result, f"email local part 'john' should be redacted, got: {result}"
        assert "example" not in result, f"email domain 'example' should be redacted, got: {result}"

    def test_ssn_still_redacted(self, lds_redactor):
        """SSN is still redacted when preserve_dates is True."""
        text = "SSN is 123-45-6789 here"
        result = lds_redactor.redact_text(text)
        assert "123-45-6789" not in result, f"SSN '123-45-6789' should be redacted, got: {result}"

    def test_mrn_still_redacted(self, lds_redactor):
        """MRN numbers are still redacted when preserve_dates is True."""
        text = "Patient MRN12345 record"
        result = lds_redactor.redact_text(text)
        assert "MRN12345" not in result, f"MRN 'MRN12345' should be redacted, got: {result}"

    def test_phone_still_redacted(self, lds_redactor):
        """Phone numbers are still redacted when preserve_dates is True."""
        text = "Call (217) 555-0198 now"
        result = lds_redactor.redact_text(text)
        assert "555-0198" not in result, f"phone number '555-0198' should be redacted, got: {result}"

    def test_url_still_redacted(self, lds_redactor):
        """URLs are still redacted when preserve_dates is True."""
        text = "Visit https://secure.example.com for details"
        result = lds_redactor.redact_text(text)
        assert "secure.example.com" not in result, f"URL domain should be redacted, got: {result}"

    def test_hex_still_redacted(self, lds_redactor):
        """Hexadecimal numbers 6+ chars are still redacted when preserve_dates is True."""
        text = "ID is ABCDEF123456 here"
        result = lds_redactor.redact_text(text)
        assert "ABCDEF123456" not in result, f"hex ID should be redacted, got: {result}"

    def test_non_allowlisted_words_still_redacted(self, lds_redactor):
        """Non-allowlisted words are still redacted when preserve_dates is True."""
        text = "hello world"
        result = lds_redactor.redact_text(text)
        assert result == "XXXXX XXXXX", f"expected 'XXXXX XXXXX', got: {result}"

    def test_mixed_content_dates_preserved_pii_redacted(self, lds_allowlist_redactor):
        """Dates preserved but other PII redacted in mixed content."""
        text = "Report on 2022-09-07: PI: John Doe Rev-0"
        result = lds_allowlist_redactor.redact_text(text)
        assert "Report" in result, f"allowlisted word 'Report' should be preserved, got: {result}"
        assert "2022" in result, f"year '2022' should be preserved, got: {result}"
        assert "09" in result, f"month '09' should be preserved, got: {result}"
        assert "07" in result, f"day '07' should be preserved, got: {result}"
        assert "John" not in result, f"name 'John' should be redacted, got: {result}"
        assert "Doe" not in result, f"name 'Doe' should be redacted, got: {result}"

    def test_user_example_with_preserve_dates(self, lds_allowlist_redactor):
        """User example: dates kept, names redacted."""
        text = "mint Lesion Report: PI: John Doe Rev-0 [2022-09-07]"
        result = lds_allowlist_redactor.redact_text(text)
        assert "mint" in result, f"allowlisted word 'mint' should be preserved, got: {result}"
        assert "Lesion" in result, f"allowlisted word 'Lesion' should be preserved, got: {result}"
        assert "Report" in result, f"allowlisted word 'Report' should be preserved, got: {result}"
        assert "2022" in result, f"year '2022' should be preserved, got: {result}"
        assert "John" not in result, f"name 'John' should be redacted, got: {result}"
        assert "Doe" not in result, f"name 'Doe' should be redacted, got: {result}"

    def test_default_behavior_unchanged(self):
        """Default TextRedactor (preserve_dates=False) still redacts dates."""
        redactor = TextRedactor()
        text = "Date is 2022-09-07 today"
        result = redactor.redact_text(text)
        assert "XXXX-XX-XX" in result, f"date should be redacted when preserve_dates=False, got: {result}"

    def test_gauntlet_preserve_dates(self, lds_full_allowlist_redactor):
        """Gauntlet: dates/times preserved, all other PII redacted."""
        text = (
            "John A. Smith presented on 11/22/2025 at 14:37 for evaluation. "
            "MRN 009874563, SSN 000-12-3456. "
            "Address: 742 Evergreen Terrace, Springfield, IL 62704. "
            "Phone: (217) 555-0198. "
            "Prior CT dated 06/18/2023. Results discussed at 15:42."
        )
        result = lds_full_allowlist_redactor.redact_text(text)

        # Dates should be preserved
        assert "11" in result, f"date month '11' should be preserved, got: {result}"
        assert "22" in result, f"date day '22' should be preserved, got: {result}"
        assert "2025" in result, f"year '2025' should be preserved, got: {result}"
        assert "2023" in result, f"year '2023' should be preserved, got: {result}"

        # Times should be preserved
        assert "14" in result, f"hour '14' should be preserved, got: {result}"
        assert "37" in result, f"minute '37' should be preserved, got: {result}"
        assert "15" in result, f"hour '15' should be preserved, got: {result}"
        assert "42" in result, f"minute '42' should be preserved, got: {result}"

        # Patient names should still be redacted
        assert "John" not in result, f"name 'John' should be redacted, got: {result}"
        assert "Smith" not in result, f"name 'Smith' should be redacted, got: {result}"

        # IDs should still be redacted
        assert "009874563" not in result, f"MRN '009874563' should be redacted, got: {result}"
        assert "000-12-3456" not in result, f"SSN '000-12-3456' should be redacted, got: {result}"

        # Address should still be redacted
        assert "Evergreen" not in result, f"address word 'Evergreen' should be redacted, got: {result}"
        assert "Terrace" not in result, f"address word 'Terrace' should be redacted, got: {result}"
        assert "62704" not in result, f"ZIP code '62704' should be redacted, got: {result}"

        # Phone should still be redacted
        assert "555-0198" not in result, f"phone number '555-0198' should be redacted, got: {result}"

    def test_token_pairs_dates_preserved(self, lds_allowlist_redactor):
        """Token pairs mode preserves dates when preserve_dates is True."""
        text = "Report on 2022-09-07"
        result, pairs = lds_allowlist_redactor.redact_text(text, return_token_pairs=True)
        assert "2022" in result, f"year '2022' should be preserved, got: {result}"
        assert "09" in result, f"month '09' should be preserved, got: {result}"
        assert "07" in result, f"day '07' should be preserved, got: {result}"

    def test_track_redacted_dates_not_tracked(self, lds_allowlist_redactor):
        """Tracked redacted set does not include dates when preserve_dates is True."""
        text = "Report on 2022-09-07 by John"
        result, redacted = lds_allowlist_redactor.redact_text(text, track_redacted=True)
        assert "2022" in result, f"year '2022' should be preserved, got: {result}"
        assert "John" not in result, f"name 'John' should be redacted, got: {result}"
        assert "John" in redacted or "john" in redacted, f"'John' should be in redacted set, got: {redacted}"

    def test_accession_number_redacted_with_preserve_dates(self, lds_full_allowlist_redactor):
        """Accession number containing an embedded date is redacted even with preserve_dates."""
        text = "Accession LC20260110100"
        result = lds_full_allowlist_redactor.redact_text(text)
        assert "LC20260110100" not in result, f"accession number should be redacted, got: {result}"
        assert "LC" not in result, f"accession prefix 'LC' should be redacted, got: {result}"

    def test_uppercase_short_names_redacted_with_preserve_dates(self, lds_full_allowlist_redactor):
        """Short uppercase names must not be mistaken for timezone abbreviations."""
        text = "CT CHEST FOR KIM LEE"
        result = lds_full_allowlist_redactor.redact_text(text)
        assert "KIM" not in result, f"name 'KIM' should be redacted, got: {result}"
        assert "LEE" not in result, f"name 'LEE' should be redacted, got: {result}"
        # Medical terms should still be preserved
        assert "CT" in result, f"medical term 'CT' should be preserved, got: {result}"

    def test_real_timezone_preserved_with_preserve_dates(self, lds_redactor):
        """Real timezone abbreviations are preserved when preserve_dates is True."""
        redactor = TextRedactor(allowlist={"scan", "at"}, preserve_dates=True)
        text = "Scan at 14:30 EST"
        result = redactor.redact_text(text)
        assert "EST" in result, f"timezone 'EST' should be preserved, got: {result}"
