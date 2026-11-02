#!/usr/bin/env bash
# Runs the multi-app probes on host ART, each case in its own dalvikvm, with artbridge's VM flags.
# Usage: run.sh [check | case <kind>... | drop <plain|leak> <cycles> | all]. Output and each run's
# log: out/probes/multi-app/results/. DINE_PROBE_PREFIX: the ART prefix (default out/linux/prefix).
# DINE_PROBE_EXTRA_JAR: a dex jar added to app b's class path (build.sh makes api-impl-deflated.jar).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
out=$root/out/probes/multi-app
prefix=${DINE_PROBE_PREFIX:-$root/out/linux/prefix}
results=$out/results
mkdir -p "$results"
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

case ${1:-all} in
  check) vm check check ;;
  case) shift; for c in "$@"; do vm "case-$c" case "$c"; done ;;
  drop) vm "drop-$2${DINE_PROBE_EXTRA_JAR:+-extra}" drop "$2" "$3" ;;
  all)
    vm check check
    for c in "${cases[@]}"; do vm "case-$c" case "$c"; done
    vm drop-plain drop plain 10
    vm drop-leak drop leak 2
    ;;
  *) echo "run.sh: unknown mode $1" >&2; exit 2 ;;
esac
