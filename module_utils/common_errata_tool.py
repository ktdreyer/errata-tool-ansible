from lxml import html
import os
import re
from enum import IntEnum
import posixpath
import requests
from requests_gssapi import HTTPSPNEGOAuth, DISABLED


class PushTargetScraper(object):
    """
    Scrape the Push Target name-to-id mappings.

    The ET server currently requires that we POST PushTarget ID integers
    instead of names. This applies to the following resources:

      products (CLOUDWF-7)
      product_versions (CLOUDWF-5)

    See /developer-guide/push-push-targets-options-and-tasks.html for
    information about Push Targets. This class uses the same string names
    described there.

    These Push Targets are defined in the ET database.
    See the PushTarget.create() statements in the errata-rails.git
    ActiveRecord migration scripts ("db" directory).
    The push targets' string names are also listed in
    config/initializers/settings.rb (see ":pub_push_targets").

    These ints are not identical between dev, stage and prod. We cannot
    hard-code these ID numbers in the client here because nothing guarantees
    the accidental order that ActiveRecord has inserted the records over the
    years.

    Once we have the ability to edit all Push Target settings by name instead
    of ID, we can delete this class.
    """
    # Map PushTarget descriptions to names. This map comes from
    # /developer-guide/push-push-targets-options-and-tasks.html
    DESCRIPTIONS = {
        'Push to RHN Live': 'rhn_live',
        'Push to RHN Stage': 'rhn_stage',
        'Push to CDN Live': 'cdn',
        'Push to CDN Stage': 'cdn_stage',
        'Push docker images to CDN': 'cdn_docker',
        'Push docker images to CDN docker stage': 'cdn_docker_stage',
        'Push to public FTP server': 'ftp',
        'Push sources to CentOS git': 'altsrc',
        # These two HSS entries are old and deprecated. We include them here
        # for completeness (to avoid KeyErrors). Delete these once the ET devs
        # delete them entirely and the ET server no longer returns any
        # information about them.
        'Push to HSS Internal validation': 'hss_validate',
        'Push to HSS Internal production': 'hss_prod',
    }

    def __init__(self, client):
        """
        :param client: Client class
        """
        self.client = client
        self._enum = None

    @property
    def enum(self):
        """
        :returns: IntEnum that maps Push Target names to IDs.
        """
        if self._enum is None:
            content = self._get_form_page_content()
            targets = self._scrape_content(content)
            self._enum = IntEnum('PushTargets', targets)
        return self._enum

    def convert_to_ints(self, names):
        """ Convert a list of push target names to ints """
        return [int(self.enum[name]) for name in names]

    def _get_form_page_content(self):
        """
        :returns: HTML web page string for the "new product" form.
        """
        endpoint = 'products/new'
        response = self.client.get(endpoint)
        response.raise_for_status()
        return response.content

    def _scrape_content(self, content):
        """
        :param str content: HTML from the "new product" web page.
        """
        doc = html.document_fromstring(content)
        inputs = doc.xpath('//input[@name="product[push_targets][]"]')
        results = {}
        for input_ in inputs:
            id_ = int(input_.attrib['value'])
            parent = input_.getparent()
            # See app/views/products/_edit_push_targets.html.erb
            text = parent.text_content()
            m = re.search(r'(Push .+) \(Pub Target:', text)
            if not m:
                raise ValueError('no target description in %s' % text)
            description = m.group(1)
            name = self.DESCRIPTIONS[description]
            results[name] = id_
        return results


class WorkflowRulesScraper(object):
    """
    Scrape the Workflow Rules name-to-id mappings.

    The ET server code also refers to Workflow Rules as "StateMachineRuleSet"s
    internally.

    There are two endpoints that require us to send Workflow Rule ID numbers
    (ints) instead of names (human-readable strings):

      POST to /products (see CLOUDWF-7)
      POST and PUT to /api/v1/releases (CLOUDWF-298)

    When we fix these, we will no longer need this WorkflowRulesScraper class.
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


def user_id(client, login_name):
    """
    Convert a user login_name to an id

    Needed for products (CLOUDWF-7) and releases (CLOUDWF-298)
    """
    response = client.get('api/v1/user/%s' % login_name)
    if response.status_code == 400:
        data = response.json()
        if 'errors' in data:
            errors = data['errors']
            raise RuntimeError(errors)
    response.raise_for_status()
    data = response.json()
    return data['id']


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
