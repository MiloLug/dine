"""`dine ios …`: device tunnel, build/install/launch, processes, logs, symbols, interactive lldb."""

import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import paths
from .paths import DineError

TUNNELD = "http://127.0.0.1:49151/"
# native/dev/dbgagent listens on this port on the phone when the app gets it in its environment.
AGENT_ENV, AGENT_PORT = "DINE_DBG_AGENT_PORT", 47801


def pmd(*args: str, timeout: float = 60) -> str:
    try:
        r = subprocess.run([str(paths.PMD), *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise DineError(f"pymobiledevice3 {' '.join(args[:3])} timed out after {timeout:g}s") from None
    if r.returncode:
        raise DineError(f"pymobiledevice3 {shlex.join(args)} failed:\n{(r.stderr or r.stdout).strip()[-1500:]}")
    return r.stdout


def tunnel_up() -> bool:
    try:
        with urllib.request.urlopen(TUNNELD, timeout=3) as r:
            return b"tunnel-address" in r.read()
    except OSError:
        return False


def require_tunnel() -> None:
    if not tunnel_up():
        raise DineError("no device tunnel (iOS 17+ developer services): tools/dine ios tunnel start")


def _unit_active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def _amds_route() -> str | None:
    """The route usbmuxd-bridge's connection to Windows AMDS (127.0.0.1:27015) takes in WSL's
    mirrored networking, or None when there is no such route. wsl-quickack keeps quickack on it."""
    out = subprocess.run(["ip", "route", "show", "table", "127"], capture_output=True, text=True).stdout
    return next((line.strip() for line in out.splitlines() if line.startswith("127.0.0.1 ")), None)


def quickack_warning() -> str | None:
    route = _amds_route()
    if route is None or "quickack 1" in route:
        return None
    return "the usbmux route to Windows has no quickack: every small lldb reply waits ~40 ms " \
           "(wsl-quickack not running? docs/first-run.md, step 3)"


UNITS = ("usbmuxd-bridge", "dine-tunneld")


def _ddi_mounted() -> bool:
    try:
        return any(i.get("IsMounted") for i in json.loads(pmd("mounter", "list", "--tunnel", "", timeout=15)))
    except (DineError, json.JSONDecodeError):
        return False


def tunnel_status() -> str:
    lines = [f"{u}: {'active' if _unit_active(u) else 'inactive'}" for u in UNITS]
    up = tunnel_up()
    lines.append(f"tunnel: {'up' if up else 'down'}")
    route = _amds_route()
    lines.append(f"quickack: {'n/a' if route is None else 'on' if 'quickack 1' in route else 'off'}")
    lines.append(f"ddi: {'mounted' if up and _ddi_mounted() else 'not mounted'}")
    return "\n".join(lines)


def tunnel_start() -> str:
    """Start dine-tunneld if it's down (it normally runs from boot), wait for the tunnel, and mount
    the Developer Disk Image, which a phone reboot unmounts."""
    if not _unit_active("dine-tunneld"):
        print("starting dine-tunneld (sudo)", file=sys.stderr)
        subprocess.run(["sudo", "systemctl", "start", "dine-tunneld"], check=True)
    deadline = time.monotonic() + 20
    while not tunnel_up():
        if time.monotonic() > deadline:
            raise DineError("dine-tunneld runs but no tunnel after 20s: is the phone connected and "
                            f"unlocked? journalctl -u dine-tunneld\n{tunnel_status()}")
        time.sleep(1)
    if not _ddi_mounted():
        pmd("mounter", "auto-mount", "--tunnel", "", timeout=120)
    if warning := quickack_warning():
        print(f"warning: {warning}", file=sys.stderr)
    return tunnel_status()


def bundle_base(app: str) -> str:
    """The bundle ID in the app's xtool.yml, which is also its os_log subsystem."""
    text = (paths.app_dir(app) / "xtool.yml").read_text()
    return re.search(r"^bundleID:\s*(\S+)", text, re.M).group(1)


async def _bundle_id(rsd, app: str) -> str:
    """Installed bundle ID: free-account xtool installs are prefixed `XTL-<TeamID>.`."""
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    base = bundle_base(app)
    async with InstallationProxyService(rsd) as ip:
        installed = list(await ip.get_apps(application_type="User"))
    for b in installed:
        if re.fullmatch(rf"XTL-[A-Z0-9]+\.{re.escape(base)}", b):
            return b
    if base in installed:
        return base
    raise DineError(f"{base} isn't installed on the phone: tools/dine ios run {app}")


def launch(app: str, suspended: bool = False) -> int:
    """Launch through DVT with the debug agent on (kills a running instance first); returns the pid."""
    from pymobiledevice3.exceptions import PyMobileDevice3Exception
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
    require_tunnel()

    async def run(rsd):
        bundle = await _bundle_id(rsd, app)
        async with DvtProvider(rsd) as dvt, ProcessControl(dvt) as pc:
            return await asyncio.wait_for(pc.launch(bundle, kill_existing=True, start_suspended=suspended,
                                                    environment={AGENT_ENV: str(AGENT_PORT)}), 60)
    try:
        return _with_rsd(run)
    except (AssertionError, TimeoutError, PyMobileDevice3Exception) as e:
        raise DineError(f"launching {app} failed: {str(e) or type(e).__name__}\n(screen off or phone "
                        "locked, developer certificate not trusted, or the DDI unmounted after a reboot: "
                        "tools/dine ios tunnel start)") from None


def _with_rsd(fn):
    """Run `fn(rsd)` against the tunneld device in a fresh event loop: in-process, ~1 s cheaper than
    a pymobiledevice3 CLI run."""
    from pymobiledevice3.tunneld.api import get_tunneld_devices

    async def main():
        rsds = await get_tunneld_devices()
        if not rsds:
            raise DineError("tunneld has no device: is the phone connected? tools/dine ios tunnel status")
        try:
            return await fn(rsds[0])
        finally:
            for rsd in rsds:
                await rsd.close()
    return asyncio.run(main())


def processes(app: str | None = None) -> list[dict]:
    from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    require_tunnel()

    async def proclist(rsd):
        async with DvtProvider(rsd) as dvt, DeviceInfo(dvt) as info:
            return await info.proclist()
    procs = _with_rsd(proclist)
    return [p for p in procs if p.get("name") == app] if app else procs


def kill(pid: int) -> None:
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
    require_tunnel()

    async def run(rsd):
        async with DvtProvider(rsd) as dvt, ProcessControl(dvt) as pc:
            await pc.kill(pid)
    _with_rsd(run)


def screenshot() -> bytes:
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.screenshot import Screenshot
    require_tunnel()

    async def run(rsd):
        async with DvtProvider(rsd) as dvt, Screenshot(dvt) as shot:
            return await shot.get_screenshot()
    return _with_rsd(run)


def debugserver_url() -> str:
    require_tunnel()

    async def url(rsd):
        port = rsd.get_service_port("com.apple.internal.dt.remote.debugproxy")
        return f"connect://[{rsd.service.address[0]}]:{port}"
    return _with_rsd(url)


def symbols_dir() -> Path:
    async def version(rsd):
        return rsd.product_version, rsd.product_build_version
    return paths.OUT / "ios-symbols/{} ({})".format(*_with_rsd(version))


def lldb_platform_cmd() -> str:
    """System dylibs come from the phone's shared cache split by `dine ios symbols`; Swift `po` needs
    their symbols. Without them lldb reads device memory, minimal info only."""
    symbols = symbols_dir()
    if (symbols / "Symbols").is_dir():
        return f'platform select remote-ios --sysroot "{symbols}"'
    print(f"no local system symbols for this iOS ({symbols}): tools/dine ios symbols, for Swift po",
          file=sys.stderr)
    return "platform select remote-ios"


def lldb_setup_cmds() -> list[str]:
    """Run right after `target create`. lldb can't resolve the DWARF SDK on Linux (HostInfoError);
    without target.sdk-path, Swift expressions can't import Darwin."""
    cmds = [f'settings set target.sdk-path "{paths.env("DINE_IOS_SDK")}"']
    log = os.environ.get("DINE_LLDB_LOG")
    if log:
        Path(log).mkdir(parents=True, exist_ok=True)
        cmds += [f'log enable -T -f "{log}/lldb.log" lldb types expr',
                 f'log enable -T -f "{log}/swift-health.log" swift health',
                 f'log enable -T -f "{log}/gdb-remote.log" gdb-remote packets']
    return cmds


# 16 KiB (the device page) per memory read instead of 512 bytes. DINE_LLDB_LOAD_LEVEL=complete
# reads symbols from device memory too: ~30 s slower, but `po` works without local symbols.
def lldb_memory_cmds() -> list[str]:
    # Not symbols.enable-lldb-index-cache: with a warm cache, attach segfaults in
    # Symbol::ResolveReExportedSymbol (lldb 21 swiftlang).
    return [f"settings set target.memory-module-load-level {os.environ.get('DINE_LLDB_LOAD_LEVEL', 'minimal')}",
            "settings set target.process.memory-cache-line-size 16384"]


def release() -> bool:
    """DINE_RELEASE=1: the iOS builds leave out every dev and test part (CLAUDE.md)."""
    value = os.environ.get("DINE_RELEASE", "")
    if value not in ("", "0", "1"):
        raise DineError(f"DINE_RELEASE={value!r}: set 1 for a release build, or leave it unset")
    return value == "1"


def atl_hooks_problem(build_dir: Path, release: bool) -> str | None:
    """The iOS ATL build's test_hooks option against the build being made: the archive comes from
    a separate step (`ios build-atl`), and a stale dev one would ship its hooks."""
    info = build_dir / "meson-info/intro-buildoptions.json"
    if not info.exists():
        return f"no iOS ATL build in {build_dir}: run tools/dine ios build-atl"
    hooks = next((o["value"] for o in json.loads(info.read_text()) if o["name"] == "test_hooks"), None)
    want = "DINE_RELEASE=1 tools/dine ios build-atl" if release else "tools/dine ios build-atl"
    if hooks is None:
        return f"the iOS ATL build predates its test_hooks option: run {want}"
    if hooks == release:
        return (f"the iOS ATL build has test_hooks={str(hooks).lower()}, this is a "
                f"{'release' if release else 'dev'} build: run {want}")
    return None


def check_atl_build() -> None:
    """For `ios run`, before it kills or builds anything."""
    if problem := atl_hooks_problem(paths.OUT / "ios/build/dine-atl", release()):
        raise DineError(problem)


def run_libexec(script: str, *args: str) -> int:
    release()  # a malformed DINE_RELEASE stops here, before any script reads it
    return subprocess.run([str(paths.LIBEXEC / script), *args]).returncode


def cmd_install(app: str) -> int:
    """build-native, build-dev, build-assets + `xtool dev run` (build, sign, install); the caller
    runs check_atl_build first and launches after."""
    rel = release()
    require_tunnel()
    rc = run_libexec("build-ios-native.sh") or run_libexec("build-ios-dev.sh") or run_libexec("build-ios-assets.sh", app)
    if rc:
        return rc
    cmd = ["xtool", "dev", "run", *(["-c", "release"] if rel else [])]
    # xtool crashes with stdin = /dev/null (epoll_ctl EPERM): give it a pty when not on a terminal.
    xtool = cmd if sys.stdin.isatty() else ["script", "-qec", shlex.join(cmd), "/dev/null"]
    proc = subprocess.Popen(xtool, cwd=paths.app_dir(app), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = b""
    # Chunks, not lines: xtool's yes/no prompts end without a newline.
    while chunk := os.read(proc.stdout.fileno(), 4096):
        sys.stdout.buffer.write(chunk)
        sys.stdout.flush()
        out += chunk
    # Installs fine, then its pre-iOS-17 debugserver launch step fails; tolerate only that error.
    if proc.wait() and b"DebugserverClient" not in out:
        return proc.returncode
    return 0


def cmd_symbols() -> int:
    """Local copies of the phone's system dylibs, so lldb reads their symbols from disk instead of
    device memory. Pulls the dyld shared cache (~7 GB, ~5 min) and splits it with ipsw."""
    if subprocess.run(["sh", "-c", "command -v ipsw"], capture_output=True).returncode:
        raise DineError("ipsw not found: paru -S ipsw-bin")
    require_tunnel()
    d = symbols_dir()
    if (d / "Symbols").is_dir():
        print(f"already there: {d}")
        return 0
    d.mkdir(parents=True, exist_ok=True)
    dsc = d / "dsc"
    subprocess.run([str(paths.PMD), "developer", "fetch-symbols", "download", "--tunnel", "", str(dsc)], check=True)
    cache = next(dsc.rglob("Caches/com.apple.dyld/dyld_shared_cache_arm64e"), None)
    if cache is None:
        raise DineError(f"no dyld_shared_cache_arm64e in {dsc}: the download is incomplete; delete {d} and rerun")
    # --all keeps the install paths, which is the DeviceSupport Symbols/ layout lldb expects.
    subprocess.run(["ipsw", "dyld", "extract", str(cache), "--all", "-o", str(d / "Symbols.tmp")], check=True)
    (d / "Symbols.tmp").rename(d / "Symbols")
    subprocess.run(["rm", "-rf", str(dsc)], check=True)
    print(f"symbols ready: {d}")
    return 0


def cmd_lldb(app: str, suspended: bool, extra: list[str]) -> None:
    """Interactive lldb: launch (optionally suspended, for startup breakpoints) and attach."""
    if warning := quickack_warning():
        print(f"warning: {warning}", file=sys.stderr)
    pid = launch(app, suspended)
    url = debugserver_url()
    print(f"attaching to {app} pid {pid} via {url}"
          + (" (suspended: set breakpoints, then continue)" if suspended else ""), file=sys.stderr)
    args = ["-o", lldb_platform_cmd()]
    for c in lldb_memory_cmds() + [f'target create "{paths.app_binary(app)}"'] + lldb_setup_cmds():
        args += ["-o", c]
    # `process connect` with no process blocks in sync mode, hence the SetAsync dance.
    args += ["-o", "script lldb.debugger.SetAsync(True)", "-o", f"process connect {url}",
             "-o", "script import time; time.sleep(2); lldb.debugger.SetAsync(False)",
             "-o", f"process attach -p {pid}"]
    lldb = paths.env("DINE_LLDB")
    os.execv(lldb, [lldb, *args, *extra])


def cmd_lldb_offline(app: str, bp: str, extra: list[str]) -> None:
    """lldb on a synthetic core (tools/libexec/ios-core.py) stopped at `bp`, no phone. Checks the
    Swift expression context in seconds; `expr` itself can't run there."""
    lldb = paths.env("DINE_LLDB")
    binary = paths.app_binary(app)
    out = subprocess.run([lldb, "-b", "-o", f'target create "{binary}"', "-o", f"b {bp}"],
                         capture_output=True, text=True).stdout
    m = re.search(r"address = (0x[0-9a-f]+)", out)
    if not m:
        raise DineError(f"no address for breakpoint {bp!r} in {binary}")
    core = paths.OUT / f"ios/{app}.core"
    core.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-I", str(paths.LIBEXEC / "ios-core.py"), str(binary), str(core), m.group(1)],
                   check=True)
    args = ["-o", f'target create "{binary}" --core "{core}"']
    for c in lldb_setup_cmds() + [f"target modules load --file {app} --slide 0"]:
        args += ["-o", c]
    os.execv(lldb, [lldb, *args, *extra])
