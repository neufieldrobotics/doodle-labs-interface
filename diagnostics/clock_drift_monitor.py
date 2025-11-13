#!/usr/bin/env python3
"""
Clock Drift Monitor for Multi-Robot System

This script monitors clock drift between payloads over time. It takes multiple
time measurements and calculates the drift rate, which helps identify if clocks
are diverging (indicating NTP issues or hardware clock problems).

This is particularly important for TDMA schemes where even small drifts can
accumulate and cause slot timing conflicts.

Usage:
    python3 clock_drift_monitor.py [--ips IP1 IP2 ...] [--duration SECONDS] [--samples N]
"""

import argparse
import subprocess
import sys
import time
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json
import statistics


class ClockDriftMonitor:
    """
    Monitor clock drift between multiple hosts over time.
    """
    
    DEFAULT_IPS = [
        "10.19.30.100",
        "10.19.30.101",
        "10.19.30.102",
        "10.19.30.103",
        "10.19.30.104"
    ]
    
    def __init__(self, ips: List[str], duration: int = 60, samples: int = 10):
        """
        Initialize the clock drift monitor.
        
        Args:
            ips: List of IP addresses to monitor
            duration: Total duration of monitoring in seconds
            samples: Number of samples to take
        """
        self.ips = ips
        self.duration = duration
        self.samples = samples
        self.interval = duration / (samples - 1) if samples > 1 else 1
        self.measurements: List[Dict[str, float]] = []
        
    def get_time_from_host(self, ip: str) -> Optional[Tuple[float, float]]:
        """
        Get high-precision time from a remote host.
        
        Args:
            ip: IP address of the host
            
        Returns:
            Tuple of (local_time, remote_time) or None if failed
        """
        try:
            local_before = time.time()
            
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=2",
                 "-o", "StrictHostKeyChecking=no",
                 f"root@{ip}", "date +%s.%N"],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            local_after = time.time()
            
            if result.returncode == 0:
                remote_time = float(result.stdout.strip())
                # Use average of before/after for local timestamp
                local_time = (local_before + local_after) / 2
                return local_time, remote_time
            return None
        except (subprocess.TimeoutExpired, ValueError, Exception) as e:
            return None
    
    def take_sample(self, sample_num: int) -> Dict[str, float]:
        """
        Take a single time sample from all hosts.
        
        Args:
            sample_num: Sample number (for display)
            
        Returns:
            Dictionary mapping IP to time offset from local clock
        """
        print(f"📸 Sample {sample_num}/{self.samples} at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        
        sample = {"timestamp": time.time()}
        
        for ip in self.ips:
            result = self.get_time_from_host(ip)
            if result:
                local_time, remote_time = result
                # Calculate offset: positive means remote is ahead
                offset = remote_time - local_time
                sample[ip] = offset
                print(f"  {ip}: {offset * 1000:+.2f} ms")
            else:
                print(f"  {ip}: ❌ Failed")
                sample[ip] = None
        
        return sample
    
    def calculate_drift(self, ip: str) -> Optional[Tuple[float, float, float]]:
        """
        Calculate clock drift rate for a given host.
        
        Args:
            ip: IP address to analyze
            
        Returns:
            Tuple of (drift_rate_ms_per_sec, initial_offset, final_offset) or None
        """
        # Extract valid measurements for this IP
        valid_measurements = [
            (m["timestamp"], m[ip]) 
            for m in self.measurements 
            if ip in m and m[ip] is not None
        ]
        
        if len(valid_measurements) < 2:
            return None
        
        # First and last measurement
        t0, offset0 = valid_measurements[0]
        t1, offset1 = valid_measurements[-1]
        
        # Calculate drift rate (ms per second)
        time_elapsed = t1 - t0
        offset_change = offset1 - offset0
        drift_rate = (offset_change / time_elapsed) * 1000  # ms per second
        
        return drift_rate, offset0 * 1000, offset1 * 1000
    
    def calculate_statistics(self, ip: str) -> Optional[Dict]:
        """
        Calculate statistical measures for a host's time offset.
        
        Args:
            ip: IP address to analyze
            
        Returns:
            Dictionary with mean, std dev, min, max of offsets
        """
        offsets = [m[ip] for m in self.measurements if ip in m and m[ip] is not None]
        
        if len(offsets) < 2:
            return None
        
        offsets_ms = [o * 1000 for o in offsets]
        
        return {
            "mean": statistics.mean(offsets_ms),
            "stdev": statistics.stdev(offsets_ms) if len(offsets_ms) > 1 else 0,
            "min": min(offsets_ms),
            "max": max(offsets_ms),
            "range": max(offsets_ms) - min(offsets_ms),
            "count": len(offsets_ms)
        }
    
    def run_monitoring(self):
        """
        Run the monitoring session.
        """
        print("=" * 70)
        print("⏱️  CLOCK DRIFT MONITORING")
        print("=" * 70)
        print(f"Hosts: {', '.join(self.ips)}")
        print(f"Duration: {self.duration} seconds")
        print(f"Samples: {self.samples}")
        print(f"Interval: {self.interval:.1f} seconds")
        print("=" * 70)
        print()
        
        try:
            for i in range(self.samples):
                sample = self.take_sample(i + 1)
                self.measurements.append(sample)
                
                if i < self.samples - 1:
                    time.sleep(self.interval)
                print()
            
        except KeyboardInterrupt:
            print("\n⚠️  Monitoring interrupted by user")
            if len(self.measurements) < 2:
                print("Not enough samples collected for analysis.")
                return
    
    def analyze_drift(self):
        """
        Analyze the collected measurements and report drift.
        """
        if len(self.measurements) < 2:
            print("❌ Not enough samples collected for drift analysis")
            return
        
        print("=" * 70)
        print("📊 DRIFT ANALYSIS")
        print("=" * 70)
        
        monitoring_duration = self.measurements[-1]["timestamp"] - self.measurements[0]["timestamp"]
        print(f"Monitoring duration: {monitoring_duration:.1f} seconds")
        print(f"Samples collected: {len(self.measurements)}")
        print()
        
        # Analyze each host
        drift_results = {}
        
        for ip in self.ips:
            print(f"🖥️  {ip}")
            print("-" * 70)
            
            # Calculate drift
            drift_result = self.calculate_drift(ip)
            if drift_result is None:
                print("  ❌ Insufficient data for analysis")
                print()
                continue
            
            drift_rate, initial_offset, final_offset = drift_result
            drift_results[ip] = drift_rate
            
            # Calculate statistics
            stats = self.calculate_statistics(ip)
            
            print(f"  Initial offset: {initial_offset:+.2f} ms")
            print(f"  Final offset:   {final_offset:+.2f} ms")
            print(f"  Change:         {final_offset - initial_offset:+.2f} ms")
            print(f"  Drift rate:     {drift_rate:+.3f} ms/sec")
            print()
            
            if stats:
                print(f"  Statistics over {stats['count']} samples:")
                print(f"    Mean offset: {stats['mean']:+.2f} ms")
                print(f"    Std dev:     {stats['stdev']:.2f} ms")
                print(f"    Range:       {stats['range']:.2f} ms ({stats['min']:+.2f} to {stats['max']:+.2f})")
            
            # Interpretation
            print()
            print("  Interpretation:")
            abs_drift = abs(drift_rate)
            if abs_drift < 0.01:
                print("    ✅ Excellent - negligible drift")
            elif abs_drift < 0.1:
                print("    ✓ Good - minimal drift")
            elif abs_drift < 1.0:
                print("    ⚠️  Warning - noticeable drift")
            else:
                print("    ❌ Critical - significant drift detected")
                print("       Consider checking NTP configuration!")
            
            # Project drift over time
            drift_per_minute = drift_rate * 60
            drift_per_hour = drift_rate * 3600
            print(f"    Projected drift: {drift_per_minute:+.1f} ms/min, {drift_per_hour:+.1f} ms/hour")
            
            print()
        
        # Compare drifts between hosts
        if len(drift_results) > 1:
            print("=" * 70)
            print("🔄 RELATIVE DRIFT ANALYSIS")
            print("=" * 70)
            
            ips_with_drift = list(drift_results.keys())
            reference_ip = ips_with_drift[0]
            reference_drift = drift_results[reference_ip]
            
            print(f"Using {reference_ip} as reference (drift: {reference_drift:+.3f} ms/sec)")
            print()
            
            max_relative_drift = 0.0
            for ip in ips_with_drift[1:]:
                relative_drift = drift_results[ip] - reference_drift
                max_relative_drift = max(max_relative_drift, abs(relative_drift))
                
                status = "✓" if abs(relative_drift) < 0.1 else "⚠️"
                print(f"  {status} {ip}: {relative_drift:+.3f} ms/sec")
            
            print()
            print(f"Maximum relative drift: {max_relative_drift:.3f} ms/sec")
            
            if max_relative_drift < 0.1:
                print("✅ All clocks drifting together (good for relative timing)")
            else:
                print("⚠️  Clocks drifting apart (may cause TDMA slot conflicts)")
        
        print("=" * 70)
    
    def save_results(self, filename: str = "clock_drift_results.json"):
        """
        Save the measurements to a JSON file.
        
        Args:
            filename: Output filename
        """
        with open(filename, 'w') as f:
            json.dump(self.measurements, f, indent=2)
        print(f"\n💾 Measurements saved to: {filename}")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Monitor clock drift across multiple payloads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor default payloads for 60 seconds with 10 samples
  python3 clock_drift_monitor.py
  
  # Monitor for 5 minutes with 30 samples
  python3 clock_drift_monitor.py --duration 300 --samples 30
  
  # Monitor specific IPs
  python3 clock_drift_monitor.py --ips 10.19.30.100 10.19.30.101
  
  # Quick test (30 seconds, 5 samples)
  python3 clock_drift_monitor.py --duration 30 --samples 5
        """
    )
    
    parser.add_argument(
        '--ips',
        nargs='+',
        default=ClockDriftMonitor.DEFAULT_IPS,
        help='List of IP addresses to monitor (default: 10.19.30.100-104)'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Monitoring duration in seconds (default: 60)'
    )
    
    parser.add_argument(
        '--samples',
        type=int,
        default=10,
        help='Number of samples to take (default: 10)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Save measurements to JSON file'
    )
    
    args = parser.parse_args()
    
    if args.samples < 2:
        print("Error: Need at least 2 samples for drift analysis", file=sys.stderr)
        sys.exit(1)
    
    try:
        monitor = ClockDriftMonitor(args.ips, args.duration, args.samples)
        monitor.run_monitoring()
        monitor.analyze_drift()
        
        if args.output:
            monitor.save_results(args.output)
        
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
