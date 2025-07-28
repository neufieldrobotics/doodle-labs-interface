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

### INFO TO DEFINE NETWORK AND SCHEDULE
HOSTNAME_TO_IP_MAPPING = {
    "payload0": "10.19.30.100",
    "payload1": "10.19.30.101",
    "nuroampayload02": "10.19.30.102",
    "neuroam-desktop": "10.19.30.103",
    "payload4": "10.19.30.104",
}
ORANGE_BOX_IPS = ["10.19.30.2", "10.19.30.3"]
NODE_LIST = sorted(list(HOSTNAME_TO_IP_MAPPING.values()) + ORANGE_BOX_IPS)

def edge_coloring_schedule(nodes):
    """Return list[ list[(a,b)] ]: perfect matchings of K_n."""
    edges, schedule, used = list(permutations(nodes, 2)), [], set()

    # remove edges coming from the orange boxes
    edges = [edge for edge in edges if edge[0] not in ORANGE_BOX_IPS]

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

    # check that, for each slot, no node is used more than once
    for slot in schedule:
        seen = set()
        for a, b in slot:
            if a in seen or b in seen:
                raise ValueError(f"Node {a} or {b} used more than once in slot {slot}")
            seen.update({a, b})

    return schedule

SCHEDULE = edge_coloring_schedule(NODE_LIST)
NUM_SLOTS = len(SCHEDULE)


### TIMING INFO
GUARD_TIME = 0.5  # seconds
IPERF_TIME = 3.0  # seconds
SLOT_LENGTH = GUARD_TIME + IPERF_TIME  # total time for one slot


class EdgePayloadMonitor(Node):
    def __init__(self):
        super().__init__(
            "edge_payload_monitor", automatically_declare_parameters_from_overrides=True
        )

        import os
        self.hostname = os.uname()[1]
        self.my_ip = HOSTNAME_TO_IP_MAPPING.get(self.hostname, None)
        if self.my_ip is None:
            raise RuntimeError(
                f"Unknown hostname {self.hostname} for user {self.get_namespace()}, "
                "do not know IP address."
            )

        self.reachable: set[str] = set()
        self.num_slots = len(SCHEDULE)

        self.create_subscription(
            String, "doodle_monitor/peer_list", self.peer_list_cb, 10
        )
        self.ping_pub = self.create_publisher(String, "doodle_monitor/ping_result", 10)
        self.iperf_pub = self.create_publisher(
            String, "doodle_monitor/iperf_result", 10
        )

        self.create_timer(0.25, self.edge_slot_runner)

        self.get_logger().info(
            f"edge-schedule ready: slot_len={SLOT_LENGTH}s  "
            f"slots={self.num_slots}  my_ip={self.my_ip}"
        )

        # DEBUGGING HELPER
        sched_str = json.dumps(SCHEDULE, sort_keys=True)
        fingerprint = hashlib.md5(sched_str.encode()).hexdigest()[:8]
        self.get_logger().info(
            f"schedule MD5={fingerprint}  slots={len(SCHEDULE)} -> {SCHEDULE}"
        )

    def edge_slot_runner(self):
        if not SCHEDULE:
            return

        now = time.time()
        slot_idx = int(now // SLOT_LENGTH) % self.num_slots
        slotted_comms = SCHEDULE[slot_idx]

        slot_start = math.floor(now / SLOT_LENGTH) * SLOT_LENGTH
        end_start_window = slot_start + (GUARD_TIME / 2.0)
        slot_end = slot_start + SLOT_LENGTH

        # if outside of the window given to start the test, skip
        now_is_in_start_window = slot_start <= now < end_start_window
        if not now_is_in_start_window:
            self.get_logger().debug(
                f"Not in start window ({slot_start:.1f} to {end_start_window:.1f}) - "
                f"waiting until {slot_end:.1f}s"
            )
            return

        # find if the current device is slotted to run a test
        my_test_partner = None
        for client, server in slotted_comms:
            if client == self.my_ip:
                my_test_partner = server
                break

        if not my_test_partner:
            self.get_logger().info(f"[SLEEP] {self.my_ip} not active in slot {slot_idx}")
            return

        # check if the partner is reachable
        if my_test_partner not in self.reachable:
            self.get_logger().info(f"[NO REACH] Current IP {self.my_ip} cannot reach partner {my_test_partner}, skipping.")
            return

        # run the ping and iperf tests
        self.get_logger().info(f"[TRYING] {self.my_ip} contacting {my_test_partner}")
        self.run_ping(my_test_partner)
        self.run_iperf(my_test_partner)

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
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.STDOUT, timeout=GUARD_TIME / 2.0
            )
            ok = True
        except subprocess.CalledProcessError as e:
            out, ok = e.output, False
        self.ping_pub.publish(String(data=json.dumps({"ip": ip, "ok": ok, "raw": out})))
        self.get_logger().debug(f"PING {ip}: {'ok' if ok else 'fail'} - {out.strip()}")

    def run_iperf(self, ip):
        timeout = IPERF_TIME + (GUARD_TIME / 2.0)
        cmd = ["iperf3", "-c", ip, "-t", str(IPERF_TIME), "-b", "0", "--json"]
        try:
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout
            )
            ok = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # Use hasattr to safely access e.output
            out = e.output if hasattr(e, "output") else "Test timed out"
            ok = False
            self.get_logger().warn(f"IPERF {ip} failed: {e}")
            time.sleep(IPERF_TIME)

        if out is None:
            out = "No output from iperf"

        # check if out is a stringified JSON. If so, let's print the
        # info under "end -> sum_received -> bits_per_second"
        # and print out the Mbps value.
        try:
            json.loads(out)
            parsed_out = json.loads(out)
            if "end" in parsed_out and "sum_received" in parsed_out["end"]:
                bits_per_second = parsed_out["end"]["sum_received"]["bits_per_second"]
                mbps = bits_per_second / 1_000_000
                self.get_logger().info(f"[BANDWIDTH] IPERF {ip}: {mbps:.1f} Mbps")
        except json.JSONDecodeError:
            self.get_logger().warn(f"IPERF {ip}: iperf output is not valid JSON: {out}")
            out = json.dumps({"error": "Invalid JSON output from iperf"})

        result = {"role": "client", "ip": ip, "ok": ok, "raw": out}
        self.iperf_pub.publish(String(data=json.dumps(result)))


def main(args=None):
    rclpy.init(args=args)
    node = EdgePayloadMonitor()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
