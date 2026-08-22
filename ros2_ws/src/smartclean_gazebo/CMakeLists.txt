cmake_minimum_required(VERSION 3.10)
project(smartclean_gazebo)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch maps models worlds urdf rviz
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_model_contract
    test/test_model_contract.py
  )
  ament_add_pytest_test(
    test_gui_contract
    test/test_gui_contract.py
  )
  ament_add_pytest_test(
    test_trash_scene_contract
    test/test_trash_scene_contract.py
  )
  ament_add_pytest_test(
    test_camera_contract
    test/test_camera_contract.py
  )
  ament_add_pytest_test(
    test_lidar_contract
    test/test_lidar_contract.py
  )
  ament_add_pytest_test(
    test_nav2_contract
    test/test_nav2_contract.py
  )
  ament_add_pytest_test(
    test_trash_mission_contract
    test/test_trash_mission_contract.py
  )
endif()

ament_package()
