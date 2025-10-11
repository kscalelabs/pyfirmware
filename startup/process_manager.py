import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import websockets
from dataclasses import dataclass
from typing import Dict, Optional, Any
from pathlib import Path



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
        
        # Define available process options with their commands
        self.options = {
            "display": {
                "cmd": ["python3", "display.py"]
            },
            "qr": {
                "cmd": ["python3", "qr_code.py"]
            },
            "camera": {
                "cmd": ["python3", "../firmware/gstreamer.py"]
            },
            "sounds": {
                "cmd": ["python", "sounds.py"]
            },
            "download": {
                "cmd": ["bash", "download_kinfer_policies.sh"]
            },
            "run_policy": {
                "cmd": ["python", "-m", "firmware.main", "--websocket"],
                "cwd": str(Path(__file__).parent.parent.absolute())  # jack-dev directory
            }
        }
    
    def start_process(self, name: str) -> bool:
        """Start a subprocess by name. Name must be one of: display, qr, camera, sounds, download, run_policy."""
        try:
            # Validate name
            if name not in self.options:
                print(f"Invalid process name: {name}. Must be one of: {list(self.options.keys())}")
                return False
            
            if name in self.processes and self.processes[name].poll() is None:
                print(f"Process {name} is already running")
                return False
            
            # Get process configuration
            config = self.options[name]
            cmd = config["cmd"]
            
            # Set working directory - use config's cwd if specified, otherwise startup folder
            cwd = config.get("cwd", str(Path(__file__).parent.absolute()))
            
            # Prepare environment
            env = os.environ.copy()
            # Start process
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                preexec_fn=None
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
            
            print(f"Started process {name} (PID: {process.pid})")
            
            # Start monitoring task
            asyncio.create_task(self._monitor_process(name, process))
            
            return True
            
        except Exception as e:
            print(f"Failed to start process {name}: {e}")
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
            print(f"Process {name} not found")
            return False
        print(f"Stopping process {name}")
        process = self.processes[name]
        
        try:
            # Try graceful shutdown first
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f"Process {name} didn't stop gracefully, force killing")
                process.kill()
                process.wait()
            
            # Update status
            if name in self.status:
                self.status[name].running = False
                self.status[name].exit_code = process.returncode
            
            del self.processes[name]
            print(f"Stopped process {name}")
            
            return True
            
        except Exception as e:
            print(f"Error stopping process {name}: {e}")
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
            print(f"Failed to send input to {name}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all processes."""
        status_dict = {}
        
        # Include all possible processes, even if not started yet
        for name in self.options.keys():
            if name in self.status:
                status = self.status[name]
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
            else:
                # Process has never been started
                status_dict[name] = {
                    'running': False,
                    'pid': None,
                    'start_time': None,
                    'exit_code': None,
                    'last_error': None,
                    'uptime': 0,
                    'cpu_percent': 0.0,
                    'memory_mb': 0.0
                }
        
        return status_dict
    
    def cleanup_all(self):
        """Stop all processes and cleanup."""
        print("Cleaning up all processes")
        for name in list(self.processes.keys()):
            self.stop_process(name, timeout=5)
        self.running = False
    
    def _set_process_priority(self, priority: int):
        """Set process priority (requires root)."""
        def set_priority():
            try:
                os.nice(priority)
            except PermissionError:
                print(f"Failed to set priority {priority} (requires root)")
        return set_priority
    
    async def _monitor_process(self, name: str, process: subprocess.Popen):
        """Monitor if process is alive."""
        try:
            # Just wait for process to end
            while process.poll() is None and self.running:
                await asyncio.sleep(1.0)
            
            # Process ended
            self.status[name].running = False
            self.status[name].exit_code = process.returncode
            print(f"Process '{name}' ended (exit code: {process.returncode})")
            
        except Exception as e:
            print(f"Error monitoring process {name}: {e}")
            self.status[name].last_error = str(e)

