#!/usr/bin/env python3
"""
VuNMix Desktop — Main entry point.

A Python desktop companion for the VuNMix hardware audio mixer.
Controls Windows audio sessions and communicates with the ESP32-S3 via USB serial.

Usage:
    python vunmix.py              # Normal mode (system tray)
    python vunmix.py --debug      # Debug mode (verbose logging to console)
    python vunmix.py --version    # Print embedded build metadata
"""

import faulthandler
import logging
import os
import sys
import threading

# Add the desktop directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_info import APP_VERSION, BUILD_DATE, GIT_SHA, PROTOCOL_VERSION, build_summary
from config import AppConfig, CONFIG_DIR
from app_controller import AppController
from connection_ui import ConnectionTrayApp


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    fmt = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'

    os.makedirs(CONFIG_DIR, exist_ok=True)
    log_file = os.path.join(CONFIG_DIR, 'vunmix.log')
    fault_file = open(log_file, 'a', encoding='utf-8')
    faulthandler.enable(file=fault_file, all_threads=True)

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_file, mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout) if sys.stdout is not None else logging.NullHandler()
        ]
    )

    # Quiet noisy libraries
    logging.getLogger('comtypes').setLevel(logging.WARNING)
    logging.getLogger('PIL').setLevel(logging.WARNING)

    def log_unhandled(exc_type, exc_value, exc_traceback):
        logging.getLogger('vunmix').critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def log_thread_exception(args):
        logging.getLogger('vunmix').critical(
            "Unhandled thread exception in %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_unhandled
    threading.excepthook = log_thread_exception


def main():
    if '--version' in sys.argv:
        print(build_summary())
        return

    debug = '--debug' in sys.argv
    setup_logging(debug)

    log = logging.getLogger('vunmix')
    log.info("VuNMix Desktop %s", APP_VERSION)
    log.info(
        "Build metadata: protocol=%d git=%s built=%s",
        PROTOCOL_VERSION,
        GIT_SHA,
        BUILD_DATE,
    )

    # Load config
    config = AppConfig.load()
    log.info(f"COM Port preference: {config.com_port}")
    log.info(f"Sync Interval: {config.update_interval_ms}ms")

    # Create controller
    controller = AppController(config)
    controller.start()

    # Run tray app (blocking)
    tray = ConnectionTrayApp(config, controller)
    try:
        tray.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        controller.stop()
        log.info("VuNMix stopped.")


if __name__ == '__main__':
    main()
