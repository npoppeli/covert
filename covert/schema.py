# -*- coding: utf-8 -*-
"""
covert.schema
-----
Classes and functions related to the validation of items.

Inspiration drawn from Voluptuous by Alec Thomas and Cerberus by Nicola Iarocci.
Voluptuous has the drawback that it can handle multiple errors, but has error messages that
are not user-friendly and not configurable either.
Cerberus has the drawback that it doesn't truly validate embedded lists and dictionaries.
"""

from datetime import datetime, date, time
class ValidationError(ValueError):
    pass

class SchemaError(ValueError):
    pass

class Schema(object):
    def __init__(self, schema, required=False):
        if isinstance(schema, dict):
            self.schema = schema
            self.required = required
            self._validate = self._compile(schema)
            self._errors = []
        else
            raise SchemaError()

    def __call__(self, doc):
        try:
            return self._validate(doc)
        except Exception as e:
            self._errors.append(str(e))
            return False

    def _compile(self, schema):
        if isinstance(schema, dict):
            return self._compile_dict(schema)
        elif isinstance(schema, list):
            return self._compile_list(schema)
        schema_type = type(schema)
        if schema_type is type:
            schema_type = schema
        if schema_type in (int, long, str, float, list, dict):
            return _compile_scalar(schema)
        raise SchemaError('unsupported schema data type %r' %
                          type(schema).__name__)
