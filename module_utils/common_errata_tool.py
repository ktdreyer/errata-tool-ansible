from lxml import html
import os
import re
from enum import IntEnum
import posixpath
import requests
from requests_gssapi import HTTPSPNEGOAuth, DISABLED


class ErrataToolError(ValueError):
    def __init__(self, response):
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            data = {}
        error = data.get('error') or data.get('errors') or response.text
        msg = 'Unexpected response from Errata Tool: %s' % error
        request = response.request
        msg += '\n  Request: %s %s' % (request.method, request.path_url)
        msg += '\n  Status code: %d' % response.status_code
        if request.body:
            msg += '\n  Request body: %s' % request.body.decode('utf-8')
        super(ErrataToolError, self).__init__(msg)
        self.response = response


class WorkflowRulesScraper(object):
    """
    Scrape the Workflow Rules name-to-id mappings.

    The ET server code also refers to Workflow Rules as "StateMachineRuleSet"s
    internally.

    There is one endpoint that requires us to send Workflow Rule ID numbers
    (ints) instead of names (human-readable strings):

      POST and PUT to /api/v1/releases (CLOUDWF-298)

    When we fix this, we will no longer need this WorkflowRulesScraper class.
    """
    def __init__(self, client):
        """
        :param client: Client class
        """
        self.client = client
        self._enum = None

    @property
    def enum(self):
        """
        :returns: IntEnum that maps Workflow Rule names to IDs.
        """
        if self._enum is None:
            content = self._get_page_content()
            rules = self._scrape_content(content)
            self._enum = IntEnum('WorkflowRules', rules)
        return self._enum

    def _get_page_content(self):
        """
        :returns: HTML web page string for the "workflow_rules" web page.
        """
        endpoint = 'workflow_rules'
        response = self.client.get(endpoint)
        response.raise_for_status()
        return response.content

    def _scrape_content(self, content):
        """
        :param str content: HTML from the "workflow_rules" web page.
        :returns: dict of {"name": "id"} workflow rule mappings.
        """
        doc = html.document_fromstring(content)
        trs = doc.xpath('//tr[starts-with(@id, "state_machine_rule_set_")]')
        results = {}
        for tr in trs:
            html_id = tr.attrib['id']
            m = re.search(r'\d+$', html_id)
            if not m:
                raise ValueError('could not find ID number in %s' % html_id)
            id_ = int(m.group(0))
            td = tr.find('td')
            # See app/views/workflow_rules/index.html.erb
            text = td.text_content()
            name = text.strip()
            results[name] = id_
        return results


class DefaultSolutions(IntEnum):
    """
    Again, the reason we track ID mappings is because the HTML
    form for product configuration only accepts solution ID numbers, rather
    than name strings.
    """
    # XXX rethink this now that we're using the /api/v1/products REST API
    DEFAULT = 1
    ENTERPRISE = 2
    RHN_TOOLS = 3


RELEASE_TYPES = frozenset([
    'QuarterlyUpdate',
    'Zstream',
    'Async',
])


def diff_settings(settings, params):
    """
    Diff the "live" settings against our Ansible parameters.

    :param dict settings: settings for a Product, or Product Version, etc.
    :param dict params: settings from our Ansible playbook.
    :returns: a list of three-element tuples:
              1. the key that has changed
              2. the old value
              3. the new value
    """
    differences = []
    for key in params:
        current_value = settings[key]
        new_value = params[key]
        if isinstance(new_value, list):
            # Need to do the comparison with sets.
            if set(current_value) != set(new_value):
                differences.append((key, current_value, new_value))
        elif current_value != new_value:
            differences.append((key, current_value, new_value))
    return differences


def describe_changes(changes):
    """
    Human-readable changes suitable for stdout_lines

    :param list changes: list of three-element tuples: "key", "old value",
                         "new value" (see diff_settings())
    """
    tmpl = 'changing %s from %s to %s'
    return [tmpl % change for change in changes]


