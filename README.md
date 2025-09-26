# firmware

From scratch barebones python firmware rewrite. Intent is to keep it small, around 1k lines of code. Previous versions were 10x bigger. Minimize complexity --> Minimize bugs.


### Entrypoint:
```bash
scripts/deploy.sh
```

### Sinewave test:
Test the CAN buses by running a slow sinewave command at 10% pd gains on all joints
```bash
python firmware/can.py
```
