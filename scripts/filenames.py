"""ファイル名生成・サニタイズの純粋関数群（テスタブル）."""
import re
import unicodedata
from typing import List, Optional


# ファイルシステムで違法/問題のある文字を置換または除去
_FILENAME_TRANSLATIONS = str.maketrans({
    "/": "-", "\\": "-", ":": "-",
    "?": "", "*": "", '"': "",
    "<": "", ">": "", "|": "",
    "\n": " ", "\r": " ", "\t": " ",
})

# 制御文字（C0/C1）を除去するための正規表現
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Windowsの予約ファイル名（拡張子なしのbasenameで判定）
WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def sanitize(s: Optional[str], max_len: Optional[int] = None) -> str:
    """ファイル名コンポーネントを安全な形に整形.

    - tab/newline/CRを空白に変換してから他の制御文字を除去
    - Unicode NFCに正規化（macOSのNFDとWindowsのNFCの不一致を回避）
    - ファイルシステム違法文字を置換
    - 連続空白を単一に
    - 必要なら指定長に切り詰め（末尾の.と空白は除去）

    末尾の.は意図的に保持する（"et al." のような正当な用途のため）。
    最終ファイル名としての末尾.除去は build_filename の責任。
    """
    if not s:
        return ""
    s = s.translate(_FILENAME_TRANSLATIONS)
    s = unicodedata.normalize("NFC", s)
    s = _CONTROL_CHAR_PATTERN.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip(". ")
    return s


# 年の抽出: 妥当な年範囲のみ、文字列の冒頭か区切り文字直後にあるものを優先
_YEAR_AT_START = re.compile(r"^\s*(\d{4})\b")
_YEAR_FENCED = re.compile(r"[\s\-/.,(\[](\d{4})\b")
_VALID_YEAR_RANGE = (1500, 2199)


def extract_year(date_str: Optional[str]) -> str:
    """Zoteroの date 文字列から発行年を抽出.

    Zoteroのdateフィールドは自由形式（"2023", "2023-04-15", "April 2023", "1999-2003"等）
    最初の有効な4桁年を返す。arXiv ID等の埋め込み年や、版番号等の数字は弾く方針。
    """
    if not date_str:
        return ""

    candidates: List[str] = []
    m = _YEAR_AT_START.match(date_str)
    if m:
        candidates.append(m.group(1))
    candidates.extend(_YEAR_FENCED.findall(date_str))

    for c in candidates:
        year = int(c)
        if _VALID_YEAR_RANGE[0] <= year <= _VALID_YEAR_RANGE[1]:
            return c
    return ""


def first_creator_string(authors: List[str]) -> str:
    """Zoteroの 'firstCreator' 風の表記を生成.

    - 1人: "Smith"
    - 2人: "Smith and Jones"
    - 3人以上: "Smith et al."
    """
    clean = [a.strip() for a in authors if a and a.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{clean[0]} et al."


def is_windows_reserved(basename: str) -> bool:
    stem = basename.split(".")[0].upper()
    return stem in WINDOWS_RESERVED_NAMES


def build_filename(
    title: Optional[str],
    date: Optional[str],
    authors: List[str],
    max_title_len: int = 100,
    sep: str = " - ",
    extension: str = ".pdf",
) -> Optional[str]:
    """メタデータから「Author - Year - Title.pdf」形式のファイル名を生成.

    Returns:
        ファイル名（拡張子含む）。titleが空の場合はNoneを返す（情報損失防止）。
    """
    sanitized_title = sanitize(title, max_len=max_title_len)
    if not sanitized_title:
        return None

    fc = sanitize(first_creator_string(authors))
    year = extract_year(date)

    parts = [p for p in (fc, year, sanitized_title) if p]
    base = sep.join(parts).rstrip(". ")
    if not base:
        return None

    if is_windows_reserved(base):
        base = f"_{base}"

    return base + extension
