"""WebSocket interface for remote robot control using blocking I/O."""

import json
import os
import socket
import struct
import threading
from pathlib import Path
from typing import Optional

from simple_websocket_server import WebSocketServer, WebSocket

from firmware.logger import Logger


class RobotWebSocket(WebSocket):
    """WebSocket handler that stores connection reference."""
    
    def handle(self):
        """Handle incoming messages - put them in the queue."""
        message = json.loads(self.data)
        if hasattr(self.server, 'interface'):
            self.server.interface.message_queue.append(message)
    
    def connected(self):
        """Called when client connects."""
        if hasattr(self.server, 'interface'):
            self.server.interface._on_connect(self)


class WebSocketInterface:
    """WebSocket interface using blocking I/O - no async needed!"""
    
    def __init__(self, logger: Logger, host: str = "0.0.0.0", port: int = 8760):
        """Initialize and wait for a client connection."""
        self.logger = logger
        self.host = host
        self.port = port
        self.websocket = None
        self.server = None
        self.message_queue = []
        self._server_thread = None
        self._connected_event = threading.Event()
        
        # Start server and wait for connection
        self._start_server()
        self._wait_for_connection()
    
    def _start_server(self):
        """Start the WebSocket server in a background thread."""
        self.logger.info(f"🚀 Starting WebSocket server on {self.host}:{self.port}")
        
        # Create the server
        self.server = WebSocketServer(self.host, self.port, RobotWebSocket)
        self.server.interface = self  # Give server reference to this interface
        
        # Start server in background thread
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()
        
        self.logger.info(f"✅ WebSocket server running on ws://{self.host}:{self.port}")
        self.logger.info(f"⏳ Waiting for client connection...")
    
    def _on_connect(self, websocket):
        """Called when a client connects."""
        self.websocket = websocket
        self.logger.info(f"🔌 Client connected from {websocket.address}")
        self._connected_event.set()
    
    def _wait_for_connection(self, timeout: int = 300):
        """Block until a client connects."""
        if not self._connected_event.wait(timeout=timeout):
            raise TimeoutError("No client connected within timeout period")
    
    def send_message(self, message_type: str, data: dict = None) -> None:
        """Send a JSON message to the client (blocking)."""
        if not self.websocket:
            return
        
        message = {"type": message_type, "data": data or {}}
        try:
            self.websocket.send_message(json.dumps(message))
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
    
    def wait_for_message(self, expected_types: list[str], timeout: int = 300) -> Optional[dict]:
        """Wait for a message of expected type(s) (blocking)."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check message queue
            if self.message_queue:
                message = self.message_queue.pop(0)
                
                if message.get("type") == "abort":
                    self.send_message("aborted")
                    return {"type": "abort"}
                
                if message.get("type") in expected_types:
                    return message
                else:
                    self.send_message("error", {
                        "message": f"Expected one of {expected_types}, got {message.get('type')}"
                    })
                    continue
            
            # Sleep briefly to avoid busy waiting
            time.sleep(0.01)
        
        # Timeout
        self.send_message("timeout", {
            "message": f"Waiting for one of: {expected_types}"
        })
        return None
    
    def get_command_source(self) -> str:
        """Return command source type."""
        return "UDP"
    
    def ask_motor_permission(self, actuator_info={}) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        self.send_message("request_motor_enable", actuator_info)
        
        while True:
            message = self.wait_for_message(["enable_motors"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "enable_motors":
                self.send_message("enabling_motors")
                return True
    
    def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        self.send_message("request_policy_start", {
            "message": "Ready to start policy?"
        })
        
        while True:
            message = self.wait_for_message(["start_policy"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "start_policy":
                self.send_message("policy_started")
                return True
    
    def send_policy_status(self, step_id: int, dt_ms: float) -> None:
        """Send policy status update to client (non-blocking)."""
        try:
            self.send_message("policy_status", {
                "step_id": step_id,
                "dt_ms": dt_ms
            })
        except:
            pass
    
    def get_kinfer_path(self, policy_dir: str = None) -> Optional[str]:
        """Send list of available kinfer files and wait for user selection."""
        # Find all .kinfer files in ~/.policies or provided directory
        if policy_dir:
            search_dir = Path(policy_dir)
        else:
            search_dir = Path.home() / ".policies"
        
        kinfer_files = []
        
        if search_dir.exists():
            # Get all .kinfer files with metadata
            for filepath in search_dir.glob("*.kinfer"):
                kinfer_files.append({
                    "name": filepath.name,
                    "path": str(filepath),
                    "size": filepath.stat().st_size,
                    "modified": filepath.stat().st_mtime
                })
            
            # Sort by modification time (newest first)
            kinfer_files.sort(key=lambda x: x["modified"], reverse=True)
        
        if not kinfer_files:
            self.send_message("error", {
                "message": f"No kinfer files found in {search_dir}"
            })
            return None
        
        # Send list to client
        self.send_message("kinfer_list", {
            "files": kinfer_files,
            "count": len(kinfer_files)
        })
        
        # Wait for client to select one
        while True:
            message = self.wait_for_message(["select_kinfer"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "abort":
                return None
            
            selected_path = message.get("data", {}).get("path")
            if selected_path and os.path.exists(selected_path):
                self.send_message("kinfer_selected", {"path": selected_path})
                return selected_path
            else:
                self.send_message("error", {
                    "message": f"Invalid kinfer file path: {selected_path}"
                })
    
    def stop(self):
        """Close the WebSocket connection and server."""
        self.logger.info("🔌 Closing WebSocket connection...")
        try:
            if self.websocket:
                self.websocket.close()
                self.logger.info("✅ WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"Error closing websocket: {e}")
        
        if self.server:
            self.logger.info("🛑 Stopping WebSocket server...")
            try:
                self.server.close()
                self.logger.info("✅ WebSocket server stopped")
            except Exception as e:
                self.logger.error(f"Error stopping server: {e}")
    
    def close(self):
        """Alias for stop() for compatibility."""
        self.stop()