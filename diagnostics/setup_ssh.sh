#!/bin/bash
# SSH Setup and Connectivity Test for Payloads
# Helps set up password-less SSH access to all payloads

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default payload IPs
DEFAULT_IPS="10.19.30.100 10.19.30.101 10.19.30.102 10.19.30.103 10.19.30.104"
IPS="$DEFAULT_IPS"
USERNAME="root"
SETUP_KEYS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ips)
            shift
            IPS=""
            while [[ $# -gt 0 ]] && [[ ! $1 =~ ^-- ]]; do
                IPS="$IPS $1"
                shift
            done
            ;;
        --user)
            USERNAME="$2"
            shift 2
            ;;
        --setup-keys)
            SETUP_KEYS=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Test SSH connectivity and optionally set up SSH keys"
            echo ""
            echo "Options:"
            echo "  --ips IP1 IP2 ...   List of IPs to check (default: 10.19.30.100-104)"
            echo "  --user USERNAME     SSH username (default: root)"
            echo "  --setup-keys        Copy SSH keys to remote hosts"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # Test connectivity"
            echo "  $0 --setup-keys                 # Set up SSH keys"
            echo "  $0 --ips 10.19.30.100           # Test single host"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              SSH CONNECTIVITY TEST & SETUP                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if SSH key exists
if [ ! -f ~/.ssh/id_rsa ] && [ ! -f ~/.ssh/id_ed25519 ]; then
    echo -e "${YELLOW}⚠️  No SSH key found${NC}"
    echo ""
    read -p "Generate new SSH key? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ssh-keygen -t ed25519 -C "neuroam-$(hostname)" -f ~/.ssh/id_ed25519
        echo -e "${GREEN}✓ SSH key generated${NC}"
    else
        echo "Continuing without key generation..."
    fi
    echo ""
fi

# Test connectivity to each host
echo -e "${BLUE}Testing connectivity to ${#IPS[@]} host(s)...${NC}"
echo ""

SUCCESS=0
FAILED=0
FAILED_HOSTS=""

for IP in $IPS; do
    echo -n "Testing ${IP}... "
    
    # Try SSH connection with timeout
    if timeout 3 ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no -o BatchMode=yes "${USERNAME}@${IP}" "echo 'OK'" &>/dev/null; then
        echo -e "${GREEN}✓ OK${NC}"
        ((SUCCESS++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
        FAILED_HOSTS="$FAILED_HOSTS $IP"
    fi
done

echo ""
echo -e "Results: ${GREEN}${SUCCESS} successful${NC}, ${RED}${FAILED} failed${NC}"

# If setup-keys is requested and there were failures
if [ "$SETUP_KEYS" = true ] && [ $FAILED -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}Setting up SSH keys for failed hosts...${NC}"
    echo ""
    
    for IP in $FAILED_HOSTS; do
        echo -e "${BLUE}Setting up key for ${IP}...${NC}"
        
        # Check if ssh-copy-id is available
        if command -v ssh-copy-id &> /dev/null; then
            ssh-copy-id -o ConnectTimeout=5 "${USERNAME}@${IP}"
        else
            # Manual key copy
            echo "ssh-copy-id not found, using manual method..."
            if [ -f ~/.ssh/id_ed25519.pub ]; then
                KEY_FILE=~/.ssh/id_ed25519.pub
            else
                KEY_FILE=~/.ssh/id_rsa.pub
            fi
            
            cat "$KEY_FILE" | ssh -o ConnectTimeout=5 "${USERNAME}@${IP}" \
                "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
        fi
        
        # Test again
        if ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no -o BatchMode=yes "${USERNAME}@${IP}" "echo 'OK'" &>/dev/null; then
            echo -e "${GREEN}✓ Key setup successful for ${IP}${NC}"
        else
            echo -e "${RED}✗ Key setup failed for ${IP}${NC}"
        fi
        echo ""
    done
    
    # Retest all
    echo -e "${BLUE}Retesting all connections...${NC}"
    echo ""
    
    SUCCESS=0
    FAILED=0
    
    for IP in $IPS; do
        echo -n "Testing ${IP}... "
        
        if timeout 3 ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no -o BatchMode=yes "${USERNAME}@${IP}" "echo 'OK'" &>/dev/null; then
            echo -e "${GREEN}✓ OK${NC}"
            ((SUCCESS++))
        else
            echo -e "${RED}✗ FAILED${NC}"
            ((FAILED++))
        fi
    done
    
    echo ""
    echo -e "Final results: ${GREEN}${SUCCESS} successful${NC}, ${RED}${FAILED} failed${NC}"
fi

echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All SSH connections successful!${NC}"
    echo "You can now run the diagnostic scripts."
else
    echo -e "${YELLOW}⚠️  Some connections failed${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Verify hosts are reachable:"
    echo "     ping <IP>"
    echo ""
    echo "  2. Check SSH service is running on remote hosts:"
    echo "     ssh ${USERNAME}@<IP> 'systemctl status sshd'"
    echo ""
    echo "  3. Try manual SSH connection:"
    echo "     ssh ${USERNAME}@<IP>"
    echo ""
    echo "  4. Set up keys with:"
    echo "     $0 --setup-keys"
fi

echo ""

exit $FAILED