def task_diff_data(before, after, item_name, item_type,
                   keys_to_copy=[], keys_to_omit=[]):
    """
    Prepare a dict suitable for use as the value of the 'diff' key in
    the dict returned by an ansible task.

    """
    if before is None:
        # Creating a new item
        before_header = "Not present"
        after_header = "New %s '%s'" % (item_type, item_name)

        # Need to use an empty dict instead of None otherwise
        # ansible's built-in diff callback will throw errors
        # trying to call splitlines() on it
        before = {}

    else:
        # Modifying an existing item
        before_header = "Original %s '%s'" % (item_type, item_name)
        after_header = "Modified %s '%s'" % (item_type, item_name)

        # Don't accidentally modify the method params
        after = after.copy()
        before = before.copy()

        # Avoid misleading diffs by copying some values from the
        # before dict to the after dict
        for key in keys_to_copy:
            if key in before and key not in after:
                after[key] = before[key]

        # Skip some keys if they're not useful
        for key in keys_to_omit + ['id']:
            if key in before and key not in after:
                del before[key]

    return {
        'before': before,
        'after': after,
        'before_header': before_header,
        'after_header': after_header,
    }


class UserNotFoundError(Exception):
    """ This user does not exist """
    pass


def get_user(client, login_name, fatal=False):
    """
    Look up data for a user by login_name

    Needed for users, products (for role assertions) and releases (CLOUDWF-298)

    :param str login_name: for example kdreyer@redhat.com
    :param bool fatal: if True, raise UserNotFoundError instead of returning
                        None. Defaults to False.
                        Exceptions are exceptional. If you regularly expect
                        users to be missing, then set this to False. If it's
                        surprising and fatal for users to be missing, then set
                        this to True.
    :returns: a dict of information about this user, or None if the user does
              not exist in the ET database.
    :raises: UserNotFoundError if the user does not exist and "fatal" is True.
    :raises: requests.exceptions.HTTPError if the ET replies with an
             unexpected HTTP response.
    """
    response = client.get('api/v1/user/%s' % login_name)
    data = response.json()
    if response.status_code == 400 and 'errors' in data:
        login_name_errors = data['errors'].get('login_name', [])
        if '%s not found.' % login_name in login_name_errors:
            if fatal:
                raise UserNotFoundError(login_name)
            return None
    response.raise_for_status()
    return data


def user_id(client, login_name):
    """
    Convert a user login_name to an id

    Needed for products (CLOUDWF-7) and releases (CLOUDWF-298)

    :param str login_name: for example kdreyer@redhat.com
    :returns: a user ID (int)
    :raises: UserNotFoundError if the user does not exist in the ET database.
    :raises: requests.exceptions.HTTPError if the ET replies with an
             unexpected HTTP response.
    """
    return get_user(client, login_name, fatal=True)['id']


class Client(object):
    """
    Simple ET API client

    GET and POST to API endpoints with a stored baseurl and auth scheme.

    By default, this uses GSSAPI (Kerberos) authentication with the production
    Errata Tool server URL. You can override these settings with environment
    variables like so:

      ERRATA_TOOL_URL=https://my.errata.dev.host/
      ERRATA_TOOL_AUTH="notkerberos"
    """
    def __init__(self):
        self.baseurl = os.getenv('ERRATA_TOOL_URL',
                                 'https://errata.devel.redhat.com')
        self.session = requests.Session()
        auth = os.getenv('ERRATA_TOOL_AUTH', 'kerberos')
        if auth == 'kerberos':
            self.session.auth = HTTPSPNEGOAuth(opportunistic_auth=True,
                                               mutual_authentication=DISABLED)

    def delete(self, endpoint, **kwargs):
        url = posixpath.join(self.baseurl, endpoint)
        return self.session.delete(url, **kwargs)

    def get(self, endpoint, **kwargs):
        url = posixpath.join(self.baseurl, endpoint)
        return self.session.get(url, **kwargs)

    def post(self, endpoint, **kwargs):
        url = posixpath.join(self.baseurl, endpoint)
        return self.session.post(url, **kwargs)

    def put(self, endpoint, **kwargs):
        url = posixpath.join(self.baseurl, endpoint)
        return self.session.put(url, **kwargs)

    def request(self, method, endpoint, **kwargs):
        url = posixpath.join(self.baseurl, endpoint)
        return self.session.request(method, url, **kwargs)
