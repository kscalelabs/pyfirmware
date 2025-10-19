# Kbot Firmware

From scratch firmware rewrite in python. Intent is to keep it as small and as simple as possible. Minimize complexity --> Minimize bugs.

## Control loop overview
Loop runs at 50hz. Roundtrip time is around 4.5ms, after which it waits 15.5ms to get to 50hz.

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

**Robot Control Keybindings**

| Key(s)    | Command         | Change    |
|-----------|-----------------|-----------|
| `w` / `s` | x-vel           | +0.1/-0.1 |
| `a` / `d` | y-vel           | +0.1/-0.1 |
| `q` / `e` | yaw ω           | +0.1/-0.1 |
| `=` / `-` | base height     | +0.05/-0.05 |
| `r` / `f` | base roll       | +0.1/-0.1 |
| `t` / `g` | base pitch      | +0.1/-0.1 |
| `0`       | reset cmds      | -         |


## Dev usage (internal use only)

⚠️ **WARNING: BETA POLICIES** ⚠️

Untested, unlabeled, incompatible policies that **WILL** break your bot:

```bash
kbot-deploy [--gstreamer] [--command-source keyboard|udp]
```

## Alternative manual installation
```bash
conda env create -n firmware -f environment.yml
conda activate firmware
pip install .
```


## Known bugs
- critical faults raise an error, stopping the firmware, rather than gracefully handling
