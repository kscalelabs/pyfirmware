# Kbot Firmware

From scratch barebones firmware rewrite in python. Intent is to keep it small, around 1k lines of code. Previous versions were 10x bigger. Minimize complexity --> Minimize bugs.

### Control loop overview
Loop runs at 50hz. Roundtrip time is around 4.5ms, after which it waits 15.5ms to get to 50hz.

Loop:
   - Read sensor values from actuators, imu, etc
   - Forward pass through policy network
   - Send policy actions to motors

### Installation
```bash
# create/update conda env
make setup

# activate environment
conda activate firmware

# install package for end users
pip install .
```

### Usage
```bash
# sine wave actuator test
kbot-sine

# run policy on bot
kbot-run <path-to-policy.kinfer>
```

### Dev usage (internal)
```bash
# deploy and run on robot
scripts/deploy.sh <path-to-policy.kinfer> [keyboard|udp]
```

### Alternative manual install
```bash
conda env create -n firmware -f environment.yml
conda activate firmware
pip install .
```

### Development setup
```bash
# create/update conda env
make setup
conda activate firmware

# install in editable mode with dev extras
pip install -e .[dev]
```
