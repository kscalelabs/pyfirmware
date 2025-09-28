# Kbot Firmware

From scratch barebones firmware rewrite in python. Intent is to keep it small, around 1k lines of code. Previous versions were 10x bigger. Minimize complexity --> Minimize bugs.

### Control loop overview
Loop runs at 50hz. Roundtrip time is around 4.5ms, after which it waits 15.5ms to get to 50hz.

Loop:
   - Read sensor values from actuators, imu, etc
   - Forward pass through policy network
   - Send policy actions to motors

### Installation:
```bash
conda activate klog
pip install -r firmware/requirements.txt
```

### Run policy on robot:
```bash
scripts/deploy.sh
```

### Sinewave test:
Test the CAN buses and actuators with a slow sinewave command at 10% pd gains on all joints
```bash
scripts/sine_wave_test.sh
```
