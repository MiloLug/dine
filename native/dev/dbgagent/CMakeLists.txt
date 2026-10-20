cmake_minimum_required(VERSION 3.24)
project(dbgagent OBJCXX)

set(CMAKE_OBJCXX_STANDARD 20)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)

add_library(dbgagent STATIC agent.mm)
target_compile_options(dbgagent PRIVATE -fobjc-arc)
target_include_directories(dbgagent PUBLIC include)
install(TARGETS dbgagent ARCHIVE DESTINATION lib)
install(FILES include/dbgagent.h DESTINATION include)
