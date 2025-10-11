import os
import signal
import time
import random
import pygame

class DisplayManager:
    def __init__(self):
        """Fullscreen face with occasional blink, no threads."""

        # Prefer KMSDRM on console boots; comment these on desktop if you like
        os.environ.setdefault("SDL_VIDEODRIVER", "KMSDRM")
        os.environ.setdefault("SDL_KMSDRM_DEVICE", "/dev/dri/card0")
        os.environ.setdefault("SDL_RENDER_DRIVER", "software")  # avoid EGL hassles

        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        info = pygame.display.Info()
        self.w, self.h = info.current_w, info.current_h

        # In case Plymouth is still up
        os.system("plymouth quit >/dev/null 2>&1")

        # Load assets
        self.face = self._load_scaled("face.png")
        self.blink = self._load_scaled("blink.png")

        # Blink state
        self.blink_duration = 0.25
        self._schedule_next_blink()

        # Fallback color cycle (only if face missing)
        self.colors = [(255,0,0),(0,255,0),(0,0,255),(255,255,255)]
        self.ci = 0
        self.last_cycle = time.perf_counter()
        self.cycle_interval = 0.5

    def _assets_dir(self):
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(os.path.dirname(here), "face_assets")

    def _load_scaled(self, name):
        path = os.path.join(self._assets_dir(), name)
        if not os.path.exists(path):
            print(f"Warning: missing {path}")
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(img, (self.w, self.h))
        except Exception as e:
            print(f"Error loading {name}: {e}")
            return None

    def _schedule_next_blink(self):
        now = time.perf_counter()
        self.next_blink_time = now + random.randint(1, 10)   # wait 1–30s
        self.blink_end_time = None

    def update(self):
        # keep SDL responsive
        pygame.event.pump()
        now = time.perf_counter()

        # Blink state machine (no threads)
        show_blink = False
        if self.blink is not None:
            if self.blink_end_time is None:
                # Not blinking right now
                if now >= self.next_blink_time:
                    self.blink_end_time = now + self.blink_duration
                    show_blink = True
                else:
                    show_blink = False
            else:
                # Currently blinking
                show_blink = True
                if now >= self.blink_end_time:
                    self.blink_end_time = None
                    self._schedule_next_blink()

        # Draw
        self.screen.fill((0, 0, 0))
        if show_blink and self.blink is not None:
            self.screen.blit(self.blink, (0, 0))
        elif self.face is not None:
            self.screen.blit(self.face, (0, 0))
        else:
            # Fallback color cycle if assets missing
            if now - self.last_cycle >= self.cycle_interval:
                self.ci = (self.ci + 1) % len(self.colors)
                self.last_cycle = now
            self.screen.fill(self.colors[self.ci])

        pygame.display.flip()

    def close(self):
        pygame.quit()


def main():
    print("Starting Face")
    dm = DisplayManager()
    
    # Flag for graceful shutdown
    shutdown_requested = [False]  # Using list so it can be modified in closure
    
    def signal_handler(signum, frame):
        print(f"Received signal {signum}, shutting down gracefully...")
        shutdown_requested[0] = True
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        while not shutdown_requested[0]:
            dm.update()
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        print("Closing display...")
        dm.close()

if __name__ == "__main__":
    main()
