cmake_minimum_required(VERSION 3.10)
project(smartclean_gazebo)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch models worlds
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_model_contract
    test/test_model_contract.py
  )
endif()

ament_package()
