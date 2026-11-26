"""The gtk smoke check `back-gtk`: the gtk agent's `back` replies what Android's Back closed, for each
kind it names and for a Back that closes nothing."""

from .gtkdrive import Problem, Session
from .gtkinput import DIALOG_APK, NAV_APK, WINDOWS_APK


def _back(session: Session, want: str | None) -> int:
    """Back, which must close `want`; the log's index before it."""
    mark = session.mark()
    got = session.back()
    if got != want:
        raise session.fail(f"back closed {got!r}, want {want!r}")
    return mark


def menu(env: dict[str, str]) -> None:
    with Session(WINDOWS_APK, "dev/dine/windows/MenuActivity", env) as s:
        s.wait_line("menu activity created")
        mark = s.mark()
        s.activate("menu")
        s.wait_line("menu shown", mark)
        s.wait_line("menu dismissed", _back(s, "menu"))


def drop_down(env: dict[str, str]) -> None:
    """An AutoCompleteTextView's drop-down, a window that isn't a Dialog's, which takes Back before the IME."""
    with Session(WINDOWS_APK, "dev/dine/windows/PopupActivity", env) as s:
        s.wait_line("popup activity created")
        mark = s.mark()
        s.insert("fruit", "ap")
        s.wait_line("actv dropdown shown", mark)
        s.wait_line("actv dropdown dismissed", _back(s, "window"))


def dialog(env: dict[str, str]) -> None:
    with Session(DIALOG_APK, "dev/dine/dialog/OutsideActivity", env) as s:
        s.wait_line("outside shown")
        s.wait_line("outside dismissed", _back(s, "dialog"))


def modal_dialog(env: dict[str, str]) -> None:
    """An alert that can't be canceled: Back closes nothing, the alert stays."""
    with Session(DIALOG_APK, "dev/dine/dialog/ModalActivity", env) as s:
        s.wait_label("Done")
        mark = _back(s, None)
        if not any(l == "Done" for _, l in s.labels()):
            raise s.fail("the alert went with a Back that closed nothing")
        if any("modal canceled" in l for l in s.lines_since(mark)):
            raise s.fail("Back canceled the alert that can't be canceled")


def activity(env: dict[str, str]) -> None:
    """Back on the root activity would end ATL on gtk, so Back here finishes the one over it."""
    with Session(NAV_APK, "dev/dine/nav/TouchTapActivity", env) as s:
        s.wait_line("nav: U onResume")
        mark = s.mark()
        s.activate("go")
        s.wait_line("nav: Q onResume", mark)
        s.wait_line("nav: U onResume", _back(s, "activity"))


CHECKS = [menu, drop_down, dialog, modal_dialog, activity]


def run(env: dict[str, str]) -> str | None:
    try:
        for check in CHECKS:
            check(env)
    except Problem as e:
        return str(e)
    return None
