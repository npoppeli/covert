# -*- coding: utf-8 -*-
"""Objects and functions related to events.
"""

from .common import logger
from . import common as c

event_handler = {}

def add_handler(evnt, handler):
    """add handler for event"""
    if callable(handler):
        if evnt in event_handler:
            logger.debug(c._('Cannot override handler for {}').format(evnt))
        else:
            logger.debug(c._('New event handler for {}').format(evnt))
            event_handler[evnt] = handler
    else:
        logger.debug(c._('Event handler for {} is not a callable').format(evnt))

def event(evnt, item):
    """call handler for event 'event'"""
    if evnt in event_handler:
        event_handler[evnt](item)
