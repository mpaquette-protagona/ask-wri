"""Helpers that turn the model's text answer into structured, checkable sources.
Pure Python, no AWS: the agent uses them to find which quote supports which citation.
"""
import re
from difflib import SequenceMatcher

# The agent ends every answer with a line "=== QUOTES ===" followed by one line per cited source.
# The older "## Sources" heading is still accepted.
SOURCES_SPLIT = re.compile(r"\n(?:=+\s*QUOTES\s*=+|#{1,4}\s*\**Sources\**)\s*\n", re.IGNORECASE)
# One quote line: [3] "quoted text"   (pages and bullets before the quote are ignored)
SOURCE_LINE = re.compile(r'^\s*[-*]?\s*((?:\[\d+\]\s*)+)[^"\u201c\u201d]*?["\u201c](.+)["\u201d]\.?\s*$')
_SIMPLE = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                         "\u2013": "-", "\u2014": "-", "\u00a0": " "})


def split_answer(text):
    """Return (answer body, text of the Sources section or "")."""
    parts = SOURCES_SPLIT.split("\n" + text, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) == 2 else "")


def cited_numbers(body):
    """Return the sorted source numbers used as [n] in the answer body."""
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", body)})


def parse_quotes(sources_text):
    """Return {source number: quote} read from the Sources section."""
    quotes = {}
    for line in sources_text.splitlines():
        match = SOURCE_LINE.match(line)
        if match:
            for number in re.findall(r"\d+", match.group(1)):
                quotes[int(number)] = match.group(2).strip()
    return quotes


def _normalize(text):
    """Lowercase, straighten quotes and collapse whitespace.
    Returns the new text and, for each of its characters, the index in the original text."""
    chars, index, previous_space = [], [], False
    for i, ch in enumerate(text.translate(_SIMPLE)):
        if ch.isspace():
            if previous_space:
                continue
            ch, previous_space = " ", True
        else:
            previous_space = False
        for piece in ch.lower():
            chars.append(piece)
            index.append(i)
    return "".join(chars), index


def locate_quote(quote, text, min_ratio=0.6):
    """Return (start, end) of the quote inside text, or None when it is not really there.
    A quote with "..." in it is matched piece by piece; a slightly altered quote must still
    share a long unbroken run of text with the passage."""
    norm_text, index = _normalize(text)
    norm_quote, _ = _normalize(quote)
    strip = " .\"'"
    norm_quote = norm_quote.strip(strip)
    if len(norm_quote) < 12:
        return None
    pieces = [p.strip(strip) for p in re.split("\u2026|\\.\\.\\.", norm_quote)]
    pieces = [p for p in pieces if len(p) >= 12]
    spans, position = [], 0
    for piece in pieces:
        found = norm_text.find(piece, position)
        if found >= 0:
            spans.append((found, found + len(piece)))
            position = found + len(piece)
    start = end = None
    if spans and sum(e - s for s, e in spans) >= min_ratio * sum(len(p) for p in pieces):
        start, end = spans[0][0], spans[-1][1]
        if end - start > 3 * len(norm_quote) + 200:  # pieces far apart: highlight the first only
            end = spans[0][1]
    else:
        match = SequenceMatcher(None, norm_text, norm_quote, autojunk=False).find_longest_match(
            0, len(norm_text), 0, len(norm_quote))
        if match.size >= max(25, min_ratio * len(norm_quote)):
            start, end = match.a, match.a + match.size
    if start is None:
        return None
    return index[start], index[end - 1] + 1


def excerpt(text, span=None, limit=6000):
    """Cut a long passage down to about `limit` characters around the quote.
    Returns (text, span inside the cut text or None, cut at start, cut at end)."""
    if len(text) <= limit:
        return text, span, False, False
    centre = (span[0] + span[1]) // 2 if span else limit // 2
    start = max(0, min(centre - limit // 2, len(text) - limit))
    end = start + limit
    while 0 < start < len(text) and not text[start - 1].isspace() and start < end:
        start += 1  # do not start in the middle of a word
    while end < len(text) and not text[end].isspace() and end > start:
        end -= 1  # do not end in the middle of a word
    cut = text[start:end]
    inside = (span[0] - start, span[1] - start) if span and span[0] >= start and span[1] <= end else None
    return cut, inside, start > 0, end < len(text)
