"""WebSocket interface for remote robot control using blocking I/O."""

import json
import os
import socket
import struct
import threading
from pathlib import Path
from typing import Optional

from simple_websocket_server import WebSocketServer, WebSocket

from firmware.launchInterface.launch_interface import LaunchInterface

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
    
    def close(self):
        """Called when client disconnects."""
        if hasattr(self.server, 'interface'):
            self.server.interface._on_disconnect(self)
        super().close()


class WebSocketInterface(LaunchInterface):
    """WebSocket interface using blocking I/O - no async needed!"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8760):
        """Initialize and wait for a client connection."""
        self.host = host
        self.port = port
        self.websocket = None
        self.server = None
        self.message_queue = []
        self._server_thread = None
        self._connected_event = threading.Event()
        
        # Initialize connection tracking
        self.active_connection_ip = None
        self.active_step = -1
        self.steps = [
            ["select_kinfer"],
            ["enable_motors"],
            ["start_policy"]
        ]
        
        # Start server and wait for connection
        self._start_server()
        self._wait_for_connection()
    
    def _start_server(self):
        """Start the WebSocket server in a background thread."""
        print(f"🚀 Starting WebSocket server on {self.host}:{self.port}")
        
        # Create the server
        self.server = WebSocketServer(self.host, self.port, RobotWebSocket)
        self.server.interface = self  # Give server reference to this interface
        
        # Start server in background thread
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()
        
        print(f"✅ WebSocket server running on ws://{self.host}:{self.port}")
        print(f"⏳ Waiting for client connection...")


    def process_step(self, timeout: int = 300) -> bool:
        expected_types = self.steps[self.active_step]
        """Process a step of the policy. Returns True if should continue, False to abort."""
        """Wait for a message of expected type(s) (blocking)."""
        import time
        start_time = time.time()

        
        while time.time() - start_time < timeout:
            # Check message queue
            if self.message_queue:
                message = self.message_queue.pop(0)
                
                if message.get("type") == "abort":
                    self.send_message("aborted")
                    self.active_step = -1
                    return message
                
                if message.get("type") in expected_types:
                    self.active_step = -1
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
        return True
    
    def _on_connect(self, websocket):
        """Called when a client connects."""
        client_ip = websocket.address[0] if websocket.address else "unknown"
        
        # Check if there's already an active connection from a different IP
        if self.active_connection_ip is not None and self.active_connection_ip != client_ip:
            print(f"❌ Connection denied: Already connected from {self.active_connection_ip}")
            websocket.close()
            return
        
        # If no active connection, or same IP reconnecting
        self.websocket = websocket
        self.active_connection_ip = client_ip
        print(f"🔌 Client connected from {websocket.address}")
        
        # Check if we need to resume from an active step
        if self.active_step != -1:
            print(f"🔄 Resuming from active step {self.active_step}")
            # Send resume message to client
            self.send_message("resume_step", {
                "step": self.active_step,
                "expected_types": self.steps[self.active_step]
            })
        
        self._connected_event.set()
    
    def _on_disconnect(self, websocket):
        """Called when a client disconnects."""
        client_ip = websocket.address[0] if websocket.address else "unknown"
        print(f"🔌 Client disconnected from {websocket.address}")
        
        # Only reset connection tracking if this was the active connection
        if self.active_connection_ip == client_ip:
            print(f"🔄 Clearing connection tracking for IP: {client_ip}")
            self.active_connection_ip = None
            self.websocket = None
            
            # Note: We keep active_step so user can resume if they reconnect
    
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
            print(f"Error sending message: {e}")
    
    def get_command_source(self) -> str:
        """Return command source type."""
        return "UDP"
    
    def ask_motor_permission(self, robot_devices: dict = {}) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        self.send_message("request_motor_enable", robot_devices)
        self.active_step = 1
        message = self.process_step()
        if message and message.get("type") == "enable_motors":
            self.send_message("enabling_motors")
            return True
        return False
    
    def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        self.send_message("request_policy_start", {
            "message": "Ready to start policy?"
        })
        self.active_step = 2
        message = self.process_step()        
        if message and message.get("type") == "start_policy":
            self.send_message("policy_started")
            return True
        return False
    def get_kinfer_path(self, policy_dir: str = None) -> str or None:
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

        self.active_step = 0
        message = self.process_step()
        if message.type == "abort":
            return None
        if message and message.get("type") == "select_kinfer":
            selected_path = message.get("data", {}).get("path")
            return selected_path
        return None
    
    def stop(self):
        """Close the WebSocket connection and server."""
        print("🔌 Closing WebSocket connection...")
        
        # Reset connection tracking
        self.active_connection_ip = None
        self.active_step = -1
        
        try:
            if self.websocket:
                self.websocket.close()
                print("✅ WebSocket connection closed")
        except Exception as e:
            print(f"Error closing websocket: {e}")
        
        if self.server:
            print("🛑 Stopping WebSocket server...")
            try:
                self.server.close()
                print("✅ WebSocket server stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")