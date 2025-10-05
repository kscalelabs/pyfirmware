"""Defines motion sequences for robot arm movements."""

import math
from typing import Dict, List, Tuple
import numpy as np
import attrs

# Define the joint names and their default positions for KBOT
COMMANDS = [
    "xvel",
    "yvel",
    "yawrate",
]
POSITIONS = [
    "base_height",
    "base_roll",
    "base_pitch",
    "rshoulderpitch",
    "rshoulderroll", 
    "rshoulderyaw",
    "relbowpitch",
    "rwristroll",
    "lshoulderpitch",
    "lshoulderroll",
    "lshoulderyaw",
    "lelbowpitch",
    "lwristroll"
]


ACTION_SPACE_JOINT_LIMITS: dict[str, tuple[float, float]] = {
    "rshoulderpitch": (-3.490658, 1.047198),
    "rshoulderroll": (-1.658063-math.radians(10.0), 0.436332+math.radians(10.0)),
    "rshoulderyaw": (-1.671886, 1.671886),
    "relbowpitch": (0.0-math.radians(90.0), 2.478368+math.radians(90.0)),
    "rwristroll": (-1.37881, 1.37881),
    "lshoulderpitch": (-1.047198, 3.490658),
    "lshoulderroll": (-0.436332-math.radians(10.0), 1.658063+math.radians(10.0)),
    "lshoulderyaw": (-1.671886, 1.671886),
    "lelbowpitch": (-2.478368-math.radians(90.0), 0.0+math.radians(90.0)),
    "lwristroll": (-1.37881, 1.37881),
}

@attrs.define
class Keyframe:
    """A keyframe in a motion sequence."""
    time: float
    positions: Dict[str, float] = attrs.field(factory=dict)
    commands: Dict[str, float] = attrs.field(factory=dict)

class Motion:
    """Represents a sequence of arm motions with keyframes and interpolation."""
    
    def __init__(self, keyframes: List[Keyframe], dt: float):
        """Initialize a motion sequence.
        
        Args:
            keyframes: List of keyframes defining the motion
            dt: Time step for interpolation
        """
        self.keyframes = sorted(keyframes, key=lambda k: k.time)
        self.total_duration = self.keyframes[-1].time
        self.dt = dt
        self.current_time = 0.0
        
    def get_next_motion_frame(self) -> Dict[str, float] | None:
        """Get the next motion frame.
        
        Returns:
            Dictionary of all values,
            or None if sequence is complete
        """
        if self.current_time > self.total_duration:
            return None
            
        # Find surrounding keyframes
        next_idx = 0
        while (next_idx < len(self.keyframes) and 
               self.keyframes[next_idx].time < self.current_time):
            next_idx += 1
            
        # Get interpolated positions
        if next_idx == 0:
            positions = self.keyframes[0].positions.copy()
            commands = self.keyframes[0].commands.copy()
        elif next_idx >= len(self.keyframes):
            positions = self.keyframes[-1].positions.copy()
            commands = self.keyframes[-1].commands.copy()
        else:
            # Interpolate between keyframes
            prev_frame = self.keyframes[next_idx - 1]
            next_frame = self.keyframes[next_idx]
            
            alpha = ((self.current_time - prev_frame.time) / 
                    (next_frame.time - prev_frame.time))
            
            positions = {}
            for joint in POSITIONS:
                prev_pos = prev_frame.positions.get(joint, 0.0)
                next_pos = next_frame.positions.get(joint, 0.0)
                positions[joint] = prev_pos + alpha * (next_pos - prev_pos)
            
            # Use the previous keyframe's commands
            commands = prev_frame.commands.copy()
        
        # Convert to ordered numpy arrays
        all_values = {
            **{cmd: commands.get(cmd, 0.0) for cmd in COMMANDS},
            **{joint: positions.get(joint, 0.0) for joint in POSITIONS}
        }

        # clamp the values to the action space joint limits
        for joint, value in all_values.items():
            if joint in ACTION_SPACE_JOINT_LIMITS:
                all_values[joint] = max(ACTION_SPACE_JOINT_LIMITS[joint][0], min(ACTION_SPACE_JOINT_LIMITS[joint][1], value))
        
        self.current_time += self.dt
        return all_values
    
    def reset(self):
        """Reset the motion sequence to start."""
        self.current_time = 0.0

