#!/usr/bin/env python3
"""
This script launches a ROS 2 node for orchestrating network tests.

The `EdgePayloadMonitor` node follows a deterministic, time-slotted schedule to
run ping and iperf3 tests between pairs of nodes in the network. This approach,
known as edge coloring, ensures that all nodes can participate in testing
without interfering with each other, as no two nodes will be communicating with
the same partner in the same time slot.

The schedule is generated based on a list of nodes defined in the ROS 2
parameter configuration. The node subscribes to a topic to get a list of
reachable peers and only runs tests with peers that are known to be online.
"""
import json
import time
import math
import subprocess
import hashlib
from itertools import permutations
from typing import List, Tuple, Dict, Any, Optional
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

def edge_coloring_schedule(nodes: List[str], orange_box_ips: List[str]) -> List[List[Tuple[str, str]]]:
    """
    Generates a deterministic, edge-colored schedule for network tests.

    This function creates a schedule of one-to-one pairings (edges) for a fully
    connected graph of nodes (K_n). Each slot in the schedule is a "perfect
    matching," meaning each node is used at most once. This prevents contention
    during testing.

    Args:
        nodes: A list of IP addresses of all nodes in the network.
        orange_box_ips: A list of IPs to be excluded as test initiators.

    Returns:
        A list of slots, where each slot is a list of (client, server) tuples.
    """
    edges = list(permutations(nodes, 2))
    schedule: List[List[Tuple[str, str]]] = []
    used: set[Tuple[str, str]] = set()

    # Exclude edges where the client is one of the specified orange box IPs
    edges = [edge for edge in edges if edge[0] not in orange_box_ips]

    while len(used) < len(edges):
        slot: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for a, b in edges:
            if (a, b) in used:
                continue
            if a not in seen and b not in seen:
                slot.append((a, b))
                seen.update({a, b})
                used.add((a, b))
        schedule.append(slot)

    # Verification step: ensure no node is used more than once per slot
    for slot in schedule:
        seen = set()
        for a, b in slot:
            if a in seen or b in seen:
                raise ValueError(f"Node {a} or {b} used more than once in slot {slot}")
            seen.update({a, b})

    return schedule

### TIMING INFO
IPERF_TIMEOUT_BUFFER = 0.4
PING_TIMEOUT_BUFFER = 0.15
GENERAL_TIMING_BUFFER = 0.1
IPERF_TIME = 1.0  # seconds
SLOT_LENGTH = IPERF_TIME + IPERF_TIMEOUT_BUFFER + PING_TIMEOUT_BUFFER + GENERAL_TIMING_BUFFER
TIME_SYNC_THRESHOLD_S = 0.5  # seconds, for clock drift detection

