from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool
from ansible.module_utils.common_errata_tool import UserNotFoundError
from ansible.module_utils.parsing.convert_bool import boolean
import os


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_product

short_description: Create and manage products in the Errata Tool
description:
   - Create, update, and delete products within Red Hat's Errata Tool.
options:
   short_name:
     description:
       - "example: RHCEPH"
     required: true
   name:
     description:
       - "example: Red Hat Ceph Storage"
     required: true
   description:
     description:
       - "example: Red Hat Ceph Storage"
     required: true
   bugzilla_product_name:
     description:
       - "example: null"
     required: false
   valid_bug_states:
     description:
       - A list of valid Bugzilla bug states
     choices: [NEW, ASSIGNED, ON_DEV, POST, MODIFIED, ON_QA, VERIFIED]
     required: false
     default: [MODIFIED, VERIFIED]
   active:
     description:
       - Is the product active for Errata filing?
     choices: [true, false]
     default: true
   ftp_path:
     description:
       - This value is usually an empty string for most products. For RHEL, it
         is "os".
     required: false
     default: ""
   ftp_subdir:
     description:
       - For most products, this is usually the short name of the product,
         for example "RHCEPH". For RHEL, this is "os".
     required: false
     default: null
   internal:
     description:
       - A Red Hat Internal Product
     default: false
   default_docs_reviewer:
     description:
       - The default docs reviewer for advisories. "null" means "Unassigned".
         (Note that once you have changed this value from something other than
         "null", there is no way to change it back to "null".)
       - This account must already exist in the Errata Tool. You may create it
         with the web UI, or the errata_tool_user Ansible module, or some
         other method.
       - This user account must have the "docs" role.
     default: null
   push_targets:
     description:
       - One or more push targets (specify a list)
       - See /developer-guide/push-push-targets-options-and-tasks.html
         for more explanation about these push targets.
     choices: [rhn_live, rhn_stage, ftp, cdn, cdn_stage, altsrc, cdn_docker,
               cdn_docker_stage]
     required: true
   default_solution:
     description:
       - Default "solution" text when filing advisories
     choices: [enterprise, default]
     required: true
   state_machine_rule_set:
     description:
       - Workflow Rule Set
     choices: ["See https://errata.devel.redhat.com/workflow_rules"]
     required: true
   move_bugs_on_qe:
     description:
       - '"true" means: move the bugs to ON_QA when the advisory moves to QE
         state.'
       - '"false" means: move the bugs to ON_QA as soon as the bugs are
         attached to the advisory.'
     choices: [true, false]
     default: false
   text_only_advisories_require_dists:
     description:
       - DEPRECATED. This field was removed from Errata Tool in ET 4.14.
         Text only advisories now always require that CDN repos are specified.
       - For backwards compatibility the field is accepted but its value is
         ignored. It will be removed entirely in future release of this module.
     choices: [true, false]
     default: true
   exd_org_group:
     description:
       - The name of the "EXD org group" that is responsible for this product.
         The Errata Tool uses this field to file Jira tickets for release
         engineering (eg. for missing RPM product listings).
       - See https://errata.devel.redhat.com/api/v1/exd_org_groups for a
         list of EXD org groups.
     choices: ['RHEL', 'Cloud', 'Middleware & Management', 'Pipeline Value']
     default: 'RHEL'
   show_bug_package_mismatch_warning:
     description:
       - If true a warning will be shown for builds where the package doesn't
         match the expected package for the advisory.
       - The expected package is decided based on the advisory's bugs'
         components or its synopsis.
       - For products where this warning is not considered useful it can be
         disabled.
     choices: [true, false]
     default: true

requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


BUGZILLA_STATES = set([
    'ASSIGNED',
    'CLOSED',
    'MODIFIED',
    'NEW',
    'ON_DEV',
    'ON_QA',
    'POST',
    'RELEASE_PENDING',
    'VERIFIED',
])


# See https://errata.devel.redhat.com/api/v1/exd_org_groups
# In theory these could change, but it seems unlikely.
EXD_ORG_GROUPS = {
    'RHEL': 1,
    'Cloud': 2,
    'Middleware & Management': 3,
    'Pipeline Value': 4,
}


class InvalidInputError(Exception):
    """ Invalid user input for a parameter """
    def __init__(self, param, value):
        self.param = param
        self.value = value


def validate_params(params):
    """
    Sanity-check user input for some parameters.

    Raises InvalidInputError if the user specified an invalid value for a
    parameter.
    """
    for state in params['valid_bug_states']:
        if state not in BUGZILLA_STATES:
            raise InvalidInputError('valid_bug_states', state)
    solution = params['default_solution'].upper()
    try:
        common_errata_tool.DefaultSolutions[solution]
    except KeyError:
        raise InvalidInputError('default_solution', solution)


