"""
Test helpers, copied from ansible's test/units/modules/utils.py
"""

import os
import json

from ansible.module_utils import basic
from ansible.module_utils._text import to_bytes

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(TESTS_DIR, 'fixtures')


def set_module_args(args):
    if '_ansible_remote_tmp' not in args:
        args['_ansible_remote_tmp'] = '/tmp'
    if '_ansible_keep_remote_files' not in args:
        args['_ansible_keep_remote_files'] = False

    args = json.dumps({'ANSIBLE_MODULE_ARGS': args})
    basic._ANSIBLE_ARGS = to_bytes(args)


class AnsibleExitJson(Exception):
    pass


class AnsibleFailJson(Exception):
    pass


def exit_json(*args, **kwargs):
    if 'changed' not in kwargs:
        kwargs['changed'] = False
    raise AnsibleExitJson(kwargs)


def fail_json(*args, **kwargs):
    kwargs['failed'] = True
    raise AnsibleFailJson(kwargs)


def load_json(filename):
    """
    Load a JSON fixture file from disk

    :returns: dict
    """
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path) as json_file:
        data = json.load(json_file)
    return data


def load_html(filename):
    """
    Load a HTML fixture file from disk

    :returns: string (file contents)
    """
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path) as html_file:
        contents = html_file.read()
    return contents
