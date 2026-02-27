from __future__ import annotations

import logging

import tkinter as tk

from thelocalai.app import TheLocalAIApp
from thelocalai.config import APP_TITLE
from thelocalai.runtime import install_exception_hooks, setup_logging
from thelocalai.security import acquire_single_instance_lock


def main():
    setup_logging()
    log = logging.getLogger("thelocalai")
    install_exception_hooks(log)
    acquire_single_instance_lock()
    log.info("Starting %s", APP_TITLE)

    root = tk.Tk()
    TheLocalAIApp(root)
    root.mainloop()

    log.info("%s closed", APP_TITLE)


if __name__ == "__main__":
    main()
