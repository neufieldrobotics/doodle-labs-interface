#!/usr/bin/env python3
"""
This script simulates and visualizes the edge-colored scheduling of network tests.

It is a standalone, non-ROS script that loads the same network configuration
as the ROS 2 nodes. The main purpose is to provide a visual representation of
the time-slotted schedule, showing which nodes are communicating in each slot.
This is useful for debugging the scheduling algorithm and understanding the
communication patterns.

The simulation runs in a loop, printing the current state and updating a
matplotlib plot to show the active communication links.
"""
import json
import time
import math
import hashlib
from itertools import permutations
from typing import List, Tuple, Dict, Any, Optional
import yaml
import os

### TIMING INFO
GUARD_TIME = 0.5  # seconds
IPERF_TIME = 3.0  # seconds
SLOT_LENGTH = GUARD_TIME + IPERF_TIME  # total time for one slot

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

class EdgePayloadMonitor:
    """
    A class to simulate the behavior of the EdgePayloadMonitor ROS 2 node.

    This class loads the network configuration, generates the schedule, and
    runs a simulation loop to visualize the communication slots.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initializes the simulator.

        Args:
            config: A dictionary containing the network configuration.
        """
        self.hostname_to_ip_mapping: Dict[str, str] = config['edge_payload_monitor']['ros__parameters']['hostname_to_ip_mapping']
        self.orange_box_ips: List[str] = config['edge_payload_monitor']['ros__parameters']['orange_box_ips']
        self.node_list: List[str] = sorted(list(self.hostname_to_ip_mapping.values()) + self.orange_box_ips)

        # For simulation purposes, we assume the identity of the first payload
        self.hostname: str = list(self.hostname_to_ip_mapping.keys())[0]
        self.my_ip: Optional[str] = self.hostname_to_ip_mapping.get(self.hostname)
        if self.my_ip is None:
            raise RuntimeError(
                f"Unknown hostname {self.hostname}, cannot determine my IP address."
            )

        self.schedule: List[List[Tuple[str, str]]] = edge_coloring_schedule(self.node_list, self.orange_box_ips)
        self.num_slots: int = len(self.schedule)

        print(f"edge-schedule ready: slot_len={SLOT_LENGTH}s  slots={self.num_slots}  my_name={self.my_ip}")
        sched_str = json.dumps(self.schedule, sort_keys=True)
        fingerprint = hashlib.md5(sched_str.encode()).hexdigest()[:8]
        print(f"schedule MD5={fingerprint}  slots={len(self.schedule)} -> {self.schedule}")

        self.fig, self.ax = None, None

    def edge_slot_runner(self) -> None:
        """
        The main simulation loop runner.

        This function calculates the current time slot, visualizes the
        communications for that slot, and simulates the iperf test if the
        current node is active.
        """
        now = time.time()
        slot_idx = int(now // SLOT_LENGTH) % self.num_slots
        slotted_comms = self.schedule[slot_idx]

        slot_start = math.floor(now / SLOT_LENGTH) * SLOT_LENGTH
        end_start_window = slot_start + GUARD_TIME
        slot_end = slot_start + SLOT_LENGTH

        def _wait_for_next_slot() -> None:
            """Calculates the remaining time in the slot and sleeps."""
            time.sleep(max(0, slot_end - time.time()))

        print(f"[DEBUG] Slot {slot_idx} starts at {slot_start:.1f}s, ends at {slot_end:.1f}s")
        self.visualize_comms(slotted_comms, None)

        now_is_in_start_window = slot_start <= now < end_start_window
        if not now_is_in_start_window:
            _wait_for_next_slot()
            return

        my_test_partner: Optional[str] = None
        for client, server in slotted_comms:
            if client == self.my_ip:
                my_test_partner = server
                break

        if not my_test_partner:
            _wait_for_next_slot()
            return

        self.run_iperf(my_test_partner)

    def run_iperf(self, ip: str) -> None:
        """
        Simulates running an iperf test.

        Args:
            ip: The IP address of the test partner.
        """
        print(f"[INFO] Running IPERF to {ip} (simulated)")
        time.sleep(IPERF_TIME)

    def visualize_comms(self, edges: List[Tuple[str, str]], colors: Optional[List[str]]) -> None:
        """
        Visualizes the communication links for the current slot.

        Args:
            edges: A list of (client, server) tuples representing the active links.
            colors: A list of colors for the edges.
        """
        import matplotlib.pyplot as plt
        import networkx as nx

        if self.fig is None or self.ax is None:
            self.fig, self.ax = plt.subplots(figsize=(8, 6))

        self.ax.clear()
        self.ax.set_title("Edge Coloring Schedule Visualization", fontsize=16)
        self.ax.axis("off")
        G = nx.DiGraph()
        G.add_nodes_from(self.node_list)
        pos = nx.circular_layout(G)
        nx.draw_networkx_nodes(G, pos, ax=self.ax, node_color='lightblue', node_size=1000, edgecolors='k')
        nx.draw_networkx_labels(G, pos, ax=self.ax, font_size=14, font_weight='bold')

        if colors is None:
            colors = ['black'] * len(edges)

        assert len(edges) == len(colors), "Edges and colors must have the same length."

        nx.draw_networkx_edges(
            G, pos, edgelist=edges, ax=self.ax,
            width=3, edge_color=colors,
            arrows=True,
            arrowsize=30,
            arrowstyle='-|>',
            connectionstyle='arc3,rad=0.1'
        )

        plt.tight_layout()
        plt.show(block=False)
        plt.pause(0.1)

def main() -> None:
    """
    The main entry point for the schedule tester script.
    """
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'network_params.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    monitor = EdgePayloadMonitor(config)
    try:
        while True:
            monitor.edge_slot_runner()
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Shutting down.")

if __name__ == "__main__":
    main()
