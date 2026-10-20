cmake_minimum_required(VERSION 3.24)
project(runtimetests CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# JNI libraries of dine-art's authored runtime tests, linked into Dine. ART finds each through
# JEP 178's JNI_OnLoad_<lib> in the main image.
set(tests ${CMAKE_CURRENT_SOURCE_DIR}/../../../dine-art/tests/runtime/authored)
add_library(runtimetests STATIC ${tests}/dine-0002-jni-args/jni_args.cc)
set_source_files_properties(${tests}/dine-0002-jni-args/jni_args.cc
                            PROPERTIES COMPILE_DEFINITIONS JNI_OnLoad=JNI_OnLoad_dinejniargs)
# jni.h is installed into the prefix by `tools/dine ios build-art`.
target_include_directories(runtimetests PRIVATE ${CMAKE_INSTALL_PREFIX}/include)
install(TARGETS runtimetests ARCHIVE DESTINATION lib)
