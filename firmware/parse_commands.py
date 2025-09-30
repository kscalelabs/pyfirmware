#!/usr/bin/env python3
"""
Parse commands.txt and display in a readable table format.
Shows frame number, timestamp, and all arm joint values.
"""

import sys

def parse_commands_file(filepath):
    """Parse commands.txt and print as a formatted table."""
    
    # Column names based on UDP listener mapping
    headers = [
        "Frame", "Time",
        "XVel", "YVel", "YawRate", 
        "BaseHeight", "BaseRoll", "BasePitch",
        "LShoulderPitch", "LShoulderRoll", "LElbowPitch", "LElbowRoll", "LWristRoll", "LWristGripper",
        "RShoulderPitch", "RShoulderRoll", "RElbowPitch", "RElbowRoll", "RWristRoll", "RWristGripper"
    ]
    
    # Print header
    print(f"{'Frame':>6} {'Time':>10} " + " ".join(f"{h:>10}" for h in headers[2:]))
    print("-" * (6 + 10 + 10 * len(headers[2:])))
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                values = line.strip().split()
                if len(values) < 20:
                    continue
                
                frame = values[0]
                time = values[1]
                data = values[2:20]  # 18 values
                
                # Format and print row
                print(f"{frame:>6} {float(time):>10.6f} " + " ".join(f"{float(v):>10.6f}" for v in data))
                
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "/tmp/commands.txt"
    
    parse_commands_file(filepath)

