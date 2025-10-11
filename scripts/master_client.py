#!/usr/bin/env python3
"""
Client for K-Bot Master Process WebSocket interface.
Provides command-line interface to control the master process.
"""

import asyncio
import json
import argparse
import websockets
import sys


class MasterClient:
    """Client for communicating with K-Bot Master Process."""
    
    def __init__(self, host="localhost", port=8766):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"
    
    async def send_command(self, command):
        """Send a command to the master process."""
        try:
            async with websockets.connect(self.uri) as websocket:
                await websocket.send(json.dumps(command))
                response = await websocket.recv()
                return json.loads(response)
        except Exception as e:
            return {"type": "error", "message": str(e)}
    
    async def deploy_policy(self, policy_name, args=None):
        """Deploy a policy."""
        command = {
            "type": "deploy_policy",
            "policy_name": policy_name,
            "args": args or []
        }
        return await self.send_command(command)
    
    async def start_gstreamer(self):
        """Start GStreamer process."""
        command = {"type": "start_gstreamer"}
        return await self.send_command(command)
    
    
    async def stop_process(self, name):
        """Stop a process."""
        command = {"type": "stop", "name": name}
        return await self.send_command(command)
    
    async def send_input(self, name, input_str):
        """Send input to a process."""
        command = {"type": "send_input", "name": name, "input": input_str}
        return await self.send_command(command)
    
    async def get_status(self):
        """Get status of all processes."""
        command = {"type": "status"}
        return await self.send_command(command)


async def main():
    parser = argparse.ArgumentParser(description="K-Bot Master Process Client")
    parser.add_argument("--host", default="localhost", help="Master process host")
    parser.add_argument("--port", type=int, default=8764, help="Master process port")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Deploy policy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy a policy")
    deploy_parser.add_argument("policy_name", help="Name of the policy to deploy")
    deploy_parser.add_argument("--args", nargs="*", help="Additional arguments")
    
    # Start gstreamer command
    subparsers.add_parser("start-gstreamer", help="Start GStreamer process")
    
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a process")
    stop_parser.add_argument("name", help="Name of the process to stop")
    
    # Send input command
    input_parser = subparsers.add_parser("input", help="Send input to a process")
    input_parser.add_argument("--name", default="policy", help="Process name")
    input_parser.add_argument("text", help="Input text to send")
    
    # Status command
    subparsers.add_parser("status", help="Get status of all processes")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    client = MasterClient(args.host, args.port)
    
    try:
        if args.command == "deploy":
            result = await client.deploy_policy(args.policy_name, args.args)
        elif args.command == "start-gstreamer":
            result = await client.start_gstreamer()
        elif args.command == "stop":
            result = await client.stop_process(args.name)
        elif args.command == "input":
            result = await client.send_input(args.name, args.text)
        elif args.command == "status":
            result = await client.get_status()
        
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
