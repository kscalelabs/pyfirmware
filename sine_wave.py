import math
import socket
import time
import json
from firmware.actuators import RobotConfig

# Mapping from command names to actuator names
mapping = {
    "rshoulderpitch": "dof_right_shoulder_pitch_03",
    "rshoulderroll": "dof_right_shoulder_roll_03",
    "rshoulderyaw": "dof_right_shoulder_yaw_02",
    "relbowpitch": "dof_right_elbow_02",
    "rwristroll": "dof_right_wrist_00",
    "rgripper": "dof_right_wrist_gripper_05",
    "lshoulderpitch": "dof_left_shoulder_pitch_03",
    "lshoulderroll": "dof_left_shoulder_roll_03",
    "lshoulderyaw": "dof_left_shoulder_yaw_02",
    "lelbowpitch": "dof_left_elbow_02",
    "lwristroll": "dof_left_wrist_00",
    "lgripper": "dof_left_wrist_gripper_05",
}

# Get robot configuration and home positions
robot_config = RobotConfig()
home_positions = robot_config.home_positions

# Create home position command dictionary
command_home = dict()
print(home_positions)
for command_name, actuator_name in mapping.items():
    angle = home_positions[actuator_name]
    command_home[command_name] = angle

# UDP settings
UDP_HOST = "127.0.0.1"  # Localhost
UDP_PORT = 10000

def send_udp_command(commands):
    """Send UDP command to the robot."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Format message as expected by UDP listener
        message = json.dumps({"commands": commands})
        sock.sendto(message.encode('utf-8'), (UDP_HOST, UDP_PORT))
    finally:
        sock.close()

def sine_wave_motion():
    """Generate sine wave motion around home position."""
    print("Starting sine wave motion...")
    print("Press Ctrl+C to stop")
    
    # Send home position first
    print("Moving to home position...")
    send_udp_command(command_home)
    time.sleep(2)  # Wait for robot to reach home position
    
    # Sine wave parameters
    amplitude = math.radians(10)  # 10 degrees amplitude
    frequency = 0.5  # 0.5 Hz (2 second period)
    
    print(f"Starting sine wave on all joints with ±10° amplitude")
    
    try:
        start_time = time.time()
        while True:
            # Calculate current time
            current_time = time.time() - start_time
            
            # Create command with sine wave applied to all joints
            current_command = {}
            for joint_name, home_angle in command_home.items():
                # Calculate sine wave value for this joint
                sine_value = amplitude * math.sin(2 * math.pi * frequency * current_time)
                
                # Calculate new angle (home + sine wave)
                new_angle = home_angle + sine_value
                current_command[joint_name] = new_angle
            
            # Send command
            send_udp_command(current_command)
            
            # Print current time for debugging
            print(f"Time: {current_time:.2f}s")
            
            # Control loop frequency (50 Hz)
            time.sleep(0.02)
            
    except KeyboardInterrupt:
        print("\nStopping sine wave motion...")
        print("Returning to home position...")
        send_udp_command(command_home)
        time.sleep(1)
        print("Done!")

if __name__ == "__main__":
    sine_wave_motion()