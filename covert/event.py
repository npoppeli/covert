# -*- coding: utf-8 -*-
"""Objects and functions related to events.
"""

import logging
from . import setting
from . import common as c

logger = logging.getLogger('covert')
event_handler = {}

def add_handler(event_name, handler):
    """add handler for event `event_name`"""
    if callable(handler):
        if event_name in event_handler:
            logger.debug(c._('Cannot override handler for {}').format(event_name))
        else:
            if setting.debug > 2:
                logger.debug(c._('New event handler for {}').format(event_name))
            event_handler[event_name] = handler
    else:
        logger.debug(c._('Event handler for {} is not a callable').format(event_name))

def event(event_name, item, tree={}):
    """call handler for event `event_name` and render tree `tree` (optional)"""
    key = "{}:{}".format(item.name.lower(), event_name)
    if key in event_handler:
        event_handler[key](item, tree)
