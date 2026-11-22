#!/usr/bin/env bash
# Runs the multi-app probes on host ART, each case in its own dalvikvm, with artbridge's VM flags.
# Usage: run.sh [check | case <kind>... | drop <plain|leak> <cycles> | all]. Every mode builds first
# (build.sh); a failed build ends it with status 1. `check` and `all` also end with status 1,
# before any case, when the check is not "check ok" with status 0. Output and each run's log:
# out/probes/multi-app/results/. DINE_PROBE_PREFIX: the ART prefix (default out/linux/prefix).
# DINE_PROBE_EXTRA_JAR: a dex jar added to app b's class path (build.sh makes api-impl-deflated.jar).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
out=$root/out/probes/multi-app
prefix=$(realpath -- "${DINE_PROBE_PREFIX:-$root/out/linux/prefix}") || exit 1
results=$out/results
mkdir -p "$results"
export DINE_PROBE_PREFIX=$prefix
"$here/build.sh" > "$results/build.log" 2>&1 || { tail -n 20 "$results/build.log" >&2; echo "run.sh: build.sh failed (results/build.log)" >&2; exit 1; }
cases=(wait park park-fresh park-unpark sleep read-inject read-shutdown read-close read-rawclose busy catchall juclock blocked frozen
  clinit storm-control storm native-careful native-careless)

vm() {  # vm <log name> <driver args...>; stdout to <name>.log, stderr to <name>.err
  local log=$results/$1.log err=$results/$1.err work
  shift
  work=$(mktemp -d)
  env LD_LIBRARY_PATH="$prefix/lib" ANDROID_DATA="$work" XDG_CACHE_HOME="$work" ANDROID_LOG_TAGS='*:e' \
    timeout 300 "$prefix/bin/dalvikvm" -Xint -Xusejit:false -Xnorelocate -XX:DumpNativeStackOnSigQuit:false \
    -Xcheck:jni -Djava.library.path="$out" -Dprobe.dir="$out" -Dprobe.extrajar="${DINE_PROBE_EXTRA_JAR:-}" \
    -Dprobe.bootjars="$prefix/lib/java/dex/art/core-oj-hostdex.jar:$prefix/lib/java/dex/art/core-libart-hostdex.jar" \
    -cp "$out/driver.jar" probe.Driver "$@" > "$log" 2> "$err"
  local rc=$?
  rm -rf "$work"
  grep -hE '^(check|case|drop|native:|app )' "$log" "$err"
  echo "$* rc=$rc"
}

guard() {  # the probe library's own check: it must agree with libart before a case means anything
  local lines
  lines=$(vm check check)
  printf '%s\n' "$lines"
  if [[ $lines != "check ok"* || $lines != *$'\ncheck rc=0' ]]; then
    echo "run.sh: the check failed, so the probes don't match libart: no case run (results/check.log, check.err)" >&2
    exit 1
  fi
}

case ${1:-all} in
  check) guard ;;
  case) shift; for c in "$@"; do vm "case-$c" case "$c"; done ;;
  drop) vm "drop-$2${DINE_PROBE_EXTRA_JAR:+-extra}" drop "$2" "$3" ;;
  all)
    guard
    for c in "${cases[@]}"; do vm "case-$c" case "$c"; done
    vm drop-plain drop plain 10
    vm drop-leak drop leak 2
    ;;
  *) echo "run.sh: unknown mode $1" >&2; exit 2 ;;
esac
