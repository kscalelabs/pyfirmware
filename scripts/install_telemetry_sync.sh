#!/usr/bin/env bash

set -euo pipefail

# Configuration
REMOTE_USER="dpsh"
REMOTE_HOST="mu"
LOCAL_LOGS_DIR="$HOME/kinfer-logs"
HOSTNAME=$(hostname)
REMOTE_BASE_DIR="/home/$REMOTE_USER/robot_telemetry"
REMOTE_LOGS_DIR="$REMOTE_BASE_DIR/$HOSTNAME"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installing Kinfer Telemetry Sync Service${NC}"

# Stop and disable existing service if it exists
if systemctl is-active --quiet kinfer-logs-sync; then
    echo -e "\n${YELLOW}Stopping existing service...${NC}"
    sudo systemctl stop kinfer-logs-sync
fi

if systemctl is-enabled --quiet kinfer-logs-sync 2>/dev/null; then
    echo -e "${YELLOW}Disabling existing service...${NC}"
    sudo systemctl disable kinfer-logs-sync
fi

# Install required packages
echo -e "\n${YELLOW}Installing required packages...${NC}"
sudo apt-get update
sudo apt-get install -y inotify-tools rsync

# Ensure local logs directory exists
mkdir -p "$LOCAL_LOGS_DIR"

# Set up SSH key if it doesn't exist
if [ ! -f "$HOME/.ssh/id_rsa" ]; then
    echo -e "\n${YELLOW}Setting up SSH key...${NC}"
    ssh-keygen -t rsa -N "" -f "$HOME/.ssh/id_rsa"
fi

# Copy SSH key to remote host
echo -e "\n${YELLOW}Copying SSH key to remote host...${NC}"
echo "Please enter the password for $REMOTE_USER@$REMOTE_HOST when prompted:"
ssh-copy-id "$REMOTE_USER@$REMOTE_HOST"

# Create remote directory
echo -e "\n${YELLOW}Creating remote directory...${NC}"
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_LOGS_DIR"

# Remove old sync script if it exists
SYNC_SCRIPT="/usr/local/bin/kinfer-logs-sync.sh"
if [ -f "$SYNC_SCRIPT" ]; then
    echo -e "\n${YELLOW}Removing old sync script...${NC}"
    sudo rm -f "$SYNC_SCRIPT"
fi

# Create sync script
echo -e "\n${YELLOW}Creating sync script...${NC}"
sudo tee "$SYNC_SCRIPT" > /dev/null << 'SCRIPT_EOF'
#!/bin/bash

LOCAL_LOGS_DIR="$1"
REMOTE_USER="$2"
REMOTE_HOST="$3"
REMOTE_LOGS_DIR="$4"

# Watch for file changes (recursive to catch subdirectories)
inotifywait -m -r "$LOCAL_LOGS_DIR" -e close_write,moved_to,move,modify --format '%e %w%f' | while read event file; do
    echo "$(date): Detected $event on $file"
    # Brief wait to ensure flush completes (logger uses f.flush() so data should be immediate)
    sleep 0.1
    echo "$(date): Starting sync..."
    if rsync -avz --exclude='*.swp' --exclude='*.swx' --exclude='*.tmp' --exclude='*~' "$LOCAL_LOGS_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_LOGS_DIR/"; then
        echo "$(date): Sync completed successfully"
    else
        echo "$(date): Sync failed"
    fi
done
SCRIPT_EOF

sudo chmod +x "$SYNC_SCRIPT"

# Create systemd service file
echo -e "\n${YELLOW}Creating systemd service...${NC}"
sudo tee /etc/systemd/system/kinfer-logs-sync.service > /dev/null << EOF
[Unit]
Description=Kinfer Log Sync Service
After=network.target

[Service]
ExecStart=$SYNC_SCRIPT $LOCAL_LOGS_DIR $REMOTE_USER $REMOTE_HOST $REMOTE_LOGS_DIR
User=$USER
Group=$USER
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
echo -e "\n${YELLOW}Enabling and starting service...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable kinfer-logs-sync
sudo systemctl start kinfer-logs-sync
sudo systemctl status kinfer-logs-sync

# Test the connection and initial sync
echo -e "\n${YELLOW}Testing initial sync...${NC}"
rsync -avz "$LOCAL_LOGS_DIR/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_LOGS_DIR/"

echo -e "\n${GREEN}Installation complete!${NC}"
echo -e "Logs from $LOCAL_LOGS_DIR will be automatically synced to $REMOTE_USER@$REMOTE_HOST:$REMOTE_LOGS_DIR"
echo -e "\nTo check service status: ${YELLOW}systemctl status kinfer-logs-sync${NC}"
echo -e "To view logs: ${YELLOW}journalctl -u kinfer-logs-sync${NC}"
