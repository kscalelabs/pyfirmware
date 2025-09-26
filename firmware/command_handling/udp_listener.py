import json
import socket

from command_handling.command_interface import CommandInterface


class UDPListener(CommandInterface):
    """Listens for UDP commands and updates the command vector."""

    def __init__(self, port: int = 10000, host: str = "0.0.0.0"):
        super().__init__()
        self.port = port
        self.host = host
        self.sock = None
        self.start()

    def _read_input(self) -> None:
        """Read UDP packets and update command vector."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
            self.sock.settimeout(0.1)
            
            while self._running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    command_data = json.loads(data.decode('utf-8'))
                    
                    if command_data.get('type') == 'reset':
                        self.reset_cmd()
                    else:
                        # Update commands
                        updates = command_data.get('commands', {})
                        for index_str, delta in updates.items():
                            index = int(index_str)
                            if 0 <= index < 16:
                                self.cmd[index] += float(delta)
                                self.cmd[index] = max(-0.3, min(0.3, self.cmd[index]))
                        
                except socket.timeout:
                    continue
                except Exception:
                    continue
                    
        except Exception:
            pass
        finally:
            if self.sock:
                self.sock.close()

    def stop(self) -> None:
        """Stop UDP listening."""
        super().stop()
        if self.sock:
            self.sock.close()
            self.sock = None
