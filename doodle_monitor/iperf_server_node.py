#!/usr/bin/env python3
"""
This script launches a ROS 2 node that continuously runs an iperf3 server.

The node is designed to handle one iperf3 client connection at a time,
publishing the JSON results of each test to a ROS 2 topic. This is useful for
automated network performance monitoring in a ROS 2 ecosystem.

An alternative to running this node is to set up iperf3 as a systemd service,
as described in the initial comment block. This provides a more robust,
non-ROS-dependent solution for running the iperf3 server.

sudo nano /etc/systemd/system/iperf3.service

Paste:
[Unit]
Description=iperf3 bandwidth‑test server
After=network.target

[Service]
ExecStart=/usr/bin/iperf3 -s
Restart=on-failure

[Install]
WantedBy=multi-user.target

Restart and check status:
sudo systemctl daemon-reload
sudo systemctl enable --now iperf3
sudo systemctl status iperf3
"""
import json
import subprocess
import threading
from typing import Optional, Dict, Any
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class IperfServer(Node):
    """
    A ROS 2 node that manages an iperf3 server.

    This node continuously runs `iperf3 -s --one-off` in a loop, which means
    the server accepts a single client connection and then exits. The node
    captures the JSON output from the iperf3 server, enriches it with metadata,
    and publishes it to the `/doodle_monitor/iperf_result` topic.

    The server loop is run in a separate thread to avoid blocking the ROS 2
    executor.
    """

    def __init__(self) -> None:
        """
        Initializes the IperfServer node.

        This sets up the ROS 2 publisher and starts the server loop in a
        background thread.
        """
        super().__init__("iperf_server")
        self.pub = self.create_publisher(String, "doodle_monitor/iperf_result", 10)
        # Launch the server loop in its own thread to avoid blocking rclpy.spin()
        th = threading.Thread(target=self._server_loop, daemon=True)
        th.start()
        self.get_logger().info("iperf3 server manager started")

    def _server_loop(self) -> None:
        """
        The main loop for running the iperf3 server.

        This loop runs continuously as long as the ROS 2 context is active.
        In each iteration, it starts an iperf3 server process, waits for it
        to complete, and then processes its output. It includes error handling
        for common issues like the iperf3 command not being found.
        """
        while rclpy.ok():
            self.get_logger().info("Starting new iperf3 server instance, waiting for client...")
            try:
                # Start the iperf3 server in one-off mode with JSON output
                proc = subprocess.Popen(
                    ["iperf3", "-s", "--json", "--one-off"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                output, stderr = proc.communicate()

                # Check for errors during the iperf3 server execution
                if proc.returncode != 0:
                    self.get_logger().error(f"iperf3 server exited with error code {proc.returncode}: {stderr}")
                    continue

                # Handle cases where the server exits without any output
                if not output:
                    self.get_logger().warn("iperf3 server exited with no output.")
                    continue

                self._process_iperf_output(output)

            except FileNotFoundError:
                self.get_logger().error("iperf3 command not found. Make sure iperf3 is installed and in the system's PATH.")
                break  # Exit the loop if iperf3 is not installed
            except Exception as e:
                self.get_logger().error(f"An unexpected error occurred in server loop: {e}")

    def _process_iperf_output(self, output: str) -> None:
        """
        Parses the iperf3 JSON output and publishes it.

        Args:
            output: The JSON string output from the iperf3 server.
        """
        try:
            data: Dict[str, Any] = json.loads(output)
            # Extract the remote host IP from the JSON data
            peer_ip: Optional[str] = data.get("start", {}).get("connected", [{}])[0].get("remote_host")

            if not peer_ip:
                self.get_logger().warn("Could not find remote_host in iperf3 JSON.")
                return

            # Prepare the message and publish it
            msg = {"role": "server", "ip": peer_ip, "ok": True, "raw": data}
            self.pub.publish(String(data=json.dumps(msg)))
            self.get_logger().info(f"Server result sent for client {peer_ip}")

        except (json.JSONDecodeError, IndexError) as e:
            self.get_logger().warn(f"Could not parse iperf3 server JSON output: {e}")

def main(args: Optional[list] = None) -> None:
    """
    The main entry point for the iperf_server node.
    """
    rclpy.init(args=args)
    node = IperfServer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()