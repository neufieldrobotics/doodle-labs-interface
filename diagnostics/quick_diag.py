#!/usr/bin/env python3
"""
Quick Network and Time Diagnostics for Payload Network

This script performs rapid diagnostics to identify common issues with the
time-division multiplexing setup. It checks:
- Network connectivity (ping)
- SSH accessibility  
- System clock status
- NTP/Chrony service status
- Time zone configuration
- ROS daemon status

Use this for quick troubleshooting before running detailed time sync checks.

Usage:
    python3 quick_diag.py [--ips IP1 IP2 ...]
"""

import argparse
import subprocess
import sys
import concurrent.futures
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class QuickDiagnostics:
    """
    Quick diagnostic checks for multi-robot network.
    """
    
    DEFAULT_IPS = [
        "10.19.30.100",
        "10.19.30.101",
        "10.19.30.102",
        "10.19.30.103",
        "10.19.30.104"
    ]
    
    def __init__(self, ips: List[str], parallel: bool = True):
        """
        Initialize diagnostics.
        
        Args:
            ips: List of IP addresses to check
            parallel: Run checks in parallel for speed
        """
        self.ips = ips
        self.parallel = parallel
        self.results: Dict[str, Dict] = {}
    
    def ping_host(self, ip: str, count: int = 3, timeout: int = 2) -> Tuple[bool, Optional[float]]:
        """
        Ping a host to check basic network connectivity.
        
        Args:
            ip: IP address to ping
            count: Number of ping packets
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (success, average_rtt_ms)
        """
        try:
            result = subprocess.run(
                ["ping", "-c", str(count), "-W", str(timeout), ip],
                capture_output=True,
                text=True,
                timeout=timeout * count + 2
            )
            
            if result.returncode == 0:
                # Parse RTT from output
                for line in result.stdout.split('\n'):
                    if 'avg' in line or 'rtt' in line:
                        parts = line.split('=')
                        if len(parts) > 1:
                            stats = parts[1].split('/')
                            if len(stats) >= 2:
                                return True, float(stats[1])
                return True, None
            return False, None
        except (subprocess.TimeoutExpired, Exception):
            return False, None
    
    def check_ssh(self, ip: str, timeout: int = 2) -> bool:
        """
        Check if SSH connection is possible.
        
        Args:
            ip: IP address to check
            timeout: Connection timeout
            
        Returns:
            True if SSH works, False otherwise
        """
        try:
            result = subprocess.run(
                ["ssh", "-o", f"ConnectTimeout={timeout}",
                 "-o", "StrictHostKeyChecking=no",
                 "-o", "BatchMode=yes",
                 f"root@{ip}", "exit"],
                capture_output=True,
                timeout=timeout + 1
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def get_hostname(self, ip: str) -> Optional[str]:
        """Get hostname from remote host."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}", "hostname"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None
    
    def check_ntp_service(self, ip: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Check NTP/Chrony service status.
        
        Returns:
            Tuple of (service_name, status)
        """
        try:
            # Check for chronyd
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}", 
                 "systemctl is-active chronyd 2>/dev/null || "
                 "systemctl is-active ntpd 2>/dev/null || "
                 "systemctl is-active systemd-timesyncd 2>/dev/null || "
                 "echo 'none'"],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            if result.returncode == 0:
                status = result.stdout.strip()
                
                if 'chronyd' in status or status == 'active':
                    # Try to determine which service
                    check_result = subprocess.run(
                        ["ssh", "-o", "ConnectTimeout=2",
                         "-o", "StrictHostKeyChecking=no",
                         f"root@{ip}",
                         "systemctl is-active chronyd && echo 'chronyd' || "
                         "systemctl is-active ntpd && echo 'ntpd' || "
                         "systemctl is-active systemd-timesyncd && echo 'timesyncd'"],
                        capture_output=True,
                        text=True,
                        timeout=3
                    )
                    lines = check_result.stdout.strip().split('\n')
                    service = lines[-1] if lines else 'unknown'
                    return service, 'active'
                
                return 'unknown', status
            return None, None
        except (subprocess.TimeoutExpired, Exception):
            return None, None
    
    def check_time_sync_status(self, ip: str) -> Optional[str]:
        """Check if system clock is synchronized."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}",
                 "timedatectl status 2>/dev/null | grep 'synchronized' || echo 'N/A'"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None
    
    def check_ros_daemon(self, ip: str) -> bool:
        """Check if ROS daemon is running."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}",
                 "pgrep -f 'ros2 daemon' > /dev/null && echo 'running' || echo 'not running'"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return 'running' in result.stdout
            return False
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def check_timezone(self, ip: str) -> Optional[str]:
        """Get timezone setting."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}",
                 "timedatectl 2>/dev/null | grep 'Time zone' || date +%Z"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, Exception):
            return None
    
    def diagnose_single_host(self, ip: str) -> Dict:
        """
        Run all diagnostic checks on a single host.
        
        Args:
            ip: IP address to diagnose
            
        Returns:
            Dictionary with diagnostic results
        """
        print(f"\n🔍 Diagnosing {ip}...")
        
        result = {
            "ip": ip,
            "ping": False,
            "ssh": False,
            "hostname": None,
            "ntp_service": None,
            "ntp_status": None,
            "time_sync": None,
            "timezone": None,
            "ros_daemon": False
        }
        
        # Ping test
        ping_ok, rtt = self.ping_host(ip)
        result["ping"] = ping_ok
        if ping_ok:
            rtt_str = f" ({rtt:.1f} ms)" if rtt else ""
            print(f"  ✓ Ping{rtt_str}")
        else:
            print(f"  ❌ Ping failed")
            return result
        
        # SSH test
        ssh_ok = self.check_ssh(ip)
        result["ssh"] = ssh_ok
        if ssh_ok:
            print(f"  ✓ SSH accessible")
        else:
            print(f"  ❌ SSH failed")
            return result
        
        # Get hostname
        hostname = self.get_hostname(ip)
        result["hostname"] = hostname
        if hostname:
            print(f"  ℹ️  Hostname: {hostname}")
        
        # Check NTP service
        ntp_service, ntp_status = self.check_ntp_service(ip)
        result["ntp_service"] = ntp_service
        result["ntp_status"] = ntp_status
        if ntp_service:
            status_icon = "✓" if ntp_status == "active" else "⚠️"
            print(f"  {status_icon} NTP service: {ntp_service} ({ntp_status})")
        else:
            print(f"  ⚠️  NTP service: unknown")
        
        # Check time synchronization
        time_sync = self.check_time_sync_status(ip)
        result["time_sync"] = time_sync
        if time_sync:
            if 'yes' in time_sync.lower():
                print(f"  ✓ Time synchronized")
            else:
                print(f"  ⚠️  Time sync: {time_sync}")
        
        # Check timezone
        timezone = self.check_timezone(ip)
        result["timezone"] = timezone
        if timezone:
            print(f"  ℹ️  Timezone: {timezone}")
        
        # Check ROS daemon
        ros_ok = self.check_ros_daemon(ip)
        result["ros_daemon"] = ros_ok
        if ros_ok:
            print(f"  ✓ ROS daemon running")
        else:
            print(f"  ⚠️  ROS daemon not detected")
        
        return result
    
    def diagnose_all_hosts(self):
        """Run diagnostics on all hosts."""
        print("=" * 70)
        print("🏥 QUICK DIAGNOSTICS")
        print("=" * 70)
        print(f"Checking {len(self.ips)} host(s)...")
        
        if self.parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.ips)) as executor:
                future_to_ip = {
                    executor.submit(self.diagnose_single_host, ip): ip 
                    for ip in self.ips
                }
                for future in concurrent.futures.as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    try:
                        self.results[ip] = future.result()
                    except Exception as e:
                        print(f"❌ Error checking {ip}: {e}")
                        self.results[ip] = {"ip": ip, "error": str(e)}
        else:
            for ip in self.ips:
                self.results[ip] = self.diagnose_single_host(ip)
    
    def print_summary(self):
        """Print summary of diagnostics."""
        print("\n" + "=" * 70)
        print("📋 SUMMARY")
        print("=" * 70)
        
        # Count issues
        reachable = sum(1 for r in self.results.values() if r.get("ping"))
        ssh_ok = sum(1 for r in self.results.values() if r.get("ssh"))
        ntp_active = sum(1 for r in self.results.values() 
                        if r.get("ntp_status") == "active")
        time_synced = sum(1 for r in self.results.values() 
                         if r.get("time_sync") and "yes" in r.get("time_sync", "").lower())
        ros_running = sum(1 for r in self.results.values() if r.get("ros_daemon"))
        
        total = len(self.ips)
        
        print(f"\n📊 Status Overview:")
        print(f"  Reachable (ping):     {reachable}/{total}")
        print(f"  SSH accessible:       {ssh_ok}/{total}")
        print(f"  NTP active:           {ntp_active}/{total}")
        print(f"  Time synchronized:    {time_synced}/{total}")
        print(f"  ROS daemon running:   {ros_running}/{total}")
        
        # Identify issues
        issues = []
        
        if reachable < total:
            unreachable = [ip for ip, r in self.results.items() if not r.get("ping")]
            issues.append(f"Unreachable hosts: {', '.join(unreachable)}")
        
        if ssh_ok < reachable:
            no_ssh = [ip for ip, r in self.results.items() 
                     if r.get("ping") and not r.get("ssh")]
            issues.append(f"SSH issues: {', '.join(no_ssh)}")
        
        if ntp_active < ssh_ok:
            no_ntp = [ip for ip, r in self.results.items() 
                     if r.get("ssh") and r.get("ntp_status") != "active"]
            issues.append(f"NTP not active: {', '.join(no_ntp)}")
        
        if time_synced < ssh_ok:
            not_synced = [ip for ip, r in self.results.items() 
                         if r.get("ssh") and not (r.get("time_sync") and "yes" in r.get("time_sync", "").lower())]
            issues.append(f"Time not synced: {', '.join(not_synced)}")
        
        # Check timezone consistency
        timezones = set(r.get("timezone") for r in self.results.values() 
                       if r.get("timezone"))
        if len(timezones) > 1:
            issues.append(f"Multiple timezones detected: {timezones}")
        
        if issues:
            print(f"\n⚠️  Issues Found:")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")
        else:
            print(f"\n✅ No major issues detected!")
        
        print("\n💡 Recommendations:")
        if ntp_active < ssh_ok:
            print("  • Start NTP service: systemctl start chronyd")
        if time_synced < ssh_ok:
            print("  • Check NTP configuration: chronyc sources")
            print("  • Verify network access to NTP servers")
        if len(timezones) > 1:
            print("  • Ensure all hosts use the same timezone")
        if ros_running < ssh_ok:
            print("  • Start ROS daemon if needed: ros2 daemon start")
        
        print("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Quick diagnostics for payload network",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--ips',
        nargs='+',
        default=QuickDiagnostics.DEFAULT_IPS,
        help='List of IP addresses to check (default: 10.19.30.100-104)'
    )
    
    parser.add_argument(
        '--sequential',
        action='store_true',
        help='Run checks sequentially instead of in parallel'
    )
    
    args = parser.parse_args()
    
    try:
        diag = QuickDiagnostics(args.ips, parallel=not args.sequential)
        diag.diagnose_all_hosts()
        diag.print_summary()
        
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
