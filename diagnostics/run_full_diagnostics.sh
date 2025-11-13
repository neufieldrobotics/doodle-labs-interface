#!/bin/bash
# Complete Time Sync Diagnostic Suite
# Runs all diagnostic tools in sequence for comprehensive analysis

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default settings
IPS="10.19.30.100 10.19.30.101 10.19.30.102 10.19.30.103 10.19.30.104"
DRIFT_DURATION=60
DRIFT_SAMPLES=10
SAVE_RESULTS=false
OUTPUT_DIR=""

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
        --drift-duration)
            DRIFT_DURATION="$2"
            shift 2
            ;;
        --drift-samples)
            DRIFT_SAMPLES="$2"
            shift 2
            ;;
        --save)
            SAVE_RESULTS=true
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --quick)
            # Quick mode: skip drift monitoring
            QUICK_MODE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Run complete time synchronization diagnostics"
            echo ""
            echo "Options:"
            echo "  --ips IP1 IP2 ...       List of IPs to check (default: 10.19.30.100-104)"
            echo "  --drift-duration SEC    Drift monitoring duration (default: 60)"
            echo "  --drift-samples N       Number of drift samples (default: 10)"
            echo "  --save DIR              Save all results to directory"
            echo "  --quick                 Skip drift monitoring (faster)"
            echo "  -h, --help              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Full diagnostics on all payloads"
            echo "  $0 --quick                            # Quick check only"
            echo "  $0 --ips 10.19.30.100 10.19.30.101   # Check specific payloads"
            echo "  $0 --save results/                    # Save all results"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create output directory if saving results
if [ "$SAVE_RESULTS" = true ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_DIR="${OUTPUT_DIR:-time_sync_diagnostics_$TIMESTAMP}"
    mkdir -p "$OUTPUT_DIR"
    echo -e "${BLUE}📁 Results will be saved to: $OUTPUT_DIR${NC}"
    echo ""
fi

# Header
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         TIME SYNCHRONIZATION DIAGNOSTIC SUITE                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Payloads to check:${NC} $IPS"
echo ""
echo "This will run three diagnostic phases:"
echo "  1. Quick health check"
echo "  2. Time synchronization check"
if [ "$QUICK_MODE" != true ]; then
    echo "  3. Clock drift monitoring (${DRIFT_DURATION}s)"
fi
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo ""

# Phase 1: Quick Diagnostics
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}PHASE 1: Quick Health Check${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$SAVE_RESULTS" = true ]; then
    python3 "$SCRIPT_DIR/quick_diag.py" --ips $IPS 2>&1 | tee "$OUTPUT_DIR/01_quick_diag.log"
    PHASE1_RESULT=${PIPESTATUS[0]}
else
    python3 "$SCRIPT_DIR/quick_diag.py" --ips $IPS
    PHASE1_RESULT=$?
fi

echo ""
if [ $PHASE1_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Phase 1 complete${NC}"
else
    echo -e "${YELLOW}⚠ Phase 1 completed with warnings${NC}"
fi
echo ""
read -p "Press Enter to continue to Phase 2..."
echo ""

# Phase 2: Time Sync Check
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}PHASE 2: Time Synchronization Check${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$SAVE_RESULTS" = true ]; then
    python3 "$SCRIPT_DIR/time_sync_checker.py" --ips $IPS --output "$OUTPUT_DIR/02_time_sync.json" 2>&1 | tee "$OUTPUT_DIR/02_time_sync.log"
    PHASE2_RESULT=${PIPESTATUS[0]}
else
    python3 "$SCRIPT_DIR/time_sync_checker.py" --ips $IPS
    PHASE2_RESULT=$?
fi

echo ""
if [ $PHASE2_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Phase 2 complete - Systems synchronized${NC}"
else
    echo -e "${YELLOW}⚠ Phase 2 complete - Synchronization issues detected${NC}"
fi
echo ""

# Phase 3: Drift Monitoring (unless quick mode)
if [ "$QUICK_MODE" != true ]; then
    read -p "Press Enter to continue to Phase 3 (drift monitoring)..."
    echo ""
    
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}PHASE 3: Clock Drift Monitoring${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}This will take ${DRIFT_DURATION} seconds...${NC}"
    echo ""
    
    if [ "$SAVE_RESULTS" = true ]; then
        python3 "$SCRIPT_DIR/clock_drift_monitor.py" --ips $IPS --duration $DRIFT_DURATION --samples $DRIFT_SAMPLES --output "$OUTPUT_DIR/03_drift_data.json" 2>&1 | tee "$OUTPUT_DIR/03_drift_monitor.log"
        PHASE3_RESULT=${PIPESTATUS[0]}
    else
        python3 "$SCRIPT_DIR/clock_drift_monitor.py" --ips $IPS --duration $DRIFT_DURATION --samples $DRIFT_SAMPLES
        PHASE3_RESULT=$?
    fi
    
    echo ""
    if [ $PHASE3_RESULT -eq 0 ]; then
        echo -e "${GREEN}✓ Phase 3 complete${NC}"
    else
        echo -e "${YELLOW}⚠ Phase 3 completed with warnings${NC}"
    fi
fi

# Final Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                      DIAGNOSTIC SUMMARY                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Determine overall status
if [ $PHASE2_RESULT -eq 0 ]; then
    echo -e "${GREEN}✅ OVERALL STATUS: PASS${NC}"
    echo "All systems are synchronized within acceptable limits."
else
    echo -e "${YELLOW}⚠️  OVERALL STATUS: WARNING${NC}"
    echo "Time synchronization issues detected. Review the output above."
    echo ""
    echo "Common fixes:"
    echo "  • Restart NTP service: systemctl restart chronyd"
    echo "  • Force sync: chronyc makestep"
    echo "  • Check NTP sources: chronyc sources"
fi

if [ "$SAVE_RESULTS" = true ]; then
    echo ""
    echo -e "${BLUE}📁 All results saved to: $OUTPUT_DIR${NC}"
    echo ""
    echo "Files created:"
    ls -lh "$OUTPUT_DIR"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Exit with appropriate code
exit $PHASE2_RESULT
