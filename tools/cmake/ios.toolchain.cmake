# Cross-compile for iOS (arm64) from Linux with system clang + the Darwin SDK built by xtool.
# Usage: cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=tools/cmake/ios.toolchain.cmake ...
# Needs DINE_IOS_SDK (from env.sh) or -DDINE_IOS_SDK=/path/to/iPhoneOS.sdk.

if(NOT DINE_IOS_SDK)
  set(DINE_IOS_SDK "$ENV{DINE_IOS_SDK}")
endif()
if(NOT DINE_IOS_SDK OR NOT EXISTS "${DINE_IOS_SDK}")
  message(FATAL_ERROR "DINE_IOS_SDK not set or missing; source env.sh after `xtool sdk install`")
endif()
set(DINE_IOS_MIN "17.0" CACHE STRING "Minimum iOS deployment target")

# Pass to try_compile projects too.
list(APPEND CMAKE_TRY_COMPILE_PLATFORM_VARIABLES DINE_IOS_SDK DINE_IOS_MIN)

set(CMAKE_SYSTEM_NAME iOS)
set(CMAKE_SYSTEM_PROCESSOR arm64)
set(CMAKE_OSX_ARCHITECTURES arm64)
set(CMAKE_OSX_SYSROOT "${DINE_IOS_SDK}")
set(CMAKE_OSX_DEPLOYMENT_TARGET "${DINE_IOS_MIN}")

set(_target arm64-apple-ios${DINE_IOS_MIN})
set(CMAKE_C_COMPILER clang)
set(CMAKE_CXX_COMPILER clang++)
set(CMAKE_ASM_COMPILER clang)
# OBJCXX detection only resolves a bare compiler name into the cache, which this file's plain
# variable shadows: give it the full path.
find_program(_clangxx clang++ REQUIRED NO_CACHE)
set(CMAKE_OBJCXX_COMPILER ${_clangxx})
set(CMAKE_C_COMPILER_TARGET ${_target})
set(CMAKE_CXX_COMPILER_TARGET ${_target})
set(CMAKE_ASM_COMPILER_TARGET ${_target})
set(CMAKE_OBJCXX_COMPILER_TARGET ${_target})

set(CMAKE_AR llvm-ar CACHE FILEPATH "")
set(CMAKE_RANLIB llvm-ranlib CACHE FILEPATH "")
set(CMAKE_INSTALL_NAME_TOOL llvm-install-name-tool CACHE FILEPATH "")
set(CMAKE_LINKER_TYPE LLD)
# xtool's ld64.lld (DINE_IOS_TOOLSET_BIN, env.sh): the system one rejects the SDK's .tbd stubs.
set(CMAKE_EXE_LINKER_FLAGS_INIT "-B$ENV{DINE_IOS_TOOLSET_BIN}")

# No Xcode here: libc++ headers come from the SDK; never shell out to xcrun.
set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_FIND_ROOT_PATH "${DINE_IOS_SDK}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
