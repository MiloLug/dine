# Sourced after env.sh. ios_cmake SRC BUILD [cmake args...]: configure the CMake project SRC into
# BUILD with tools/cmake/ios.toolchain.cmake, then build it.
ios_cmake() {
  local src=$1 build=$2
  shift 2
  local toolchain="$DINE_ROOT/tools/cmake/ios.toolchain.cmake" cache="$build/CMakeCache.txt"
  # CMake keeps the toolchain and the source dir of the first configure, so a moved one needs a
  # fresh dir. A reconfigure stores the toolchain as UNINITIALIZED, a first configure as FILEPATH.
  if [[ -f $cache ]] && ! { grep -qxF -e "CMAKE_TOOLCHAIN_FILE:FILEPATH=$toolchain" \
                                   -e "CMAKE_TOOLCHAIN_FILE:UNINITIALIZED=$toolchain" "$cache" &&
                            grep -qxF "CMAKE_HOME_DIRECTORY:INTERNAL=$src" "$cache"; }; then
    rm -rf "$build"
  fi
  cmake -S "$src" -B "$build" -G Ninja -Wno-unused-cli \
    -DCMAKE_TOOLCHAIN_FILE="$toolchain" -DDINE_IOS_MIN="$DINE_IOS_MIN" \
    -DCMAKE_BUILD_TYPE="${DINE_IOS_BUILD_TYPE:-RelWithDebInfo}" "$@"
  cmake --build "$build"
}
