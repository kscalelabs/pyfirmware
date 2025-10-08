#!/usr/bin/env python3
"""
Master process for K-Bot display/camera/QR management.
Simple WebSocket interface to control processes.
"""

import asyncio
import json
import signal
import sys
import websockets
from process_manager import ProcessManager


class WebSocketHandler:
    """Handles WebSocket connections and commands."""
    
    def __init__(self, process_manager: ProcessManager):
        self.pm = process_manager
        self.clients = set()
        self.first_connection = True
    
    async def handle_client(self, websocket, path):
        """Handle a WebSocket client connection."""
        self.clients.add(websocket)
        client_ip = websocket.remote_address[0]
        print(f"Client connected from {client_ip}")
        
        # Stop QR code on first connection
        if self.first_connection:
            print("First connection received, stopping QR code")
            self.pm.stop_process("qr")
            self.first_connection = False
        
        try:
            async for message in websocket:
                await self.handle_command(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"Client {client_ip} disconnected")
        except Exception as e:
            print(f"Error handling client {client_ip}: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def handle_command(self, websocket, message: str):
        """Process incoming commands: {type: "display|qr|camera", active: true|false}"""
        try:
            cmd = json.loads(message)
            process_type = cmd.get("type")
            active = cmd.get("active")
            
            # Validate input
            if process_type not in self.pm.options:
                await websocket.send(json.dumps({
                    "success": False,
                    "error": f"Invalid type. Must be one of: {list(self.pm.options.keys())}"
                }))
                return
            
            if not isinstance(active, bool):
                await websocket.send(json.dumps({
                    "success": False,
                    "error": "active must be true or false"
                }))
                return
            
            # Execute command
            if active:
                success = self.pm.start_process(process_type)
            else:
                success = self.pm.stop_process(process_type)
            
            # Send response
            await websocket.send(json.dumps({
                "success": success,
                "type": process_type,
                "active": active
            }))
                
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "success": False,
                "error": "Invalid JSON"
            }))
        except Exception as e:
            print(f"Error processing command: {e}")
            await websocket.send(json.dumps({
                "success": False,
                "error": str(e)
            }))

async def main():
    """Main master process loop."""
    print("Starting K-Bot Master Process")
    
    # Initialize process manager
    process_manager = ProcessManager()
    
    # Set up signal handlers for cleanup
    def signal_handler(signum, frame):
        print(f"Received signal {signum}, shutting down...")
        process_manager.cleanup_all()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start QR code on boot
    print("Starting QR code display...")
    if process_manager.start_process("qr"):
        print("QR code display started")
    else:
        print("Failed to start QR code display")
    
    # Initialize WebSocket handler
    ws_handler = WebSocketHandler(process_manager)
    
    # Start WebSocket server
    print("Starting WebSocket server on port 8764")
    server = await websockets.serve(
        ws_handler.handle_client,
        "0.0.0.0",
        8764,
        ping_interval=30,
        ping_timeout=10
    )
    
    print("Master process ready")
    print("Available processes: display, qr, camera")
    print("Send: {\"type\": \"display|qr|camera\", \"active\": true|false}")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        print("Shutdown requested")
    finally:
        process_manager.cleanup_all()
        print("Master process stopped")


if __name__ == "__main__":
    asyncio.run(main())
