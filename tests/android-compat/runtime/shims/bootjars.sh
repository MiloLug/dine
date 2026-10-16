#!/usr/bin/env bash
# Stand-in for AOSP art/tools/bootjars.sh. default-build only asks for `--<mode> --core --path`
# (the d8 desugaring classpath): answer with art_standalone's libcore classes.
echo "$DINE_CORE_JAR"
