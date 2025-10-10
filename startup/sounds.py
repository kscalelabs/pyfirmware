#!/usr/bin/env python3
"""
Sound playback system for K-Bot.
WebSocket server on port 8599 that accepts sound commands.
"""

import asyncio
import json
import os
import subprocess
import websockets
from pathlib import Path


class SoundPlayer:
    """Plays sounds on the specified audio device."""
    
    def __init__(self, card: int = 2, device: int = 0):
        self.audio_device = f"hw:{card},{device}"
        self.sound_dir = Path(__file__).parent / "sounds"
        self.sound_dir.mkdir(exist_ok=True)
        
        # Define sound file mappings
        self.sounds = {
            "hello": self.sound_dir / "hello.wav",
            "carhorn": self.sound_dir / "carhorn.mp3", 
            "sus": self.sound_dir / "sus.mp3"
        }
        
        print(f"Sound player initialized")
        print(f"Audio device: {self.audio_device}")
        print(f"Sound directory: {self.sound_dir}")
        
        # Check which sound files exist
        for name, path in self.sounds.items():
            if path.exists():
                print(f"  ✓ {name}: {path}")
            else:
                print(f"  ✗ {name}: {path} (missing)")
    
    async def play_sound(self, sound_name: str) -> bool:
        """Play a sound file asynchronously."""
        if sound_name not in self.sounds:
            print(f"Unknown sound: {sound_name}")
            return False
        
        sound_file = self.sounds[sound_name]
        
        if not sound_file.exists():
            print(f"Sound file not found: {sound_file}")
            return False
        
        try:
            print(f"Playing sound: {sound_name}")
            
            # Choose player based on file extension
            file_ext = sound_file.suffix.lower()
            
            if file_ext == ".mp3":
                # Use mpg123 for MP3 files
                process = await asyncio.create_subprocess_exec(
                    "mpg123",
                    "-a", self.audio_device,
                    "-q",  # quiet mode
                    str(sound_file),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
            elif file_ext == ".wav":
                # Use aplay for WAV files
                process = await asyncio.create_subprocess_exec(
                    "aplay",
                    "-D", self.audio_device,
                    str(sound_file),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
            else:
                print(f"Unsupported file format: {file_ext}")
                return False
            
            # Wait for playback to complete
            await process.wait()
            
            if process.returncode == 0:
                print(f"Finished playing: {sound_name}")
                return True
            else:
                print(f"Error playing {sound_name}: return code {process.returncode}")
                return False
                
        except Exception as e:
            print(f"Error playing sound {sound_name}: {e}")
            return False


class SoundWebSocketServer:
    """WebSocket server that accepts sound commands."""
    
    def __init__(self, port: int = 8599):
        self.port = port
        self.player = SoundPlayer(card=2, device=0)
        self.clients = set()
    
    async def handle_client(self, websocket):
        """Handle a WebSocket client connection."""
        self.clients.add(websocket)
        client_ip = websocket.remote_address[0]
        print(f"Client connected from {client_ip}")
        
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
        """Process incoming sound commands."""
        try:
            cmd = json.loads(message)
            print(f"Received command: {cmd}")
            
            sound = cmd.get("sound")
            
            # Play the sound
            success = await self.player.play_sound(sound)
            
            # Send response
            await websocket.send(json.dumps({
                "success": success,
                "sound": sound
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
    """Main entry point."""
    print("Starting K-Bot Sound System")
    server = SoundWebSocketServer(port=8599)
    
    try:
        print(f"Starting WebSocket server on port {server.port}...")
        async with websockets.serve(
            server.handle_client,
            "0.0.0.0",
            server.port,
            ping_interval=30,
            ping_timeout=10
        ):
            print(f"✓ Sound WebSocket server running on 0.0.0.0:{server.port}")
            print("  Available sounds: hello, bye, sus")
            print('  Send: {"sound": "hello|bye|sus"}')
            print()
            
            # Keep running
            await asyncio.Future()
            
    except OSError as e:
        print(f"Failed to start WebSocket server: {e}")
        print(f"Port {server.port} may already be in use")
        return
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())

