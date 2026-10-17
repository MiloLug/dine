"""Text matchers shared by `wait --log`, `wait --at` and `ui tap`."""

import re

_WORD = re.compile(r"\w+(?:\+\+|#)?")


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def loose(pattern: str):
    """Case-insensitive, punctuation-blind: each pattern word prefixes a text word, in order.
    "loaded apps" matches "loaded 3 apps"; "hello" matches "hello++, Button"."""
    want = words(pattern)
    if not want:
        raise ValueError(f"pattern has no words: {pattern!r}")

    def match(text: str) -> bool:
        it = iter(words(text))
        return all(any(got.startswith(w) for got in it) for w in want)
    return match


def regex(pattern: str):
    rx = re.compile(pattern)
    return lambda text: rx.search(text) is not None


def location(spec: str):
    """`file:line` matches by path suffix; anything else, a path suffix or a function-name substring."""
    file, _, line = spec.rpartition(":")
    if file and line.isdigit():
        return lambda loc: (loc.get("file") or "").endswith(file) and loc.get("line") == int(line)
    return lambda loc: (loc.get("file") or "").endswith(spec) or spec in (loc.get("function") or "")
