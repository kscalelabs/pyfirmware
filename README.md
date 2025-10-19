# Kbot Firmware - Upper Body Branch

This branch solves the upper body control problem by providing direct actuator control without policy dependencies. It's designed for testing and development of upper body movements.

## Branch Information

This branch is based on: https://github.com/kscalelabs/pyfirmware/tree/upper-body

## Overview

This firmware provides:
- Direct actuator control without policy networks
- UDP command interface for external control
- Simple sine wave motion testing
- Integration with VR teleop visualization

## Installation

```bash
git clone https://github.com/kscalelabs/pyfirmware.git
cd pyfirmware
git checkout upper-body

make setup # installs conda env
conda activate firmware
pip install .
```

## Usage

### Starting the Actuators

To start the actuator control system:

```bash
kbot-run
```

Or alternatively:
```bash
python main.py
```

This will start the actuator control loop at 50Hz and listen for UDP commands on port 10000.

### Testing with Sine Wave Motion

To test the actuators with a sine wave motion:

```bash
python sine_wave.py
```

This will apply ±10° sine wave motion to all joints


### Command Format

The system accepts UDP commands in JSON format:

```json
{
  "commands": {
    "rshoulderpitch": 0,
    "rshoulderroll": 0,
    "relbowpitch": 0,
    "rwristroll": 0,
    "rgripper": 0,
    "lshoulderpitch": 0,
    "lshoulderroll": 0,
    "lshoulderyaw": 0,
    "lelbowpitch": 0,
    "lwristroll": 0,
    "lgripper": 0
  }
}
```

## Testing with VR Teleop Visualizer

Before sending commands to the physical robot, it's recommended to test using the rerun visualizer from the VR teleop project:

1. Clone the VR teleop repository:
   ```bash
   git clone https://github.com/kscalelabs/kbot_vr_teleop.git
   ```

2. Use the rerun visualizer to visualize your commands before sending them to the robot

## Joint Mapping

The system uses the following joint mapping:

| Command Name | Actuator Name |
|--------------|---------------|
| rshoulderpitch | dof_right_shoulder_pitch_03 |
| rshoulderroll | dof_right_shoulder_roll_03 |
| rshoulderyaw | dof_right_shoulder_yaw_02 |
| relbowpitch | dof_right_elbow_02 |
| rwristroll | dof_right_wrist_00 |
| rgripper | dof_right_wrist_gripper_05 |
| lshoulderpitch | dof_left_shoulder_pitch_03 |
| lshoulderroll | dof_left_shoulder_roll_03 |
| lshoulderyaw | dof_left_shoulder_yaw_02 |
| lelbowpitch | dof_left_elbow_02 |
| lwristroll | dof_left_wrist_00 |
| lgripper | dof_left_wrist_gripper_05 |

## Control Loop

The control loop runs at 50Hz:
- Reads sensor values from actuators
- Processes UDP commands
- Sends actuator commands to motors
- Waits for next cycle

## Development

### Manual Installation
```bash
conda env create -n firmware -f environment.yml
conda activate firmware
pip install .
```

### Development Setup
```bash
# create/update conda env
make setup
conda activate firmware

# install in editable mode with dev extras
pip install -e .[dev]
```

## Safety Notes

- Always test commands with the visualizer before sending to physical robot
- Use Ctrl+C to safely stop motion and return to home position
- Monitor robot behavior during testing