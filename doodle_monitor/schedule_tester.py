#!/usr/bin/env python3
"""
Simulate edge-colored scheduling of UDP and ping tests between nodes,
without any ROS dependencies.

* slot_length      = guard_time + iperf_time   (e.g. 1.3 s)
* num_slots        = len(schedule)  ==  (#nodes-even) ? n-1 : n
* full cycle       = slot_length x num_slots
"""

import json, time, math, hashlib
from itertools import permutations

### TIMING INFO
GUARD_TIME = 0.5  # seconds
IPERF_TIME = 3.0  # seconds
SLOT_LENGTH = GUARD_TIME + IPERF_TIME  # total time for one slot


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

print(f"SCHEDULE:")
for idx, slot in enumerate(SCHEDULE):
    print(f"  Slot {idx}: {slot}")
print(f"Total slots: {NUM_SLOTS}  Slot length: {SLOT_LENGTH}s\n\n")


class EdgePayloadMonitor:
    def __init__(self, ):
        import os
        # self.hostname = os.uname()[1]
        self.hostname = list(HOSTNAME_TO_IP_MAPPING.keys())[0]
        self.my_ip = HOSTNAME_TO_IP_MAPPING.get(self.hostname, None)
        if self.my_ip is None:
            raise RuntimeError(
                f"Unknown hostname {self.hostname} for user {os.getenv('USER', 'unknown')}, "
                "do not know IP address."
            )

        self.num_slots = len(SCHEDULE)

        print(f"edge-schedule ready: slot_len={SLOT_LENGTH}s  slots={self.num_slots}  my_name={self.my_ip}")
        sched_str = json.dumps(SCHEDULE, sort_keys=True)
        fingerprint = hashlib.md5(sched_str.encode()).hexdigest()[:8]
        print(f"schedule MD5={fingerprint}  slots={len(SCHEDULE)} -> {SCHEDULE}")

        self.fig, self.ax = None, None

    def edge_slot_runner(self):
        now = time.time()

        slot_idx = int(now // SLOT_LENGTH) % self.num_slots
        slotted_comms = SCHEDULE[slot_idx]
        # print(f"[DEBUG] Running slot {slot_idx} at {now:.1f}s: {slotted_comms}")

        def _wait_for_next_slot():
            time.sleep(max(0, slot_end - now))

        print(f"[DEBUG] Slot {slot_idx} starts at {slot_start:.1f}s, ends at {slot_end:.1f}s")

        self.visualize_comms(slotted_comms, None)

        now_is_in_start_window = slot_start <= now < end_start_window
        if not now_is_in_start_window:
            # wait until the next slot starts
            # print(f"[DEBUG] Not in start window ({slot_start:.1f} to {end_start_window:.1f}) - waiting until {slot_end:.1f}s\n")

            _wait_for_next_slot()
            return

        my_test_partner = None
        for client, server in slotted_comms:
            if client == self.my_ip:
                my_test_partner = server
                break

        if not my_test_partner:
            # print(f"[DEBUG] {self.my_ip} not in slot {slot_idx}, skipping.")
            _wait_for_next_slot()
            return

        self.run_iperf(my_test_partner)

    def run_iperf(self, ip):
        timeout = IPERF_TIME + 0.5
        # cmd = ["iperf3", "-c", ip, "-t", str(IPERF_TIME), "-b", "0", "--json"]
        # print(f"[INFO] Running IPERF to {ip} (simulated)")
        ok = True

        # wait the iperf time
        time.sleep(IPERF_TIME)

    def visualize_comms(self, edges, colors):
        import matplotlib.pyplot as plt
        import networkx as nx
        from matplotlib import animation, cm

        if self.fig is None or self.ax is None:
            self.fig, self.ax = plt.subplots(figsize=(8, 6))

        # clear existing edges
        self.ax.clear()
        self.ax.set_title("Edge Coloring Schedule Visualization", fontsize=16)
        self.ax.axis("off")
        G = nx.DiGraph()
        G.add_nodes_from(NODE_LIST)
        pos = nx.circular_layout(G)
        nx.draw_networkx_nodes(
            G, pos, ax=self.ax, node_color='lightblue', node_size=1000, edgecolors='k'
        )
        nx.draw_networkx_labels(
            G, pos, ax=self.ax, font_size=14, font_weight='bold'
        )

        if colors is None:
            colors = ['black'] * len(edges)

        assert len(edges) == len(colors), "Edges and colors must have the same length."

        # draw the edges as directed from first to second node
        nx.draw_networkx_edges(
            G, pos, edgelist=edges, ax=self.ax,
            width=3, edge_color=colors,
            arrows=True,
            arrowsize=30,              # default is 10 — this makes it much bigger
            arrowstyle='-|>',          # a classic filled arrow
            connectionstyle='arc3,rad=0.1'  # optional: slight curve to separate edges
        )

        # visualize the plot, so we can watch it while running
        plt.tight_layout()
        plt.show(block=False)
        plt.pause(0.1)


def main():
    monitor = EdgePayloadMonitor()
    try:
        while True:
            monitor.edge_slot_runner()
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Shutting down.")


if __name__ == "__main__":
    main()
