# Structured state for the perception -> navigation -> cleaning mission.
std_msgs/Header header

uint32 schema_version
string mission_id

# IDLE, WAITING_FOR_NAV2, WAITING_FOR_DETECTIONS, SELECTING_TARGET,
# NAVIGATING_TO_TARGET, VERIFYING_CLEANING_GATE, CLEANING_TARGET,
# REMOVING_TARGET, RETURNING_TO_DOCK, COMPLETED, FAILED.
string state
string failure_code
string detail

string active_target_id
string active_class_name
float32[3] active_target_position
float32[3] active_goal_pose_xyyaw
string[] discovered_trash_ids
string[] cleaned_ids
string[] remaining_trash_ids
string[] failed_ids

uint32 initial_trash_count
uint32 navigation_goals_sent
uint32 cleaning_events
float32 progress
bool return_after_done
bool returned_to_dock
