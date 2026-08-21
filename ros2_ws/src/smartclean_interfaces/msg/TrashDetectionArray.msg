# Array of trash detections with detector performance diagnostics.
std_msgs/Header header

smartclean_interfaces/TrashDetection[] detections

# Detector processing latency for this frame in milliseconds.
float32 processing_ms

# Sliding-window detector frames per second.
float32 fps
