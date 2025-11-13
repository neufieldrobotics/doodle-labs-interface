# Time Synchronization Diagnostic Tools

This directory contains diagnostic tools to help debug time synchronization and communication issues in the NeuROAM multi-robot system using Doodle Labs radios.

## Overview

For Time Division Multiple Access (TDMA) schemes to work correctly, all payloads must have synchronized clocks. Even small time differences can cause slot timing conflicts and communication issues.

## Tools

### 1. `quick_diag.py` - Quick System Health Check

**Purpose:** Rapid diagnostics to identify common configuration issues.

**What it checks:**
- Network connectivity (ping test)
- SSH accessibility
- Hostname identification
- NTP/Chrony service status
- System clock synchronization status
- Timezone configuration
- ROS daemon status

**Usage:**
```bash
# Check all default payloads (10.19.30.100-104)
./quick_diag.py

# Check specific payloads
./quick_diag.py --ips 10.19.30.100 10.19.30.101

# Run checks sequentially (slower but easier to read)
./quick_diag.py --sequential
```

**When to use:** Run this first to identify basic configuration problems before diving into detailed time sync analysis.

---

### 2. `time_sync_checker.py` - Time Synchronization Checker

**Purpose:** Check if all payloads have synchronized system time and ROS time.

**What it checks:**
- System time on each payload
- ROS time (if ROS is running)
- Time differences between payloads
- NTP synchronization status

**Usage:**
```bash
# Check all default payloads
./time_sync_checker.py

# Check with custom threshold (50ms instead of default 100ms)
./time_sync_checker.py --threshold 0.05

# Check specific payloads
./time_sync_checker.py --ips 10.19.30.100 10.19.30.101 10.19.30.102

# Save results to JSON file
./time_sync_checker.py --output sync_results.json

# Continuous monitoring mode (check every 10 seconds)
./time_sync_checker.py --continuous --interval 10
```

**Interpreting results:**
- ✅ PASS: All clocks within threshold
- ⚠️ WARN: Time spread exceeds threshold
- Check the time spread value - anything under 10ms is excellent for TDMA
- Look for individual payloads with large offsets

**Exit codes:**
- 0: All systems synchronized
- 1: Synchronization issues detected

---

### 3. `clock_drift_monitor.py` - Clock Drift Monitor

**Purpose:** Monitor how clock differences change over time to identify drift issues.

**What it measures:**
- Initial time offset for each payload
- Final time offset after monitoring period
- Drift rate (ms per second)
- Statistical analysis of time stability

**Usage:**
```bash
# Monitor for 60 seconds with 10 samples (default)
./clock_drift_monitor.py

# Quick test: 30 seconds, 5 samples
./clock_drift_monitor.py --duration 30 --samples 5

# Detailed monitoring: 5 minutes, 30 samples
./clock_drift_monitor.py --duration 300 --samples 30

# Monitor specific payloads
./clock_drift_monitor.py --ips 10.19.30.100 10.19.30.101

# Save measurements for later analysis
./clock_drift_monitor.py --output drift_data.json
```

**Interpreting drift rates:**
- < 0.01 ms/sec: Excellent (negligible drift)
- 0.01-0.1 ms/sec: Good (minimal drift)
- 0.1-1.0 ms/sec: Warning (noticeable drift)
- > 1.0 ms/sec: Critical (significant drift, check NTP!)

**Important:** Look at relative drift between payloads. If all clocks drift together at similar rates, TDMA timing remains intact. If they drift apart, slot conflicts will occur.

---

## Typical Diagnostic Workflow

### Step 1: Quick Health Check
```bash
./quick_diag.py
```
This identifies basic issues like:
- Network connectivity problems
- SSH configuration issues
- NTP service not running
- Timezone mismatches

### Step 2: Check Current Synchronization
```bash
./time_sync_checker.py
```
This tells you if clocks are currently aligned within acceptable limits.

### Step 3: Monitor for Drift (if needed)
```bash
./clock_drift_monitor.py --duration 120 --samples 20
```
Run this if you suspect clocks are drifting apart over time.

---

## Common Issues and Solutions

### Issue: Large time spread (> 100ms)

**Possible causes:**
- NTP not running on some payloads
- No network access to NTP servers
- System clock not set to sync with NTP

**Solutions:**
```bash
# On affected payload, check NTP status
systemctl status chronyd

# If not running, start it
systemctl start chronyd
systemctl enable chronyd

# Check NTP sources
chronyc sources

# Force immediate sync
chronyc makestep
```

### Issue: Clocks drifting apart over time

**Possible causes:**
- Poor NTP configuration
- Hardware clock issues
- Network issues preventing NTP updates

**Solutions:**
```bash
# Check NTP tracking
chronyc tracking

# Verify NTP servers are reachable
chronyc sources -v

# Check system logs
journalctl -u chronyd -n 50
```

### Issue: ROS time not available

**Possible causes:**
- ROS not running
- ROS daemon not started

**Solutions:**
```bash
# Start ROS daemon
ros2 daemon start

# Verify ROS is working
ros2 node list
```

### Issue: Different timezones

**Possible causes:**
- Inconsistent system configuration

**Solutions:**
```bash
# Set timezone (all payloads should match)
timedatectl set-timezone UTC  # or America/New_York, etc.

# Verify
timedatectl status
```

---

## Understanding TDMA Requirements

For successful TDMA operation:

1. **Absolute sync < 10ms**: All payloads should be within 10ms of each other
2. **Low drift rate**: Clocks should drift together (< 0.1 ms/sec relative drift)
3. **Consistent updates**: NTP should update regularly (check with `chronyc tracking`)

---

## Requirements

These scripts require:
- Python 3.6+
- SSH access to all payloads (password-less recommended)
- Standard Linux utilities: `ping`, `ssh`, `date`
- Optional: `timedatectl`, `chronyc`, or `ntpq` for NTP diagnostics

---

## Tips for Best Results

1. **Run from a stable host**: Run these tools from a payload or ground station with stable connectivity
2. **Check at different times**: Run checks during both idle and high-traffic periods
3. **Monitor periodically**: Use continuous mode during long operations
4. **Document baselines**: Save results when system is working well for comparison
5. **Check after changes**: Re-run diagnostics after any NTP or network configuration changes

---

## Troubleshooting the Scripts

### SSH connection issues
If scripts can't connect via SSH:
```bash
# Test manual SSH
ssh root@10.19.30.100

# Check SSH keys
ssh-add -l

# Add key if needed
ssh-add ~/.ssh/id_rsa
```

### Timeout issues
If checks are timing out, you may have network congestion:
```bash
# Check network latency
ping -c 10 10.19.30.100

# Try with fewer parallel checks
./quick_diag.py --sequential
```

---

## Integration with Existing Monitor

These diagnostic scripts complement the existing `monitor_node.py` and `optimized_payload_monitor.py`:

- `monitor_node.py`: Monitors link state from Doodle Labs radios
- `optimized_payload_monitor.py`: Monitors payload-to-payload communication
- **These diagnostic scripts**: Verify time synchronization, which is fundamental for TDMA

Run these diagnostics when you see unexplained communication failures or timing-related errors.

---

## Further Reading

- [Chrony documentation](https://chrony.tuxfamily.org/doc/4.0/chrony.conf.html)
- [NTP Best Practices](https://www.ntp.org/documentation/4.2.8-series/prefer/)
- [PTP for sub-millisecond sync](https://en.wikipedia.org/wiki/Precision_Time_Protocol)
