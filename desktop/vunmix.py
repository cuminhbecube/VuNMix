#!/usr/bin/env python3
"""
VuNMix Desktop — Main entry point.

A Python desktop companion for the VuNMix hardware audio mixer.
Controls Windows audio sessions and communicates with the ESP32-S3 via USB serial.

Usage:
    python vunmix.py              # Normal mode (system tray)
    python vunmix.py --debug      # Debug mode (verbose logging to console)
"""

import logging
import sys
import os

# Add the desktop directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AppConfig
from app_controller import AppController
from gui import TrayApp


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    fmt = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    logging.basicConfig(level=level, format=fmt, datefmt='%H:%M:%S')

    # Quiet noisy libraries
    logging.getLogger('comtypes').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)


def main():
    debug = '--debug' in sys.argv
    setup_logging(debug)

    log = logging.getLogger('vunmix')
    log.info("╔══════════════════════════════════════╗")
    log.info("║         VuNMix Desktop v0.1          ║")
    log.info("╚══════════════════════════════════════╝")

    # Load config
    config = AppConfig.load()
    log.info(f"COM Port: {config.com_port}")
    log.info(f"Sync Interval: {config.update_interval_ms}ms")

    # Create controller
    controller = AppController(config)
    controller.start()

    # Run tray app (blocking)
    tray = TrayApp(config, controller)
    try:
        tray.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        controller.stop()
        log.info("VuNMix stopped.")


if __name__ == '__main__':
    main()
