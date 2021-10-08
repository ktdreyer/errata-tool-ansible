from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool
from ansible.module_utils.common_errata_tool import UserNotFoundError
from ansible.module_utils.six import raise_from
from ansible.module_utils.parsing.convert_bool import boolean
import re
import os
from lxml import html


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


class DocsReviewerNotFoundError(UserNotFoundError):
    pass


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


def scrape_error_message(response):
    """
    Return the text inside "<div id="error-message">...</div>" in this HTML
    response.

    :param response: Requests.response object
    :returns: message text (str)
    """
    content = response.text
    doc = html.document_fromstring(content)
    messages = doc.xpath('//div[@id="error-message"]')
    if len(messages) != 1:
        print('expected 1 <div id="error-message">, found %d' % len(messages))
        raise ValueError(response.text)
    message = messages[0]
    message = message.text_content().strip()
    return message


def scrape_error_explanations(response):
    """
    Return the text inside "<div class="errorExplanation"> ... </div>" in this
    HTML response.

    :param response: Requests.response object
    :returns: list of messages (str)
    """
    content = response.text
    doc = html.document_fromstring(content)
    lis = doc.xpath('//div[@class="errorExplanation"]//li/text()')
    errors = [li.strip() for li in lis]
    return errors


def html_form_data(client, params):
    """ Transform our Ansible params into an HTML form "data" for POST'ing.
    """
    data = {}
    data['product[short_name]'] = params['short_name']
    data['product[name]'] = params['name']
    data['product[description]'] = params['description']
    data['product[bugzilla_product_name]'] = params['bugzilla_product_name']
    data['product[valid_bug_states][]'] = params['valid_bug_states']
    data['product[isactive]'] = int(params['active'])
    data['product[ftp_path]'] = params['ftp_path']
    data['product[ftp_subdir]'] = params.get('ftp_subdir', '')
    data['product[is_internal]'] = int(params['internal'])
    docs_reviewer = params.get('default_docs_reviewer')
    if docs_reviewer is not None:
        try:
            docs_user_id = common_errata_tool.user_id(client, docs_reviewer)
        except UserNotFoundError as e:
            raise_from(DocsReviewerNotFoundError(str(e)), e)
        data['product[default_docs_reviewer_id]'] = docs_user_id
    # push targets need scraper
    push_targets = params['push_targets']
    push_target_scraper = common_errata_tool.PushTargetScraper(client)
    push_target_ints = push_target_scraper.convert_to_ints(push_targets)
    data['product[push_targets][]'] = push_target_ints
    # This is an internal-only product thing that we can probably skip:
    # data['product[cdw_flag_prefix]'] = params['cdw_flag_prefix']
    solution = params['default_solution'].upper()
    solution_id = int(common_errata_tool.DefaultSolutions[solution])
    data['product[default_solution_id]'] = solution_id
    state_machine_rule_set = params['state_machine_rule_set']
    rules_scraper = common_errata_tool.WorkflowRulesScraper(client)
    state_machine_rule_set_id = int(rules_scraper.enum[state_machine_rule_set])
    data['product[state_machine_rule_set_id]'] = state_machine_rule_set_id
    data['product[move_bugs_on_qe]'] = int(params['move_bugs_on_qe'])
    exd_org_group = params.get('exd_org_group')
    if exd_org_group is not None:
        exd_org_group_id = int(EXD_ORG_GROUPS[exd_org_group])
        data['product[exd_org_group_id]'] = exd_org_group_id
    return data


def handle_form_errors(response):
    # If there are incorrect or missing fields, we will receive a HTTP 200
    # with a list of the wrong fields, or just an HTTP 500 error.
    if response.status_code == 500:
        # One way to trigger this HTTP 500 error is to send a bogus
        # default_docs_reviewer_id that does not exist (eg. 1000000000)
        message = scrape_error_message(response)
        raise RuntimeError(message)
    if 'errorExplanation' in response.text:
        errors = scrape_error_explanations(response)
        raise RuntimeError(*errors)
    response.raise_for_status()


def create_product(client, params):
    """ See CLOUDWF-7 for official create API """
    data = html_form_data(client, params)

    # Hack for CLOUDWF-309:
    # If there are any push targets, then create the product *without* push
    # targets first, and then edit the product with the push targets.
    saved_push_targets = data.pop('product[push_targets][]')

    response = client.post('products', data=data)
    handle_form_errors(response)

    # Hack for CLOUDWF-309, part 2:
    # Edit product we just created so that we can set the push targets.
    if saved_push_targets:
        # Get the new product ID for the product we just created.
        m = re.search(r'\d+$', response.url)
        if not m:
            err = 'could not find new product ID from %s' % response.url
            raise RuntimeError(err)
        product_id = int(m.group(0))
        edit_product(client, product_id, params)


def edit_product(client, product_id, params):
    """
    Edit an existing product.

    See CLOUDWF-7 for official edit API.

    :param client: Errata Client
    :param int product_id: ID of the product we will edit
    :param dict params: ansible module params
    """
    data = html_form_data(client, params)
    data['_method'] = 'patch'
    response = client.post('products/%d' % product_id, data=data)
    handle_form_errors(response)


def prepare_diff_data(before, after):
    return common_errata_tool.task_diff_data(
        before=before,
        after=after,
        item_name=after['short_name'],
        item_type='product',
        keys_to_copy=[
            # This field exists in ET but is not yet supported by
            # this ansible module
            'show_bug_package_mismatch_warning',
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
            edit_product(client, product['id'], params)
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
        exd_org_group=dict(choices=EXD_ORG_GROUPS.keys()),
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

    try:
        result = ensure_product(client, params, check_mode)
    except DocsReviewerNotFoundError as e:
        msg = 'default_docs_reviewer %s account not found' % e
        module.fail_json(msg=msg, changed=False, rc=1)

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

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