def get_product(client, short_name):
    """
    Get a single product by name.

    :param Client: common_errata_tool.Client instance
    :param str short_name: Product short name, eg RHCEPH
    :returns: a dict of information about this product, or None if the Errata
              Tool has no product with this short_name
    """
    endpoint = 'api/v1/products/%s' % short_name
    response = client.get(endpoint)
    if response.status_code != 200:
        return None
    result = response.json()
    product = result['data']['attributes']
    product['id'] = result['data']['id']

    # The current REST API returns some inconsistent names for booleans.
    # Some booleans have no "is" verb, and some have "is", and some have
    # "is_". Rather than exposing this ugly API detail to users, we'll paper
    # over it here by renaming the keys to drop "is" and "is_".
    product['active'] = product.pop('isactive')
    product['internal'] = product.pop('is_internal')

    # Simplify the "relationships" data to simple names.

    relationships = result['data']['relationships']

    # default_docs_reviewer
    default_docs_reviewer = relationships['default_docs_reviewer']
    if default_docs_reviewer:
        product['default_docs_reviewer'] = default_docs_reviewer['login_name']
    else:
        product['default_docs_reviewer'] = None

    # default_solution
    product['default_solution'] = relationships['default_solution']['title']

    # push_targets
    product['push_targets'] = [pt['name'] for pt in
                               relationships['push_targets']]

    # state_machine_rule_set
    state_machine_rule_set = relationships['state_machine_rule_set']
    if state_machine_rule_set:
        product['state_machine_rule_set'] = state_machine_rule_set['name']
    else:
        product['state_machine_rule_set'] = None

    # exd_org_group
    product['exd_org_group'] = relationships['exd_org_group']['name']

    return product


def create_product(client, params):
    """
    Create a new ET product

    :param client: Errata Client
    :param dict params: ansible module params
    """
    # Send the server's name for these parameters
    # (see comment in get_product())
    product = params.copy()
    if 'active' in product:
        product['isactive'] = product.pop('active')
    if 'internal' in product:
        product['is_internal'] = product.pop('internal')
    data = {'product': product}
    response = client.post('api/v1/products', json=data)
    if response.status_code != 201:
        raise common_errata_tool.ErrataToolError(response)


def edit_product(client, product_id, differences):
    """
    Edit an existing product.

    :param client: Errata Client
    :param int product_id: ID of the product we will edit
    :param list differences: changes to make
    """
    # Create a Ansible params-like dict for the API.
    params = {}
    for difference in differences:
        key, _, new = difference
        params[key] = new
    # Send the server's name for these parameters
    # (see comment in get_product())
    if 'active' in params:
        params['isactive'] = params.pop('active')
    if 'internal' in params:
        params['is_internal'] = params.pop('internal')
    endpoint = 'api/v1/products/%d' % product_id
    data = {'product': params}
    response = client.put(endpoint, json=data)
    # TODO: verify 200 is the right code to expect here?
    if response.status_code != 200:
        raise common_errata_tool.ErrataToolError(response)


def prepare_diff_data(before, after):
    return common_errata_tool.task_diff_data(
        before=before,
        after=after,
        item_name=after['short_name'],
        item_type='product',
        keys_to_copy=[
            # Any field listed here exists in ET but is not
            # yet supported by this ansible module
        ],
    )


def ensure_product(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    params = {param: val for param, val in params.items() if val is not None}
    short_name = params['short_name']
    product = get_product(client, short_name)
    if not product:
        result['changed'] = True
        result['stdout_lines'] = ['created %s product' % short_name]
        result['diff'] = prepare_diff_data(product, params)
        if not check_mode:
            create_product(client, params)
        return result
    differences = common_errata_tool.diff_settings(product, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        result['diff'] = prepare_diff_data(product, params)
        if not check_mode:
            edit_product(client, product['id'], differences)
    return result


def run_module():
    module_args = dict(
        short_name=dict(required=True),
        name=dict(required=True),
        description=dict(required=True),
        bugzilla_product_name=dict(default=''),
        valid_bug_states=dict(type='list', default=['MODIFIED', 'VERIFIED']),
        active=dict(type='bool', default=True),
        ftp_path=dict(default=""),
        ftp_subdir=dict(),
        internal=dict(type='bool', default=False),
        default_docs_reviewer=dict(),
        push_targets=dict(type='list', required=True),
        default_solution=dict(required=True),
        state_machine_rule_set=dict(required=True),
        move_bugs_on_qe=dict(type='bool', default=False),
        text_only_advisories_require_dists=dict(type='bool', default=True),
        exd_org_group=dict(choices=list(EXD_ORG_GROUPS.keys())),
        show_bug_package_mismatch_warning=dict(type='bool'),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )
    # Ignore this attribute since it doesn't exist any more in ET
    del module.params['text_only_advisories_require_dists']

    check_mode = module.check_mode
    params = module.params

    try:
        validate_params(params)
    except InvalidInputError as e:
        msg = 'invalid %s value "%s"' % (e.param, e.value)
        module.fail_json(msg=msg, changed=False, rc=1)

    client = common_errata_tool.Client()

    result = ensure_product(client, params, check_mode)

    if (
        check_mode
        and result['changed']
        and params['default_docs_reviewer']
        and boolean(os.getenv('ANSIBLE_STRICT_USER_CHECK_MODE', False))
    ):
        try:
            user = common_errata_tool.get_user(
                client, params['default_docs_reviewer'], True
            )
        except UserNotFoundError as e:
            msg = 'default_docs_reviewer %s account not found' % e
            module.fail_json(msg=msg, changed=False, rc=1)

        if 'docs' not in user['roles']:
            msg = (
                "User %s does not have 'docs' role in ET"
                % params['default_docs_reviewer']
            )
            module.fail_json(msg=msg, changed=False, rc=1)

        if not user.get('enabled'):
            # Note, the ET server does not require the default_docs_reviewer
            # account to be enabled, but normally a human release engineer
            # would check that an account is enabled before using it. For ease
            # of use, we'll raise that error here when
            # ANSIBLE_STRICT_USER_CHECK_MODE is True.
            msg = (
                "default_docs_reviewer %s is not enabled"
                % params['default_docs_reviewer']
            )
            module.fail_json(msg=msg, changed=False, rc=1)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
