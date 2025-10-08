#!/usr/bin/env python3
"""
This script launches a ROS 2 node for monitoring the state of a Doodle Labs radio.

The `LinkStateScraper` node periodically connects to the radio via SSH, fetches a
JSON file containing link state information, and publishes this data to various
ROS 2 topics. This allows for real-time monitoring of the radio's performance
and status within a ROS 2 environment.
"""
import rclpy
from rclpy.node import Node
import paramiko
import os
import json
from std_msgs.msg import Float32, Int32, String, Int32MultiArray
from typing import Dict, Any, List, Optional

class LinkStateScraper(Node):
    """
    A ROS 2 node that scrapes link state data from a radio via SSH.

    This node reads its configuration from ROS 2 parameters, including SSH
    credentials and the remote filepath of the JSON data. It maintains a
    persistent SSH connection to the radio and periodically scrapes the data,
    publishing it to specialized topics.
    """

    def __init__(self) -> None:
        """
        Initializes the LinkStateScraper node.

        This sets up the node's parameters, publishers, and a timer to trigger
        the scraping process periodically. It also initializes the SSH client.
        """
        super().__init__('monitor_node', automatically_declare_parameters_from_overrides=True)

        self.hostname: str = os.uname()[1]
        self.radio_ip: str = self._get_radio_ip()

        # Load parameters from the YAML configuration file
        self.username: str = self.get_parameter('username').value
        self.password: str = self.get_parameter('password').value
        self.filepath: str = self.get_parameter('filepath').value
        self.passive_timer: float = self.get_parameter('passive_timer').value
        raw_map: str = self.get_parameter('mac_to_ip_map').value
        self.mac_to_ip_map: Dict[str, str] = json.loads(raw_map)

        self._setup_publishers()
        self.static_info_print: bool = False

        self.get_logger().info(f"MAC->IP map: {self.mac_to_ip_map}")

        # Initialize the SSH client
        self.ssh: paramiko.SSHClient = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_connected: bool = False

        # Start the periodic scraping process
        self.timer = self.create_timer(self.passive_timer, self.scrape)
        self.get_logger().info("Scraper node started, will attempt connection on first scrape.")

    def _get_radio_ip(self) -> str:
        """
        Determines the radio IP address based on the hostname.

        Returns:
            The IP address of the radio.

        Raises:
            RuntimeError: If the hostname is not found in the mapping.
        """
        hostname_to_radio_ip: Dict[str, str] = self.get_parameter('hostname_to_radio_ip').value
        try:
            return hostname_to_radio_ip[self.hostname]
        except KeyError:
            raise RuntimeError(f"Unknown hostname {self.hostname}, do not know radio IP address.")

    def _setup_publishers(self) -> None:
        """Initializes all the ROS 2 publishers for the node."""
        self.raw_json_pub = self.create_publisher(String, 'doodle_monitor/raw', 10)
        self.sys_cpu_load = self.create_publisher(Int32MultiArray, 'doodle_monitor/sys/cpu_load', 10)
        self.sys_freemem = self.create_publisher(Int32, 'doodle_monitor/sys/freemem', 10)
        self.sys_localtime = self.create_publisher(Int32, 'doodle_monitor/sys/localtime', 10)
        self.noise = self.create_publisher(Float32, 'doodle_monitor/noise', 10)
        self.activity = self.create_publisher(Int32, 'doodle_monitor/activity', 10)
        self.lna_status = self.create_publisher(Int32, 'doodle_monitor/lna_status', 10)
        self.sta_status = self.create_publisher(String, 'doodle_monitor/sta_status', 10)
        self.mesh_status = self.create_publisher(String, 'doodle_monitor/mesh_status', 10)
        self.peer_list_pub = self.create_publisher(String, 'doodle_monitor/peer_list', 10)

    def _connect_ssh(self) -> None:
        """
        Establishes an SSH connection to the radio if not already connected.
        """
        if not self.ssh_connected:
            try:
                self.ssh.connect(
                    self.radio_ip,
                    username=self.username,
                    password=self.password,
                    look_for_keys=False,
                    timeout=5.0,
                    disabled_algorithms=dict(pubkeys=["rsa-sha2-512", "rsa-sha2-256"])
                )
                self.ssh_connected = True
                self.get_logger().info(f"SSH connection to {self.radio_ip} established.")
            except (paramiko.AuthenticationException, paramiko.SSHException, TimeoutError) as e:
                self.get_logger().error(f"SSH connection failed: {e}. Will retry in {self.passive_timer} seconds.")
                self.ssh_connected = False

    def scrape(self) -> None:
        """
        The main scraping function, executed periodically by the timer.

        This function ensures an SSH connection is active, executes a command
        to read the link state file, and then passes the output for parsing
        and publishing.
        """
        self._connect_ssh()
        if not self.ssh_connected:
            return

        try:
            stdin, stdout, stderr = self.ssh.exec_command(f'cat {self.filepath}')
            output: str = stdout.read().decode()
            error: str = stderr.read().decode()
            stdin.close()
            stdout.close()
            stderr.close()

            if error:
                self.get_logger().error(f"Error executing command on remote: {error}")
                return

            if output:
                self.parse_and_publish(output)
            else:
                self.get_logger().error(f"scrape returned no output")

        except paramiko.SSHException as e:
            self.get_logger().error(f"SSH error during scrape: {e}. Connection lost.")
            self.ssh_connected = False
            self.ssh.close()

    def parse_and_publish(self, json_string: str) -> None:
        """
        Parses the JSON string and publishes the data to various topics.

        Args:
            json_string: The raw JSON string fetched from the radio.
        """
        msg = String()
        msg.data = json_string
        self.raw_json_pub.publish(msg)

        try:
            data: Dict[str, Any] = json.loads(json_string)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"JSON decode failed, skipping this sample: {e}")
            return

        # Log static radio info once
        if not self.static_info_print:
            oper_chan: str = data.get('oper_chan', 'N/A')
            oper_freq: str = data.get('oper_freq', 'N/A')
            chan_width: str = data.get('chan_width', 'N/A')
            self.get_logger().info(f"Radio Stats -> Channel: {oper_chan}, Freq: {oper_freq} MHz, Width: {chan_width} MHz")
            self.static_info_print = True

        # Publish system info
        sysinfo: Dict[str, Any] = data.get('sysinfo', {})
        cpu_load_list: List[int] = sysinfo.get("cpu_load", [])
        cpu_msg = Int32MultiArray(data=cpu_load_list)
        self.sys_cpu_load.publish(cpu_msg)

        freemem_val: int = sysinfo.get("freemem", 0)
        self.sys_freemem.publish(Int32(data=freemem_val))

        localtime_val: int = sysinfo.get("localtime", 0)
        self.sys_localtime.publish(Int32(data=localtime_val))

        # Publish radio stats
        noise_val: float = float(data.get("noise", 0.0))
        self.noise.publish(Float32(data=noise_val))

        activity_val: int = int(data.get("activity", 0))
        self.activity.publish(Int32(data=activity_val))

        lna_status_val: int = int(data.get("lna_status", 0))
        self.lna_status.publish(Int32(data=lna_status_val))

        # Publish station and mesh stats
        sta_stats_list: List[Dict[str, Any]] = data.get('sta_stats', [])
        mesh_stats_list: List[Dict[str, Any]] = data.get('mesh_stats', [])
        sta_stats_json_string: str = json.dumps(sta_stats_list)
        mesh_stats_json_string: str = json.dumps(mesh_stats_list)
        self.sta_status.publish(String(data=sta_stats_json_string))
        self.mesh_status.publish(String(data=mesh_stats_json_string))

        self.publish_payload_list(mesh_stats_list)

    def publish_payload_list(self, mesh_stats_list: List[Dict[str, Any]]) -> None:
        """
        Extracts and publishes a list of reachable peers.

        Args:
            mesh_stats_list: A list of dictionaries, each representing a mesh link.
        """
        peers = set()
        for entry in mesh_stats_list:
            mac: str = entry.get("orig_address", "").lower()
            ip: Optional[str] = self.mac_to_ip_map.get(mac)
            if ip:
                peers.add(ip)
        peer_list_msg = String()
        peer_list_msg.data = json.dumps({"peers": sorted(list(peers))})
        self.peer_list_pub.publish(peer_list_msg)

    def destroy_node(self) -> None:
        """
        Cleans up resources when the node is shut down.
        """
        self.get_logger().info("Closing SSH connection")
        if self.ssh:
            self.ssh.close()
        super().destroy_node()

def main(args: Optional[List[str]] = None) -> None:
    """
    The main entry point for the monitor_node.
    """
    rclpy.init(args=args)
    node = LinkStateScraper()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
