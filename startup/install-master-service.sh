#!/bin/bash
# Install K-Bot Master Process as systemd service

set -e

echo "Installing K-Bot Master Process service..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should not be run as root" 
   exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Copy service file to systemd directory
echo "Copying service file..."
sudo cp "$PROJECT_DIR/kbot-master.service" /etc/systemd/system/

# Reload systemd daemon
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable the service (start on boot)
echo "Enabling service to start on boot..."
sudo systemctl enable kbot-master.service

# Create log directory if it doesn't exist
sudo mkdir -p /var/log
sudo touch /var/log/kbot-master.log
sudo chown pi:pi /var/log/kbot-master.log

echo "Installation complete!"
echo ""
echo "Commands to manage the service:"
echo "  sudo systemctl start kbot-master    # Start the service"
echo "  sudo systemctl stop kbot-master     # Stop the service"
echo "  sudo systemctl status kbot-master   # Check status"
echo "  sudo systemctl restart kbot-master  # Restart the service"
echo "  journalctl -u kbot-master -f        # View logs in real-time"
echo ""
echo "The service will automatically start on boot."
