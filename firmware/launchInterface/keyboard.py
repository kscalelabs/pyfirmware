"""Keyboard-based launch interface for local robot control."""

import curses
import sys
from pathlib import Path
from typing import List, Optional

from firmware.launchInterface.launch_interface import LaunchInterface


def _curses_select_with_filter(stdscr: curses.window, items: List[Path]) -> Optional[Path]:
    curses.curs_set(1)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    query = ""
    sel_idx = 0
    scroll = 0

    def filtered() -> List[Path]:
        q = query.lower()
        if not q:
            return items
        return [p for p in items if q in p.stem.lower()]

    def clamp_sel() -> None:
        nonlocal sel_idx, scroll
        f = filtered()
        if not f:
            sel_idx = 0
            scroll = 0
            return
        sel_idx = max(0, min(sel_idx, len(f) - 1))
        h, w = stdscr.getmaxyx()
        list_rows = max(1, h - 3)  # 1 for search, 1 for header, 1 for padding
        # Keep selection within scroll window
        if sel_idx < scroll:
            scroll = sel_idx
        elif sel_idx >= scroll + list_rows:
            scroll = sel_idx - list_rows + 1

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # Search bar
        stdscr.addstr(0, 0, "Search: ")
        stdscr.clrtoeol()
        stdscr.addstr(0, 8, query[: max(0, w - 9)])

        # Header
        stdscr.addstr(1, 0, "Policies (↑/↓ to move, Enter to select, Esc to cancel)")
        stdscr.hline(2, 0, curses.ACS_HLINE, max(1, w - 1))

        # Render filtered list
        f = filtered()
        list_rows = max(1, h - 3)
        clamp_sel()
        view = f[scroll : scroll + list_rows]

        for i, p in enumerate(view):
            line_idx = 3 + i
            is_selected = (scroll + i) == sel_idx
            name = p.stem  # Remove .kinfer extension
            size_mb = p.stat().st_size / (1024 * 1024)
            text = f"{name}  ({size_mb:.2f} MB)"
            text = text[: max(1, w - 1)]
            if is_selected:
                stdscr.attron(curses.A_REVERSE)
            stdscr.addstr(line_idx, 0, text)
            stdscr.clrtoeol()
            if is_selected:
                stdscr.attroff(curses.A_REVERSE)

        # Empty state
        if not f:
            stdscr.addstr(4, 0, "No matches.")

        # Place cursor at end of query
        stdscr.move(0, 8 + len(query))
        stdscr.refresh()

        ch = stdscr.getch()

        # Enter
        if ch in (curses.KEY_ENTER, 10, 13):
            if f:
                return f[sel_idx]
            else:
                continue

        # Esc (cancel)
        if ch == 27:
            return None

        # Backspace (handle a few common codes)
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if query:
                query = query[:-1]
            continue

        # Up / Down / Page Up / Page Down / Home / End
        if ch == curses.KEY_UP:
            sel_idx -= 1
            clamp_sel()
            continue
        if ch == curses.KEY_DOWN:
            sel_idx += 1
            clamp_sel()
            continue
        if ch == curses.KEY_PPAGE:  # Page Up
            sel_idx -= max(1, list_rows - 1)
            clamp_sel()
            continue
        if ch == curses.KEY_NPAGE:  # Page Down
            sel_idx += max(1, list_rows - 1)
            clamp_sel()
            continue
        if ch == curses.KEY_HOME:
            sel_idx = 0
            clamp_sel()
            continue
        if ch == curses.KEY_END:
            if filtered():
                sel_idx = len(filtered()) - 1
                clamp_sel()
            continue

        # Typing (printable chars)
        if 32 <= ch <= 126:
            query += chr(ch)
            clamp_sel()
            continue


class KeyboardLaunchInterface(LaunchInterface):
    """Simple launch interface for keyboard control without network connection."""

    def __init__(self) -> None:
        """Initialize keyboard launch interface."""
        print("Using keyboard launch interface")

    def get_command_source(self) -> str:
        """Return the command source type."""
        while True:
            print("=================")
            print("Select command source: (k) Keyboard, (u) UDP")
            response = input("Enter choice: ").lower()
            print("=================")
            if response == "k":
                return "keyboard"
            elif response == "u":
                return "udp"
            print("Invalid choice. Please enter K or U")

    def ask_motor_permission(self, robot_devices: dict) -> bool:
        """Ask permission to enable motors. Returns True if should enable, False to abort."""
        print("----|--------------------------|-------|----------|--------|-------|-------")
        actuators = robot_devices["actuator_status"]
        print("\nActuator states:")
        print("ID  | Name                     | Angle | Velocity | Torque | Temp  | Faults")
        for act_id, data in actuators.items():
            fault_color = "\033[1;31m" if data["fault_flags"] > 0 else "\033[1;32m"
            print(
                f"{act_id:3d} | {data['name']:24s} | {data['angle']:5.2f} | {data['velocity']:8.2f} | "
                f"{data['torque']:6.2f} | {data['temperature']:5.1f} | {fault_color}{data['fault_flags']:3d}\033[0m"
            )
            if data["fault_flags"] > 0:
                print("\033[1;33mWARNING: Actuator faults detected\033[0m")
        print("IMU:" + robot_devices["imu"].__class__.__name__)
        while True:
            print("=================")
            print("Enable motors (y/n):")
            response = input("Enter choice: ").lower()
            print("=================")
            if response == "n":
                return False
            elif response == "y":
                return True
            print("Invalid input. Please enter 'y' or 'n'")

    def launch_policy_permission(self) -> bool:
        """Ask permission to start policy. Returns True if should start, False to abort."""
        while True:
            print("=================")
            print("🚀 Ready to start policy")

            print("Start policy? (y/n): ")
            response = input("Enter choice: ").lower()
            print("=================")
            if response == "y":
                return True
            elif response == "n":
                return False
            print("Invalid input. Please enter 'y' or 'n'")

    def get_kinfer_path(self, policy_dir_path: str) -> str:
        """TUI: live-search + arrow-key selection for .kinfer files."""
        policy_dir = Path(policy_dir_path)

        if not policy_dir.exists():
            print(f"Policy directory not found: {policy_dir}")
            sys.exit(1)
        if not policy_dir.is_dir():
            print(f"Path is not a directory: {policy_dir}")
            sys.exit(1)

        kinfer_files = sorted(policy_dir.glob("*.kinfer"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not kinfer_files:
            print(f"No .kinfer files found in {policy_dir}")
            sys.exit(1)

        selected = curses.wrapper(_curses_select_with_filter, kinfer_files)
        if not selected:
            print("No policy file selected")
            sys.exit(1)
        return str(selected)
