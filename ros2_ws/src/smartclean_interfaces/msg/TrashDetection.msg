# A single trash detection produced by an image-based detector.
#
# Coordinates: bbox_xyxy is in the analysis image (the image the detector
# received, after any documented correction). For the Gazebo RGB camera the
# raw /camera/image_raw frame is used directly (no flip; see calibration
# notes in logs/2026-08-22-overnight-autonomous-work.md).

# Schema version for forward compatibility.
uint32 schema_version

# Unique detection id within one detector session.
string detection_id

# Canonical trash class from smartclean_sim.models.TRASH_CLASSES.
string class_name

# Match score in [0, 1]. The color baseline reports a heuristic score,
# not a calibrated probability.
float32 confidence

# Bounding box [x_min, y_min, x_max, y_max] in pixels.
float32[4] bbox_xyxy

# Timestamp of the source image this detection was computed from.
builtin_interfaces/Time image_stamp

# Which detector produced this detection.
string source

# True when position fields are reliable.
bool position_valid

# Detected position (x, y, z) in position_frame_id when position_valid.
float32[3] position

# Frame id of position.
string position_frame_id

# Mask/contour area in pixels (diagnostic).
float32 area_px
