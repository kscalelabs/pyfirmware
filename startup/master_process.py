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
        
        # Register callback for status changes
        self.pm.set_status_change_callback(self.broadcast_status)
    
    async def broadcast_status(self):
        """Broadcast current process status to all connected clients."""
        if not self.clients:
            return
        
        status = self.pm.get_status()
        message = json.dumps({
            "type": "status_update",
            "processes": status
        })
        
        # Send to all connected clients
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                print(f"Error broadcasting to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        self.clients -= disconnected
    
    async def handle_client(self, websocket):
        """Handle a WebSocket client connection."""
        self.clients.add(websocket)
        client_ip = websocket.remote_address[0]
        print(f"Client connected from {client_ip}")
        
        # Send initial status to the newly connected client
        try:
            status = self.pm.get_status()
            await websocket.send(json.dumps({
                "type": "status_update",
                "processes": status
            }))
        except Exception as e:
            print(f"Error sending initial status to {client_ip}: {e}")
        
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
            print(f"Received command: {cmd}")
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
    try:
        print("Starting WebSocket server on port 8764...", flush=True)
        server = await websockets.serve(
            ws_handler.handle_client,
            "0.0.0.0",
            8764,
            ping_interval=30,
            ping_timeout=10
        )
        
        print("✓ WebSocket server running on 0.0.0.0:8764", flush=True)
        print("✓ Master process ready", flush=True)
        print("  Available processes: display, qr, camera", flush=True)
        print("  Send: {\"type\": \"display|qr|camera\", \"active\": true|false}", flush=True)
        print(flush=True)
        
        await server.wait_closed()
    except OSError as e:
        print(f"Failed to start WebSocket server: {e}", flush=True)
        print("Port 8764 may already be in use. Check with: netstat -tlnp | grep 8764", flush=True)
        process_manager.cleanup_all()
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested", flush=True)
    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        process_manager.cleanup_all()
        sys.exit(1)
    finally:
        process_manager.cleanup_all()
        print("Master process stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
