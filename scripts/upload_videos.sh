#!/bin/bash

# Script to upload videos to remote server and clean up local files
# Usage: ./upload_videos.sh

set -euo pipefail

# Configuration
REMOTE_USER="dpsh"
REMOTE_HOST="mu"
REMOTE_PATH="~/robot_telemetry/videos"
LOCAL_VIDEO_DIR="$HOME/videos"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Video Upload Script ===${NC}"
echo "Local directory: $LOCAL_VIDEO_DIR"
echo "Remote destination: $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH"
echo

# Check if local video directory exists
if [ ! -d "$LOCAL_VIDEO_DIR" ]; then
    echo -e "${RED}Error: Local video directory '$LOCAL_VIDEO_DIR' does not exist${NC}"
    exit 1
fi

# Check if there are any video files
video_files=$(find "$LOCAL_VIDEO_DIR" -name "*.mp4" -type f)
if [ -z "$video_files" ]; then
    echo -e "${YELLOW}No MP4 files found in $LOCAL_VIDEO_DIR${NC}"
    exit 0
fi

# Count files
file_count=$(echo "$video_files" | wc -l)
echo -e "${GREEN}Found $file_count MP4 file(s) to upload${NC}"

# Create remote directory if it doesn't exist
echo -e "${YELLOW}Creating remote directory if needed...${NC}"
ssh "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH"

# Upload files
echo -e "${YELLOW}Uploading files...${NC}"
rsync -avz --progress "$LOCAL_VIDEO_DIR"/*.mp4 "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

# Verify upload
echo -e "${YELLOW}Verifying upload...${NC}"
remote_files=$(ssh "$REMOTE_USER@$REMOTE_HOST" "ls -la $REMOTE_PATH/*.mp4 2>/dev/null | wc -l" || echo "0")
echo "Remote files count: $remote_files"

if [ "$remote_files" -ge "$file_count" ]; then
    echo -e "${GREEN}Upload verification successful${NC}"
    
    # Ask for confirmation before deletion
    echo -e "${YELLOW}Upload completed successfully.${NC}"
    echo -e "${RED}About to delete local video files. This action cannot be undone.${NC}"
    read -p "Do you want to delete the local files? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Deleting local files...${NC}"
        rm -f "$LOCAL_VIDEO_DIR"/*.mp4
        echo -e "${GREEN}Local files deleted successfully${NC}"
    else
        echo -e "${YELLOW}Local files preserved${NC}"
    fi
else
    echo -e "${RED}Upload verification failed. Local files will not be deleted.${NC}"
    echo "Expected $file_count files, found $remote_files on remote server"
    exit 1
fi

echo -e "${GREEN}=== Upload process completed ===${NC}"
