"""Ultra-simple face display - just shows face.png."""

import os
import pygame
from pathlib import Path


def start():
    """Start displaying face.png."""
    try:
        # Setup display
        os.environ.setdefault("SDL_VIDEODRIVER", "KMSDRM")
        os.environ.setdefault("SDL_KMSDRM_DEVICE", "/dev/dri/card0")
        os.environ.setdefault("SDL_RENDER_DRIVER", "software")
        
        pygame.init()
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        
        # Load and display face
        assets_dir = Path(__file__).parent.parent.parent / "assets"
        face_path = assets_dir / "face.png"
        
        if face_path.exists():
            face_image = pygame.image.load(str(face_path))
            
            # Scale to fit screen
            screen_width, screen_height = screen.get_size()
            img_width, img_height = face_image.get_size()
            scale = min(screen_width / img_width, screen_height / img_height) * 0.8
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            face_image = pygame.transform.scale(face_image, (new_width, new_height))
            
            # Draw centered
            screen.fill((0, 0, 0))
            img_x = (screen_width - new_width) // 2
            img_y = (screen_height - new_height) // 2
            screen.blit(face_image, (img_x, img_y))
            pygame.display.flip()
            
            print("Face displayed")
            return True
        else:
            print(f"Face image not found: {face_path}")
            return False
            
    except Exception as e:
        print(f"Error starting face display: {e}")
        return False


def stop():
    """Stop face display."""
    try:
        pygame.quit()
        print("Face display stopped")
        return True
    except Exception as e:
        print(f"Error stopping face display: {e}")
        return False