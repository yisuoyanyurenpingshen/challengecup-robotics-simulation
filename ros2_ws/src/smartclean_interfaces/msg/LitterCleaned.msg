# Emitted only after the robot has reached a detected litter target, stopped,
# and the cleaning actuator has confirmed removal of the corresponding entity.
std_msgs/Header header

uint32 schema_version
string mission_id
string event_id

# Stable mission-local track id and the most recent frame-local detection id.
string track_id
string source_detection_id
string class_name
float32 confidence

# All positions use header.frame_id (normally map).
float32[3] target_position
float32[3] robot_position
float32[3] tool_position
float32 base_target_distance_m
float32 cleaning_distance_m
float32 target_clearance_m

# Arrival and continuous-stop evidence captured before removal. A successful
# NavigateToPose result has action_msgs/GoalStatus value 4.
int8 navigation_status
float32 stop_duration_s
float32 linear_speed_mps
float32 angular_speed_rps

# Simulation actuator evidence. Real-robot adapters may use another actuator
# name and leave entity_name empty.
string actuator
string entity_name
bool removal_confirmed
