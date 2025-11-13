# NeuROAM Time Synchronization Diagnostic Tools

Diagnostic tools for debugging time synchronization and TDMA communication issues in the NeuROAM multi-robot system with Doodle Labs radios.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Available Tools](#available-tools)
- [Common Workflows](#common-workflows)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   ./install_dependencies.sh
   ```

2. **Run quick diagnostic:**
   ```bash
   ./quick_diag.py
   ```

3. **If issues found, see detailed docs:**
   - [QUICKSTART.md](QUICKSTART.md) - Basic usage guide
   - [DIAGNOSTICS.md](DIAGNOSTICS.md) - Comprehensive diagnostic guide

## 📦 Installation

### Automatic Installation

```bash
cd /path/to/NeuROAM/src/doodle-labs-interface/diagnostics
./install_dependencies.sh
```

### Manual Installation

If you prefer to install manually:

```bash
sudo apt-get update
sudo apt-get install sshpass
```

## 🛠️ Available Tools

### 1. `quick_diag.py` - System Health Check

Quick diagnostic to identify basic configuration issues.

```bash
./quick_diag.py                    # Check all payloads (100-104)
./quick_diag.py --ips 10.19.30.100 # Check specific payload
./quick_diag.py --sequential       # Run checks one at a time
```

**Checks:**
- ✓ Network connectivity (ping)
- ✓ SSH accessibility
- ✓ NTP service status
- ✓ Time synchronization
- ✓ Timezone configuration
- ✓ ROS daemon status

### 2. `time_sync_checker.py` - Time Synchronization Check

Detailed analysis of time synchronization between payloads.

```bash
./time_sync_checker.py                           # Basic check
./time_sync_checker.py --threshold 0.05          # 50ms threshold
./time_sync_checker.py --continuous --interval 5 # Monitor every 5 sec
./time_sync_checker.py --output results.json     # Save results
```

**Features:**
- Measures system time differences
- Measures ROS time differences  
- Compares against configurable threshold (default 100ms)
- Continuous monitoring mode
- JSON output for analysis

### 3. `clock_drift_monitor.py` - Clock Drift Analysis

Monitor how clocks drift apart over time.

```bash
./clock_drift_monitor.py                              # 60 sec, 10 samples
./clock_drift_monitor.py --duration 30 --samples 5    # Quick test
./clock_drift_monitor.py --duration 300 --samples 30  # Detailed analysis
./clock_drift_monitor.py --output drift.json          # Save data
```

**Features:**
- Measures drift rate (ms/sec)
- Statistical analysis (mean, std dev, range)
- Relative drift between payloads
- Drift projection over time

### 4. `run_full_diagnostics.sh` - Complete Test Suite

Runs all three diagnostic phases in sequence.

```bash
./run_full_diagnostics.sh                    # Full test
./run_full_diagnostics.sh --quick            # Skip drift monitoring
./run_full_diagnostics.sh --save results/    # Save all outputs
```

### 5. `setup_ssh.sh` - SSH Configuration Helper

Test and set up SSH connectivity to payloads.

```bash
./setup_ssh.sh                 # Test connectivity
./setup_ssh.sh --setup-keys    # Set up SSH keys
```

## 🔄 Common Workflows

### First-Time Setup

```bash
# 1. Install dependencies
./install_dependencies.sh

# 2. Test SSH connectivity
./setup_ssh.sh

# 3. Run quick diagnostic
./quick_diag.py

# 4. If all good, run full suite
./run_full_diagnostics.sh
```

### Daily Operation Check

```bash
# Quick health check before mission
./quick_diag.py

# If warnings appear, investigate with:
./time_sync_checker.py
```

### Debugging Time Sync Issues

```bash
# 1. Identify problem hosts
./quick_diag.py

# 2. Check current sync status
./time_sync_checker.py

# 3. Monitor for drift
./clock_drift_monitor.py --duration 120 --samples 20

# 4. Save results for analysis
./time_sync_checker.py --output sync_$(date +%Y%m%d_%H%M%S).json
```

### Continuous Monitoring

```bash
# Monitor time sync every 10 seconds
./time_sync_checker.py --continuous --interval 10

# Or run periodic checks with cron (every 5 minutes)
*/5 * * * * cd /path/to/diagnostics && ./time_sync_checker.py --output /var/log/time_sync_$(date +\%H\%M).json
```

## 🐛 Troubleshooting

### SSH Connection Failed

**Symptom:**
```
❌ Ping succeeded but SSH failed
```

**Solutions:**

1. **Check credentials:**
   ```bash
   ./quick_diag.py --username neuroam --password neuroam
   ```

2. **Test SSH manually:**
   ```bash
   sshpass -p neuroam ssh neuroam@10.19.30.100 'echo OK'
   ```

3. **Check SSH service on payload:**
   ```bash
   ssh neuroam@10.19.30.100 'systemctl status sshd'
   ```

### Time Not Synchronized

**Symptom:**
```
⚠️ NTP service: chronyd (inactive)
⚠️ Time not synced
```

**Solutions:**

```bash
# On each payload:
ssh neuroam@10.19.30.100

# Start NTP service
sudo systemctl start chronyd
sudo systemctl enable chronyd

# Force immediate sync
sudo chronyc makestep

# Verify
chronyc tracking
```

### Large Time Spread

**Symptom:**
```
⚠️ WARN: Time spread (150.00 ms) exceeds threshold (100.00 ms)
```

**Immediate fix:**
```bash
# Force sync on all payloads
for ip in 10.19.30.{100..104}; do
    sshpass -p neuroam ssh neuroam@$ip 'sudo chronyc makestep'
done

# Verify
./time_sync_checker.py
```

**Long-term fix:**
- Ensure NTP servers are reachable from all payloads
- Configure same NTP servers on all payloads
- Consider using PTP for sub-millisecond synchronization

### sshpass Not Found

**Symptom:**
```
⚠️ Warning: sshpass not found
```

**Solution:**
```bash
./install_dependencies.sh
# Or manually:
sudo apt-get install sshpass
```

## 📚 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started quickly with basic usage
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Comprehensive diagnostic guide with detailed explanations
- **[ssh_helper.py](ssh_helper.py)** - Common SSH utilities (for developers)

## 🔧 Authentication

All scripts support password and key-based authentication:

**Default credentials:**
- Username: `neuroam`
- Password: `neuroam`

**Custom credentials:**
```bash
./quick_diag.py --username myuser --password mypass
```

**Key-based auth:**
```bash
# Set up keys (one-time)
./setup_ssh.sh --setup-keys

# Then scripts will use keys automatically
./quick_diag.py
```

## 📊 Understanding Results

### Time Sync Thresholds

| Threshold | Quality | Notes |
|-----------|---------|-------|
| < 1 ms    | Excellent | Ideal for TDMA |
| 1-10 ms   | Good | Acceptable for most TDMA |
| 10-100 ms | Fair | May cause issues |
| > 100 ms  | Poor | TDMA will likely fail |

### Drift Rates

| Drift Rate | Status | Action |
|------------|--------|--------|
| < 0.01 ms/sec | Excellent | None needed |
| 0.01-0.1 ms/sec | Good | Monitor |
| 0.1-1.0 ms/sec | Warning | Check NTP config |
| > 1.0 ms/sec | Critical | Fix NTP immediately |

## 🤝 Integration

These diagnostic tools complement the existing monitoring system:

- **monitor_node.py**: Monitors Doodle Labs radio link state
- **optimized_payload_monitor.py**: Monitors payload communications
- **These tools**: Verify time synchronization (fundamental for TDMA)

Run diagnostics when you see unexplained communication failures or timing errors.

## 🔄 Updates & Maintenance

**Check for issues after:**
- System updates
- Network configuration changes
- Adding/removing payloads
- Power cycles
- Long downtimes

**Regular maintenance:**
```bash
# Weekly check
./quick_diag.py

# Monthly detailed analysis
./run_full_diagnostics.sh --save results_$(date +%Y%m%d)/
```

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review [DIAGNOSTICS.md](DIAGNOSTICS.md) for detailed help
3. Save diagnostic output: `./quick_diag.py > diagnostic_output.txt`
4. Contact the NeuROAM team with the output

## 🔐 Security Note

These scripts store passwords in command-line arguments by default for convenience. For production use:

1. Set up SSH keys: `./setup_ssh.sh --setup-keys`
2. Use environment variables for passwords
3. Restrict access to diagnostic directory

---

**Last Updated:** November 13, 2025  
**Maintained by:** NeuROAM Team
