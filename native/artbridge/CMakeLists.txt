cmake_minimum_required(VERSION 3.24)
project(artbridge CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(DINE_DEV "Probes and runtime-suite runs (dev.cpp, include/dineart_dev.h)" OFF)

add_library(artbridge STATIC artbridge.cpp)
if(DINE_DEV)
  target_sources(artbridge PRIVATE dev.cpp)
  target_compile_definitions(artbridge PRIVATE DINE_DEV)
endif()
# jni.h comes into the prefix with `tools/dine ios build-art`, atl/ with `tools/dine ios build-atl`.
target_include_directories(artbridge PUBLIC include PRIVATE ${CMAKE_INSTALL_PREFIX}/include)
install(TARGETS artbridge ARCHIVE DESTINATION lib)
install(FILES include/dineart.h DESTINATION include)
