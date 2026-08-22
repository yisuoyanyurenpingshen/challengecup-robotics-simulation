cmake_minimum_required(VERSION 3.10)
project(smartclean_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/LitterCleaned.msg"
  "msg/TrashDetection.msg"
  "msg/TrashDetectionArray.msg"
  "msg/TrashMissionState.msg"
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_mission_interfaces_contract
    test/test_mission_interfaces_contract.py
  )
endif()

ament_package()
