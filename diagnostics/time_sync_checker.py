#!/usr/bin/env python3
"""
Time Synchronization Checker for Multi-Robot System

This script checks if all payloads (10.19.30.100-104) have synchronized system time
and ROS time. This is critical for time-division multiple access (TDMA) schemes
where precise timing coordination is required.

The script performs the following checks:
1. System time synchronization across all payloads
2. ROS time synchronization (if ROS is running)
3. Time drift between payloads
4. NTP status (if available)

Usage:
    python3 time_sync_checker.py [--ips IP1 IP2 ...] [--threshold SECONDS]
"""

import argparse
import subprocess
import sys
import time
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json
import shutil


class TimeSyncChecker:
    """
    A utility class to check time synchronization across multiple robots/payloads.
    """
    
    DEFAULT_IPS = [
        "10.19.30.100",
        "10.19.30.101",
        "10.19.30.102",
        "10.19.30.103",
        "10.19.30.104"
    ]
    
    # Default threshold for time difference warning (in seconds)
    DEFAULT_THRESHOLD = 0.1  # 100ms
    
    def __init__(self, ips: List[str], username: str = "neuroam", password: Optional[str] = None, threshold: float = DEFAULT_THRESHOLD):
        """
        Initialize the time sync checker.
        
        Args:
            ips: List of IP addresses to check
            username: SSH username (default: neuroam)
            password: SSH password (if None, will try key-based auth)
            threshold: Maximum acceptable time difference in seconds
        """
        self.ips = ips
        self.username = username
        self.password = password
        self.threshold = threshold
        self.results: Dict[str, Dict] = {}
        self.use_sshpass = password is not None and shutil.which("sshpass") is not None
        
        if password and not self.use_sshpass:
            print("⚠️  Warning: sshpass not found. Install it for password authentication:")
            print("   sudo apt-get install sshpass")
            print("   Trying key-based authentication instead...\n")
    
    def _build_ssh_command(self, ip: str, remote_command: str, timeout: int = 2) -> List[str]:
        """
        Build SSH command with appropriate authentication method.
        
        Args:
            ip: IP address
            remote_command: Command to run on remote host
            timeout: Connection timeout
            
        Returns:
            List of command arguments
        """
        ssh_opts = [
            "-o", f"ConnectTimeout={timeout}",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
        ]
        
        if self.use_sshpass:
            return ["sshpass", "-p", self.password, "ssh"] + ssh_opts + [f"{self.username}@{ip}", remote_command]
        else:
            return ["ssh"] + ssh_opts + [f"{self.username}@{ip}", remote_command]
    
    def check_ssh_connectivity(self, ip: str, timeout: int = 2) -> bool:
        """
        Check if SSH connection to the given IP is possible.
        
        Args:
            ip: IP address to check
            timeout: Connection timeout in seconds
            
        Returns:
            True if SSH connection successful, False otherwise
        """
        try:
            cmd = self._build_ssh_command(ip, "echo 'OK'", timeout)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception) as e:
            return False
    
    def get_system_time(self, ip: str) -> Optional[Tuple[float, float, float]]:
        """
        Get the system time from a remote host via SSH with latency compensation.
        
        This method measures the round-trip time and uses the midpoint to estimate
        when the remote timestamp was actually captured, providing more accurate
        time synchronization measurements.
        
        Args:
            ip: IP address of the host
            
        Returns:
            Tuple of (remote_time, local_time_estimate, uncertainty) or None if failed
            - remote_time: The timestamp from the remote host
            - local_time_estimate: Estimated local time when remote measurement occurred (midpoint)
            - uncertainty: Half the round-trip time (measurement uncertainty in seconds)
        """
        try:
            # Record local time before SSH command
            local_before = time.time()
            
            # Use date +%s.%N to get high-precision timestamp
            cmd = self._build_ssh_command(ip, "date +%s.%N", 2)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3
            )
            
            # Record local time after SSH command
            local_after = time.time()
            
            if result.returncode == 0:
                remote_time = float(result.stdout.strip())
                # Use midpoint of before/after as best estimate of when measurement occurred
                local_time_estimate = (local_before + local_after) / 2
                # Half the round-trip time is the uncertainty
                uncertainty = (local_after - local_before) / 2
                return remote_time, local_time_estimate, uncertainty
            return None
        except (subprocess.TimeoutExpired, ValueError, Exception) as e:
            print(f"  ⚠️  Failed to get system time from {ip}: {e}")
            return None
    
    def get_ros_time(self, ip: str) -> Optional[Tuple[float, float, float]]:
        """
        Get the ROS time from a remote host via SSH with latency compensation.
        
        Args:
            ip: IP address of the host
            
        Returns:
            Tuple of (remote_time, local_time_estimate, uncertainty) or None if ROS not available
        """
        try:
            # Record local time before SSH command
            local_before = time.time()
            
            # Check if ROS is running and get the time
            ros_cmd = (
                "source /opt/ros/*/setup.bash 2>/dev/null && "
                "ros2 node list > /dev/null 2>&1 && "
                "python3 -c 'import rclpy; rclpy.init(); "
                "node = rclpy.create_node(\"time_check\"); "
                "t = node.get_clock().now(); "
                "print(t.nanoseconds / 1e9); "
                "node.destroy_node(); rclpy.shutdown()' 2>/dev/null"
            )
            
            cmd = self._build_ssh_command(ip, ros_cmd, 2)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Record local time after SSH command
            local_after = time.time()
            
            if result.returncode == 0 and result.stdout.strip():
                remote_time = float(result.stdout.strip())
                local_time_estimate = (local_before + local_after) / 2
                uncertainty = (local_after - local_before) / 2
                return remote_time, local_time_estimate, uncertainty
            return None
        except (subprocess.TimeoutExpired, ValueError, Exception) as e:
            return None
    
    def get_ntp_status(self, ip: str) -> Optional[str]:
        """
        Get NTP synchronization status from a remote host.
        
        Args:
            ip: IP address of the host
            
        Returns:
            NTP status string, or None if not available
        """
        try:
            # Try to get timedatectl status
            ntp_cmd = (
                "timedatectl status 2>/dev/null | grep 'synchronized\\|NTP' || "
                "chronyc tracking 2>/dev/null | head -n 3 || "
                "ntpq -p 2>/dev/null | head -n 3 || echo 'N/A'"
            )
            
            cmd = self._build_ssh_command(ip, ntp_cmd, 2)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return "N/A"
        except (subprocess.TimeoutExpired, Exception):
            return "N/A"
    
    def check_single_host(self, ip: str) -> Dict:
        """
        Perform all time checks on a single host.
        
        Args:
            ip: IP address to check
            
        Returns:
            Dictionary with check results
        """
        print(f"\n📡 Checking {ip}...")
        
        result = {
            "ip": ip,
            "reachable": False,
            "system_time": None,
            "system_time_local": None,
            "system_time_uncertainty": None,
            "ros_time": None,
            "ros_time_local": None,
            "ros_time_uncertainty": None,
            "ntp_status": None,
            "check_timestamp": time.time()
        }
        
        # Check connectivity
        if not self.check_ssh_connectivity(ip):
            print(f"  ❌ Cannot reach {ip} via SSH")
            return result
        
        result["reachable"] = True
        print(f"  ✓ SSH connection successful")
        
        # Get system time
        system_time_result = self.get_system_time(ip)
        if system_time_result:
            remote_time, local_time, uncertainty = system_time_result
            result["system_time"] = remote_time
            result["system_time_local"] = local_time
            result["system_time_uncertainty"] = uncertainty
            dt = datetime.fromtimestamp(remote_time)
            print(f"  ✓ System time: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} (±{uncertainty*1000:.1f}ms)")
        else:
            print(f"  ❌ Failed to get system time")
        
        # Get ROS time
        ros_time_result = self.get_ros_time(ip)
        if ros_time_result:
            remote_time, local_time, uncertainty = ros_time_result
            result["ros_time"] = remote_time
            result["ros_time_local"] = local_time
            result["ros_time_uncertainty"] = uncertainty
            dt = datetime.fromtimestamp(remote_time)
            print(f"  ✓ ROS time: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} (±{uncertainty*1000:.1f}ms)")
        else:
            print(f"  ⚠️  ROS time not available (ROS may not be running)")
        
        # Get NTP status
        ntp_status = self.get_ntp_status(ip)
        if ntp_status and ntp_status != "N/A":
            result["ntp_status"] = ntp_status
            print(f"  ℹ️  NTP: {ntp_status[:100]}...")
        
        return result
    
    def check_all_hosts(self) -> Dict[str, Dict]:
        """
        Check time synchronization on all configured hosts.
        
        Returns:
            Dictionary mapping IP addresses to their check results
        """
        print("=" * 70)
        print("🕐 TIME SYNCHRONIZATION CHECK")
        print("=" * 70)
        print(f"Checking {len(self.ips)} payload(s)...")
        print(f"Threshold: {self.threshold * 1000:.1f} ms")
        
        # Collect results
        for ip in self.ips:
            self.results[ip] = self.check_single_host(ip)
        
        return self.results
    
    def analyze_results(self) -> Tuple[bool, str]:
        """
        Analyze the collected results and generate a summary.
        
        Returns:
            Tuple of (is_synchronized, summary_message)
        """
        print("\n" + "=" * 70)
        print("📊 ANALYSIS")
        print("=" * 70)
        
        reachable_hosts = [ip for ip, r in self.results.items() if r["reachable"]]
        unreachable_hosts = [ip for ip, r in self.results.items() if not r["reachable"]]
        
        if not reachable_hosts:
            summary = "❌ CRITICAL: No hosts are reachable!"
            print(summary)
            return False, summary
        
        if unreachable_hosts:
            print(f"\n⚠️  Unreachable hosts: {', '.join(unreachable_hosts)}")
        
        # Analyze system time synchronization
        system_times = [(ip, r["system_time"], r["system_time_local"], r["system_time_uncertainty"]) 
                       for ip, r in self.results.items() 
                       if r["system_time"] is not None]
        
        if len(system_times) < 2:
            summary = "⚠️  Not enough hosts with system time to compare"
            print(f"\n{summary}")
            return False, summary
        
        # Calculate time differences (accounting for when measurements were taken)
        print(f"\n🕐 System Time Analysis:")
        print(f"  Reachable hosts with time: {len(system_times)}")
        
        # Calculate average measurement uncertainty
        avg_uncertainty = sum(u for _, _, _, u in system_times) / len(system_times)
        print(f"  Average measurement uncertainty: ±{avg_uncertainty * 1000:.2f} ms")
        
        # Use the first host as reference
        reference_ip, ref_remote, ref_local, ref_uncertainty = system_times[0]
        print(f"\n  Using {reference_ip} as reference:")
        
        # Calculate compensated time differences
        max_diff = 0.0
        compensated_diffs = []
        
        for ip, remote_time, local_time, uncertainty in system_times[1:]:
            # Calculate time offset accounting for when measurements were taken locally
            # offset = (remote - local_remote) - (ref_remote - ref_local)
            # This gives us the clock offset between the two hosts
            time_offset = (remote_time - local_time) - (ref_remote - ref_local)
            
            # Combined uncertainty (RSS of individual uncertainties)
            combined_uncertainty = (uncertainty**2 + ref_uncertainty**2)**0.5
            
            compensated_diffs.append(abs(time_offset))
            max_diff = max(max_diff, abs(time_offset))
            
            status = "✓" if abs(time_offset) <= self.threshold else "⚠️"
            print(f"    {status} {ip}: {time_offset * 1000:+.2f} ms (±{combined_uncertainty * 1000:.1f} ms)")
        
        # Calculate statistics
        if compensated_diffs:
            time_spread = max(compensated_diffs)
            avg_diff = sum(compensated_diffs) / len(compensated_diffs)
            print(f"\n  Max offset: {time_spread * 1000:.2f} ms")
            print(f"  Avg offset: {avg_diff * 1000:.2f} ms")
        
        # Analyze ROS time synchronization
        ros_times = [(ip, r["ros_time"], r["ros_time_local"], r["ros_time_uncertainty"]) 
                    for ip, r in self.results.items() 
                    if r["ros_time"] is not None]
        
        if ros_times:
            print(f"\n🤖 ROS Time Analysis:")
            print(f"  Hosts with ROS time: {len(ros_times)}")
            
            if len(ros_times) >= 2:
                # Calculate average measurement uncertainty
                ros_avg_uncertainty = sum(u for _, _, _, u in ros_times) / len(ros_times)
                print(f"  Average measurement uncertainty: ±{ros_avg_uncertainty * 1000:.2f} ms")
                
                reference_ip, ref_ros_remote, ref_ros_local, ref_ros_uncertainty = ros_times[0]
                print(f"\n  Using {reference_ip} as reference:")
                
                ros_compensated_diffs = []
                for ip, ros_remote, ros_local, ros_uncertainty in ros_times[1:]:
                    # Calculate compensated offset
                    time_offset = (ros_remote - ros_local) - (ref_ros_remote - ref_ros_local)
                    combined_uncertainty = (ros_uncertainty**2 + ref_ros_uncertainty**2)**0.5
                    
                    ros_compensated_diffs.append(abs(time_offset))
                    status = "✓" if abs(time_offset) <= self.threshold else "⚠️"
                    print(f"    {status} {ip}: {time_offset * 1000:+.2f} ms (±{combined_uncertainty * 1000:.1f} ms)")
                
                if ros_compensated_diffs:
                    ros_max_offset = max(ros_compensated_diffs)
                    ros_avg_offset = sum(ros_compensated_diffs) / len(ros_compensated_diffs)
                    print(f"\n  Max offset: {ros_max_offset * 1000:.2f} ms")
                    print(f"  Avg offset: {ros_avg_offset * 1000:.2f} ms")
        else:
            print(f"\n⚠️  No ROS time available (ROS may not be running on any host)")
        
        # Final verdict
        print("\n" + "=" * 70)
        is_synced = max_diff <= self.threshold
        
        if is_synced:
            summary = f"✅ PASS: All systems synchronized within {self.threshold * 1000:.1f} ms"
            print(summary)
        else:
            summary = f"⚠️  WARN: Max time offset ({max_diff * 1000:.2f} ms) exceeds threshold ({self.threshold * 1000:.1f} ms)"
            print(summary)
            print("\nRecommendations:")
            print("  • Check NTP configuration on all hosts")
            print("  • Verify network connectivity between hosts and NTP servers")
            print("  • Consider using PTP for sub-millisecond synchronization")
            print("  • Restart chronyd/ntpd services if needed")
        
        print("=" * 70)
        
        return is_synced, summary
    
    def save_results(self, filename: str = "time_sync_results.json"):
        """
        Save the results to a JSON file.
        
        Args:
            filename: Output filename
        """
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Results saved to: {filename}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Check time synchronization across multiple payloads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check default payloads (10.19.30.100-104)
  python3 time_sync_checker.py
  
  # Check specific IPs
  python3 time_sync_checker.py --ips 10.19.30.100 10.19.30.101
  
  # Use custom threshold (50ms)
  python3 time_sync_checker.py --threshold 0.05
  
  # Save results to file
  python3 time_sync_checker.py --output results.json
        """
    )
    
    parser.add_argument(
        '--ips',
        nargs='+',
        default=TimeSyncChecker.DEFAULT_IPS,
        help='List of IP addresses to check (default: 10.19.30.100-104)'
    )
    
    parser.add_argument(
        '--username',
        default='neuroam',
        help='SSH username (default: neuroam)'
    )
    
    parser.add_argument(
        '--password',
        default='neuroam',
        help='SSH password (default: neuroam)'
    )
    
    parser.add_argument(
        '--threshold',
        type=float,
        default=TimeSyncChecker.DEFAULT_THRESHOLD,
        help=f'Maximum acceptable time difference in seconds (default: {TimeSyncChecker.DEFAULT_THRESHOLD})'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Save results to JSON file'
    )
    
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously with periodic checks'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=10,
        help='Interval between checks in continuous mode (seconds)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.continuous:
            print("Running in continuous mode. Press Ctrl+C to stop.\n")
            iteration = 1
            while True:
                print(f"\n{'#' * 70}")
                print(f"# Iteration {iteration}")
                print(f"{'#' * 70}")
                
                checker = TimeSyncChecker(args.ips, args.username, args.password, args.threshold)
                checker.check_all_hosts()
                is_synced, summary = checker.analyze_results()
                
                if args.output:
                    output_name = f"{args.output.rsplit('.', 1)[0]}_{iteration}.json"
                    checker.save_results(output_name)
                
                iteration += 1
                print(f"\nNext check in {args.interval} seconds...")
                time.sleep(args.interval)
        else:
            checker = TimeSyncChecker(args.ips, args.username, args.password, args.threshold)
            checker.check_all_hosts()
            is_synced, summary = checker.analyze_results()
            
            if args.output:
                checker.save_results(args.output)
            
            # Exit with appropriate code
            sys.exit(0 if is_synced else 1)
            
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
