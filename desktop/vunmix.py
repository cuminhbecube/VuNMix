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
from config import AppConfig
from media_controller import MediaAppController
from diagnostics import MAIN_LOG_FILE, configure_logging
from connection_ui import ConnectionTrayApp


_fault_stream = None


def setup_logging(debug: bool = False):
    global _fault_stream
    configure_logging(debug)

    _fault_stream = open(MAIN_LOG_FILE, "a", encoding="utf-8")
    faulthandler.enable(file=_fault_stream, all_threads=True)

    def log_unhandled(exc_type, exc_value, exc_traceback):
        logging.getLogger("vunmix").critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def log_thread_exception(args):
        logging.getLogger("vunmix").critical(
            "Unhandled thread exception in %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_unhandled
    threading.excepthook = log_thread_exception


def main():
    if "--version" in sys.argv:
        print(build_summary())
        return

    debug = "--debug" in sys.argv
    setup_logging(debug)

    log = logging.getLogger("vunmix")
    log.info("VuNMix Desktop %s", APP_VERSION)
    log.info(
        "Build metadata: protocol=%d git=%s built=%s",
        PROTOCOL_VERSION,
        GIT_SHA,
        BUILD_DATE,
    )
    log.info("Main log: %s", MAIN_LOG_FILE)

    config = AppConfig.load()
    log.info("COM Port preference: %s", config.com_port)
    log.info("Sync Interval: %sms", config.update_interval_ms)

    controller = MediaAppController(config)
    controller.start()

    tray = ConnectionTrayApp(config, controller)
    try:
        tray.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        controller.stop()
        log.info("VuNMix stopped.")


if __name__ == "__main__":
    main()
