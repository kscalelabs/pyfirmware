"""Simplified WebSocket interface for robot control."""

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from simple_websocket_server import WebSocket, WebSocketServer


class WebSocketLaunchInterface:
    def __init__(self, host: str = "0.0.0.0", port: int = 8760) -> None:
        self.host = host
        self.port = port
        self.websocket: Optional[WebSocket] = None

        self.allow_motors = False
        self.allow_policy = False
        self.selected_kinfer: Optional[str] = None
        self.abort = False
        self.current_step = "started"
        self.kinfer_files: list[dict[str, Any]] = []
        self.devices_data: dict[str, Any] = {}
        self.policy_name: Optional[str] = None
        self._running = True
        self.server = self._create_server(host, port)

        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
            name="WebSocketServer"
        )

        self.broadcast_thread = threading.Thread(
            target=self._broadcast_state_loop,
            daemon=True,
            name="StateBroadcaster"
        )

        self.server_thread.start()
        self.broadcast_thread.start()
        print(f"WebSocket server running on ws://{host}:{port}")

    def _create_server(self, host: str, port: int) -> WebSocketServer:
        """Create a WebSocketServer with a handler that references this interface."""
        interface = self

        class RobotWebSocketHandler(WebSocket):
            def handle(self) -> None:
                try:
                    msg = json.loads(self.data)
                    interface._handle_message(msg)
                except Exception as e:
                    print(f"Bad message: {e}")

            def connected(self) -> None:
                print(f"Client connected from {self.address}")
                interface.websocket = self

            def handle_close(self) -> None:
                print(f"Client disconnected from {self.address}")
                interface.websocket = None

        return WebSocketServer(host, port, RobotWebSocketHandler)

    def _broadcast_state_loop(self) -> None:
        """Continuously broadcast state to connected clients every second."""
        while self._running:
            if self.websocket:
                self._send_state()
            time.sleep(1.0)

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Handle incoming WebSocket messages."""
        msg_type = msg.get("type")

        if msg_type == "enable_motors":
            self.allow_motors = True
        elif msg_type == "start_policy":
            self.allow_policy = True
        elif msg_type == "select_kinfer":
            data = msg.get("data", {})
            self.selected_kinfer = data.get("path")
        elif msg_type == "abort":
            self.abort = True

    def _send_message(self, msg_type: str, data: dict[str, Any] | None = None) -> None:
        """Send a message to the connected WebSocket client."""
        if self.websocket:
            try:
                payload = json.dumps({"type": msg_type, "data": data or {}})
                self.websocket.send_message(payload)
            except Exception as e:
                print(f"Error sending message: {e}")

    def _send_state(self) -> None:
        """Send current state to client."""
        state = {
            "policy_name": self.policy_name,
            "current_step": self.current_step,
            "kinfer_files": self.kinfer_files,
            "devices_data": self.devices_data,
        }
        self._send_message("state", state)

    def ask_motor_permission(self, devices: dict[str, Any]) -> bool:
        self.devices_data = devices
        return self._wait_for_flag(lambda: self.allow_motors, "enable_motors")

    def launch_policy_permission(self, policy_name: str) -> bool:
        self.policy_name = policy_name
        launch_permission = self._wait_for_flag(lambda: self.allow_policy, "start_policy")
        if launch_permission:
            self.current_step = "launched"
        return launch_permission

    def get_command_source(self) -> str:
        return "udp"

    def get_kinfer_path(self, policy_dir: str) -> Optional[str]:
        path = Path(policy_dir)
        self.kinfer_files = [
            {"name": f.name, "path": str(f), "size": f.stat().st_size, "modified": f.stat().st_mtime}
            for f in path.glob("*.kinfer")
        ]
        if not self.kinfer_files:
            print("No kinfer files found.")
            return None
        if self._wait_for_flag(lambda: self.selected_kinfer is not None, "select_kinfer"):
            return self.selected_kinfer
        return None

    def _wait_for_flag(self, condition: Callable[[], bool], step_name: str, timeout: int = 300) -> bool:
        """Block until condition() is True."""
        start_time = time.time()
        self.current_step = step_name
        while time.time() - start_time < timeout:
            if condition():
                self.current_step = "done"
                return True
            if self.abort:
                self.current_step = "aborted"
                return False
            time.sleep(0.1)
        return False

    def stop(self) -> None:
        """Shutdown the WebSocket server and close connections."""
        print("Shutting down WebSocket interface")
        self._running = False
        if self.websocket:
            self.websocket.close()
        if self.server:
            self.server.close()
