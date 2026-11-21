"""The gtk smoke check `text-gtk`: widgets.apk's TextActivity under gtk, text typed through the gtk
agent's `type` into a GtkText. Java answers with its filters and snapshots; the field shows what Java
holds, which the agent words as "hint: text"."""

import time

from . import paths
from .gtkdrive import Problem, Session

WIDGETS_APK = paths.OUT / "tests/apks/widgets.apk"

# GDK keyval and hardware keycode
RETURN = (0xFF0D, 36)


def _field(s: Session, hint: str, want: str) -> None:
    """The field `hint` shows `want` within 5 s: a report may be on its way."""
    deadline = time.monotonic() + 5
    while True:
        shown = s.field_labels(hint)
        if shown == [f"{hint}: {want}" if want else hint]:
            return
        if time.monotonic() > deadline:
            raise s.fail(f"the field {hint!r} reads {shown}, want {want!r}")
        time.sleep(0.2)


def typing(env: dict[str, str]) -> None:
    """The filter drops the digit and the field takes Java's text back; Java's setText reaches the field;
    typing goes on at Java's cursor."""
    with Session(WIDGETS_APK, "dev/dine/widgets/TextActivity", env) as s:
        s.wait_line("text shown")
        mark = s.mark()
        s.type("name", "hi1")
        s.wait_line('text after "hi"', mark)
        _field(s, "name", "hi")
        mark = s.mark()
        s.tap("fill")
        s.wait_line('text after "filled"', mark)
        _field(s, "name", "filled")
        mark = s.mark()
        s.type("name", "!")
        s.wait_line('text after "filled!"', mark)
        _field(s, "name", "filled!")


def key_behind_text(env: dict[str, str]) -> None:
    """A Return typed in the same main-loop call as a character reaches Java after the character: its key
    listener reads the text with it."""
    with Session(WIDGETS_APK, "dev/dine/widgets/TextActivity", env) as s:
        s.wait_line("text shown")
        mark = s.mark()
        s.type("name", "o", RETURN)
        s.wait_line("text enter-key", mark)
        got = [l.split(": ", 1)[-1] for l in s.lines_since(mark) if "text enter-key" in l]
        if got != ['text enter-key "o"']:
            raise s.fail(f"Java's key listener read {got}, want the text with the character")


CHECKS = [typing, key_behind_text]


def run(env: dict[str, str]) -> str | None:
    try:
        for check in CHECKS:
            check(env)
    except Problem as e:
        return str(e)
    return None
