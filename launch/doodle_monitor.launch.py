# launch/doodle_monitor.launch.py
from launch import LaunchDescription
from launch.actions import TimerAction
from launch_ros.actions import Node
import os

DELAY = 8.0

def generate_launch_description():
    cfg = os.path.join(
        os.path.dirname(__file__), "../config/network_params.yaml"
    )

    monitor = Node(
        package="doodle_monitor",
        executable="monitor_node",
        name="monitor_node",
        parameters=[cfg],
        output="screen"
    )

    client = TimerAction(
        period=DELAY,
        actions=[
            Node(
                package="doodle_monitor",
                executable="optimized_payload_monitor",
                name="optimized_payload_monitor",
                parameters=[cfg],
                output="screen"
            )
        ]
    )

    server = Node(
        package="doodle_monitor",
        executable="iperf_server_node",
        name="iperf_server_node",
        parameters=[cfg]
    )
    

    return LaunchDescription([monitor, server, client])




