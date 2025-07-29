from launch import LaunchDescription
from launch.actions import TimerAction
from launch_ros.actions import Node
import os

DELAY = 8.0
RESPAWN_DELAY = 2.0

def generate_launch_description():
    cfg = os.path.join(
        os.path.dirname(__file__), "../config/network_params.yaml"
    )

    monitor = Node(
        package="doodle_monitor",
        executable="monitor_node",
        name="monitor_node",
        parameters=[cfg],
        output="screen",
        respawn=True,
        respawn_delay=RESPAWN_DELAY
    )

    client = TimerAction(
        period=DELAY,
        actions=[
            Node(
                package="doodle_monitor",
                executable="optimized_payload_monitor",
                name="optimized_payload_monitor",
                parameters=[cfg],
                output="screen",
                respawn=True,
                respawn_delay=RESPAWN_DELAY
            )
        ]
    )

    server = Node(
        package="doodle_monitor",
        executable="iperf_server_node",
        name="iperf_server_node",
        parameters=[cfg],
        output="screen",
        respawn=True,
        respawn_delay=RESPAWN_DELAY
    )

    return LaunchDescription([monitor, server, client])
