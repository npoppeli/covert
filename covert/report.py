# -*- coding: utf-8 -*-
"""
covert.report
-----
Objects and functions related to reporting, logging etcetera.
"""

import datetime, json, logging
from .common import ComplexEncoder

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

def print_doc(doc):
    return json.dumps(doc, sort_keys=True, indent=2, separators=(',', ': '), cls=ComplexEncoder)