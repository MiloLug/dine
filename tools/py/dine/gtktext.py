"""The gtk smoke check `text-gtk`: widgets.apk's TextActivity under gtk, text put through the gtk
agent's `insert` into a GtkText. Java answers with its filters and snapshots; the field shows what Java
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


def inserting(env: dict[str, str]) -> None:
    """The filter drops the digit and the field takes Java's text back; Java's setText reaches the field;
    inserting goes on at Java's cursor."""
    with Session(WIDGETS_APK, "dev/dine/widgets/TextActivity", env) as s:
        s.wait_line("text shown")
        mark = s.mark()
        s.insert("name", "hi1")
        s.wait_line('text after "hi"', mark)
        _field(s, "name", "hi")
        mark = s.mark()
        s.activate("fill")
        s.wait_line('text after "filled"', mark)
        _field(s, "name", "filled")
        mark = s.mark()
        s.insert("name", "!")
        s.wait_line('text after "filled!"', mark)
        _field(s, "name", "filled!")


def key_behind_text(env: dict[str, str]) -> None:
    """A Return pressed in the same main-loop call as an inserted character reaches Java after the
    character: its key listener reads the text with it."""
    with Session(WIDGETS_APK, "dev/dine/widgets/TextActivity", env) as s:
        s.wait_line("text shown")
        mark = s.mark()
        s.insert("name", "o", RETURN)
        s.wait_line("text enter-key", mark)
        got = [l.split(": ", 1)[-1] for l in s.lines_since(mark) if "text enter-key" in l]
        if got != ['text enter-key "o"']:
            raise s.fail(f"Java's key listener read {got}, want the text with the character")


def input_state(env: dict[str, str]) -> None:
    """GTK gives input where Android's dispatch does: to a field in a disabled ScrollView and to a
    transparent one, not to a disabled one; an activation of a field under blocksDescendants, whose
    focus Java refuses, leaves GTK's focus on the field Java holds focused."""
    with Session(WIDGETS_APK, "dev/dine/widgets/InputStateActivity", env) as s:
        s.wait_line("inputstate shown")
        want = {"scrolled": True, "faded": True, "off": False, "blocked": True}
        got = {hint: s.state(hint)["sensitive"] for hint in want}
        problems = [f"the fields' GTK sensitivity is {got}, want {want}"] if got != want else []
        s.activate("scrolled")
        s.wait_line("inputstate focus scrolled true")
        mark = s.mark()
        s.activate("blocked")
        s.ask("settle 3000")
        deadline = time.monotonic() + 3
        while s.state("blocked")["focused"] or not s.state("scrolled")["focused"]:
            if time.monotonic() > deadline:
                problems.append("GTK's focus didn't go back from the field under blocksDescendants to the one Java holds focused")
                break
            time.sleep(0.1)
        focus = [l for l in s.lines_since(mark) if "inputstate focus blocked" in l]
        if focus:
            problems.append(f"Java focused the blocked field: {focus}")
        if problems:
            raise s.fail("; ".join(problems))


def long_alert(env: dict[str, str]) -> None:
    """An alert whose message is taller than the window keeps room for the view under the message."""
    with Session(WIDGETS_APK, "dev/dine/widgets/TextActivity", env) as s:
        s.wait_line("text shown")
        mark = s.mark()
        s.activate("long alert")
        # the last layout's: the box gets the height it asks for
        deadline = time.monotonic() + 10
        while True:
            heights = [l.split("text long content ", 1)[1] for l in s.lines_since(mark) if "text long content " in l]
            if heights and heights[-1].split(" of ")[0] == heights[-1].split(" of ")[1] != "0":
                break
            if time.monotonic() > deadline:
                raise s.fail(f"the alert's view got heights (of what it asks) {heights}")
            time.sleep(0.2)
        s.activate("Close")
        s.wait_line("text long closed", mark)


CHECKS = [inserting, key_behind_text, input_state, long_alert]


def run(env: dict[str, str]) -> str | None:
    try:
        for check in CHECKS:
            check(env)
    except Problem as e:
        return str(e)
    return None
