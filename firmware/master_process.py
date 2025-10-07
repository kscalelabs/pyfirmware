#!/usr/bin/env python3
"""
Master process for K-Bot firmware management.
Provides WebSocket interface to control policy deployment, GStreamer, and QR code display.
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import websockets
from dataclasses import dataclass
from typing import Dict, Optional, Any
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/kbot-master.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessStatus:
    name: str
    pid: Optional[int]
    running: bool
    start_time: Optional[float]
    exit_code: Optional[int]
    last_error: Optional[str]
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


class ProcessManager:
    """Manages subprocess lifecycle and monitoring."""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.status: Dict[str, ProcessStatus] = {}
        self.running = True
        self.qr_started = False
        
    def start_process(self, name: str, cmd: list, cwd: str = None, priority: int = None) -> bool:
        """Start a subprocess with optional priority boost."""
        try:
            if name in self.processes and self.processes[name].poll() is None:
                logger.warning(f"Process {name} is already running")
                return False
            
            # Prepare environment
            env = os.environ.copy()
            if priority is not None:
                # Note: requires root privileges to set negative nice value
                env['NICE_VALUE'] = str(priority)
            
            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                bufsize=0,  # Unbuffered for real-time output
                universal_newlines=True,
                preexec_fn=self._set_process_priority(priority) if priority else None
            )
            
            self.processes[name] = process
            self.status[name] = ProcessStatus(
                name=name,
                pid=process.pid,
                running=True,
                start_time=time.time(),
                exit_code=None,
                last_error=None
            )
            
            logger.info(f"Started process {name} (PID: {process.pid})")
            
            # Start monitoring task
            asyncio.create_task(self._monitor_process(name, process))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start process {name}: {e}")
            self.status[name] = ProcessStatus(
                name=name,
                pid=None,
                running=False,
                start_time=None,
                exit_code=None,
                last_error=str(e)
            )
            return False
    
    def stop_process(self, name: str, timeout: int = 10) -> bool:
        """Stop a process gracefully with timeout."""
        if name not in self.processes:
            logger.warning(f"Process {name} not found")
            return False
        
        process = self.processes[name]
        
        try:
            # Try graceful shutdown first
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"Process {name} didn't stop gracefully, force killing")
                process.kill()
                process.wait()
            
            # Update status
            if name in self.status:
                self.status[name].running = False
                self.status[name].exit_code = process.returncode
            
            del self.processes[name]
            logger.info(f"Stopped process {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping process {name}: {e}")
            return False
    
    def send_input(self, name: str, input_str: str) -> bool:
        """Send input to a process's stdin."""
        if name not in self.processes:
            return False
        
        process = self.processes[name]
        if process.poll() is not None:
            return False
        
        try:
            process.stdin.write(input_str + '\n')
            process.stdin.flush()
            return True
        except Exception as e:
            logger.error(f"Failed to send input to {name}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all processes."""
        status_dict = {}
        for name, status in self.status.items():
            status_dict[name] = {
                'running': status.running,
                'pid': status.pid,
                'start_time': status.start_time,
                'exit_code': status.exit_code,
                'last_error': status.last_error,
                'uptime': time.time() - status.start_time if status.start_time else 0,
                'cpu_percent': status.cpu_percent,
                'memory_mb': status.memory_mb
            }
        return status_dict
    
    def cleanup_all(self):
        """Stop all processes and cleanup."""
        logger.info("Cleaning up all processes")
        for name in list(self.processes.keys()):
            self.stop_process(name, timeout=5)
        self.running = False
    
    def _set_process_priority(self, priority: int):
        """Set process priority (requires root)."""
        def set_priority():
            try:
                os.nice(priority)
            except PermissionError:
                logger.warning(f"Could not set priority {priority} (requires root)")
        return set_priority
    
    async def _monitor_process(self, name: str, process: subprocess.Popen):
        """Monitor process output and status."""
        try:
            while process.poll() is None and self.running:
                # Read output (non-blocking)
                try:
                    line = process.stdout.readline()
                    if line:
                        logger.info(f"[{name}] {line.strip()}")
                except:
                    pass
                
                # Update resource usage
                try:
                    import psutil
                    proc = psutil.Process(process.pid)
                    self.status[name].cpu_percent = proc.cpu_percent()
                    self.status[name].memory_mb = proc.memory_info().rss / 1024 / 1024
                except:
                    pass
                
                await asyncio.sleep(0.1)
            
            # Process ended
            self.status[name].running = False
            self.status[name].exit_code = process.returncode
            logger.info(f"Process {name} ended with code {process.returncode}")
            
        except Exception as e:
            logger.error(f"Error monitoring process {name}: {e}")
            self.status[name].last_error = str(e)


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
        logger.info(f"Client connected from {client_ip}")
        
        # Kill QR code on first connection
        if self.first_connection and self.pm.qr_started:
            logger.info("First WebSocket connection received, stopping QR code display")
            self.pm.stop_process("qr")
            self.first_connection = False
        
        try:
            async for message in websocket:
                await self.handle_command(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_ip} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_ip}: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def handle_command(self, websocket, message: str):
        """Process incoming commands."""
        try:
            cmd = json.loads(message)
            cmd_type = cmd.get("type")
            
            if cmd_type == "deploy_policy":
                policy_name = cmd.get("policy_name", "default")
                args = cmd.get("args", [])
                cmd_list = ["kbot-deploy", policy_name] + args
                success = self.pm.start_process("policy", cmd_list, priority=-5)
                
                await websocket.send(json.dumps({
                    "type": "response",
                    "command": "deploy_policy",
                    "success": success,
                    "policy_name": policy_name
                }))
            
            elif cmd_type == "start_gstreamer":
                cmd_list = ["python", "gstreamer.py"]
                success = self.pm.start_process("gstreamer", cmd_list, cwd=".")
                
                await websocket.send(json.dumps({
                    "type": "response", 
                    "command": "start_gstreamer",
                    "success": success
                }))
            
            elif cmd_type == "stop":
                process_name = cmd.get("name")
                success = self.pm.stop_process(process_name)
                
                await websocket.send(json.dumps({
                    "type": "response",
                    "command": "stop",
                    "name": process_name,
                    "success": success
                }))
            
            elif cmd_type == "send_input":
                process_name = cmd.get("name", "policy")
                input_str = cmd.get("input", "")
                success = self.pm.send_input(process_name, input_str)
                
                await websocket.send(json.dumps({
                    "type": "response",
                    "command": "send_input",
                    "success": success
                }))
            
            elif cmd_type == "status":
                status = self.pm.get_status()
                
                await websocket.send(json.dumps({
                    "type": "status",
                    "data": status
                }))
            
            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Unknown command: {cmd_type}"
                }))
                
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid JSON"
            }))
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            await websocket.send(json.dumps({
                "type": "error",
                "message": str(e)
            }))


async def main():
    """Main master process loop."""
    logger.info("Starting K-Bot Master Process")
    
    # Initialize process manager
    process_manager = ProcessManager()
    
    # Start QR code display on startup
    logger.info("Starting QR code display...")
    qr_success = process_manager.start_process(
        "qr", 
        ["python", "startup/qr_code.py"], 
        cwd="."
    )
    if qr_success:
        process_manager.qr_started = True
        logger.info("QR code display started successfully")
    else:
        logger.error("Failed to start QR code display")
    
    # Set up signal handlers for cleanup
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        process_manager.cleanup_all()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize WebSocket handler
    ws_handler = WebSocketHandler(process_manager)
    
    # Start WebSocket server
    logger.info("Starting WebSocket server on port 8764")
    server = await websockets.serve(
        ws_handler.handle_client,
        "0.0.0.0",
        8764,
        ping_interval=30,
        ping_timeout=10
    )
    
    logger.info("Master process ready, waiting for connections...")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    finally:
        process_manager.cleanup_all()
        logger.info("Master process stopped")


if __name__ == "__main__":
    asyncio.run(main())
