from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool
import re
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
       - Does the product require channels or repos for text-only advisories?
         For instance many Middleware products have no presence on RHN or RHSM,
         so set this to false to allow pushes without channels or repos.
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


class InvalidInputError(Exception):
    """ Invalid user input for a parameter """
    def __init__(self, param, value):
        self.param = param
        self.value = value


def validate_params(module, params):
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
    if relationships['default_docs_reviewer']:
        product['default_docs_reviewer'] = relationships['default_docs_reviewer']['login_name']
    else:
        product['default_docs_reviewer'] = None

    # default_solution
    product['default_solution'] = relationships['default_solution']['title']

    # push_targets
    product['push_targets'] = [pt['name'] for pt in
                               relationships['push_targets']]

    # state_machine_rule_set
    if relationships['state_machine_rule_set']:
        product['state_machine_rule_set'] = relationships['state_machine_rule_set']['name']
    else:
        product['state_machine_rule_set'] = None

    return product


def scrape_pre(response):
    """
    Return the text inside "<pre> ... </pre>" in this HTML response.

    :param response: Requests.response object
    :returns: message text (str)
    """
    content = response.text
    doc = html.document_fromstring(content)
    pres = doc.xpath('//pre')
    if len(pres) != 1:
        print('expected 1 <pre>, found %s' % len(pres))
        raise ValueError(response.text)
    pre = pres[0]
    message = pre.text_content().strip()
    return message


def scrape_error_explanation(response):
    """
    Return the text inside "<div class="errorExplanation"> ... </div>" in this HTML response.

    :param response: Requests.response object
    :returns: message text (str)
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
    data['product[ftp_subdir]'] = params['ftp_subdir']
    data['product[is_internal]'] = int(params['internal'])
    if params['default_docs_reviewer'] is not None:
        default_docs_reviewer_id = common_errata_tool.user_id(client, params['default_docs_reviewer'])
        data['product[default_docs_reviewer_id]'] = default_docs_reviewer_id
    # push targets need scraper
    push_target_scraper = common_errata_tool.PushTargetScraper(client)
    push_target_ints = push_target_scraper.convert_to_ints(params['push_targets'])
    data['product[push_targets][]'] = push_target_ints
    # This is an internal-only product thing that we can probably skip:
    # data['product[cdw_flag_prefix]'] = params['cdw_flag_prefix']
    solution = params['default_solution'].upper()
    solution_id = int(common_errata_tool.DefaultSolutions[solution])
    data['product[default_solution_id]'] = solution_id
    workflow_rules_scraper = common_errata_tool.WorkflowRulesScraper(client)
    state_machine_rule_set_id = int(workflow_rules_scraper.enum[params['state_machine_rule_set']])
    data['product[state_machine_rule_set_id]'] = state_machine_rule_set_id
    data['product[move_bugs_on_qe]'] = int(params['move_bugs_on_qe'])
    data['product[text_only_advisories_require_dists]'] = int(params['text_only_advisories_require_dists'])
    return data


def handle_form_errors(response):
    # If there are incorrect or missing fields, we will receive a HTTP 200
    # with a list of the wrong fields, or just an HTTP 500 error.
    if response.status_code == 500:
        message = scrape_pre(response)
        raise RuntimeError(message)
    if 'errorExplanation' in response.text:
        errors = scrape_error_explanation(response)
        raise RuntimeError(errors)
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
            raise RuntimeError('could not determine new product ID')
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


def ensure_product(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    short_name = params['short_name']
    product = get_product(client, short_name)
    if not product:
        result['changed'] = True
        result['stdout_lines'] = ['created %s product' % short_name]
        if not check_mode:
            create_product(client, params)
        return result
    differences = common_errata_tool.diff_settings(product, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
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
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    try:
        validate_params(module, params)
    except InvalidInputError as e:
        msg = 'invalid %s value "%s"' % (e.param, e.value)
        module.fail_json(msg=msg, changed=False, rc=1)

    client = common_errata_tool.Client()

    result = ensure_product(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
