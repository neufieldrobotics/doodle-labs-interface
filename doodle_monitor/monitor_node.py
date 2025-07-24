import rclpy
from rclpy.node import Node
import paramiko
import os
import json
from std_msgs.msg import Float32, Int32, String, Int32MultiArray


hostname_to_radio_ip = {
    'payload0':     "10.223.20.201",
    'payload1': "10.223.21.49",
    'nuroampayload02': "10.223.21.45",
    'neuroam-desktop': "10.223.20.209",
    'payload4': "10.223.20.173"
}

class LinkStateScraper(Node):
    def __init__(self):
        super().__init__('monitor_node', automatically_declare_parameters_from_overrides=True)

        self.hostname = os.uname()[1]
        try:
            self.radio_ip = hostname_to_radio_ip[self.hostname]
        except KeyError:
            raise RuntimeError(f"Unknown hostname {self.hostname}, do not know radio IP address.")

        self.username = self.get_parameter('username').value
        self.password = self.get_parameter('password').value
        self.filepath = self.get_parameter('filepath').value
        self.passive_timer = self.get_parameter('passive_timer').value
        raw_map = self.get_parameter('mac_to_ip_map').value
        self.mac_to_ip_map = json.loads(raw_map)


        self.raw_json_pub = self.create_publisher(String, 'doodle_monitor/raw', 10)
        self.sys_cpu_load = self.create_publisher(Int32MultiArray, 'doodle_monitor/sys/cpu_load', 10)
        self.sys_freemem = self.create_publisher(Int32, 'doodle_monitor/sys/freemem', 10)
        self.sys_localtime = self.create_publisher(Int32, 'doodle_monitor/sys/localtime', 10)
        self.static_info_print = False
        #self.oper_chan
        #self.oper_freq
        #self.chan_width
        self.noise = self.create_publisher(Float32, 'doodle_monitor/noise', 10)
        self.activity = self.create_publisher(Int32, 'doodle_monitor/activity', 10)
        self.lna_status = self.create_publisher(Int32, 'doodle_monitor/lna_status', 10)
        self.sta_status = self.create_publisher(String, 'doodle_monitor/sta_status', 10)
        self.mesh_status = self.create_publisher(String, 'doodle_monitor/mesh_status', 10)
        self.peer_list_pub = self.create_publisher(String, 'doodle_monitor/peer_list', 10)


        # uses mesh status and mac_to_IP
        self.get_logger().info(f"MAC->IP map: {self.mac_to_ip_map}")



        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_connected = False

        self.timer = self.create_timer(self.passive_timer, self.scrape)
        self.get_logger().info("Scraper node started, will attempt connection on first scrape.")


    def scrape(self):


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
            except Exception as e:
                self.get_logger().error(f"SSH connection failed: {e}. Will retry in {self.passive_timer} seconds.")
                return


        stdin, stdout, stderr = self.ssh.exec_command(f'cat {self.filepath}')
        output = stdout.read().decode()
        stdin.close()
        stdout.close()
        stderr.close()

        if output:
            self.parse_and_publish(output)
        else:
            self.get_logger().error(f"scrape returned no output")



    def parse_and_publish(self, json_string):
        msg = String()
        msg.data = json_string
        self.raw_json_pub.publish(msg)

        try:
            data = json.loads(json_string)
        except json.JSONDecodeError as e:
            self.get_logger().warn(f"JSON decode failed, skipping this sample: {e}")
            return


        if not self.static_info_print:
            oper_chan = data.get('oper_chan', 'N/A')
            oper_freq = data.get('oper_freq', 'N/A')
            chan_width = data.get('chan_width', 'N/A')
            self.get_logger().info(f"Radio Stats -> Channel: {oper_chan}, Freq: {oper_freq} MHz, Width: {chan_width} MHz")
            self.static_info_print = True

        sysinfo = data.get('sysinfo', {})
        cpu_load_list = sysinfo.get("cpu_load", [])
        cpu_msg = Int32MultiArray(data=cpu_load_list)
        self.sys_cpu_load.publish(cpu_msg)

        freemem_val = sysinfo.get("freemem", 0)
        self.sys_freemem.publish(Int32(data=freemem_val))

        localtime_val = sysinfo.get("localtime", 0)
        self.sys_localtime.publish(Int32(data=localtime_val))

        noise_val = float(data.get("noise", 0.0))
        self.noise.publish(Float32(data=noise_val))

        activity_val = int(data.get("activity", 0))
        self.activity.publish(Int32(data=activity_val))

        lna_status_val = int(data.get("lna_status", 0))
        self.lna_status.publish(Int32(data=lna_status_val))

        sta_stats_list = data.get('sta_stats', [])
        mesh_stats_list = data.get('mesh_stats', [])
        sta_stats_json_string = json.dumps(sta_stats_list)
        mesh_stats_json_string = json.dumps(mesh_stats_list)
        self.sta_status.publish(String(data=sta_stats_json_string))
        self.mesh_status.publish(String(data=mesh_stats_json_string))


        # Get payload list
        self.publish_payload_list(mesh_stats_list)

    def publish_payload_list(self, mesh_stats_list):

        peers = set()

        # Possible alternative so that it only captures direct communication
        # for entry in mesh_stats_list:
        #     if entry.get("hop_status") != "direct":
        #         continue
        #     mac = entry.get("orig_address", "").lower()
        #     ip  = self.mac_to_ip_map.get(mac)
        #     if ip:
        #         peers_set.add(ip)

        for entry in mesh_stats_list:
            mac = entry.get("orig_address", "").lower()
            ip = self.mac_to_ip_map.get(mac)
            if ip:
                peers.add(ip)
        peer_list_msg = String()
        peer_list_msg.data = json.dumps({"peers": sorted(peers)})
        self.peer_list_pub.publish(peer_list_msg)


    def destroy_node(self):
        self.get_logger().info("Closing SSH connection")
        if self.ssh:
            self.ssh.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LinkStateScraper()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
