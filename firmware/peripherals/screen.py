"""Ultra-simple face display - just shows face.png."""

import os
import pygame
from pathlib import Path
from typing import Optional


class ScreenDisplay:
    """Manages pygame face display with proper state management."""
    
    def __init__(self):
        """Initialize screen display manager."""
        self.screen: Optional[pygame.Surface] = None
        self.initialized: bool = False
    
    def start(self) -> bool:
        """Start displaying face.png."""
        # Don't reinitialize if already running
        if self.initialized:
            print("Screen already initialized")
            return True
        
        try:
            # Setup display
            os.environ.setdefault("SDL_VIDEODRIVER", "KMSDRM")
            os.environ.setdefault("SDL_KMSDRM_DEVICE", "/dev/dri/card0")
            os.environ.setdefault("SDL_RENDER_DRIVER", "software")
            
            pygame.init()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.initialized = True
            
            # Load and display face
            assets_dir = Path(__file__).parent.parent / "images"
            face_path = assets_dir / "face.png"
            
            if face_path.exists():
                face_image = pygame.image.load(str(face_path))
                
                # Scale to fit screen
                screen_width, screen_height = self.screen.get_size()
                img_width, img_height = face_image.get_size()
                scale = min(screen_width / img_width, screen_height / img_height) * 0.8
                
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                face_image = pygame.transform.scale(face_image, (new_width, new_height))
                
                # Draw centered
                self.screen.fill((0, 0, 0))
                img_x = (screen_width - new_width) // 2
                img_y = (screen_height - new_height) // 2
                self.screen.blit(face_image, (img_x, img_y))
                pygame.display.flip()
                
                print("Face displayed")
                return True
            else:
                print(f"Face image not found: {face_path}")
                # Clean up if image not found
                pygame.quit()
                self.screen = None
                self.initialized = False
                return False
                
        except Exception as e:
            print(f"Error starting face display: {e}")
            # Clean up on error
            if self.initialized:
                try:
                    pygame.quit()
                except:
                    pass
            self.screen = None
            self.initialized = False
            return False
    
    def stop(self) -> bool:
        """Stop face display."""
        if not self.initialized:
            print("Screen not initialized, nothing to stop")
            return True
        
        try:
            pygame.quit()
            self.screen = None
            self.initialized = False
            print("Face display stopped")
            return True
        except Exception as e:
            print(f"Error stopping face display: {e}")
            self.screen = None
            self.initialized = False
            return False
    
    def is_running(self) -> bool:
        """Check if screen is currently running."""
        return self.initialized