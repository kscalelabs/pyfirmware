# qr_display.py
import qrcode
from PIL import Image
import pygame
from dotenv import load_dotenv
import os
import signal
import sys

# Replace with your ID and secret
load_dotenv()
user_id = os.getenv('ROBOT_ID')
secret_key = os.getenv('AUTH_TOKEN')
ip_address = os.getenv('MY_IP')

# Combine them into a string (you can use JSON or any format)
data = f"{user_id}:{secret_key}:{ip_address}"

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    shutdown_requested = True
    pygame.quit()
    sys.exit(0)

def create_display():
    """Create the main display with background image and QR code overlay using pygame"""
    # Set up pygame for console mode (same as DisplayManager)
    os.environ.setdefault("SDL_VIDEODRIVER", "KMSDRM")
    os.environ.setdefault("SDL_KMSDRM_DEVICE", "/dev/dri/card0")
    os.environ.setdefault("SDL_RENDER_DRIVER", "software")
    
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen_width, screen_height = screen.get_size()
    
    # Load and process the background image
    bg_surface = None
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bg_image_path = os.path.join(script_dir, "hello.webp")
        bg_image = Image.open(bg_image_path)
        
        # Calculate scaling to fit the image optimally while maintaining aspect ratio
        img_width, img_height = bg_image.size
        scale_w = screen_width / img_width
        scale_h = screen_height / img_height
        scale = min(scale_w, scale_h)  # Use the smaller scale to ensure it fits
        
        # Resize the image
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        bg_image = bg_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert PIL image to pygame surface
        bg_surface = pygame.image.fromstring(
            bg_image.tobytes(), bg_image.size, bg_image.mode
        )
        
    except FileNotFoundError:
        bg_surface = None
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=9,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create QR code with explicit RGB mode
    qr_img = qr.make_image(fill_color="white", back_color="black").convert('RGB')
    
    # Convert QR code to pygame surface
    qr_surface = pygame.image.fromstring(
        qr_img.tobytes(), qr_img.size, qr_img.mode
    )
    
    # Position QR code in top right with margins
    qr_width, qr_height = qr_surface.get_size()
    margin = 20
    qr_x = screen_width - qr_width - margin
    qr_y = margin
    
    # Ensure coordinates are valid
    if qr_x < 0:
        qr_x = margin
    if qr_y < 0:
        qr_y = margin
    
    # Create text surface
    text = "Scan the QR code inside the app to connect"
    
    # Try to use a system font, fallback to default if not available
    try:
        font_size = 36
        font = pygame.font.Font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        try:
            font = pygame.font.Font("arial.ttf", 72)
        except (OSError, IOError):
            font = pygame.font.Font(None, 72)  # Default font
    
    text_surface = font.render(text, True, (255, 255, 255))  # White text
    
    # Calculate position for centered text at bottom
    text_width, text_height = text_surface.get_size()
    text_x = (screen_width - text_width) // 2
    text_y = screen_height - text_height - 40  # 40px margin from bottom
    
    return screen, bg_surface, qr_surface, (qr_x, qr_y), text_surface, (text_x, text_y)

# Register signal handler for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Create the display
screen, bg_surface, qr_surface, qr_pos, text_surface, text_pos = create_display()

# Main loop - display image permanently
clock = pygame.time.Clock()

try:
    while not shutdown_requested:
        # Handle events (minimal)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shutdown_requested = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    shutdown_requested = True
        
        # Clear screen with black
        screen.fill((0, 0, 0))
        
        # Draw background image (centered if available)
        if bg_surface is not None:
            bg_width, bg_height = bg_surface.get_size()
            bg_x = (screen.get_width() - bg_width) // 2
            bg_y = (screen.get_height() - bg_height) // 2
            screen.blit(bg_surface, (bg_x, bg_y))
        
        # Draw QR code in top right
        screen.blit(qr_surface, qr_pos)
        
        # Draw text at bottom
        screen.blit(text_surface, text_pos)
        
        # Update display
        pygame.display.flip()
        
        # Limit to 30 FPS (no need for high refresh rate for static display)
        clock.tick(30)
        
except KeyboardInterrupt:
    pass
finally:
    pygame.quit()