def create_test_motion(joint_name: str, dt: float = 0.01) -> Motion:
    """Creates a test motion for a joint: 0° -> -90° -> 90° -> 0°
    
    Args:
        joint_name: Name of the joint to test
        dt: Time step between frames
    """
    keyframes = [
        Keyframe(
            time=0.0,
            positions={joint_name: math.radians(0.0)},
            commands={}
        ),
        Keyframe(
            time=1.0,
            positions={joint_name: math.radians(-90.0)},
            commands={}
        ),
        Keyframe(
            time=2.0,
            positions={joint_name: math.radians(90.0)},
            commands={}
        ),
        Keyframe(
            time=3.0,
            positions={joint_name: math.radians(0.0)},
            commands={}
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_wave(dt: float = 0.01) -> Motion:
    """Creates a waving motion sequence."""
    keyframes = [
        Keyframe(
            time=0.0,
        ),
        Keyframe(
            time=0.5,
            positions={
                "rshoulderroll": math.radians(-45.0),
                "relbowpitch": math.radians(90.0),
            }
        ),
        Keyframe(
            time=1.0,
            positions={
                "rshoulderroll": math.radians(-45.0),
                "rshoulderyaw": math.radians(45.0),
                "relbowpitch": math.radians(90.0),
            }
        ),
        Keyframe(
            time=1.5,
            positions={
                "rshoulderroll": math.radians(-45.0),
                "rshoulderyaw": math.radians(-45.0),
                "relbowpitch": math.radians(90.0),
            }
        ),
        Keyframe(
            time=2.0,
            positions={
                "rshoulderroll": math.radians(-10.0),
                "relbowpitch": math.radians(90.0),
            }
        ),
        Keyframe(
            time=2.5,
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_salute(dt: float = 0.01) -> Motion:
    """Creates a saluting motion sequence."""
    keyframes = [
        Keyframe(
            time=0.0,
        ),
        Keyframe(
            time=0.6,
            positions={
                "rshoulderroll": math.radians(-90.0),
                "relbowpitch": math.radians(0.0),
            }
        ),
        Keyframe(
            time=1.1,
            positions={
                "rshoulderroll": math.radians(-90.0),
                "relbowpitch": math.radians(85.0),
            }
        ),
        Keyframe(
            time=2.1,
            positions={
                "rshoulderroll": math.radians(-90.0),
                "relbowpitch": math.radians(85.0),
            }
        ),
        Keyframe(
            time=2.6,
            positions={
                "rshoulderroll": math.radians(-10.0),
                "relbowpitch": math.radians(0.0),
            }
        ),
        Keyframe(
            time=3.0,
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_pickup(dt: float = 0.01) -> Motion:
    """Creates a pickup motion sequence."""
    keyframes = [
        Keyframe(
            time=0.0,
            positions={
                "rshoulderpitch": 0.0,
                "rshoulderroll": math.radians(10.0),
                "relbowpitch": 0.0,
                "rwristroll": 0.0,
                "lshoulderpitch": 0.0,
                "lshoulderroll": math.radians(-10.0),
                "lelbowpitch": 0.0,
                "lwristroll": 0.0,
            }
        ),
        Keyframe(
            time=0.5,
            positions={
                "rshoulderpitch": math.radians(-45.0),
                "rshoulderroll": math.radians(20.0),
                "relbowpitch": math.radians(-10.0),
                "rwristroll": 0.0,
                "lshoulderpitch": math.radians(45.0),
                "lshoulderroll": math.radians(-20.0),
                "lelbowpitch": math.radians(10.0),
                "lwristroll": 0.0,
                "base_pitch": math.radians(15.0),
            },
        ),
        Keyframe(
            time=1.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(20.0),
                "relbowpitch": math.radians(-45.0),
                "rwristroll": math.radians(20.0),
                "lshoulderpitch": math.radians(90.0),
                "lshoulderroll": math.radians(-20.0),
                "lelbowpitch": math.radians(45.0),
                "lwristroll": math.radians(-20.0),
                "base_height": -0.2,
                "base_pitch": math.radians(30.0),
            },
        ),
        Keyframe(
            time=1.3,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(20.0),
                "relbowpitch": math.radians(-90.0),
                "rwristroll": math.radians(30.0),
                "lshoulderpitch": math.radians(90.0),
                "lshoulderroll": math.radians(-20.0),
                "lelbowpitch": math.radians(90.0),
                "lwristroll": math.radians(-30.0),
                "base_height": -0.2,
                "base_pitch": math.radians(30.0),
            },
        ),
        Keyframe(
            time=1.8,
            positions={
                "rshoulderpitch": math.radians(-45.0),
                "rshoulderroll": math.radians(20.0),
                "relbowpitch": math.radians(-90.0),
                "rwristroll": math.radians(30.0),
                "lshoulderpitch": math.radians(45.0),
                "lshoulderroll": math.radians(-20.0),
                "lelbowpitch": math.radians(90.0),
                "lwristroll": math.radians(-30.0),
                "base_pitch": math.radians(15.0),
            },
        ),
        Keyframe(
            time=2.3,
            positions={
                "rshoulderpitch": 0.0,
                "rshoulderroll": math.radians(10.0),
                "relbowpitch": 0.0,
                "rwristroll": 0.0,
                "lshoulderpitch": 0.0,
                "lshoulderroll": math.radians(-10.0),
                "lelbowpitch": 0.0,
                "lwristroll": 0.0,
            },
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_wild_walk(dt: float = 0.01) -> Motion:
    """Creates a wild walking motion with extreme arm movements."""
    keyframes = [
        Keyframe(
            time=0.0,
            positions={
                "rshoulderpitch": 0.0,
                "rshoulderroll": 0.0,
                "rshoulderyaw": 0.0,
                "relbowpitch": 0.0,
                "lshoulderpitch": 0.0,
                "lshoulderroll": 0.0,
                "lshoulderyaw": 0.0,
                "lelbowpitch": 0.0,
            }
        ),
        Keyframe(
            time=1.0,
            positions={
                "rshoulderpitch": math.radians(-135.0),
                "rshoulderroll": math.radians(-90.0),
                "rshoulderyaw": math.radians(90.0),
                "relbowpitch": math.radians(120.0),
                "lshoulderpitch": math.radians(135.0),
                "lshoulderroll": math.radians(90.0),
                "lshoulderyaw": math.radians(-90.0),
                "lelbowpitch": math.radians(-120.0),
            },
            commands={
                "xvel": 0.5,
                "yvel": 0.0,
                "yawrate": 1.0,
            }
        ),
        Keyframe(
            time=2.0,
            positions={
                "rshoulderpitch": math.radians(90.0),
                "rshoulderroll": math.radians(45.0),
                "rshoulderyaw": math.radians(-90.0),
                "relbowpitch": math.radians(-90.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(-45.0),
                "lshoulderyaw": math.radians(90.0),
                "lelbowpitch": math.radians(90.0),
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.5,
                "yawrate": -1.0,
            }
        ),
        Keyframe(
            time=3.0,
            positions={
                "rshoulderpitch": math.radians(-180.0),
                "rshoulderroll": math.radians(-120.0),
                "rshoulderyaw": math.radians(180.0),
                "relbowpitch": math.radians(145.0),
                "lshoulderpitch": math.radians(180.0),
                "lshoulderroll": math.radians(120.0),
                "lshoulderyaw": math.radians(-180.0),
                "lelbowpitch": math.radians(-145.0),
            },
            commands={
                "xvel": 0.5,
                "yvel": -0.5,
                "yawrate": 2.0,
            }
        ),
        Keyframe(time=4.0),
    ]
    return Motion(keyframes, dt=dt)

def create_zombie_walk(dt: float = 0.01) -> Motion:
    """Creates a classic zombie shambling motion with stiff arms."""
    keyframes = [
        Keyframe(
            time=0.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(20.0),
                "rshoulderyaw": math.radians(90.0),
                "relbowpitch": math.radians(-90.0),
                "lshoulderpitch": math.radians(90.0),
                "lshoulderroll": math.radians(-20.0),
                "lshoulderyaw": math.radians(-90.0),
                "lelbowpitch": math.radians(90.0),
                "base_pitch": math.radians(15.0),
            },
            commands={
                "xvel": 0.2,
            }
        ),
        Keyframe(
            time=3.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(20.0),
                "rshoulderyaw": math.radians(90.0),
                "relbowpitch": math.radians(-90.0),
                "lshoulderpitch": math.radians(90.0),
                "lshoulderroll": math.radians(-20.0),
                "lshoulderyaw": math.radians(-90.0),
                "lelbowpitch": math.radians(90.0),
                "base_pitch": math.radians(15.0),
            },
            commands={
                "xvel": 0.2,
            }
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_pirouette(dt: float = 0.01) -> Motion:
    """Creates a graceful spinning pirouette motion."""
    keyframes = [
        Keyframe(
            time=0.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-90.0),
                "rshoulderyaw": 0.0,
                "relbowpitch": math.radians(30.0),
                "rwristroll": math.radians(-20.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(90.0),
                "lshoulderyaw": 0.0,
                "lelbowpitch": math.radians(-30.0),
                "lwristroll": math.radians(20.0),
                "base_height": 0.0,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 0.0,
            }
        ),
        # Preparation - rise and begin
        Keyframe(
            time=1.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-120.0),
                "rshoulderyaw": math.radians(45.0),
                "relbowpitch": math.radians(45.0),
                "rwristroll": math.radians(-30.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(120.0),
                "lshoulderyaw": math.radians(-45.0),
                "lelbowpitch": math.radians(-45.0),
                "lwristroll": math.radians(30.0),
                "base_height": 0.15,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 0.5,
            }
        ),
        # First rotation
        Keyframe(
            time=3.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-120.0),
                "rshoulderyaw": math.radians(45.0),
                "relbowpitch": math.radians(45.0),
                "rwristroll": math.radians(-30.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(120.0),
                "lshoulderyaw": math.radians(-45.0),
                "lelbowpitch": math.radians(-45.0),
                "lwristroll": math.radians(30.0),
                "base_height": 0.15,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 1.0,
            }
        ),
        # Second rotation - slightly faster
        Keyframe(
            time=5.0,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-120.0),
                "rshoulderyaw": math.radians(45.0),
                "relbowpitch": math.radians(45.0),
                "rwristroll": math.radians(-30.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(120.0),
                "lshoulderyaw": math.radians(-45.0),
                "lelbowpitch": math.radians(-45.0),
                "lwristroll": math.radians(30.0),
                "base_height": 0.15,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 1.2,
            }
        ),
        # Start slowing down
        Keyframe(
            time=6.5,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-120.0),
                "rshoulderyaw": math.radians(45.0),
                "relbowpitch": math.radians(45.0),
                "rwristroll": math.radians(-30.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(120.0),
                "lshoulderyaw": math.radians(-45.0),
                "lelbowpitch": math.radians(-45.0),
                "lwristroll": math.radians(30.0),
                "base_height": 0.15,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 0.5,
            }
        ),
        # Final pose
        Keyframe(
            time=7.5,
            positions={
                "rshoulderpitch": math.radians(-90.0),
                "rshoulderroll": math.radians(-90.0),
                "rshoulderyaw": 0.0,
                "relbowpitch": math.radians(30.0),
                "rwristroll": math.radians(-20.0),
                "lshoulderpitch": math.radians(-90.0),
                "lshoulderroll": math.radians(90.0),
                "lshoulderyaw": 0.0,
                "lelbowpitch": math.radians(-30.0),
                "lwristroll": math.radians(20.0),
                "base_height": 0.0,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 0.0,
            }
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_backflip(dt: float = 0.01) -> Motion:
    """Creates an attempted backflip motion using base height, pitch and counter-rotating arms."""
    keyframes = [
        # Start standing
        Keyframe(
            time=0.0,
            positions={
                "rshoulderpitch": 0.0,  # Arms neutral
                "lshoulderpitch": 0.0,
                "base_height": 0.0,
                "base_pitch": 0.0,
            }
        ),
        # Mid squat, arms starting to rise
        Keyframe(
            time=0.4,
            positions={
                "rshoulderpitch": math.radians(-45.0),  # Arms raising
                "lshoulderpitch": math.radians(45.0),
                "base_height": -0.15,
                "base_pitch": 0.0,
            }
        ),
        # Deep squat, arms forward
        Keyframe(
            time=0.8,
            positions={
                "rshoulderpitch": math.radians(-90.0),  # Arms forward
                "lshoulderpitch": math.radians(90.0),
                "base_height": -0.3,
                "base_pitch": 0.0,
            }
        ),
        Keyframe(
            time=1.2,
            positions={
                "rshoulderpitch": math.radians(-90.0),  # Arms forward
                "lshoulderpitch": math.radians(90.0),
                "base_height": -0.3,
                "base_pitch": 0.0,
            },
            commands={
                "xvel": 0.0,
                "yvel": 0.0,
                "yawrate": 0.0,
            }
        ),
        # Arms swing back hard as jump starts
        Keyframe(
            time=1.21,
            positions={
                "rshoulderpitch": math.radians(90.0),   # Arms back
                "lshoulderpitch": math.radians(-90.0),
                "base_height": 0.4,
                "base_pitch": math.radians(-50.0),
            }
        ),
        # Peak of jump, arms coming forward to drive flip
        Keyframe(
            time=1.4,
            positions={
                "rshoulderpitch": math.radians(135.0),  # Arms driving forward and down
                "lshoulderpitch": math.radians(-135.0),
                "base_height": 0.4,
                "base_pitch": math.radians(-180.0),
            }
        ),
        # Complete rotation, arms up to spot landing
        Keyframe(
            time=1.6,
            positions={
                "rshoulderpitch": math.radians(90.0),  # Arms up
                "lshoulderpitch": math.radians(-90.0),
                "base_height": 0.2,
                "base_pitch": math.radians(-340.0),
            }
        ),
        # Landing squat, arms forward for balance
        Keyframe(
            time=1.8,
            positions={
                "rshoulderpitch": math.radians(-45.0),  # Arms forward for balance
                "lshoulderpitch": math.radians(45.0),
                "base_height": -0.3,
                "base_pitch": math.radians(-360.0),
            }
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_boxing(dt: float = 0.01) -> Motion:
    """Creates a boxing motion sequence."""
    keyframes = [
        # Start neutral
        Keyframe(time=0.0),
        
        # Raise guard - walk forward
        Keyframe(
            time=0.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),  # Forward and up
                "rshoulderroll": math.radians(15.0),   # Slightly inward
                "rshoulderyaw": math.radians(30.0),    # Rotate in
                "relbowpitch": math.radians(30.0),         # Bent up
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),   # Forward and up
                "lshoulderroll": math.radians(-15.0),   # Slightly inward
                "lshoulderyaw": math.radians(-30.0),    # Rotate in
                "lelbowpitch": math.radians(-30.0),         # Bent up
                
                "base_pitch": math.radians(10.0),
            },
            commands={
                "xvel": 0.2,
            }
        ),
        # Hold guard
        Keyframe(
            time=1.8,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            }
        ),
        # Left punch land
        Keyframe(
            time=1.81,
            positions={
                # Right arm stays in guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm prepares punch
                "lshoulderpitch": math.radians(100.0),      # extend
                "lshoulderroll": math.radians(-15.0),    # Keep tight to body
                "lshoulderyaw": math.radians(-30.0),     # Natural rotation
                "lelbowpitch": math.radians(85.0),           # straight
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Left punch hold
        Keyframe(
            time=2.0,
            positions={
                # Right arm stays in guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm 
                "lshoulderpitch": math.radians(100.0),      # extend
                "lshoulderroll": math.radians(-15.0),    # Keep tight to body
                "lshoulderyaw": math.radians(-30.0),     # Natural rotation
                "lelbowpitch": math.radians(85.0),           # straight
                
                "base_pitch": math.radians(10.0),                  
            },
            commands={}
        ),
        # Return to guard
        Keyframe(
            time=2.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Hold guard briefly
        Keyframe(
            time=2.5,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Right punch land
        Keyframe(
            time=2.51,
            positions={
                # Right arm extends
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),
                
                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Right punch hold
        Keyframe(
            time=2.7,
            positions={
                # Right arm extended
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),
                
                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Return to guard and start sideways movement
        Keyframe(
            time=2.9,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={
                "yvel": 0.3,      # Start moving sideways
                "yawrate": -0.8,    # Start rotating
            }
        ),
        # stop movement, hold guard
        Keyframe(
            time=4.6,
            positions={
                # Maintain guard position during movement
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Right punch land
        Keyframe(
            time=4.61,
            positions={
                # Right arm extends
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),
                
                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # hold right punch
        Keyframe(
            time=4.8,
            positions={
                # Right arm extended
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),
                
                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # back to guard
        Keyframe(
            time=5.0,
            positions={
                # Right arm guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # left punch land
        Keyframe(
            time=5.01,
            positions={
                # Right arm guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),   
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm extends
                "lshoulderpitch": math.radians(100.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(85.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # left punch hold
        Keyframe(
            time=5.2,
            positions={
                # Right arm guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm extends
                "lshoulderpitch": math.radians(100.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(85.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # Final return to guard
        Keyframe(
            time=5.4,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),
                
                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),
                
                "base_pitch": math.radians(10.0),
            },
            commands={}
        ),
        # empty keyframe interpolate back to start
        Keyframe(
            time=5.6,
            positions={},
            commands={}
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_boxing_guard_hold(dt: float = 0.01) -> Motion:
    """Raise guard and hold without walking."""
    keyframes = [
        # Start neutral
        Keyframe(time=0.0),

        # Raise guard
        Keyframe(
            time=0.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),  # Forward and up
                "rshoulderroll": math.radians(15.0),   # Slightly inward
                "rshoulderyaw": math.radians(30.0),    # Rotate in
                "relbowpitch": math.radians(30.0),         # Bent up

                # Left arm
                "lshoulderpitch": math.radians(55.0),   # Forward and up
                "lshoulderroll": math.radians(-15.0),   # Slightly inward
                "lshoulderyaw": math.radians(-30.0),    # Rotate in
                "lelbowpitch": math.radians(-30.0),         # Bent up

                "base_pitch": math.radians(10.0),
            },
        ),

        # Hold guard for a few seconds
        Keyframe(
            time=3.0,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_boxing_left_punch(dt: float = 0.01) -> Motion:
    """Raise guard, throw left punch, return to guard. No walking."""
    keyframes = [
        # Start neutral
        Keyframe(time=0.0),

        # Raise guard
        Keyframe(
            time=0.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Hold guard
        Keyframe(
            time=1.8,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Left punch land
        Keyframe(
            time=1.81,
            positions={
                # Right arm stays in guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm extends
                "lshoulderpitch": math.radians(100.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(85.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Left punch hold
        Keyframe(
            time=2.0,
            positions={
                # Right arm stays in guard
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm extended
                "lshoulderpitch": math.radians(100.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(85.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Return to guard
        Keyframe(
            time=2.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Hold guard
        Keyframe(
            time=2.5,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_boxing_right_punch(dt: float = 0.01) -> Motion:
    """Raise guard, throw right punch, return to guard. No walking."""
    keyframes = [
        # Start neutral
        Keyframe(time=0.0),

        # Raise guard
        Keyframe(
            time=0.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Hold guard
        Keyframe(
            time=2.5,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Right punch land
        Keyframe(
            time=2.51,
            positions={
                # Right arm extends
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),

                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Right punch hold
        Keyframe(
            time=2.7,
            positions={
                # Right arm extended
                "rshoulderpitch": math.radians(-100.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(-85.0),

                # Left arm stays in guard
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Return to guard
        Keyframe(
            time=2.9,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),

        # Hold guard
        Keyframe(
            time=3.2,
            positions={
                # Right arm
                "rshoulderpitch": math.radians(-55.0),
                "rshoulderroll": math.radians(15.0),
                "rshoulderyaw": math.radians(30.0),
                "relbowpitch": math.radians(30.0),

                # Left arm
                "lshoulderpitch": math.radians(55.0),
                "lshoulderroll": math.radians(-15.0),
                "lshoulderyaw": math.radians(-30.0),
                "lelbowpitch": math.radians(-30.0),

                "base_pitch": math.radians(10.0),
            },
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_cone_motion(dt: float = 0.01) -> Motion:
    """Creates a conical motion by rotating base roll and pitch in a circular pattern."""
    # Parameters for the cone motion
    cone_angle = math.radians(15.0)  # Angle of the cone from vertical
    duration = 4.0  # Total duration of one complete motion
    
    keyframes = []
    num_keyframes = 16  # Number of points around the circle
    
    for i in range(num_keyframes + 1):  # +1 to close the circle
        t = (i / num_keyframes) * duration
        angle = (i / num_keyframes) * 2 * math.pi
        
        # Calculate roll and pitch to create circular motion
        roll = cone_angle * math.sin(angle)
        pitch = cone_angle * math.cos(angle)
        
        keyframes.append(
            Keyframe(
                time=t,
                positions={
                    "base_roll": roll,
                    "base_pitch": pitch,
                },
            )
        )
    
    return Motion(keyframes, dt=dt)

def create_come_at_me(dt: float = 0.01) -> Motion:
    """Opens arms into a slightly raised T-pose ("come at me bro"). No walking."""
    keyframes = [
        # Start neutral
        Keyframe(time=0.0),

        # Move to slightly raised T-pose
        Keyframe(
            time=0.6,
            positions={
                # Right arm (slightly above horizontal)
                "rshoulderpitch": 0.0,
                "rshoulderroll": math.radians(-100.0),
                "rshoulderyaw": 0.0,
                "relbowpitch": math.radians(10.0),

                # Left arm (slightly above horizontal)
                "lshoulderpitch": 0.0,
                "lshoulderroll": math.radians(100.0),
                "lshoulderyaw": 0.0,
                "lelbowpitch": math.radians(-10.0),

                # Neutral base
                "base_pitch": 0.0,
                "base_height": 0.0,
            },
        ),

        # Hold the pose
        Keyframe(
            time=3.0,
            positions={
                "rshoulderpitch": 0.0,
                "rshoulderroll": math.radians(-100.0),
                "rshoulderyaw": 0.0,
                "relbowpitch": math.radians(10.0),

                "lshoulderpitch": 0.0,
                "lshoulderroll": math.radians(100.0),
                "lshoulderyaw": 0.0,
                "lelbowpitch": math.radians(-10.0),

                "base_pitch": 0.0,
                "base_height": 0.0,
            },
        ),

        # Empty keyframe to interpolate back to start
        Keyframe(
            time=3.2,
            positions={},
            commands={},
        ),
    ]
    return Motion(keyframes, dt=dt)

def create_squats(dt: float = 0.01) -> Motion:
    """Creates a motion sequence of two squats."""
    keyframes = [
        Keyframe(
            time=0.0,
            positions={
                "base_height": 0.0,
            }
        ),
        Keyframe(
            time=1.0,
            positions={
                "base_height": -0.25,
            }
        ),
        Keyframe(
            time=1.5,
            positions={
                "base_height": -0.25,
            }
        ),
        Keyframe(
            time=2.5,
            positions={
                "base_height": 0.0,
            }
        ),
        Keyframe(
            time=3.0,
            positions={
                "base_height": 0.0,
            }
        ),
        Keyframe(
            time=4.0,
            positions={
                "base_height": -0.25,
            }
        ),
        Keyframe(
            time=4.5,
            positions={
                "base_height": -0.25,
            }
        ),
        Keyframe(
            time=5.5,
            positions={
                "base_height": 0.0,
                "base_pitch": 0.0,
            }
        ),
    ]
    return Motion(keyframes, dt=dt)


MOTIONS = {
    'wave': create_wave,
    'salute': create_salute,
    'pickup': create_pickup,
    'wild_walk': create_wild_walk,
    'zombie_walk': create_zombie_walk,
    'squats': create_squats,
    'pirouette': create_pirouette,
    'backflip': create_backflip,
    'boxing': create_boxing,
    'boxing_guard_hold': create_boxing_guard_hold,
    'boxing_left_punch': create_boxing_left_punch,
    'boxing_right_punch': create_boxing_right_punch,
    'come_at_me': create_come_at_me,
    'cone': create_cone_motion,
    # Test motions - automatically generate test functions for each joint
    **{
        f'test_{"".join(word[0].lower() for word in joint_name.split("_")[1:-1])}': 
            lambda dt=0.01, joint=joint_name: create_test_motion(joint, dt)
        for joint_name in POSITIONS[3:]
    }
}