# Source me:  source env.sh
# Sets up paths for iOS cross-builds (xtool Darwin SDK) and the local Linux ATL/ART prefix.

DINE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export DINE_ROOT

# Python tooling (pymobiledevice3, meson) lives in the in-repo .venv (`uv sync`); downloads no
# package manager ships (the xtool AppImage) live in out/tools/bin. Nothing goes to ~/.local.
# Setup: docs/first-run.md.
case ":$PATH:" in *":$DINE_ROOT/.venv/bin:"*) ;; *) PATH="$DINE_ROOT/.venv/bin:$DINE_ROOT/out/tools/bin:$PATH" ;; esac
# tools: the `dine` CLI; tools/bin: tracked wrappers (d8 on its own JDK).
case ":$PATH:" in *":$DINE_ROOT/tools/bin:"*) ;; *) PATH="$DINE_ROOT/tools:$DINE_ROOT/tools/bin:$PATH" ;; esac
export PATH

# iPhoneOS.sdk inside the darwin Swift SDK that `xtool sdk install` built from Xcode.xip.
if [[ -z "${DINE_IOS_SDK:-}" ]]; then
  for _d in "$HOME/.swiftpm/swift-sdks" "$HOME/.local/share/swiftpm/swift-sdks" "$HOME/.config/swiftpm/swift-sdks"; do
    [[ -d $_d ]] || continue
    DINE_IOS_SDK="$(find -L "$_d" -maxdepth 8 -type d -name 'iPhoneOS*.sdk' 2>/dev/null | sort | tail -n1)"
    [[ -n $DINE_IOS_SDK ]] && break
  done
  unset _d
fi
export DINE_IOS_SDK
# 17.4: ART's park uses os_sync_wait_on_address. Keep apps/Dine/Package.swift's iosMin in sync.
export DINE_IOS_MIN="${DINE_IOS_MIN:-17.4}"
# Linker for iOS links: clang -fuse-ld=lld -B"$DINE_IOS_TOOLSET_BIN". The system ld64.lld rejects
# the SDK's arm64e .tbd stubs; xtool's toolset ships one that reads them.
export DINE_IOS_TOOLSET_BIN="${DINE_IOS_TOOLSET_BIN:-${DINE_IOS_SDK%/Developer/Platforms/*}/toolset/bin}"
# Swift resource dir of the Darwin toolchain in the same bundle (iphoneos/prebuilt-modules, clang
# builtins). tools/libexec/lldb makes it lldb's Swift resource dir.
export DINE_IOS_SWIFT_RESOURCES="${DINE_IOS_SWIFT_RESOURCES:-${DINE_IOS_SDK%/Developer/Platforms/*}/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift}"

# Swift toolchain lldb wrapper (has the Swift plugin; /usr/bin/lldb does not).
export DINE_LLDB="$DINE_ROOT/tools/libexec/lldb"

# Device access goes through the usbmuxd-bridge systemd unit (/var/run/usbmuxd ->
# Windows AMDS on 127.0.0.1:27015). If the unit is down, uncomment:
# export USBMUXD_SOCKET_ADDRESS=127.0.0.1:27015

# Linux ATL/ART prefix, built by `tools/dine linux build`.
export DINE_LINUX_PREFIX="${DINE_LINUX_PREFIX:-$DINE_ROOT/out/linux/prefix}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-8-openjdk}"
case ":$PATH:" in *":$DINE_LINUX_PREFIX/bin:"*) ;; *) PATH="$DINE_LINUX_PREFIX/bin:$PATH" ;; esac
export PATH
export PKG_CONFIG_PATH="$DINE_LINUX_PREFIX/lib/pkgconfig:$DINE_LINUX_PREFIX/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
# ATL rpaths assume bionic_translation libs (libdl_bio, libc_bio, ...) live in a system lib dir.
case ":${LD_LIBRARY_PATH:-}:" in *":$DINE_LINUX_PREFIX/lib:"*) ;; *) export LD_LIBRARY_PATH="$DINE_LINUX_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ;; esac
