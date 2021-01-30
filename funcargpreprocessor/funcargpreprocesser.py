#!/usr/bin/python3
"""
Project : 
Author : sabariram
Date : 08-Jun-2020
"""

from functools import wraps
import re
from copy import deepcopy
from types import MethodType, FunctionType

from .exceptions import FieldError, MissingFieldError, FieldTypeError, FieldValueError
from .customtypearg import BaseArg
from .errorcode import ErrorCode


class FunctionArgPreProcessor:
    def __init__(self, definition, is_strict=True, auto_type_cast=False):
        self.is_strict = is_strict
        self.definition = self.validate_type_definition(definition)
        self.auto_type_cast = auto_type_cast

    def __call__(self, func_obj):
        @wraps(func_obj)
        def inner_function(*args, **kwargs):
            raw_argument = self.extract_request_data(*args, **kwargs)
            parsed_argument = self.parser(raw_argument, deepcopy(self.definition))
            kwargs.update(parsed_argument)
            return func_obj(*args, **kwargs)

        return inner_function

    def extract_request_data(self, *args, **kwargs):
        return {}

    def parser(self, params, definition, parent=None):
        if self.is_non_empty_value(params) is False:
            params = {}
        parsed_args = {}
        for key, type_definition in definition.items():
            value = params.pop(key, None)
            required = type_definition.pop('required', False)
            alias_key = type_definition.pop('alias', key)
            data_type = type_definition.pop('data_type', None)
            validator = type_definition.pop('validator', None)
            nested = type_definition.pop('nested', None)
            default_value = type_definition.pop('default', None)
            type_definition.pop('description', None)
            print_key = f"{parent}.{key}" if parent else key
            if self.is_non_empty_value(value):
                if validator:
                    parsed_args[alias_key] = validator(print_key, value)
                else:
                    parsed_args[alias_key] = self.parse_value(print_key, value, data_type, nested, **type_definition)
            elif default_value is not None:
                parsed_args[alias_key] = self.get_value(default_value)
            elif required:
                raise MissingFieldError(print_key)
        if self.is_strict and self.is_non_empty_value(params):
            param_list = list(params.keys())
            raise FieldError(ErrorCode.UN_RECOGNIZED_FIELD, param_list, f'Unexpected params {param_list}')
        return parsed_args

    def parse_value(self, key, value, data_type, nested, **value_constraints):
        try:
            value = self.type_cast(value, data_type)
        except Exception:
            raise FieldTypeError(key, data_type)
        if nested:
            if isinstance(nested, dict):
                if data_type is dict:
                    value = self.parser(value, nested, key)
                elif data_type is list:
                    temp = []
                    for i, item in enumerate(value):
                        temp.append(self.parser(item, deepcopy(nested), f'{key}[{i}]'))
                    value = temp
            elif data_type == list:
                temp = []
                for i, item in enumerate(value):
                    field_name = f'{key}[{i}]'
                    try:
                        item = self.type_cast(item, nested)
                        temp.append(item)
                    except Exception:
                        raise FieldTypeError(field_name, nested)
                    self.check_constraint(item, field_name, **value_constraints)
                value = temp
        else:
            self.check_constraint(value, key, **value_constraints)
        return value

    def type_cast(self, value, data_type):
        """
        To check if the value is of expected data type if not type cast it to the required datatype. Supports type cast
        for BaseParams as well
        :param value: Value from the request
        :param data_type: Expected data type of the param
        :return: type casted value
        """
        if isinstance(data_type, BaseArg):
            value = data_type(value)
        elif isinstance(value, data_type) is False:
            if self.auto_type_cast and isinstance(value, str) and data_type in (int, bool, float):
                if data_type is bool:
                    value = value.lower()
                    if value not in {"true", "false"}:
                        raise Exception()
                    value = True if value == "true" else False
                else:
                    value = data_type(value)
            else:
                raise Exception()
        return value

    @classmethod
    def check_constraint(cls, value, key, min_val=None, max_val=None, value_list=None, regex=None,
                         regex_error_message=None, min_len=None, max_len=None):
        """
        To check the value for constraints. The caller of this function provides only the value and key as positional
        argument and others as keyword arguments so that the function can be changed as the developer needs by extending
        the class and overriding the function
        :param value: Value to be checked
        :param key: Key name for passing back in error if any constraint fails
        :param min_val: Min range constraint
        :param max_val: Max range constraint
        :param value_list: Pick list constraint
        :param regex: Regular expression constraint
        :param regex_error_message: Alternate error message for regex constraint fails
        :param min_len: Minimum length of the field
        :param max_len: Maximum length of the field
        :return:
        """
        min_val = cls.get_value(min_val)
        max_val = cls.get_value(max_val)
        if min_val is not None and value < min_val:
            raise FieldValueError(ErrorCode.FIELD_MIN_RANGE_VIOLATED, key,
                                  f"{key} should be greater than or equal to {min_val}",
                                  {"minValue": min_val})
        if max_val is not None and value > max_val:
            raise FieldValueError(ErrorCode.FIELD_MAX_RANGE_VIOLATED, key,
                                  f"{key} should be lesser than or equal to {max_val}",
                                  {"maxValue": max_val})
        if value_list is not None and value not in value_list:
            raise FieldValueError(ErrorCode.FIELD_VALUE_NOT_IN_ALLOWED_LIST, key,
                                  f"{key} should be one of these - {value_list}", {"allowedValue": value_list})
        if hasattr(value, '__len__'):
            try:
                length = len(value)
                if min_len is not None and length < min_len:
                    raise FieldValueError(ErrorCode.FIELD_MIN_LENGTH_VIOLATED, key,
                                          f"{key} has a minimum length of {min_len}", {"minLength": min_len})
                if max_len is not None and length > max_len:
                    raise FieldValueError(ErrorCode.FIELD_MAX_LENGTH_VIOLATED, key,
                                          f"{key} has a maximum length of {max_len}", {"maxLength": max_len})
            except TypeError:
                pass

        if regex is not None and re.search(regex, value) is None:
            message = regex_error_message if regex_error_message else f"{key} should be of format - {regex}"
            raise FieldValueError(ErrorCode.FIELD_REGEX_VALIDATION_FAILED, key, message, {"regex": regex})

    @staticmethod
    def validate_type_definition(type_definition):
        """
        Placeholder for validating the type definition
        :param type_definition:
        :return:
        """
        # TODO:validator
        data_type = type_definition.get('data_type')
        validator = type_definition.get('validator')
        return type_definition

    @staticmethod
    def is_non_empty_value(value):
        """
        To check if the value is not None and in case of string check for non empty string
        :param value: Any basic data type
        :return:Boolean
        """
        if value is None:
            return False
        if isinstance(value, str) and len(value.strip()) == 0:
            return False
        if (isinstance(value, list) or isinstance(value, dict)) and not value:
            return False
        return True

    @staticmethod
    def get_value(value):
        if isinstance(value, FunctionType) or isinstance(value, MethodType):
            return value()
        return value
