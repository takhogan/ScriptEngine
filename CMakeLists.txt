cmake_minimum_required(VERSION 3.0.0)
project(ImageStitchCalculator VERSION 0.1.0)

include(CTest)
enable_testing()
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)
find_package( OpenCV REQUIRED )
include_directories( ${OpenCV_INCLUDE_DIRS} )

add_executable(ImageStitchCalculator lib/image_stitch_calculator.cpp)

target_link_libraries( ImageStitchCalculator ${OpenCV_LIBS} )

set(CPACK_PROJECT_NAME ${PROJECT_NAME})
set(CPACK_PROJECT_VERSION ${PROJECT_VERSION})
include(CPack)
