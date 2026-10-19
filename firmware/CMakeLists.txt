cmake_minimum_required(VERSION 3.28.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(firmware)
target_sources(app PRIVATE
    src/main.c
    src/sensors/sensor.c
    src/dsp/features.c
    src/config/config.c
    src/ble/ble_svc.c)
target_include_directories(app PRIVATE src)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
