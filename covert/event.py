# -*- coding: utf-8 -*-
"""Objects and functions related to events.
"""

import logging
from . import setting
from . import common as c

logger = logging.getLogger('covert')
event_handler = {}

def add_handler(evnt, handler):
    """add handler for event"""
    if callable(handler):
        if evnt in event_handler:
            logger.debug(c._('Cannot override handler for {}').format(evnt))
        else:
            if setting.debug > 2:
                logger.debug(c._('New event handler for {}').format(evnt))
            event_handler[evnt] = handler
    else:
        logger.debug(c._('Event handler for {} is not a callable').format(evnt))

def event(evnt, item, tree={}):
    """call handler for event 'event' and render tree 'tree' (optional)"""
    key = "{}:{}".format(item.name.lower(), evnt)
    if key in event_handler:
        event_handler[key](item, tree)
