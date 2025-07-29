"""
-This data is redundant but thought it would be good to have instead of creating large gaps between iperfs
-can instead create a dameon to run iperf -s:


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


#!/usr/bin/env python3
import json
import subprocess
import threading
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class IperfServer(Node):
    """
    Continuously runs `iperf3 -s --one-off`, publishing the server-side
    JSON result to /doodle_monitor/iperf_result after each test.
    """

    def __init__(self):
        super().__init__("iperf_server")
        self.pub = self.create_publisher(String,
                                         "doodle_monitor/iperf_result", 10)
        # Launch the server loop in its own thread
        th = threading.Thread(target=self._server_loop, daemon=True)
        th.start()
        self.get_logger().info("iperf3 server manager started")

    def _server_loop(self):
        while rclpy.ok():
            self.get_logger().info("Starting new iperf3 server instance, waiting for client...")
            proc = subprocess.Popen(["iperf3", "-s", "--json", "--one-off"], stdout=subprocess.PIPE, text=True)
            output, _ = proc.communicate()

            if not output:
                self.get_logger().warn("iperf3 server exited with no output.")
                continue

            try:
                data = json.loads(output)

                peer_ip = data.get("start", {}).get("connected", [{}])[0].get("remote_host")
                if not peer_ip:
                    self.get_logger().warn("Could not find remote_host in iperf3 JSON.")
                    continue

                msg = {"role": "server", "ip": peer_ip, "ok": True, "raw": data}
                self.pub.publish(String(data=json.dumps(msg)))
                self.get_logger().info(f"Server result sent for client {peer_ip}")

            except (json.JSONDecodeError, IndexError) as e:
                self.get_logger().warn(f"Could not parse iperf3 server JSON output: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = IperfServer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()