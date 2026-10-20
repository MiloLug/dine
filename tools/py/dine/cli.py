"""tools/dine: the single entry point for dine's dev tooling. `tools/dine <group> --help`."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time

from . import ios, linux, paths
from .dbg import client, session, smoke
from .paths import DineError

DBG_EXIT_HELP = "exit codes: 0 ok/matched, 1 error or bad state, 2 wait timeout, " \
                "3 process exited/crashed during a wait, 4 server not running"


def _ios(sub):
    p = sub.add_parser("ios", help="device: tunnel, build, run, processes, logs, symbols, lldb")
    s = p.add_subparsers(dest="action", required=True)

    t = s.add_parser("tunnel", help="iOS 17+ developer services tunnel (start uses sudo)")
    t.add_argument("op", choices=["start", "status"])
    t.set_defaults(func=lambda a: print(ios.tunnel_start() if a.op == "start" else ios.tunnel_status()))

    t = s.add_parser("build-native", help="native/<lib> → out/ios (DINE_IOS_BUILD_TYPE, default RelWithDebInfo); "
                                          "native/dev/* unless DINE_RELEASE=1")
    t.add_argument("libs", nargs="*")
    t.set_defaults(func=lambda a: ios.run_libexec("build-ios-native.sh", *a.libs))

    t = s.add_parser("build-art", help="dine-art runtime + libcore natives (and ICU, lz4, liblzma) → "
                                       "static archives in out/ios/lib")
    t.set_defaults(func=lambda a: ios.run_libexec("build-ios-art.sh"))

    t = s.add_parser("build-atl", help="dine-atl uikit build → out/ios/lib/libtranslation_layer_main.a, jars → "
                                       "out/ios/share/atl, test APKs → out/tests/apks (after linux build atl); "
                                       "DINE_RELEASE=1: no test hooks or APKs")
    t.set_defaults(func=lambda a: ios.run_libexec("build-ios-atl.sh"))

    t = s.add_parser("run", help="build-native + dev payload + build-assets + xtool dev (build/sign/install) + launch; "
                                 "kills a running instance first. DINE_RELEASE=1: release build, no dev or test code")
    t.add_argument("app", nargs="?", default="Dine")
    t.set_defaults(func=_ios_run)

    t = s.add_parser("launch", help="launch through DVT (kills a running instance); prints the pid")
    t.add_argument("app", nargs="?", default="Dine")
    t.add_argument("--suspended", action="store_true", help="wait for a debugger before running any code")
    t.set_defaults(func=_ios_launch)

    t = s.add_parser("ps", help="running processes (default: the app's)")
    t.add_argument("app", nargs="?", default="Dine")
    t.add_argument("--all", action="store_true")
    t.set_defaults(func=_ios_ps)

    t = s.add_parser("kill", help="kill an app by name, or a pid")
    t.add_argument("target")
    t.set_defaults(func=_ios_kill)

    t = s.add_parser("logs", help="live syslog of the app to this terminal (for a recorded, waitable "
                                  "log use `dbg syslog start`)")
    t.add_argument("app", nargs="?", default="Dine")
    t.set_defaults(func=lambda a: os.execv(str(paths.PMD), [str(paths.PMD), "syslog", "live", "-pn", a.app]))

    t = s.add_parser("symbols", help="phone's dyld shared cache → out/ios-symbols (Swift po); per iOS build")
    t.set_defaults(func=lambda a: ios.cmd_symbols())

    t = s.add_parser("lldb", help="interactive lldb: launch + attach (args after -- go to lldb)")
    t.add_argument("app", nargs="?", default="Dine")
    t.add_argument("--suspended", action="store_true")
    t.set_defaults(func=lambda a: ios.cmd_lldb(a.app, a.suspended, a.extra), passthrough="tail")

    t = s.add_parser("lldb-offline", help="lldb on a synthetic core stopped at <bp>, no phone")
    t.add_argument("where", nargs="+", metavar="[App] bp")
    t.set_defaults(func=_ios_lldb_offline, passthrough="tail")


def _notify_server(kind: str, text: str, mark: bool = False) -> None:
    """Log a device action in the running debug session; mark before the action, so waits see its effects."""
    if session.server_pid():
        try:
            client.call("note", {"kind": kind, "text": text, "mark": mark}, timeout=5)
        except client.NotRunning:
            pass


def _launch(app: str, suspended: bool) -> int:
    if session.server_pid():
        st = client.call("status", timeout=10).get("state") or {}
        if st.get("attached"):
            raise DineError(f"the debug server is attached to pid {st.get('pid')}, which blocks a relaunch: "
                            "tools/dine dbg detach first")
    _notify_server("launching", f"launching {app}", mark=True)
    pid = ios.launch(app, suspended)
    _notify_server("launched", f"launched {app} pid {pid}" + (" (suspended)" if suspended else ""))
    return pid


def _ios_launch(a) -> int:
    print(f"launched {a.app} pid {_launch(a.app, a.suspended)}")
    return 0


def _ios_run(a) -> int:
    ios.check_atl_build()
    # A previously debugged instance makes the install hang at "[Installing] 100%".
    for proc in ios.processes(a.app):
        _notify_server("killing", f"killing pid {proc['pid']} before reinstalling", mark=True)
        ios.kill(proc["pid"])
    rc = ios.cmd_install(a.app)
    return rc or _ios_launch(argparse.Namespace(app=a.app, suspended=False))


def _ios_ps(a):
    for p in ios.processes(None if a.all else a.app):
        print(f"{p['pid']:>7}  {p.get('name')}  {p.get('bundleIdentifier', '')}")


def _ios_kill(a):
    pids = [int(a.target)] if a.target.isdigit() else [p["pid"] for p in ios.processes(a.target)]
    if not pids:
        raise DineError(f"no running process named {a.target}")
    for pid in pids:
        _notify_server("killing", f"killing pid {pid}", mark=True)
        ios.kill(pid)
        print(f"killed {pid}")


def _ios_lldb_offline(a):
    if len(a.where) > 2:
        raise DineError("usage: tools/dine ios lldb-offline [App] <bp> [-- lldb args]")
    app, bp = (a.where if len(a.where) == 2 else ["Dine", a.where[0]])
    ios.cmd_lldb_offline(app, bp, a.extra)


def _linux(sub):
    p = sub.add_parser("linux", help="Linux ATL/ART stack")
    s = p.add_subparsers(dest="action", required=True)
    t = s.add_parser("build", help="bionic → art → opensles → atl into out/linux/prefix, then the "
                                   "headless atl-headless in its build dir (default: all)")
    t.add_argument("stages", nargs="*", choices=[[], "bionic", "art", "opensles", "atl", "atl-headless"],
                   metavar="stage")
    t.set_defaults(func=lambda a: ios.run_libexec("build-linux-stack.sh", *a.stages))
    t = s.add_parser("smoke", help="gtk runs Gravity Defied to onResume, headless runs demo_app and looper "
                                   "(after linux build; --list for the checks)")
    t.add_argument("names", nargs="*", metavar="check")
    t.add_argument("--list", action="store_true", help="print the checks")
    t.set_defaults(func=lambda a: print(linux.listing()) if a.list else linux.smoke(a.names))


def _test(sub):
    p = sub.add_parser("test", help="test suites")
    s = p.add_subparsers(dest="action", required=True)
    t = s.add_parser("runtime", help="ART run-tests on dalvikvm -Xint; args go to the harness "
                                     "(tools/dine test runtime -- --help)")
    t.set_defaults(func=lambda a: subprocess.run([sys.executable, str(paths.ROOT / "tests/harness"), *a.extra]).returncode,
                   passthrough="all")
    t = s.add_parser("unit", help="unit tests: tests/harness and tools/py")
    t.set_defaults(func=_test_unit)


def _test_unit(a):
    rc = 0
    for start, top in (("tests/harness", "tests/harness"), ("tools/py/dine", "tools/py")):
        print(f"==> {start}", flush=True)
        rc |= subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", start, "-t", top, "-q"],
                             cwd=paths.ROOT).returncode
    return rc


def _dbg(sub):
    p = sub.add_parser("dbg", aliases=["debugger"], help="the debug server: start-server, attach, wait, …",
                       description="One debug server per session; nothing starts implicitly. " + DBG_EXIT_HELP)
    p.add_argument("--max-lines", type=int, default=60, help="truncate output (default 60)")
    p.add_argument("--json", action="store_true", help="print the raw response")
    s = p.add_subparsers(dest="action", required=True)

    t = s.add_parser("start-server", help="spawn the server (fails if one runs)")
    t.add_argument("--target", default="ios", choices=["ios", "fake"])
    t.add_argument("--app", default="Dine")
    t.add_argument("--timeout", type=float, default=90)
    t.set_defaults(func=_start_server)

    t = s.add_parser("stop-server", help="detach, stop streams, exit; logs are kept")
    t.add_argument("--kill-app", action="store_true")
    t.add_argument("--timeout", type=float, default=30)
    t.set_defaults(func=_stop_server)

    def req(name, cmd, help, args=lambda a: {}, timeout=30.0, setup=None):
        t = s.add_parser(name, help=help)
        if setup:
            setup(t)
        t.add_argument("--timeout", type=float, default=timeout, help=f"seconds (default {timeout:g})")
        t.set_defaults(func=lambda a: _request(a, cmd, args(a)))
        return t

    req("status", "status", "server, process, streams, cursor")
    def syslog_setup(t):
        t.add_argument("op", choices=["start", "stop"])
        t.add_argument("--debug", action="store_true", help="keep DEBUG entries (noisy)")
        t.add_argument("--subsystem", help="only this subsystem, e.g. dev.dine.Dine")
    req("syslog", None, "capture the app's syslog into the session (start|stop)", setup=syslog_setup).set_defaults(
        func=lambda a: _request(a, f"syslog_{a.op}",
                                {"debug": a.debug, "subsystem": a.subsystem} if a.op == "start" else {}))
    req("attach", "attach", "attach lldb to the running app (never launches it)", timeout=120,
        args=lambda a: {"pid": a.pid}, setup=lambda t: t.add_argument("--pid", type=int))
    req("detach", "detach", "detach lldb; the app keeps running")

    def bp_setup(t):
        t.add_argument("op", choices=["add", "ls", "rm", "enable", "disable"])
        t.add_argument("spec", nargs="?", help="add: file:line or symbol; rm/enable/disable: id")
        t.add_argument("--cond", help="condition expression")
        t.add_argument("--once", action="store_true", help="one-shot breakpoint")
    req("bp", "bp", "breakpoints: add <file:line|symbol> | ls | rm|enable|disable <id>", setup=bp_setup,
        args=lambda a: {"op": a.op, "spec": a.spec, "cond": a.cond, "once": a.once})

    for name, help in (("continue", "resume; returns at once (then: wait --stop)"),
                       ("step", "step into (source line)"), ("next", "step over (source line)"),
                       ("finish", "step out of the frame"), ("stepi", "one instruction")):
        req(name, name, help, setup=lambda t: t.add_argument("--thread", type=int),
            args=lambda a: {"thread": a.thread})
    req("interrupt", "interrupt", "stop the running process, or interrupt a stuck lldb command")

    req("threads", "threads", "threads with their top frame")
    req("bt", "bt", "backtrace of the selected thread",
        setup=lambda t: (t.add_argument("-n", type=int, default=20), t.add_argument("--thread", type=int)),
        args=lambda a: {"n": a.n, "thread": a.thread})
    req("frame", "frame", "show or select a frame", setup=lambda t: t.add_argument("index", type=int, nargs="?"),
        args=lambda a: {"index": a.index})
    req("up", "up", "select the caller frame")
    req("down", "down", "select the callee frame")
    req("source", "source", "source around the selected frame",
        setup=lambda t: t.add_argument("-c", type=int, default=8, help="lines of context"),
        args=lambda a: {"context": a.c})
    req("vars", "vars", "variables of the selected frame (default: all locals and args)",
        setup=lambda t: t.add_argument("names", nargs="*"), args=lambda a: {"names": a.names})

    def exec_setup(t):
        t.add_argument("--lang", choices=["swift", "c++", "c", "objc"],
                       help="default: the selected frame's language")
        t.add_argument("--po", action="store_true", help="object description (like po)")
        t.add_argument("--force", action="store_true",
                       help="run it on a non-main thread blocked in the kernel (refused by default)")
        t.add_argument("--allow-exceptions", action="store_true",
                       help="let exceptions thrown and caught inside the expression run (an uncaught one "
                            "aborts the app); default: stop the expression at the first throw")
        t.add_argument("expr", nargs="+")
    req("exec", "exec", "evaluate an expression in the selected frame", timeout=60, setup=exec_setup,
        args=lambda a: {"expr": " ".join(a.expr), "lang": a.lang, "po": a.po, "allow_exceptions": a.allow_exceptions,
                        "force": a.force})
    req("cmd", "cmd", "raw lldb command (escape hatch); options go before it", timeout=60,
        setup=lambda t: t.add_argument("command", nargs=argparse.REMAINDER),
        args=lambda a: {"command": " ".join(a.command)})

    def wait_setup(t):
        t.add_argument("--timeout", type=float, required=True, help="seconds (required)")
        t.add_argument("--since", default="mark",
                       help="mark (default: before the last action command), now, or a seq number")
        t.add_argument("--all", action="store_true", help="all conditions, not any")
        t.add_argument("--stop", action="store_true", help="the process stops")
        t.add_argument("--at", help="… at file:line, file or function substring (implies --stop)")
        t.add_argument("--log", action="append", default=[], help="syslog line, loose match")
        t.add_argument("--log-re", action="append", default=[], help="syslog line, regex")
        t.add_argument("--exit", action="store_true", help="the process exits or crashes")
        t.add_argument("--ui", action="append", default=[], help="a UI element with this label appears")
    t = s.add_parser("wait", help="block until a condition holds; bounded, fails fast",
                     description="Loose match: case-insensitive, punctuation ignored, each word prefixes a "
                                 "word of the line, in order. " + DBG_EXIT_HELP)
    wait_setup(t)
    t.set_defaults(func=lambda a: _request(a, "wait", {
        "stop": a.stop, "at": a.at, "log": a.log, "log_re": a.log_re, "exit": a.exit, "ui": a.ui,
        "all": a.all, "since": a.since}))

    def log_setup(t):
        t.add_argument("op", choices=["tail", "head", "since", "grep", "show", "path"])
        t.add_argument("arg", nargs="?", help="since: seq; grep: regex (case-insensitive); show: seq")
        t.add_argument("-n", type=int, default=40, help="events (default 40)")
        t.add_argument("--src", action="append", choices=["syslog", "event", "lldb", "cmd"],
                       help="default: syslog, event, lldb")
        t.add_argument("-C", type=int, default=0, help="grep: context events")
        t.add_argument("--from", dest="since", type=int,
                       help="only events after this seq (default: since the last ios launch; 0: all)")
        t.add_argument("--app", action="store_true", help="drop other subsystems' syslog lines")
        t.add_argument("--text", action="store_true", help="message text only, no seq/time/source prefix")
    req("log", "log", "session log: tail|head|since <seq>|grep <re>|show <seq>|path", setup=log_setup,
        args=_log_args)

    def ui_setup(t):
        t.add_argument("op", choices=["ls", "tap", "back", "action", "screenshot"])
        t.add_argument("arg", nargs="?", help="tap: label (loose match) or #N from ls; action: an accessibility "
                                              "custom action's name (Back, Home, Recent apps); screenshot: path")
    req("ui", None, "app UI: ls | tap <label|#N> | back | action <name> | screenshot [path]", timeout=60,
        setup=ui_setup).set_defaults(
        func=lambda a: _request(a, f"ui_{a.op}", {"arg": a.arg} if a.arg else {}))

    def call_setup(t):
        t.add_argument("--po", action="store_true", help="object description (like po)")
        t.add_argument("fn")
        t.add_argument("args", nargs="*", help="numbers as-is, anything else a C string")
    req("call", "call", "call a function in the app on its main thread through lldb (pauses, then resumes it)",
        timeout=60, setup=call_setup, args=lambda a: {"fn": a.fn, "args": a.args, "po": a.po})

    t = s.add_parser("fresh", help="syslog on, relaunch the app (its debug agent on), wait until its UI "
                                   "answers; --attach: then attach and continue")
    t.add_argument("--attach", action="store_true")
    t.set_defaults(func=_fresh)

    t = s.add_parser("smoke", help="the app's smoke checks, one line per step; --list shows them")
    t.add_argument("names", nargs="*", metavar="scenario", help="default: all, in table order")
    t.add_argument("--list", action="store_true")
    t.add_argument("--network", action="store_true", help="include steps that need the network")
    t.set_defaults(func=_smoke)

    t = s.add_parser("fake", help="test hook: make the fake target (--target fake) emit an event")
    t.add_argument("fake_action")
    t.add_argument("text", nargs="?", default="")
    t.add_argument("--delay", type=float, default=0)
    t.add_argument("--timeout", type=float, default=10)
    t.set_defaults(func=lambda a: _request(a, "slow", {"seconds": float(a.text)}) if a.fake_action == "slow"
                   else _request(a, "fake", {"action": a.fake_action, "text": a.text, "delay": a.delay}))


def _relaunch(app: str) -> int:
    """syslog on, `ios launch`, then wait for the debug agent to show the UI; the pid."""
    resp = client.call("syslog_start", {"debug": False, "subsystem": None})
    if resp["code"]:
        raise DineError(resp["text"])
    pid = _launch(app, False)
    deadline = time.monotonic() + 30
    while (resp := client.call("ui_ls", timeout=10))["code"] or resp["text"].endswith("(no accessibility elements)"):
        if time.monotonic() > deadline:
            raise DineError(f"{app} pid {pid} launched, but its debug agent didn't answer within 30 s:\n"
                            f"{resp['text']}")
        time.sleep(0.2)
    return pid


def _fresh(a) -> int:
    st = client.call("status", timeout=10)
    pid = _relaunch(st["app"])
    print(f"launched {st['app']} pid {pid}\n" + client.call("ui_ls", timeout=10)["text"])
    if a.attach:
        for cmd, timeout in (("attach", 120), ("continue", 30)):
            resp = client.call(cmd, {}, timeout=timeout)
            print(resp["text"])
            if resp["code"]:
                return resp["code"]
    return 0


def _smoke(a) -> int:
    app = client.call("status", timeout=10)["app"]
    if a.list:
        print(smoke.listing(app))
        return 0
    return smoke.run(app, a.names, a.network, lambda: _relaunch(app))


def _log_args(a):
    args = {"op": a.op, "n": a.n, "src": a.src or [], "since": a.since, "context": a.C, "app": a.app, "text": a.text}
    if a.op == "since":
        args["since"] = int(a.arg or 0)
    elif a.op == "grep":
        if not a.arg:
            raise DineError("usage: tools/dine dbg log grep <regex>")
        args["pattern"] = a.arg
    elif a.op == "show":
        args["seq"] = a.arg
    return args


def _request(a, cmd, args) -> int:
    argv = "tools/dine dbg " + shlex.join(sys.argv[sys.argv.index(a.action) if a.action in sys.argv else 1:])
    resp = client.call(cmd, args, timeout=a.timeout, max_lines=a.max_lines, argv=argv)
    print(json.dumps(resp) if a.json else resp["text"])
    return resp["code"]


def _start_server(a) -> int:
    code, text = client.start_server(a.target, a.app, a.timeout)
    print(text)
    return code


def _stop_server(a) -> int:
    pid = session.server_pid()
    resp = client.call("shutdown", {"kill_app": a.kill_app}, timeout=a.timeout, max_lines=a.max_lines)
    print(resp["text"])
    deadline = time.monotonic() + 15
    while pid and session.server_pid() == pid and time.monotonic() < deadline:
        time.sleep(0.2)
    if session.server_pid() == pid:
        print(f"server pid {pid} still alive after 15s; kill it: kill {pid}")
        return 1
    return resp["code"]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tools/dine", description="dine dev tooling. Debugging: tools/dine dbg --help")
    sub = p.add_subparsers(dest="group", required=True)
    _ios(sub)
    _linux(sub)
    _test(sub)
    _dbg(sub)
    return p


PASSTHROUGH = (["ios", "lldb"], ["ios", "lldb-offline"], ["test", "runtime"])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    tail = []
    # Only commands that hand args to another tool split at `--`; elsewhere argparse keeps its
    # meaning (`dbg exec -- -1`).
    if argv[:2] in PASSTHROUGH and "--" in argv:
        i = argv.index("--")
        argv, tail = argv[:i], argv[i + 1:]
    p = parser()
    args, extra = p.parse_known_args(argv)
    mode = getattr(args, "passthrough", None)
    if extra and mode != "all":
        p.error(f"unrecognized arguments: {' '.join(extra)}"
                + (" (arguments for lldb go after --)" if mode == "tail" else ""))
    args.extra = extra + tail
    try:
        rc = args.func(args)
    except DineError as e:
        print(e, file=sys.stderr)
        return 1
    except client.NotRunning:
        print("server not running: tools/dine dbg start-server", file=sys.stderr)
        return client.NOT_RUNNING
    except subprocess.CalledProcessError as e:
        return e.returncode or 1
    except KeyboardInterrupt:
        return 130
    return rc if isinstance(rc, int) else 0
