cmake_minimum_required(VERSION 3.10)
project(smartclean_core)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

get_filename_component(
  SMARTCLEAN_SIM_PACKAGE
  "${CMAKE_CURRENT_SOURCE_DIR}/../../../src/smartclean_sim"
  ABSOLUTE
)
ament_python_install_package(
  smartclean_sim
  PACKAGE_DIR "${SMARTCLEAN_SIM_PACKAGE}"
)

install(
  FILES "${CMAKE_CURRENT_SOURCE_DIR}/../../../configs/demo.json"
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
