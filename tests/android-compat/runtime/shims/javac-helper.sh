#!/usr/bin/env bash
# Stand-in for AOSP art/tools/javac-helper.sh: compile against art_standalone's libcore instead
# of an AOSP out/ tree. $JAVAC may be a function exported by a test's build script.
mode=host
while true; do
  case $1 in
    --mode=*) mode=${1#--mode=} ;;
    --core-only|--show-commands) ;;
    *) break ;;
  esac
  shift
done
if [[ $mode == jvm ]]; then
  $JAVAC "$@"
else
  $JAVAC -bootclasspath "$DINE_CORE_JAR" "$@"
fi
