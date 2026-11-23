cmake_minimum_required(VERSION 3.16)
# Build only main and what it depends on: unused ESP-IDF components (Bluetooth, etc.) stay out of the build
# and out of the SBOM (docs/sbom/), so the vulnerability check covers exactly what ships.
set(COMPONENTS main)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(brim)
