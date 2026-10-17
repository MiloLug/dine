"""Decide how to run an upstream ART run-test, or why to skip it.

Upstream runs a test through its `run` script (bash on top of etc/run-test-jar), which assumes an
AOSP host tree. Those scripts never run here: the common one-line form
(`exec ${RUN} "$@" <flags>` / `./default-run "$@" <flags>`) is translated into dalvikvm arguments,
and everything else is skipped with a reason that the summary counts.
"""

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

# run-test passes `--testlib arttestd` through "$@"; tests read it as args[0].
TESTLIB = "arttestd"


class Unsupported(Exception):
    pass


@dataclass
class RunSpec:
    vm_args: list[str] = field(default_factory=list)
    main_args: list[str] = field(default_factory=list)
    main: str = "Main"
    secondary: bool = False
    timeout: int | None = None


# Flags that only affect dex2oat, images or other AOT/JIT setup. Tests run dex directly under
# -Xint with no boot image, so they are no-ops here.
IGNORED = {"--no-app-image", "--profile", "--random-profile", "--vdex", "--dm", "--prebuild",
           "--no-prebuild", "--relocate", "--no-relocate", "--no-image", "--sync",
           "--external-log-tags", "--jit", "--interpreter", "--no-optimize", "--64", "--host",
           "--quiet", "-O"}
IGNORED_WITH_ARG = {"-Xcompiler-option", "--vdex-filter", "--vdex-arg", "--compact-dex-level",
                    "--dex2oat-timeout", "--dex2oat-rt-timeout",
                    "--instruction-set-features", "--lib", "--boot"}
VM_ARG = {"--runtime-option", "--android-runtime-option"}
MAIN_ARG = {"--args", "--testlib"}
VERIFY = {"--verify-soft-fail": "-Xverify:softfail", "--no-verify": "-Xverify:none"}
JVMTI = re.compile(r"--jvmti|--with-agent")
LOAD_ARTTEST = re.compile(r"System\.loadLibrary\(\s*args\[0\]\s*\)")


def parse_run_script(text: str) -> RunSpec:
    """Translate a `run` script into a RunSpec, or raise Unsupported(reason)."""
    if JVMTI.search(text):
        raise Unsupported("jvmti")
    lines = [l.strip() for l in text.replace("\\\n", " ").splitlines()]
    lines = [l for l in lines if l and not l.startswith("#") and l not in ("set -e", "set -x")]
    if len(lines) != 1:
        raise Unsupported("custom run script")
    words = shlex.split(lines[0], comments=True)
    if words and words[0] == "exec":
        words = words[1:]
    if not words or words[0] not in ("${RUN}", "$RUN", "./default-run"):
        raise Unsupported("custom run script")

    spec = RunSpec()
    main = None
    it = iter(words[1:])
    for w in it:
        if w.startswith("$@") or w.startswith("${@"):
            spec.main_args.append(TESTLIB)
        elif w in IGNORED:
            pass
        elif w in IGNORED_WITH_ARG:
            next(it, None)
        elif w in VM_ARG:
            spec.vm_args.append(next(it))
        elif w in MAIN_ARG:
            spec.main_args.append(next(it))
        elif w in VERIFY:
            spec.vm_args.append(VERIFY[w])
        elif w == "--secondary":
            spec.secondary = True
        elif w == "--timeout":
            spec.timeout = int(next(it))
        elif w.startswith("-"):
            raise Unsupported(f"run flag {w}")
        elif main is None:
            main = w
        else:
            raise Unsupported("custom run script")
    if main:
        spec.main = main
    return spec


VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def expand_vars(args: list[str], env: dict) -> list[str]:
    """Expand $VAR / ${VAR} in translated run-script args, as bash would at run time
    (e.g. ${DEX_LOCATION}). Unknown variables are left as written."""
    def sub(m):
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))
    return [VAR.sub(sub, a) for a in args]


def classify(test_dir: Path) -> tuple[RunSpec | None, str | None]:
    """(spec, None) for a runnable test, (None, reason) for a skipped one."""
    run = test_dir / "run"
    if run.exists() and JVMTI.search(run.read_text(errors="replace")):
        return None, "jvmti"
    for src in test_dir.rglob("*.java"):
        if LOAD_ARTTEST.search(src.read_text(errors="replace")):
            return None, "needs libarttest"
    if not run.exists():
        return RunSpec(main_args=[TESTLIB]), None
    try:
        return parse_run_script(run.read_text(errors="replace")), None
    except Unsupported as e:
        return None, str(e)
