# -*- coding: utf-8 -*-
"""
covert.report
-----
Objects and functions related to reporting, logging etcetera.
"""

import logging

# logging levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
logger = logging.getLogger('waitress')
logger.setLevel(logging.DEBUG)

# logger = logging.getLogger('covert')
# logger.setLevel(logging.DEBUG)
# console = logging.StreamHandler()
# console.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
# console.setFormatter(formatter)
# logger.addHandler(console)
