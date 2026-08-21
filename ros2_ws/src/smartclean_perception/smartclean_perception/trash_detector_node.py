"""ROS 2 node wrapping the pixel-based trash detector core.

Subscribes /camera/image_raw (rgb8, best effort), publishes
/smartclean/detections (smartclean_interfaces/TrashDetectionArray) and
/smartclean/debug/detection_image (annotated rgb8). The node never reads the
Gazebo scene ground truth; every detection comes from image pixels.
"""

import time
from collections import deque
from typing import Deque

import cv2
import rclpy
import tf2_ros
from builtin_interfaces.msg import Time as RosTime
from cv_bridge import CvBridge
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import Image

from smartclean_interfaces.msg import TrashDetection as TrashDetectionMsg
from smartclean_interfaces.msg import TrashDetectionArray

from .detector_core import DetectorConfig, TrashDetector, annotate
from .position_estimator import (
    CameraIntrinsics,
    EstimatedPosition,
    PositionConfig,
    RigidTransform,
    depth_to_meters,
    estimate_position,
)

SCHEMA_VERSION = 1
DETECTOR_SOURCE = "smartclean_perception.color_baseline"


class TrashDetectorNode(Node):
    """Image-based trash detector node."""

    def __init__(self) -> None:
        super().__init__("smartclean_trash_detector")
        self._bridge = CvBridge()
        self._config = self._read_config()
        self._position_config = self._read_position_config()
        self._detector = TrashDetector(self._config)
        self._latency_ms: Deque[float] = deque(maxlen=30)
        self._latest_depth = None

        image_qos = QoSProfile(depth=10)
        image_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        self.create_subscription(
            Image, "/camera/image_raw", self._on_image, image_qos
        )
        self._detection_publisher = self.create_publisher(
            TrashDetectionArray, "/smartclean/detections", 10
        )
        self._debug_publisher = self.create_publisher(
            Image, "/smartclean/debug/detection_image", 1
        )
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        if self._position_config.use_depth:
            self.create_subscription(
                Image,
                self._position_config.depth_topic,
                self._on_depth,
                image_qos,
            )
        self.get_logger().info(
            "垃圾检测节点已启动：/camera/image_raw -> /smartclean/detections + "
            "/smartclean/debug/detection_image"
        )

    def _read_config(self) -> DetectorConfig:
        def param(name, default):
            self.declare_parameter(name, default)
            return self.get_parameter(name).value

        return DetectorConfig(
            horizon_row=int(param("horizon_row", DetectorConfig().horizon_row)),
            min_area=int(param("min_area", DetectorConfig().min_area)),
            flip_vertical=bool(
                param("flip_vertical", DetectorConfig().flip_vertical)
            ),
            white_min_value=int(
                param("white_min_value", DetectorConfig().white_min_value)
            ),
            white_max_saturation=int(
                param(
                    "white_max_saturation",
                    DetectorConfig().white_max_saturation,
                )
            ),
        )

    def _read_position_config(self) -> PositionConfig:
        def param(name, default):
            self.declare_parameter(name, default)
            return self.get_parameter(name).value

        return PositionConfig(
            use_depth=bool(param("use_depth", True)),
            depth_topic=str(
                param("depth_topic", "/camera/depth/image_rect_raw")
            ),
            position_frame_ids=tuple(
                param("position_frame_ids", ["map", "odom"])
            ),
            depth_max_stamp_delta_s=float(
                param("depth_max_stamp_delta_s", 0.5)
            ),
            depth_patch_radius=int(param("depth_patch_radius", 4)),
            camera_hfov_deg=float(param("camera_hfov_deg", 60.0)),
        )

    def _on_depth(self, message: Image) -> None:
        self._latest_depth = message

    def _stamp_seconds(self, stamp: RosTime) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def _depth_within(self, image_stamp: RosTime) -> Image:
        if self._latest_depth is None:
            return None
        delta = abs(
            self._stamp_seconds(image_stamp)
            - self._stamp_seconds(self._latest_depth.header.stamp)
        )
        if delta > self._position_config.depth_max_stamp_delta_s:
            return None
        return self._latest_depth

    def _lookup_transform(self, target_frame: str, stamp: RosTime):
        try:
            transform = self._tf_buffer.lookup_transform(
                target_frame,
                "camera_optical_frame",
                Time.from_msg(stamp),
                Duration(seconds=0.1),
            )
            return transform
        except Exception:  # noqa: BLE001 - missing TF means invalid position
            return None

    def _estimate_position(
        self, bbox_xyxy, image_stamp: RosTime
    ) -> EstimatedPosition:
        depth_msg = self._depth_within(image_stamp)
        if depth_msg is None:
            return None
        try:
            depth_raw = self._bridge.imgmsg_to_cv2(depth_msg)
            depth_m = depth_to_meters(depth_raw, depth_msg.encoding)
            intrinsics = CameraIntrinsics.from_hfov(
                depth_msg.width,
                depth_msg.height,
                self._position_config.camera_hfov_deg,
            )
        except Exception as exc:  # noqa: BLE001 - keep the node alive
            self.get_logger().warn(
                "深度数据转换失败：{}".format(exc),
                throttle_duration_sec=5.0,
            )
            return None
        for frame_id in self._position_config.position_frame_ids:
            transform_msg = self._lookup_transform(frame_id, image_stamp)
            if transform_msg is None:
                continue
            transform = RigidTransform(
                translation=(
                    transform_msg.transform.translation.x,
                    transform_msg.transform.translation.y,
                    transform_msg.transform.translation.z,
                ),
                rotation_xyzw=(
                    transform_msg.transform.rotation.x,
                    transform_msg.transform.rotation.y,
                    transform_msg.transform.rotation.z,
                    transform_msg.transform.rotation.w,
                ),
            )
            return estimate_position(
                bbox_xyxy,
                depth_m,
                intrinsics,
                transform,
                frame_id,
                patch_radius=self._position_config.depth_patch_radius,
            )
        return None

    def _on_image(self, message: Image) -> None:
        start = time.perf_counter()
        try:
            rgb = self._bridge.imgmsg_to_cv2(message, desired_encoding="rgb8")
        except Exception as exc:  # noqa: BLE001 - keep the node alive
            self.get_logger().warn(
                "图像转换失败：{}".format(exc), throttle_duration_sec=5.0
            )
            return
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        detections = self._detector.detect(bgr)
        processing_ms = (time.perf_counter() - start) * 1000.0
        self._latency_ms.append(processing_ms)

        array = TrashDetectionArray()
        array.header.stamp = message.header.stamp
        array.header.frame_id = message.header.frame_id
        array.processing_ms = float(processing_ms)
        array.fps = self._fps()
        for index, detection in enumerate(detections):
            item = TrashDetectionMsg()
            item.schema_version = SCHEMA_VERSION
            item.detection_id = "{}.{}.{}".format(
                message.header.stamp.sec,
                message.header.stamp.nanosec,
                index,
            )
            item.class_name = detection.class_name
            item.confidence = float(detection.confidence)
            item.bbox_xyxy = [float(v) for v in detection.bbox_xyxy]
            item.image_stamp = message.header.stamp
            item.source = DETECTOR_SOURCE
            position = self._estimate_position(
                detection.bbox_xyxy, message.header.stamp
            )
            if position is None:
                item.position_valid = False
                item.position = [0.0, 0.0, 0.0]
                item.position_frame_id = ""
            else:
                item.position_valid = True
                item.position = [float(v) for v in position.xyz]
                item.position_frame_id = position.frame_id
            item.area_px = float(detection.area_px)
            array.detections.append(item)
        self._detection_publisher.publish(array)

        if self._debug_publisher.get_subscription_count() > 0:
            debug_bgr = annotate(bgr, detections)
            debug_msg = self._bridge.cv2_to_imgmsg(debug_bgr, encoding="rgb8")
            debug_msg.header.stamp = message.header.stamp
            debug_msg.header.frame_id = message.header.frame_id
            self._debug_publisher.publish(debug_msg)

    def _fps(self) -> float:
        if not self._latency_ms:
            return 0.0
        mean_ms = sum(self._latency_ms) / len(self._latency_ms)
        return 1000.0 / mean_ms if mean_ms > 0 else 0.0


def main() -> None:
    rclpy.init()
    node = TrashDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
