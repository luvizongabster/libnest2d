cmake_minimum_required(VERSION 3.14)
project(nest_engine CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# nlohmann/json via FetchContent
include(FetchContent)
FetchContent_Declare(
  json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG        v3.11.2
)
FetchContent_MakeAvailable(json)

# libnest2d: expect LIBNEST2D_SOURCE_DIR set by Dockerfile (e.g. /tmp/libnest2d)
if(NOT DEFINED LIBNEST2D_SOURCE_DIR)
  set(LIBNEST2D_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/libnest2d" CACHE PATH "libnest2d source directory")
endif()

if(NOT EXISTS "${LIBNEST2D_SOURCE_DIR}/CMakeLists.txt")
  message(FATAL_ERROR "libnest2d not found at ${LIBNEST2D_SOURCE_DIR}. Set LIBNEST2D_SOURCE_DIR or clone libnest2d.")
endif()

add_subdirectory(${LIBNEST2D_SOURCE_DIR} ${CMAKE_BINARY_DIR}/libnest2d_build)

add_executable(nest_engine main.cpp)
target_link_libraries(nest_engine PRIVATE libnest2d_headeronly nlohmann_json::nlohmann_json)
