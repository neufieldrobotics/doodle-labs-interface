#!/bin/bash
# Install required dependencies for diagnostic scripts

echo "Installing dependencies for NeuROAM diagnostic tools..."
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    APT_CMD="apt-get"
else
    APT_CMD="sudo apt-get"
fi

# Update package list
echo "📦 Updating package list..."
$APT_CMD update

# Install sshpass
echo ""
echo "📦 Installing sshpass (for SSH password authentication)..."
$APT_CMD install -y sshpass

# Install chrony
echo ""
echo "📦 Installing chrony (for time synchronization)..."
$APT_CMD install -y chrony

# Enable and start chronyd
echo ""
echo "🔧 Enabling and starting chronyd service..."
if [ "$EUID" -eq 0 ]; then
    systemctl enable chronyd
    systemctl start chronyd
else
    sudo systemctl enable chronyd
    sudo systemctl start chronyd
fi

# Verify installation
echo ""
echo "✅ Verifying installation..."
if command -v sshpass &> /dev/null; then
    echo "  ✓ sshpass: $(which sshpass)"
else
    echo "  ❌ sshpass installation failed"
    exit 1
fi

if command -v chronyc &> /dev/null; then
    echo "  ✓ chrony: $(which chronyc)"
    echo "    Status: $(systemctl is-active chronyd)"
else
    echo "  ❌ chrony installation failed"
    exit 1
fi

if command -v python3 &> /dev/null; then
    echo "  ✓ python3: $(which python3)"
else
    echo "  ❌ python3 not found"
    exit 1
fi

echo ""
echo "✅ All dependencies installed successfully!"
echo ""
echo "📌 Note: On remote payloads, you'll need to install chrony separately:"
echo "   for ip in 10.19.30.{100..104}; do"
echo "     sshpass -p neuroam ssh neuroam@\$ip 'sudo apt-get install -y chrony && sudo systemctl enable --now chronyd'"
echo "   done"
echo ""
echo "You can now run the diagnostic scripts:"
echo "  ./quick_diag.py"
echo "  ./time_sync_checker.py"
echo "  ./clock_drift_monitor.py"
echo ""
