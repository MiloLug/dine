cmake_minimum_required(VERSION 3.24)
project(dinehello CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(dinehello STATIC hello.cpp)
target_include_directories(dinehello PUBLIC include)
install(TARGETS dinehello ARCHIVE DESTINATION lib)
install(FILES include/dinehello.h DESTINATION include)
