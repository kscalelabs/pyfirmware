"""WebSocket interface for remote robot control using blocking I/O."""

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from simple_websocket_server import WebSocket, WebSocketServer

from firmware.launchInterface.launch_interface import LaunchInterface


class RobotWebSocket(WebSocket):
    """WebSocket handler that stores connection reference."""

    def handle(self) -> None:
        """Handle incoming messages - put them in the queue."""
        message = json.loads(self.data)
        if hasattr(self.server, 'interface'):
            self.server.interface.message_queue.append(message)

    def connected(self) -> None:
        """Called when client connects."""
        if hasattr(self.server, 'interface'):
            self.server.interface._on_connect(self)

    def close(self) -> None:
        """Called when client disconnects."""
        if hasattr(self.server, 'interface'):
            self.server.interface._on_disconnect(self)
        super().close()


class WebSocketLaunchInterface(LaunchInterface):
    def __init__(self, host: str = "0.0.0.0", port: int = 8760) -> None:
        """Initialize and wait for a client connection."""
        self.host = host
        self.port = port
        self.websocket: Optional[WebSocket] = None
        self.server: Optional[WebSocketServer] = None
        self.message_queue: list[dict[str, Any]] = []
        self._server_thread: Optional[threading.Thread] = None
        self._connected_event = threading.Event()

        # State persistence for reconnection
        self.devices_data: dict[str, Any] = {}
        self.kinfer_files: list[dict[str, Any]] = []
        self.active_step = -1
        self.steps = [
            ["select_kinfer"],
            ["enable_motors"],
            ["start_policy"]
        ]

        # Start server and wait for connection
        self._start_server()
        self._wait_for_connection()

    def _start_server(self) -> None:
        """Start the WebSocket server in a background thread."""
        print(f"🚀 Starting WebSocket server on {self.host}:{self.port}")

        self.server = WebSocketServer(self.host, self.port, RobotWebSocket)
        self.server.interface = self  
  

        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()

        print(f"WebSocket server running on ws://{self.host}:{self.port}")

    def process_step(self, timeout: int = 300) -> Optional[dict]:
        """Process a step of the policy. Returns message dict if received, None on timeout."""
        expected_types = self.steps[self.active_step]
        expected_types.append('abort')
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.message_queue:
                message = self.message_queue.pop(0)

                if message.get("type") == "refresh_kinfer_files":
                    self.send_message("refresh", self.kinfer_files)

                if message.get("type") in expected_types:
                    self.active_step = -1
                    return message
                else:
                    self.send_message("error", {
                        "message": f"Expected one of {expected_types}, got {message.get('type')}"
                    })
                    continue

            time.sleep(0.01)

        self.send_message("timeout", {
            "message": f"Waiting for one of: {expected_types}"
        })
        return None

    def _on_connect(self, websocket: WebSocket) -> None:
        """Called when a client connects. Seamlessly override any existing connection."""
        # Close existing connection if present
        if self.websocket is not None:
            print(f"🔄 New connection from {websocket.address}, closing old connection")
            try:
                self.websocket.close()
            except Exception as e:
                print(f"Error closing old connection: {e}")

        self.websocket = websocket
        print(f"Client connected to launch interface from {websocket.address}")
        if self.kinfer_files:
            self.send_message("refresh_kinfer_files", {
                "kinfer_files": self.kinfer_files
            })
        self._connected_event.set()

    def _on_disconnect(self, websocket: WebSocket) -> None:
        print(f"Client disconnected to launch interface from {websocket.address}")
        self.websocket = None

    def _wait_for_connection(self, timeout: int = 300) -> None:
        """Block until a client connects."""
        if not self._connected_event.wait(timeout=timeout):
            raise TimeoutError("No client connected within timeout period")

    def send_message(self, message_type: str, data: Optional[dict[str, Any]] = None) -> None:
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
        print("Asking permission to enable motors")
        self.send_message("request_motor_enable", robot_devices)
        self.active_step = 1
        self.devices_data = robot_devices
        message = self.process_step()
        if message and message.get("type") == "enable_motors":
            self.send_message("enabling_motors")
            return True
        return False

    def launch_policy_permission(self, policy_name: str) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        self.send_message("request_policy_start", {
            "message": f"Ready to start {policy_name}?"
        })
        self.active_step = 2
        message = self.process_step()
        if message and message.get("type") == "start_policy":
            self.send_message("policy_started")
            return True
        return False

    def get_kinfer_path(self, policy_dir: str) -> Optional[str]:
        """Send list of available kinfer files and wait for user selection."""
        print("Getting kinfer path")
        self.active_step = 0
        search_dir = Path(policy_dir)
        self.kinfer_files = []

        if search_dir.exists():
            # Get all .kinfer files with metadata
            for filepath in search_dir.glob("*.kinfer"):
                self.kinfer_files.append({
                    "name": filepath.name,
                    "path": str(filepath),
                    "size": filepath.stat().st_size,
                    "modified": filepath.stat().st_mtime
                })

        if not self.kinfer_files:
            return None

        self.send_message("kinfer_list", {
            "files": self.kinfer_files
        })

        

        message = self.process_step()
        if message and message.get("type") == "abort":
            return None
        if message and message.get("type") == "select_kinfer":
            selected_path = message.get("data", {}).get("path", None)
            return selected_path
        return None

    def stop(self) -> None:
        """Close the WebSocket connection and server."""
        try:
            if self.websocket:
                self.websocket.close()

        except Exception as e:
            print(f"Error closing websocket: {e}")

        if self.server:
            try:
                self.server.close()
                # Wait for server thread to finish cleanly
                if self._server_thread and self._server_thread.is_alive():
                    self._server_thread.join(timeout=2.0)
                print("WebSocket server stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")
