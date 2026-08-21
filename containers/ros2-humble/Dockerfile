ARG ROS_BASE_IMAGE=ros:humble-ros-base-jammy@sha256:75dd3aba34a3838dadbb31a9f7bef769bdfa8713e6cec686fc868db2981b0987
FROM ${ROS_BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions \
        python3-pytest \
        ros-humble-desktop \
        ros-humble-demo-nodes-cpp \
        ros-humble-demo-nodes-py \
        ros-humble-navigation2 \
        ros-humble-nav2-bringup \
        ros-humble-ros-gz \
        ros-humble-slam-toolbox \
    && rm -rf /var/lib/apt/lists/*

ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd --gid "${GROUP_ID}" smartclean \
    && useradd --create-home --uid "${USER_ID}" --gid "${GROUP_ID}" smartclean

USER smartclean
WORKDIR /workspace

ENV PYTHONPATH=/workspace/src \
    ROS_DOMAIN_ID=42 \
    ROS_LOG_DIR=/workspace/.ros/log \
    RCUTILS_COLORIZED_OUTPUT=1

CMD ["bash"]
