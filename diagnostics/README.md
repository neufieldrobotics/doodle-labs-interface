# NeuROAM Time Synchronization Diagnostic Tools

Diagnostic tools for debugging time synchronization and TDMA communication issues in the NeuROAM multi-robot system with Doodle Labs radios.

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Available Tools](#-available-tools)
- [Usage Examples](#-usage-examples)
- [Understanding Results](#-understanding-results)
- [Troubleshooting](#-troubleshooting)
- [Common Workflows](#-common-workflows)
- [TDMA Requirements](#-tdma-requirements)
- [Integration & Maintenance](#-integration--maintenance)

## 🚀 Quick Start

### First Time Setup

```bash
# 1. Install sshpass (required for password authentication)
./install_dependencies.sh

# 2. Run quick diagnostic
./quick_diag.py
```

**Default credentials:** `neuroam` / `neuroam` for IPs `10.19.30.100-104`

### Quick Test

```bash
# Test SSH connectivity manually
sshpass -p neuroam ssh -o StrictHostKeyChecking=no neuroam@10.19.30.100 'echo "SSH OK"'

# If that works, run diagnostics
./quick_diag.py
```

## 📦 Installation

**Required:** `sshpass` for password authentication

```bash
# Automatic (recommended)
./install_dependencies.sh

# Or manual
sudo apt-get update && sudo apt-get install -y sshpass
```

**Alternative:** Set up SSH keys to avoid needing sshpass:
```bash
./setup_ssh.sh --setup-keys
```

## 🛠️ Available Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **`quick_diag.py`** | Fast health check (ping, SSH, NTP, timezone, ROS) | Run first, before missions |
| **`time_sync_checker.py`** | Measure time sync between payloads | When time issues suspected |
| **`clock_drift_monitor.py`** | Monitor clock drift over time | Deep dive into sync problems |
| **`run_full_diagnostics.sh`** | Run all checks in sequence | Complete system analysis |
| **`setup_ssh.sh`** | Test/setup SSH connectivity | Initial setup or SSH issues |

### Authentication Options

All scripts default to `neuroam`/`neuroam`. Override with:
```bash
./quick_diag.py --username USER --password PASS
```

Or use SSH keys (no password needed):
```bash
./setup_ssh.sh --setup-keys
./quick_diag.py  # Will use keys automatically
```

## � Usage Examples

### Basic Commands

```bash
# Quick health check (recommended first step)
./quick_diag.py

# Check specific payloads only
./quick_diag.py --ips 10.19.30.100 10.19.30.101

# Check time synchronization
./time_sync_checker.py

# Use stricter threshold (50ms instead of 100ms)
./time_sync_checker.py --threshold 0.05

# Monitor clock drift (quick 30-second test)
./clock_drift_monitor.py --duration 30 --samples 5

# Run complete diagnostic suite
./run_full_diagnostics.sh

# Save all results
./run_full_diagnostics.sh --save results_$(date +%Y%m%d)/
```

### Continuous Monitoring

```bash
# Monitor time sync every 10 seconds (Ctrl+C to stop)
./time_sync_checker.py --continuous --interval 10

# Or use cron for periodic checks (every 5 minutes)
*/5 * * * * cd /path/to/diagnostics && ./time_sync_checker.py --output /var/log/time_sync.json
```

### Custom Credentials

```bash
# All scripts support custom credentials
./quick_diag.py --username myuser --password mypass
./time_sync_checker.py --username admin --password secret
```

## 🐛 Troubleshooting

### Problem: SSH Connection Failed

```
❌ Ping succeeded but SSH failed
```

**Solutions (try in order):**

1. **Verify credentials:**
   ```bash
   ./quick_diag.py --username neuroam --password neuroam
   ```

2. **Test manually:**
   ```bash
   sshpass -p neuroam ssh -o StrictHostKeyChecking=no neuroam@10.19.30.100 'echo OK'
   ```

3. **Check SSH service:**
   ```bash
   ssh neuroam@10.19.30.100 'systemctl status sshd'
   ```

4. **Remove conflicting keys:**
   ```bash
   ssh-keygen -R 10.19.30.100
   ```

---

### Problem: sshpass Not Found

```
⚠️ Warning: sshpass not found
```

**Solution:**
```bash
./install_dependencies.sh
```

---

### Problem: Time Not Synchronized

```
⚠️ NTP service: chronyd (inactive)
```

**Fix on affected payload:**
```bash
ssh neuroam@10.19.30.100
sudo systemctl start chronyd
sudo systemctl enable chronyd
sudo chronyc makestep
chronyc tracking  # Verify
```

---

### Problem: Large Time Spread

```
⚠️ WARN: Time spread (150.00 ms) exceeds threshold
```

**Quick fix (force sync all payloads):**
```bash
for ip in 10.19.30.{100..104}; do
    sshpass -p neuroam ssh neuroam@$ip 'sudo chronyc makestep'
done
./time_sync_checker.py  # Verify
```

**Long-term fixes:**
- Ensure NTP servers are reachable from all payloads
- Configure same NTP servers on all payloads  
- Use PTP for sub-millisecond sync if needed

---

### Problem: Different Timezones

```
⚠️ Multiple timezones detected
```

**Fix (set all to UTC):**
```bash
for ip in 10.19.30.{100..104}; do
    sshpass -p neuroam ssh neuroam@$ip 'sudo timedatectl set-timezone UTC'
done
```

---

### Problem: Clocks Drifting Apart

**Check NTP health:**
```bash
ssh neuroam@10.19.30.100
chronyc tracking    # Check sync status
chronyc sources -v  # Check NTP servers
journalctl -u chronyd -n 50  # Check logs
```

## � Common Workflows

### First-Time Setup
```bash
./install_dependencies.sh  # Install sshpass
./setup_ssh.sh            # Test connectivity
./quick_diag.py           # Verify everything works
./run_full_diagnostics.sh # Complete analysis
```

### Daily Pre-Mission Check
```bash
./quick_diag.py  # Quick health check
# If all green, you're good to go!
```

### Debugging Time Sync Issues
```bash
./quick_diag.py                              # 1. Identify problems
./time_sync_checker.py                       # 2. Measure sync
./clock_drift_monitor.py --duration 120      # 3. Check drift
./time_sync_checker.py --output results.json # 4. Save for analysis
```

### Post-Problem Resolution
```bash
# After fixing NTP/network issues
./time_sync_checker.py  # Verify sync is good
# Wait 5 minutes, then:
./clock_drift_monitor.py --duration 60  # Confirm drift is minimal
```

## 📊 Understanding Results

### Time Sync Quality Guide

| Time Spread | Status | Impact on TDMA | Action |
|------------|--------|----------------|--------|
| < 1 ms | ✅ Excellent | Perfect for TDMA | None |
| 1-10 ms | ✅ Good | Works well | Monitor |
| 10-100 ms | ⚠️ Fair | May cause issues | Investigate |
| > 100 ms | ❌ Poor | TDMA will fail | Fix immediately |

### Clock Drift Rates

| Drift Rate (ms/sec) | Status | Action Required |
|---------------------|--------|-----------------|
| < 0.01 | ✅ Excellent | None |
| 0.01-0.1 | ✅ Good | Continue monitoring |
| 0.1-1.0 | ⚠️ Warning | Check NTP config |
| > 1.0 | ❌ Critical | Fix NTP now |

**Key Insight:** If all clocks drift together at similar rates, TDMA stays synchronized. If they drift apart, slot conflicts occur.

### Sample Output

#### ✅ Good Result
```
🏥 QUICK DIAGNOSTICS
======================================================================
📊 Status Overview:
  Reachable (ping):     5/5
  SSH accessible:       5/5
  NTP active:           5/5
  Time synchronized:    5/5
  ROS daemon running:   5/5

✅ No major issues detected!
```

#### ⚠️ Problem Detected
```
🔍 Diagnosing 10.19.30.100...
  ✓ Ping (2.3 ms)
  ❌ SSH failed

⚠️ Issues Found:
  1. SSH issues: 10.19.30.100
```
**Action:** Check username/password or SSH service on payload

## 🎯 TDMA Requirements

For successful TDMA operation, you need:

1. **Absolute sync < 10ms** - All payloads within 10ms of each other
2. **Low drift rate** - Clocks drift together (< 0.1 ms/sec relative drift)  
3. **Consistent NTP updates** - Check with `chronyc tracking`

**Why this matters:** Manual time-division schemes require precise timing. Even small time differences can cause slot timing conflicts and packet collisions.

---

## 🤝 Integration & Maintenance

### Integration with Existing Monitor

These tools complement your existing monitoring:

| Component | Purpose |
|-----------|---------|
| `monitor_node.py` | Monitors Doodle Labs radio link state |
| `optimized_payload_monitor.py` | Monitors payload communications |
| **These diagnostics** | Verify time sync (fundamental for TDMA) |

**When to run:** Use these diagnostics when you see unexplained communication failures or timing-related errors.

### Regular Maintenance Schedule

```bash
# Before each mission
./quick_diag.py

# Weekly monitoring
./quick_diag.py

# Monthly deep dive
./run_full_diagnostics.sh --save results_$(date +%Y%m%d)/

# After system changes
./run_full_diagnostics.sh  # Any time you update/reboot systems
```

### Check After These Events
- System updates
- Network configuration changes
- Adding/removing payloads
- Power cycles or reboots
- Long downtimes (> 1 week)

---

## 📞 Support & Security

### Getting Help

1. Check [Troubleshooting](#-troubleshooting) section above
2. Save diagnostic output: `./quick_diag.py > output.txt`
3. Contact NeuROAM team with output

### Security Notes

**⚠️ Password in command-line:** For convenience, these scripts accept passwords as arguments. For production:

1. **Use SSH keys (recommended):**
   ```bash
   ./setup_ssh.sh --setup-keys
   ```

2. **Use environment variables:**
   ```bash
   export SSH_PASS=neuroam
   ./quick_diag.py --password "$SSH_PASS"
   ```

3. **Restrict access:**
   ```bash
   chmod 700 /path/to/diagnostics
   ```

---

## 📝 Quick Reference Card

```bash
# INSTALLATION
./install_dependencies.sh

# BASIC CHECKS
./quick_diag.py                          # Health check
./time_sync_checker.py                   # Time sync status
./clock_drift_monitor.py --duration 30   # Quick drift test

# CUSTOM OPTIONS
./quick_diag.py --username USER --password PASS
./quick_diag.py --ips 10.19.30.100 10.19.30.101
./time_sync_checker.py --threshold 0.05
./time_sync_checker.py --continuous --interval 10

# COMPLETE SUITE
./run_full_diagnostics.sh
./run_full_diagnostics.sh --save results/

# TROUBLESHOOTING
./setup_ssh.sh                           # Test SSH
sshpass -p neuroam ssh neuroam@10.19.30.100 'echo OK'
./install_dependencies.sh                # Install sshpass
```

---

**Last Updated:** November 13, 2025 | **Maintained by:** NeuROAM Team
