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
from builtin_interfaces.msg import Time as RosTime
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

from smartclean_interfaces.msg import TrashDetection as TrashDetectionMsg
from smartclean_interfaces.msg import TrashDetectionArray

from .detector_core import DetectorConfig, TrashDetector, annotate

SCHEMA_VERSION = 1
DETECTOR_SOURCE = "smartclean_perception.color_baseline"


class TrashDetectorNode(Node):
    """Image-based trash detector node."""

    def __init__(self) -> None:
        super().__init__("smartclean_trash_detector")
        self._bridge = CvBridge()
        self._config = self._read_config()
        self._detector = TrashDetector(self._config)
        self._latency_ms: Deque[float] = deque(maxlen=30)

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
            item.position_valid = False
            item.position = [0.0, 0.0, 0.0]
            item.position_frame_id = ""
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