class EdgePayloadMonitor(Node):
    """
    A ROS 2 node that schedules and executes network tests.

    This node determines its role in the current time slot based on a generated
    schedule. If it is designated as a client, it will run a ping and then an
    iperf3 test against its assigned partner, provided the partner is reachable.
    """

    def __init__(self) -> None:
        """
        Initializes the EdgePayloadMonitor node.

        This sets up the node's parameters, generates the test schedule, and
        creates the necessary publishers, subscribers, and timers.
        """
        super().__init__("edge_payload_monitor", automatically_declare_parameters_from_overrides=True)

        self.hostname: str = os.uname()[1]
        self.hostname_to_ip_mapping: Dict[str, str] = self.get_parameter('hostname_to_ip_mapping').value
        self.orange_box_ips: List[str] = self.get_parameter('orange_box_ips').value
        self.node_list: List[str] = sorted(list(self.hostname_to_ip_mapping.values()) + self.orange_box_ips)
        
        self.my_ip: Optional[str] = self.hostname_to_ip_mapping.get(self.hostname)
        if self.my_ip is None:
            raise RuntimeError(
                f"Unknown hostname {self.hostname}, cannot determine my IP address."
            )

        self.schedule: List[List[Tuple[str, str]]] = edge_coloring_schedule(self.node_list, self.orange_box_ips)
        self.num_slots: int = len(self.schedule)
        self.reachable: set[str] = set()

        self.create_subscription(String, "doodle_monitor/peer_list", self.peer_list_cb, 10)
        self.ping_pub = self.create_publisher(String, "doodle_monitor/ping_result", 10)
        self.iperf_pub = self.create_publisher(String, "doodle_monitor/iperf_result", 10)

        self.create_timer(0.25, self.edge_slot_runner)

        self.get_logger().debug(
            f"edge-schedule ready: slot_len={SLOT_LENGTH}s  "
            f"slots={self.num_slots}  my_ip={self.my_ip}"
        )

        sched_str = json.dumps(self.schedule, sort_keys=True)
        fingerprint = hashlib.md5(sched_str.encode()).hexdigest()[:8]
        self.get_logger().debug(f"schedule MD5={fingerprint}  slots={len(self.schedule)} -> {self.schedule}")

    def edge_slot_runner(self) -> None:
        """
        The main runner function, executed periodically by a timer.

        This function calculates the current time slot, determines if this node
        has a role to play, and if so, executes the necessary tests.
        """
        if not self.schedule:
            return

        now = time.time()
        slot_idx = int(now // SLOT_LENGTH) % self.num_slots
        slotted_comms = self.schedule[slot_idx]

        self.get_logger().debug(f"[SLOT {slot_idx}]")

        slot_start = math.floor(now / SLOT_LENGTH) * SLOT_LENGTH
        end_start_window = slot_start + GENERAL_TIMING_BUFFER
        slot_end = slot_start + SLOT_LENGTH
        
        def _wait_for_next_slot() -> None:
            """Calculates the remaining time in the slot and sleeps."""
            time.sleep(max(0, slot_end - time.time()))

        # Skip if the current time is outside the allowed start window
        now_is_in_start_window = slot_start <= now < end_start_window
        if not now_is_in_start_window:
            self.get_logger().debug(
                f"Now: {now} Not in start window ({slot_start:.1f} to {end_start_window:.1f}) - "
                f"waiting until {slot_end:.1f}s"
            )
            _wait_for_next_slot()
            return

        # Determine if this node is a client in the current slot
        my_test_partner: Optional[str] = None
        for client, server in slotted_comms:
            if client == self.my_ip:
                my_test_partner = server
                break

        if not my_test_partner:
            self.get_logger().debug(f"[SLEEP] {self.my_ip} not active in slot {slot_idx}")
            _wait_for_next_slot()
            return

        # Skip if the designated partner is not reachable
        if my_test_partner not in self.reachable:
            self.get_logger().debug(f"[NO REACH] Current IP {self.my_ip} cannot reach partner {my_test_partner}, skipping.")
            _wait_for_next_slot()
            return

        # Execute the tests
        self.get_logger().debug(f"[TRYING] {self.my_ip} contacting {my_test_partner}")
        ping_worked = self.run_ping(my_test_partner)
        if ping_worked:
            self.run_iperf(my_test_partner)
        else:
            self.get_logger().debug(f"[PING FAIL] Current IP {self.my_ip} failed to ping {my_test_partner}, skipping.")
        _wait_for_next_slot()

    def peer_list_cb(self, msg: String) -> None:
        """
        Callback for the peer list subscriber.

        Args:
            msg: The incoming message containing the list of reachable peers.
        """
        try:
            data: Dict[str, Any] = json.loads(msg.data)
            ip_peers: List[str] = data.get("peers", [])
            self.reachable = set(ip_peers)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"bad peer_list JSON: {e}")

    def run_ping(self, ip: str) -> bool:
        """
        Runs a ping test to the specified IP address.

        Args:
            ip: The IP address to ping.

        Returns:
            True if the ping was successful, False otherwise.
        """
        cmd = ["ping", "-c", "1", "-W", "2.0", ip]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=PING_TIMEOUT_BUFFER)
            ok = True
        except subprocess.CalledProcessError as e:
            out, ok = e.output, False
        except subprocess.TimeoutExpired:
            out, ok = "Ping timed out", False
        self.ping_pub.publish(String(data=json.dumps({"ip": ip, "ok": ok, "raw": out})))
        self.get_logger().debug(f"PING {ip}: {'ok' if ok else 'fail'} - {out.strip()}")
        return ok

    def _check_time_sync(self, iperf_data: Dict[str, Any]) -> None:
        """
        Heuristically checks for time synchronization issues using iperf results.

        This method compares the timestamp from the client's iperf report with
        the timestamp from the server's embedded report (obtained using the
        `--get-server-output` flag). If the absolute difference exceeds a
        predefined threshold, a warning is logged.

        Args:
            iperf_data: The parsed JSON output from the iperf3 client.
        """
        try:
            # Extract client and server timestamps from the iperf JSON output
            client_time = iperf_data["start"]["timestamp"]["timesecs"]
            server_output = iperf_data.get("server_output_json", {})

            if not server_output:
                self.get_logger().debug("No 'server_output_json' in iperf3 result, skipping time sync check.")
                return

            server_time = server_output["start"]["timestamp"]["timesecs"]
            time_delta = abs(client_time - server_time)

            if time_delta > TIME_SYNC_THRESHOLD_S:
                self.get_logger().warn(
                    f"Potential time synchronization issue detected. "
                    f"Time delta with {server_output['start']['connected'][0]['remote_host']} "
                    f"is {time_delta:.2f}s, which exceeds the threshold of "
                    f"{TIME_SYNC_THRESHOLD_S}s. Please check NTP service on all devices."
                )
        except KeyError:
            self.get_logger().debug("Could not extract timestamps from iperf3 JSON for time sync check.")
        except Exception as e:
            self.get_logger().warn(f"An error occurred during time sync check: {e}")

    def run_iperf(self, ip: str) -> None:
        """
        Runs an iperf3 test to the specified IP address.

        This function now includes a heuristic check for time synchronization
        by comparing client and server timestamps from the iperf results.

        Args:
            ip: The IP address to run the iperf3 client against.
        """
        # The --get-server-output flag is crucial for the time sync check
        cmd = ["iperf3", "-c", ip, "-t", str(IPERF_TIME), "-b", "0", "--json", "--get-server-output"]
        out: str
        ok: bool
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=IPERF_TIME + IPERF_TIMEOUT_BUFFER)
            ok = True
        except subprocess.CalledProcessError as e:
            out = e.output if e.output is not None else "CalledProcessError with no output"
            ok = False
            self.get_logger().warn(f"IPERF {ip} failed: {e}")
        except subprocess.TimeoutExpired:
            out = "Test timed out"
            ok = False
            self.get_logger().warn(f"IPERF {ip} timed out.")

        try:
            parsed_out: Dict[str, Any] = json.loads(out)
            # If the test was successful, perform the time sync check
            if ok:
                self._check_time_sync(parsed_out)

            if "end" in parsed_out and "sum_received" in parsed_out["end"]:
                bits_per_second = parsed_out["end"]["sum_received"]["bits_per_second"]
                mbps = bits_per_second / 1_000_000
                self.get_logger().info(f"[BANDWIDTH] IPERF {ip}: {mbps:.1f} Mbps")
        except json.JSONDecodeError:
            self.get_logger().warn(f"IPERF {ip}: iperf output is not valid JSON: {out}")
            out = json.dumps({"error": "Invalid JSON output from iperf"})

        result = {"role": "client", "ip": ip, "ok": ok, "raw": out}
        self.iperf_pub.publish(String(data=json.dumps(result)))

def main(args: Optional[List[str]] = None) -> None:
    """
    The main entry point for the edge_payload_monitor node.
    """
    rclpy.init(args=args)
    node = EdgePayloadMonitor()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
