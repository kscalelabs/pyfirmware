# Kbot Firmware

From scratch firmware rewrite in python. Intent is to keep it as small and as simple as possible. Minimize complexity --> Minimize bugs.

## Control loop overview
Loop runs at 50hz. Roundtrip time is around 4.5ms. We then wait 15.5ms to get to 50hz.

Loop:
   - Read sensor values from actuators, imu, etc
   - Forward pass through policy network
   - Send policy actions to motors

## Installation
```bash
git clone https://www.github.com/kscalelabs/pyfirmware
cd pyfirmware

make setup # installs conda env
conda activate firmware
pip install .
```

## Usage
Test the actuators with a simple sinewave at low pd gains:
```bash
kbot-sine
```

Run Kscale policies:
```bash
kbot-run
```

Run your policies:
```bash
POLICY_DIR=<your-policy-dir> kbot-run
```

## Commands
Kbot accepts keyboard (`wasd`) or UDP commands.

### Keyboard Control
| Key(s)    | Command         | Change    |
|-----------|----------------|-----------|
| `w` / `s` | x-vel         | ±0.1      |
| `a` / `d` | y-vel         | ±0.1      |
| `q` / `e` | yaw ω         | ±0.1      |
| `=` / `-` | base height   | ±0.05     |
| `r` / `f` | base roll     | ±0.1      |
| `t` / `g` | base pitch    | ±0.1      |
| `0`       | reset cmds    | 0         |
| `z`       | wave          | -         |
| `x`       | salute        | -         |
| `c`       | raise arms    | -         |
| `v`       | boxing guard  | -         |
| `b`       | left punch    | -         |
| `n`       | right punch   | -         |
| `i`       | base cone     | -         |



### UDP Control

Kbot accepts two types of UDP commands:
- Policy commands: for arm teleop while walking/standing
- Direct joint commands: for individual joint control like grippers or upper-body-only robots

⚠️  Direct joint commands override the full body controller and give you direct control.


#### 1. Policy Commands
| Command | Default |
|---------|---------|
| xvel | 0 |
| yvel | 0 |
| yawrate | 0 |
| baseheight | 0 |
| baseroll | 0 |
| basepitch | 0 |
| rshoulderpitch | 0 |
| rshoulderroll | 0 |
| rshoulderyaw | 0 |
| relbowpitch | 0 |
| rwristroll | 0 |
| lshoulderpitch | 0 |
| lshoulderroll | 0 |
| lshoulderyaw | 0 |
| lelbowpitch | 0 |
| lwristroll | 0 |


#### 2. Joint Commands

| Full Name |
|-----------|
| dof_left_shoulder_pitch_03 |
| dof_left_shoulder_roll_03 |
| dof_left_shoulder_yaw_02 |
| dof_left_elbow_02 |
| dof_left_wrist_00 |
| dof_left_wrist_gripper_05 |
| dof_right_shoulder_pitch_03 |
| dof_right_shoulder_roll_03 |
| dof_right_shoulder_yaw_02 |
| dof_right_elbow_02 |
| dof_right_wrist_00 |
| dof_right_wrist_gripper_05 |
| dof_left_hip_pitch_04 |
| dof_left_hip_roll_03 |
| dof_left_hip_yaw_03 |
| dof_left_knee_04 |
| dof_left_ankle_02 |
| dof_right_hip_pitch_04 |
| dof_right_hip_roll_03 |
| dof_right_hip_yaw_03 |
| dof_right_knee_04 |
| dof_right_ankle_02 |

#### Example
Send JSON-formatted UDP commands to port 10000 on localhost (127.0.0.1) or robot IP.
```json
{
   "type": "normal",
    "commands": {
        // Policy commands
        "xvel": 0.5,
        "yvel": 0.0,
        "yawrate": 0.0,
        "baseheight": 0.8,
        "baseroll": 0.0,
        "basepitch": 0.0,
        // Direct joint commands
        "dof_left_wrist_gripper_05": 0.57
    }
}
```
```json
{
    "type": "reset"
}
```



## Dev usage (internal use only)

⚠️ **WARNING: BETA POLICIES** ⚠️

Untested, unlabeled, incompatible policies that **WILL** break your bot:

```bash
kbot-deploy [--gstreamer] [--command-source keyboard|udp]
```




## Known bugs
- critical faults raise an error, stopping the firmware, rather than gracefully handling
