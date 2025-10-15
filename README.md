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
You can test the actuators with a simple sinewave test at low pd gains by running:
```bash
kbot-sine
```

To run your policy with keyboard control enabled:
```bash
kbot-run <path-to-policy.kinfer>
```
**Keybindings**

- `0` → reset cmd
- `w` / `s` → cmd[0] x-vel  +0.1 / −0.1
- `a` / `d` → cmd[1] y-vel  +0.1 / −0.1
- `q` / `e` → cmd[2] yaw ω  +0.1 / −0.1

- `=` / `-` → cmd[3] base height +0.05 / −0.05
- `r` / `f` → cmd[4] roll  +0.1 / −0.1
- `t` / `g` → cmd[5] pitch +0.1 / −0.1


## Dev usage (internal)
```bash
kbot-deploy [--gstreamer] [--command-source keyboard|udp]
```

## Alternative manual install
```bash
conda env create -n firmware -f environment.yml
conda activate firmware
pip install .
```

## Development setup
```bash
# create/update conda env
make setup
conda activate firmware

# install in editable mode with dev extras
pip install -e .[dev]
```

## Known bugs
- critical faults raise an error, stopping the firmware, rather than gracefully handling
