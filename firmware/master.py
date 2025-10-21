"""Master WebSocket server for policy execution and screen management."""

import asyncio
import json
import sys
import time
from typing import Dict, Any, Optional
import websockets
from websockets.server import WebSocketServerProtocol

from firmware.policy_manager import SimplePolicyManager
from firmware.peripherals.screen import start as start_screen, stop as stop_screen


class MasterServer:
    """Master WebSocket server managing policy execution and screen display."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8770):
        self.host = host
        self.port = port
        self.clients: set[WebSocketServerProtocol] = set()
        self.running = False
        self.status_task: Optional[asyncio.Task] = None
        self.screen_started = False
        self.policy_manager = SimplePolicyManager()
    
    async def cleanup(self):
        """Clean up resources when server shuts down."""
        print("Cleaning up resources...")
        
        # Stop policy if running
        if self.policy_manager.get_status()["running"]:
            print("Stopping policy...")
            self.policy_manager.stop()
        
        # Stop screen if started
        if self.screen_started:
            try:
                stop_screen()
                print("Screen stopped")
            except Exception as e:
                print(f"Error stopping screen: {e}")
        
        print("Cleanup completed")
    
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new client connection."""
        self.clients.add(websocket)
        print(f"Client connected. Total clients: {len(self.clients)}")
    
    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """Unregister a client connection."""
        self.clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(self.clients)}")
    
    async def broadcast_message(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients."""
        if not self.clients:
            return
        
        message_str = json.dumps(message)
        disconnected = set()
        
        for client in self.clients:
            try:
                await client.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                print(f"Error sending message to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    async def handle_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            payload = data.get("payload")
            
            print(f"Received message: type={msg_type}, payload={payload}")
            
            if msg_type == "policy_execution":
                await self.handle_policy_command(payload)
            else:
                print(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            print(f"Invalid JSON message: {message}")
        except Exception as e:
            print(f"Error handling message: {e}")
    
    async def handle_policy_command(self, payload: str):
        """Handle policy execution commands."""
        if payload == "start":
            success = self.policy_manager.start()
            if success:
                print("Policy started successfully")
                await self.broadcast_message({
                    "type": "policy_status",
                    "payload": {"status": "started", "success": True}
                })
            else:
                print("Failed to start policy")
                await self.broadcast_message({
                    "type": "policy_status", 
                    "payload": {"status": "start_failed", "success": False}
                })
        
        elif payload == "stop":
            success = self.policy_manager.stop()
            if success:
                print("Policy stopped successfully")
                await self.broadcast_message({
                    "type": "policy_status",
                    "payload": {"status": "stopped", "success": True}
                })
            else:
                print("Failed to stop policy")
                await self.broadcast_message({
                    "type": "policy_status",
                    "payload": {"status": "stop_failed", "success": False}
                })
        
        else:
            print(f"Unknown policy command: {payload}")
    
    async def status_monitor(self):
        """Monitor policy status and broadcast updates every second."""
        while self.running:
            try:
                # Get policy status
                policy_status = self.policy_manager.get_status()
                # Broadcast combined status
                await self.broadcast_message({
                    "type": "status_update",
                    "payload": policy_status
                })
                
                await asyncio.sleep(1.0)  # Update every second
                
            except Exception as e:
                print(f"Error in status monitor: {e}")
                await asyncio.sleep(1.0)
    
    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle individual client connection."""
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            await self.unregister_client(websocket)
    
    async def start_server(self):
        """Start the WebSocket server."""
        print(f"Starting master server on {self.host}:{self.port}")
        
        # Start screen with face display
        try:
            screen_success = start_screen()
            if screen_success:
                self.screen_started = True
                print("Face displayed on screen")
            else:
                print("Failed to display face")
        except Exception as e:
            print(f"Error displaying face: {e}")
        
        # Start WebSocket server
        self.running = True
        
        # Start status monitoring task
        self.status_task = asyncio.create_task(self.status_monitor())
        
        # Start WebSocket server
        async with websockets.serve(self.handle_client, self.host, self.port):
            print(f"Master server running on ws://{self.host}:{self.port}")
            print("Waiting for connections...")
            
            # Keep server running
            try:
                await asyncio.Future()  # Run forever
            except KeyboardInterrupt:
                print("Interrupted by user")
                self.running = False
                await self.cleanup()
                pass


async def main():
    """Main entry point."""
    server = MasterServer()
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("Interrupted by user")
        await server.cleanup()
    except Exception as e:
        print(f"Fatal error: {e}")
        await server.cleanup()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)