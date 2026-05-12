"""filenames.py の純粋関数群に対するユニットテスト."""
import os
import sys
import unittest

# scripts/ にパスを通す
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from filenames import (
    build_filename,
    extract_year,
    first_creator_string,
    is_windows_reserved,
    sanitize,
)


class TestSanitize(unittest.TestCase):

    def test_empty_input(self):
        self.assertEqual(sanitize(""), "")
        self.assertEqual(sanitize(None), "")

    def test_illegal_chars_replaced(self):
        self.assertEqual(sanitize("a/b\\c:d"), "a-b-c-d")
        self.assertEqual(sanitize("a?b*c\"d<e>f|g"), "abcdefg")

    def test_whitespace_normalized(self):
        self.assertEqual(sanitize("hello   world\t\nfoo"), "hello world foo")

    def test_trailing_dot_preserved_in_part(self):
        # sanitize is part-level; trailing dots ("et al.", "Jr.") are preserved.
        # Final filename cleanup is build_filename's job.
        self.assertEqual(sanitize("Title."), "Title.")
        self.assertEqual(sanitize("Smith Jr."), "Smith Jr.")
        self.assertEqual(sanitize("Title.   "), "Title.")

    def test_max_length_truncates(self):
        s = "a" * 200
        self.assertEqual(len(sanitize(s, max_len=100)), 100)

    def test_max_length_strips_trailing_dot_after_truncation(self):
        s = "abc." + "x" * 200
        result = sanitize(s, max_len=4)
        self.assertEqual(result, "abc")  # 末尾の.は再除去

    def test_control_chars_removed(self):
        self.assertEqual(sanitize("a\x00b\x07c"), "abc")
        self.assertEqual(sanitize("a\x1fb"), "ab")

    def test_nfc_normalization(self):
        # NFD「é」(e + combining acute) → NFC「é」(precomposed)
        nfd = "Pále"  # Pále
        result = sanitize(nfd)
        self.assertEqual(result, "P\xe1le")  # NFC: Pále

    def test_et_al_period_preserved(self):
        self.assertEqual(sanitize("Smith et al."), "Smith et al.")


class TestExtractYear(unittest.TestCase):

    def test_empty_input(self):
        self.assertEqual(extract_year(""), "")
        self.assertEqual(extract_year(None), "")

    def test_simple_year(self):
        self.assertEqual(extract_year("2023"), "2023")

    def test_iso_date(self):
        self.assertEqual(extract_year("2023-04-15"), "2023")

    def test_natural_date(self):
        self.assertEqual(extract_year("April 15, 2023"), "2023")

    def test_year_range(self):
        self.assertEqual(extract_year("1999-2003"), "1999")

    def test_year_with_text_prefix(self):
        self.assertEqual(extract_year("Volume 12 (2022)"), "2022")

    def test_invalid_year_out_of_range(self):
        self.assertEqual(extract_year("1234"), "")
        self.assertEqual(extract_year("9999"), "")

    def test_no_year_in_string(self):
        self.assertEqual(extract_year("Published online"), "")
        self.assertEqual(extract_year("令和5年"), "")

    def test_version_string_with_number(self):
        # v1.2.1800 等のバージョン文字列はマッチさせる方針（過剰判定はあるが許容）
        # 重要なのは、その前の "12" や "v1" を年として誤認識しないこと
        self.assertEqual(extract_year("v1.2.1800-rev"), "1800")


class TestFirstCreatorString(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(first_creator_string([]), "")
        self.assertEqual(first_creator_string([""]), "")
        self.assertEqual(first_creator_string([None]), "")

    def test_single_author(self):
        self.assertEqual(first_creator_string(["Smith"]), "Smith")

    def test_two_authors(self):
        self.assertEqual(first_creator_string(["Smith", "Jones"]), "Smith and Jones")

    def test_three_authors(self):
        self.assertEqual(first_creator_string(["Smith", "Jones", "Brown"]), "Smith et al.")

    def test_many_authors(self):
        self.assertEqual(
            first_creator_string(["A", "B", "C", "D", "E"]),
            "A et al.",
        )

    def test_whitespace_handling(self):
        self.assertEqual(first_creator_string(["  Smith  ", " Jones "]), "Smith and Jones")
        self.assertEqual(first_creator_string([" ", "Jones"]), "Jones")


class TestIsWindowsReserved(unittest.TestCase):

    def test_reserved(self):
        self.assertTrue(is_windows_reserved("CON"))
        self.assertTrue(is_windows_reserved("PRN.pdf"))
        self.assertTrue(is_windows_reserved("AUX.txt"))
        self.assertTrue(is_windows_reserved("COM1"))
        self.assertTrue(is_windows_reserved("LPT9.doc"))

    def test_case_insensitive(self):
        self.assertTrue(is_windows_reserved("con"))
        self.assertTrue(is_windows_reserved("Aux"))

    def test_not_reserved(self):
        self.assertFalse(is_windows_reserved("CONFIG"))
        self.assertFalse(is_windows_reserved("README"))
        self.assertFalse(is_windows_reserved("CON_paper"))


class TestBuildFilename(unittest.TestCase):

    def test_standard_format(self):
        result = build_filename(
            "Ultrafast small-scale robots",
            "2022-01-15",
            ["Mao", "Smith", "Brown"],
        )
        self.assertEqual(result, "Mao et al. - 2022 - Ultrafast small-scale robots.pdf")

    def test_two_authors(self):
        result = build_filename("Test Title", "2020", ["Smith", "Jones"])
        self.assertEqual(result, "Smith and Jones - 2020 - Test Title.pdf")

    def test_no_authors(self):
        result = build_filename("Some Title", "2021", [])
        self.assertEqual(result, "2021 - Some Title.pdf")

    def test_no_date(self):
        result = build_filename("Some Title", "", ["Smith"])
        self.assertEqual(result, "Smith - Some Title.pdf")

    def test_empty_title_returns_none(self):
        result = build_filename("", "2020", ["Smith"])
        self.assertIsNone(result)

    def test_whitespace_title_returns_none(self):
        result = build_filename("   ", "2020", ["Smith"])
        self.assertIsNone(result)

    def test_title_truncation(self):
        long_title = "x" * 200
        result = build_filename(long_title, "2020", ["Smith"], max_title_len=50)
        # "Smith - 2020 - " + 50 chars + ".pdf"
        self.assertTrue(len(result) <= len("Smith - 2020 - ") + 50 + len(".pdf"))

    def test_illegal_chars_in_title(self):
        result = build_filename("Title: A/B test?", "2020", ["Smith"])
        self.assertEqual(result, "Smith - 2020 - Title- A-B test.pdf")

    def test_windows_reserved_prefixed(self):
        result = build_filename("AUX", "", [])
        self.assertEqual(result, "_AUX.pdf")


if __name__ == "__main__":
    unittest.main()
