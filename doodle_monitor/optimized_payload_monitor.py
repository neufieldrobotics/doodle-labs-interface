# doodle_monitor/edge_payload_monitor.py
#!/usr/bin/env python3
"""
Run one ping + short UDP-iperf burst to a single partner per time-slot,
using a deterministic edge-coloured schedule so that all payloads stay
in lock-step without exchanging control messages.

* slot_length      = guard_time + iperf_time   (e.g. 1.3 s)
* num_slots        = len(schedule)  ==  (#nodes-even) ? n-1 : n
* full cycle       = slot_length x num_slots
"""

import json, time, math, subprocess, hashlib
from itertools import permutations
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

def edge_coloring_schedule(nodes):
    """Return list[ list[(a,b)] ]: perfect matchings of K_n."""
    edges, schedule, used = list(permutations(nodes, 2)), [], set()
    while len(used) < len(edges):
        slot, seen = [], set()
        for a, b in edges:
            if (a, b) in used:
                continue
            if a not in seen and b not in seen:
                slot.append((a, b))
                seen.update({a, b})
                used.add((a, b))
        schedule.append(slot)
    return schedule


class EdgePayloadMonitor(Node):
    def __init__(self):
        super().__init__("edge_payload_monitor", automatically_declare_parameters_from_overrides=True)

        self.my_name = self.get_parameter("my_name").value
        self.slot_len = self.get_parameter("slot_length").value
        self.guard = self.get_parameter("guard_time").value
        self.iperf_t = self.get_parameter("iperf_time").value
        self.nodes = sorted(self.get_parameter("node_list").value)

        self.reachable: set[str] = set()
        self.schedule  = edge_coloring_schedule(self.nodes)
        self.num_slots = len(self.schedule)

        self.create_subscription(String, "doodle_monitor/peer_list", self.peer_list_cb, 10)
        self.ping_pub  = self.create_publisher(String, "doodle_monitor/ping_result", 10)
        self.iperf_pub = self.create_publisher(String, "doodle_monitor/iperf_result", 10)

        self.create_timer(0.25, self.edge_slot_runner)

        self.get_logger().info(
            f"edge‑schedule ready: slot_len={self.slot_len}s  "
            f"slots={self.num_slots}  my_name={self.my_name}")
        
        # DEBUGGING HELPER
        sched_str = json.dumps(self.schedule, sort_keys=True)
        fingerprint = hashlib.md5(sched_str.encode()).hexdigest()[:8]
        self.get_logger().info(f"schedule MD5={fingerprint}  slots={len(self.schedule)} -> {self.schedule}")

    def edge_slot_runner(self):
        if not self.schedule:
            return

        now = time.time()
        slot_idx = int(now // self.slot_len) % self.num_slots
        slot = self.schedule[slot_idx]

        my_test_partner = None
        for client, server in slot:
            if client == self.my_name:
                my_test_partner = server
                break 

        if not my_test_partner:
            return

        # Check if the target is online
        if my_test_partner not in self.reachable:
            self.get_logger().debug(f"partner {my_test_partner} offline - skip")
            return

        # Define the single window for our forward-only test
        slot_start = math.floor(now / self.slot_len) * self.slot_len
        launch_at  = slot_start + self.guard
        if launch_at <= now < launch_at + self.iperf_t:
            self.get_logger().info(f"Running FORWARD test to {my_test_partner}")
            self.run_ping(my_test_partner)
            self.run_iperf(my_test_partner) # Only runs the forward tests


    def peer_list_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            ip_peers = data.get("peers", [])
        except Exception as e:
            self.get_logger().warn(f"bad peer_list JSON: {e}")
            return

        self.reachable = set(ip_peers)

    def run_ping(self, ip):
        cmd = ["ping", "-c", "1", "-W", "2.0", ip]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=2.5)
            ok  = True
        except subprocess.CalledProcessError as e:
            out, ok = e.output, False
        self.ping_pub.publish(String(data=json.dumps({"ip": ip, "ok": ok, "raw": out})))
        # DEBUGGING HELPER
        self.get_logger().info(f"PING {ip}: {'ok' if ok else 'fail'} ")



    def run_iperf(self, ip):
        timeout = self.iperf_t + 0.5
        cmd = ["iperf3", "-c", ip, "-t", str(self.iperf_t), "-b", "0", "--json"]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout)
            ok  = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # Use hasattr to safely access e.output
            out = e.output if hasattr(e, 'output') else "Test timed out"
            ok = False
            time.sleep(self.iperf_t)

        result = {"role": "client", "ip": ip, "ok": ok, "raw": out}
        self.iperf_pub.publish(String(data=json.dumps(result)))
        self.get_logger().info(f"IPERF {ip}: {'ok' if ok else 'fail'}")

def main(args=None):
    rclpy.init(args=args)
    node = EdgePayloadMonitor()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
