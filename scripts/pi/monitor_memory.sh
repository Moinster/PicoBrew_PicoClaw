#!/bin/bash
# Memory monitoring script for PicoBrew server on Raspberry Pi
# Logs memory usage every 5 minutes to help diagnose OOM crashes.
#
# Usage:
#   sudo bash /picobrew_picoclaw/scripts/pi/monitor_memory.sh &
#
# Or add to crontab to survive reboots:
#   @reboot /bin/bash /picobrew_picoclaw/scripts/pi/monitor_memory.sh &

LOG_FILE="/home/pi/memory_log.txt"
INTERVAL=300  # 5 minutes

echo "$(date): Memory monitor started" >> "$LOG_FILE"

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # System memory
    MEM_INFO=$(free -m | awk '/Mem:/ {printf "total=%sMB used=%sMB free=%sMB available=%sMB", $2, $3, $4, $7}')
    SWAP_INFO=$(free -m | awk '/Swap:/ {printf "swap_total=%sMB swap_used=%sMB", $2, $3}')
    
    # Server process memory (RSS in KB)
    SERVER_PID=$(pgrep -f "python3 server.py" | head -1)
    if [ -n "$SERVER_PID" ]; then
        SERVER_RSS=$(ps -o rss= -p "$SERVER_PID" | tr -d ' ')
        SERVER_VSZ=$(ps -o vsz= -p "$SERVER_PID" | tr -d ' ')
        SERVER_MEM="${SERVER_RSS}KB_rss ${SERVER_VSZ}KB_vsz"
    else
        SERVER_MEM="not_running"
    fi
    
    echo "${TIMESTAMP}: ${MEM_INFO} ${SWAP_INFO} server=${SERVER_MEM}" >> "$LOG_FILE"
    
    sleep $INTERVAL
done
