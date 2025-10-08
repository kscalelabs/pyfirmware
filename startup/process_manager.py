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
                "cmd": ["python3", "startup/display.py"],
                "cwd": None,
                "priority": None
            },
            "qr": {
                "cmd": ["python3", "startup/qr_code.py"],
                "cwd": None,
                "priority": None
            },
            "camera": {
                "cmd": ["python3", "firmware/gstreamer.py"],
                "cwd": None,
                "priority": None
            }
        }
        
    def start_process(self, name: str) -> bool:
        """Start a subprocess by name. Name must be one of: display, qr, camera."""
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
            cwd = config["cwd"]
            priority = config["priority"]
            
            # Prepare environment
            env = os.environ.copy()
            if priority is not None:
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
        """Monitor process output and status."""
        try:
            while process.poll() is None and self.running:
                # Read output (non-blocking)
                try:
                    line = process.stdout.readline()
                    if line:
                        print(line)
                        pass  # Output available but not logging
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
            print(f"Process {name} ended with code {process.returncode}")
            
        except Exception as e:
            print(f"Error monitoring process {name}: {e}")
            self.status[name].last_error = str(e)

