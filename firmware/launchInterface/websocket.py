"""WebSocket interface for remote robot control."""

import asyncio
import glob
import json
import os
from pathlib import Path
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol


class WebSocketInterface:
    """WebSocket interface that waits for a client connection before proceeding."""
    
    def __init__(self, websocket: WebSocketServerProtocol, server):
        """Initialize with an established WebSocket connection."""
        self.websocket = websocket
        self.server = server
        print(f"🔌 Client connected from {websocket.remote_address}")
    
    @classmethod
    async def create(cls, host: str = "0.0.0.0", port: int = 8760):
        """Create a WebSocketInterface and wait for a client to connect."""
        print(f"🚀 Starting WebSocket server on {host}:{port}")
        
        # Create a future that will be resolved when a client connects
        connection_future = asyncio.Future()
        
        async def handle_connection(websocket):
            """Handle the WebSocket connection."""
            if not connection_future.done():
                connection_future.set_result(websocket)
            # Keep the connection alive
            try:
                await asyncio.Future()  # Wait forever
            except asyncio.CancelledError:
                pass
        
        # Start the server with SO_REUSEADDR to allow quick restart
        import socket
        server = await websockets.serve(
            handle_connection, 
            host, 
            port,
            # Allow immediate reuse of the port after shutdown
            sock=None,
            create_protocol=None,
            family=socket.AF_INET,
            flags=socket.AI_PASSIVE,
            reuse_address=True,
            reuse_port=False
        )
        print(f"✅ WebSocket server running on ws://{host}:{port}")
        print(f"⏳ Waiting for client connection...")
        
        # Wait for a client to connect
        websocket = await connection_future
        
        # Create and return the interface
        return cls(websocket, server)
    
    async def send_message(self, message_type: str, data: dict = None) -> None:
        """Send a JSON message to the client."""
        message = {"type": message_type, "data": data or {}}
        await self.websocket.send(json.dumps(message))
    
    async def wait_for_message(self, expected_types: list[str], timeout: int = 300) -> Optional[dict]:
        """Wait for a message of expected type(s)."""
        try:
            message_raw = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            message = json.loads(message_raw)
            
            if message.get("type") == "abort":
                await self.send_message("aborted")
                return {"type": "abort"}
            
            if message.get("type") in expected_types:
                return message
            else:
                await self.send_message("error", {
                    "message": f"Expected one of {expected_types}, got {message.get('type')}"
                })
                return None
        except asyncio.TimeoutError:
            await self.send_message("timeout", {
                "message": f"Waiting for one of: {expected_types}"
            })
            return None
    
    async def getCommandSource(self) -> str:
        return "UDP"
        
    async def askIMUPermission(self, imu_reader) -> bool:
        """Ask permission to continue without IMU. Returns True if should continue, False to abort."""
        print(f"IMU reader: {imu_reader}")
        if imu_reader is not None:
            await self.send_message("imu_success")
            return True
        
        await self.send_message("imu_not_found", {
            "message": "No IMU hardware detected. Continue without IMU?"
        })
        
        while True:
            message = await self.wait_for_message(["continue_without_imu", "abort"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "abort":
                await self.send_message("abort")
                return False
            
            if message["type"] == "continue_without_imu":
                await self.send_message("imu_success")
                return True
    
    async def askMotorPermission(self, actuator_info) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        await self.send_message("request_motor_enable", actuator_info)
        
        while True:
            message = await self.wait_for_message(["enable_motors", "abort"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "abort":
                await self.send_message("aborted")
                return False
            
            if message["type"] == "enable_motors":
                await self.send_message("enabling_motors")
                return True
    
    async def launchPolicyPermission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        await self.send_message("request_policy_start", {
            "message": "Ready to start policy?"
        })
        
        while True:
            message = await self.wait_for_message(["start_policy", "abort"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "abort":
                await self.send_message("aborted")
                return False
            
            if message["type"] == "start_policy":
                await self.send_message("policy_started")
                return True
    
    async def send_policy_status(self, step_id: int, dt_ms: float) -> None:
        """Send policy status update to client."""
        try:
            await self.send_message("policy_status", {
                "step_id": step_id,
                "dt_ms": dt_ms
            })
        except:
            pass
    
    async def check_for_stop(self) -> bool:
        """Check if client sent stop command. Returns True if should stop."""
        try:
            message_raw = await asyncio.wait_for(self.websocket.recv(), timeout=0.001)
            message = json.loads(message_raw)
            
            if message.get("type") == "stop_policy":
                await self.send_message("policy_stopped")
                return True
            elif message.get("type") == "abort":
                await self.send_message("aborted")
                return True
        except asyncio.TimeoutError:
            pass
        except:
            pass
        
        return False
    
    async def getKinferPath(self) -> Optional[str]:
        """Send list of available kinfer files and wait for user selection."""
        # Find all .kinfer files in ~/.policies
        policy_dir = Path.home() / ".policies"
        kinfer_files = []
        
        if policy_dir.exists():
            # Get all .kinfer files with metadata
            for filepath in policy_dir.glob("*.kinfer"):
                kinfer_files.append({
                    "name": filepath.name,
                    "path": str(filepath),
                    "size": filepath.stat().st_size,
                    "modified": filepath.stat().st_mtime
                })
            
            # Sort by modification time (newest first)
            kinfer_files.sort(key=lambda x: x["modified"], reverse=True)
        
        if not kinfer_files:
            await self.send_message("error", {
                "message": f"No kinfer files found in {policy_dir}"
            })
            return None
        
        # Send list to client
        await self.send_message("kinfer_list", {
            "files": kinfer_files,
            "count": len(kinfer_files)
        })
        
        # Wait for client to select one
        while True:
            message = await self.wait_for_message(["select_kinfer"], timeout=300)
            if not message:
                continue
            
            if message["type"] == "abort":
                return None
            
            selected_path = message.get("data", {}).get("path")
            if selected_path and os.path.exists(selected_path):
                await self.send_message("kinfer_selected", {"path": selected_path})
                return selected_path
            else:
                await self.send_message("error", {
                    "message": f"Invalid kinfer file path: {selected_path}"
                })
    
    async def close(self):
        """Close the WebSocket connection and server."""
        print("🔌 Closing WebSocket connection...")
        try:
            if self.websocket:
                await self.websocket.close()
                print("✅ WebSocket connection closed")
        except Exception as e:
            print(f"⚠️  Error closing websocket: {e}")
        
        if self.server:
            print("🛑 Stopping WebSocket server...")
            try:
                self.server.close()
                await self.server.wait_closed()
                print("✅ WebSocket server stopped")
            except Exception as e:
                print(f"⚠️  Error stopping server: {e}")
