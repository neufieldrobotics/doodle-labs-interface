# Quick Start Guide - Time Sync Diagnostics

## Prerequisites

1. **Install sshpass** (for password authentication):
   ```bash
   sudo apt-get update
   sudo apt-get install sshpass
   ```

2. **Make scripts executable** (if not already):
   ```bash
   chmod +x *.py *.sh
   ```

## Basic Usage

### Quick Health Check (Recommended First Step)

Run this first to verify basic connectivity and configuration:

```bash
./quick_diag.py
```

By default, this uses:
- **Username**: `neuroam`
- **Password**: `neuroam`
- **IPs**: `10.19.30.100-104`

### With Custom Credentials

If you need different credentials:

```bash
./quick_diag.py --username myuser --password mypass
```

### Check Specific Payloads

```bash
./quick_diag.py --ips 10.19.30.100 10.19.30.101
```

## Common Issues

### Issue: "sshpass not found"

**Solution:**
```bash
sudo apt-get install sshpass
```

### Issue: "SSH failed" but can SSH manually

**Cause**: Scripts may be using wrong username/password

**Solution**: Specify credentials explicitly:
```bash
./quick_diag.py --username neuroam --password neuroam
```

### Issue: Permission denied

**Cause**: Wrong password or SSH keys conflict

**Solutions**:
1. Verify password is correct
2. Try removing conflicting SSH keys:
   ```bash
   ssh-keygen -R 10.19.30.100
   ```

## Full Diagnostic Suite

Once quick_diag passes, run the complete test:

```bash
./run_full_diagnostics.sh
```

This will run all three diagnostic phases:
1. Quick health check
2. Time synchronization check
3. Clock drift monitoring

## Testing Individual Scripts

### Time Sync Checker
```bash
./time_sync_checker.py --username neuroam --password neuroam
```

### Clock Drift Monitor
```bash
./clock_drift_monitor.py --username neuroam --password neuroam --duration 30 --samples 5
```

## Expected Output

### ✅ Good Result
```
🏥 QUICK DIAGNOSTICS
======================================================================
Checking 5 host(s)...

🔍 Diagnosing 10.19.30.100...
  ✓ Ping (2.3 ms)
  ✓ SSH accessible
  ℹ️  Hostname: payload0
  ✓ NTP service: chronyd (active)
  ✓ Time synchronized
  ...

📋 SUMMARY
======================================================================
📊 Status Overview:
  Reachable (ping):     5/5
  SSH accessible:       5/5
  NTP active:           5/5
  Time synchronized:    5/5
  ROS daemon running:   5/5

✅ No major issues detected!
```

### ⚠️ Problem Example
```
🔍 Diagnosing 10.19.30.100...
  ✓ Ping (2.3 ms)
  ❌ SSH failed
```
**Solution**: Check username/password or SSH service on payload

## Tips

1. **Run from a stable host** - Run these from a robot or ground station with good connectivity
2. **Check during different loads** - Run during idle and during high network traffic
3. **Save results** - Use `--output` to save results for comparison:
   ```bash
   ./time_sync_checker.py --output baseline.json
   ```
4. **Continuous monitoring** - Use continuous mode to watch for intermittent issues:
   ```bash
   ./time_sync_checker.py --continuous --interval 10
   ```

## Troubleshooting Command

Quick one-liner to test SSH:
```bash
sshpass -p neuroam ssh -o StrictHostKeyChecking=no neuroam@10.19.30.100 'echo "SSH OK"'
```

If this works, the scripts should work too!
