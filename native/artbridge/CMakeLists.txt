cmake_minimum_required(VERSION 3.24)
project(artbridge CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(artbridge STATIC artbridge.cpp)
# jni.h is installed into the prefix by `tools/dine ios build-art`.
target_include_directories(artbridge PUBLIC include PRIVATE ${CMAKE_INSTALL_PREFIX}/include)
install(TARGETS artbridge ARCHIVE DESTINATION lib)
install(FILES include/dineart.h DESTINATION include)
