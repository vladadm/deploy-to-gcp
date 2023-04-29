from typing import Any, Dict, Optional, List
import logging
from logging import Logger
import sys


class DeployLogger:
    def __init__(self, loglvl: str = "INFO", name: str = "deploy"):
        self.format = "%(asctime)s %(levelname)s: %(message)s"
        self.datefmt = "%H:%M:%S"
        self.streem = sys.stderr
        self.name = name
        self.loglvl = loglvl
        self.logger = self.getLogger()

    def getLogger(self):
        logging.basicConfig(format=self.format, datefmt=self.datefmt, stream=self.streem)
        logger: Logger = logging.getLogger(self.name)
        logger.setLevel(self.loglvl)
        logging.getLogger("chardet.charsetprober").disabled = True

        return logger

    def colored(
            self, message: str, color: Optional[str] = None,
            event_type: Optional[str] = None):
        palette = {
            "Bright_Yellow": "\x1b[93;1m",
            "Yellow": "\x1b[33;1m",
            "Yellow_in_Blue": "\x1b[1;33;4;44m",
            "Green": "\x1b[32;1m",
            "Light_Green": "\x1b[92;1m",
            "Red": "\x1b[31;1m",
            "Light_Red": "\x1b[31;1m",
            "Cyan": "\x1b[36;1m",
            "Light_Purple": "\x1b[95;1m",
            "Brown": "\x1b[33;0m",
        }.get(color)
        log_message = f"{palette}{message}\x1b[0m"
        if event_type == 'error':
            log_message = f"{palette}{message}\x1b[0m"
            self.logger.error(log_message)
            return
        self.logger.info(log_message)

    # Black	30	40
    # Red	31	41
    # Green	32	42
    # Yellow	33	43
    # Blue	34	44
    # Magenta	35	45
    # Cyan	36	46
    # Light Gray	37	47
    # Gray	90	100
    # Light Red	91	101
    # Light Green	92	102
    # Light Yellow	93	103
    # Light Blue	94	104
    # Light Magenta	95	105
    # Light Cyan	96	106
    # White	97	107

    # 0	Reset/Normal
    # 1	Bold text
    # 2	Faint text
    # 3	Italics
    # 4	Underlined text
