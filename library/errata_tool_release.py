from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_release

short_description: Create and manage releases in the Errata Tool
description:
   - Create and update releases within Red Hat's Errata Tool.
options:
   product:
     description:
       - "example: RHCEPH"
       - Async releases do not require a product.
     required: false
     default: null
   name:
     description:
       - "example: rhceph-4.0"
     required: true
   description:
     description:
       - "example: Red Hat Ceph Storage 4.0"
     required: true
   type:
     description:
       - "example: QuarterlyUpdate"
     choices: [QuarterlyUpdate, Zstream, Async]
     required: true
   product_versions:
     description:
       - list of ET Product Versions, eg "[RHCEPH-4.0-RHEL-8,
         RHEL-7-RHCEPH-4.0]"
     required: true
   enabled:
     description:
       - Is the release enabled?
     choices: [true, false]
     default: true
   active:
     description:
       - Is the release active for Errata filing? This field is a legacy field
         and it should always be "true". See CLOUDWF-4516 for more explanation
         about this field.
     choices: [true, false]
     default: true
   enable_batching:
     description:
       - Can you group advisories in batches for this release?
     choices: [true, false]
     default: true
   program_manager:
     description:
       - The program manager for this release (login_name, eg
         "coolprogrammanager@redhat.com")
     required: true
   blocker_flags:
     description:
       - Bugzilla blocker flags (specify a list).
       - "Example: [ceph-3.0, devel_ack, qa_ack, pm_ack]"
       - If the release is a Zstream (or QuarterlyUpdate with
         supports_component_acl), you must specify at least one flag here. If
         the release is an Async, blocker_flags is not required.
     required: false
     default: null
   internal_target_release:
     description:
       - Internal release target Bugzilla field
       - Set to "null" if this release does not use this field in Bugzilla.
     required: false
     default: null
   zstream_target_release:
     description:
       - Zstream release target Bugzilla field
       - Set to "null" if this release does not use this field in Bugzilla.
     required: false
     default: null
   ship_date:
     description:
       - Default ship date for new advisories. "YYYY-MM-DD"
       - Note that you cannot use YAML's native date type here. You must quote
         the date value so that YAML passes a string to Ansible.
       - If the release is a QuarterlyUpdate release, ship_date is required.
         If it is a Zstream or Async, ship_date is not required.
     default: null
   allow_shadow:
     description:
       - Only relevant for QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   allow_blocker:
     description:
       - Only relevant for QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   allow_exception:
     description:
       - Only relevant for QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   allow_pkg_dupes:
     description:
       - Allow duplicate advisories for packages. Only relevant for
         QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   supports_component_acl:
     description:
       - If true, every Bugzilla ticket's component must be on the Approved
         Component List (true) for this release. If false, ET will not consult
         the Bugzilla Approved Component List for this release.
       - Only relevant for QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   limit_bugs_by_product:
     description:
       - Only relevant for QuarterlyUpdate releases.
     choices: [true, false]
     default: false
     required: false
   state_machine_rule_set:
     description:
       - Workflow Rule Set
       - If you omit this parameter, Ansible will default to "null". For new
         releases, this means the release will inherit the product's ruleset.
         For existing releases, Ansible will not edit the server-side value if
         this is null.
       - To force Ansible to change an existing release's
         state_machine_rule_set to "null" on the ET server, set this parameter
         to an empty string "". For example, if the current rule set was
         "unrestricted" and you wanted to alter it to "null" (to inherit from
         the parent product), use an empty string here.
     choices: [Default, Unrestricted, CDN Push Only, Covscan,
               Non-blocking TPS, Optional TPS DistQA, Non-blocking rpmdiff for
               RHEL-8, Ansible, RHEL-8 GA, Non-blocking TPS & Covscan,
               Non-blocking Push target & Covscan]
     default: null
     required: false
   pelc_product_version_name:
     description:
       - If your release does not use PELC, you can omit this parameter and
         the ET server will default this value to "null".
       - If the ET server already has a PELC version defined for this release
         and you wish to *unset* it, set this pelc_product_version_name
         parameter to an empty string "".
     default: null
     required: false
   brew_tags:
     description:
       - Set to an empty list "[]" to simply inherit the brew_tags
         configuration from this release's ... Product Versions?.
     required: true
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


def get_release(client, name):
    # cannot get releases directly by name, CLOUDWF-1
    r = client.get('api/v1/releases?filter[name]=%s' % name)
    r.raise_for_status()
    data = r.json()
    results = data['data']
    if not results:
        return None
    if len(results) > 1:
        raise ValueError('multiple %s releases found' % name)
    release_data = results[0]
    release = {}
    release['id'] = release_data['id']
    release.update(release_data['attributes'])

    # product
    product = release_data['relationships']['product']
    if product:
        release['product'] = product['short_name']
    else:
        release['product'] = None

    # program_manager
    program_manager = release_data['relationships']['program_manager']
    if program_manager:
        release['program_manager'] = program_manager['login_name']
    else:
        release['program_manager'] = None

    # state_machine_rule_set
    rule_set = release_data['relationships']['state_machine_rule_set']
    if rule_set:
        release['state_machine_rule_set'] = rule_set['name']
    else:
        release['state_machine_rule_set'] = None

    # brew_tags
    release['brew_tags'] = release_data['relationships']['brew_tags']

    # product_versions
    product_version_data = release_data['relationships']['product_versions']
    product_versions = [pv['name'] for pv in product_version_data]
    release['product_versions'] = product_versions

    # The current REST API returns some inconsistent names for booleans.
    # "enabled" has no verb, but "is_active" has a verb.
    # Rather than exposing this ugly API detail to users, we will paper
    # over it here by renaming the keys to drop "is_".
    release['active'] = release.pop('is_active')

    # The API returns a full timestamp "ship_date", but we only accept
    # "YYYY-MM-DD" in Ansible. "dateutil" would be more robust, but I'm trying
    # to keep the dependencies light for this initial implementation.
    if release['ship_date'] is not None:
        release['ship_date'] = release['ship_date'][:10]

    return release


def get_product_id(client, name):
    response = client.get('api/v1/products/%s' % name)
    response.raise_for_status()
    data = response.json()
    return data['data']['id']


def get_product_version_ids(client, names):
    # We have to use the "older" JSON API here since this release may not have
    # a product at all.
    ids = []
    for name in names:
        response = client.get('product_versions/%s.json' % name)
        response.raise_for_status()
        data = response.json()
        ids.append(data['id'])
    return ids


def api_data(client, params):
    """ Transform our Ansible params into JSON data for POST'ing or PUT'ing.

    :param client: Errata Client
    :param dict params: ansible module params
    """
    # XXX The docs at /developer-guide/api-http-api.html#api-apis
    # mention a few settings I have not seen before:
    # - "allow_beta"
    # - "is_deferred"
    # - "url_name" - this one is actually listed twice!
    # Are those really a valid settings? grep errata-rails.git for more
    # references to find out. That whole POST /api/v1/releases section of the
    # docs could probably use a review.
    # CLOUDWF-298 is an RFE for specifying all values by name instead of ID.
    release = params.copy()
    # Update the values for ones that the REST API will accept:
    if 'product' in release:
        product_name = release.pop('product')
        if product_name is not None:
            release['product_id'] = get_product_id(client, product_name)
    if 'program_manager' in release:
        pm_login_name = release.pop('program_manager')
        program_manager_id = common_errata_tool.user_id(client, pm_login_name)
        release['program_manager_id'] = program_manager_id
    # "active" -> "isactive"
    if 'active' in release:
        active = release.pop('active')
        release['isactive'] = active
    # "supports_component_acl" -> "disable_acl"
    if 'supports_component_acl' in release:
        supports_component_acl = release.pop('supports_component_acl')
        release['disable_acl'] = not supports_component_acl
    # "product_versions" -> "product_version_ids"
    if 'product_versions' in release:
        product_versions = release.pop('product_versions')
        product_version_ids = get_product_version_ids(client, product_versions)
        release['product_version_ids'] = product_version_ids
    # "state_machine_rule_set" -> "state_machine_rule_set_id"
    if 'state_machine_rule_set' in release:
        state_machine_rule_set = release.pop('state_machine_rule_set')
        if state_machine_rule_set:
            rules_scraper = common_errata_tool.WorkflowRulesScraper(client)
            rule_set_id = int(rules_scraper.enum[state_machine_rule_set])

            release['state_machine_rule_set_id'] = rule_set_id
        else:
            release['state_machine_rule_set_id'] = None
    # "blocker_flags" list -> str
    if 'blocker_flags' in release:
        release['blocker_flags'] = ",".join(release['blocker_flags'])
    data = {'release': release}
    if 'type' in params:
        data['type'] = params['type']
    return data


def create_release(client, params):
    data = api_data(client, params)
    response = client.post('api/v1/releases', json=data)
    if response.status_code != 201:
        raise ValueError(response.json())


def edit_release(client, release_id, differences):
    # Create a Ansible params-like dict for the api_data() method.
    params = {}
    for difference in differences:
        key, _, new = difference
        params[key] = new
    data = api_data(client, params)
    response = client.put('api/v1/releases/%d' % release_id, json=data)
    if response.status_code != 200:
        raise ValueError(response.json())


def ensure_release(client, params, check_mode):
    # Note: this looks identical to the diff_product() method.
    # Maybe we can generalize this.
    result = {'changed': False, 'stdout_lines': []}
    params = {param: val for param, val in params.items() if val is not None}

    # Special-case state_machine_rule_set, because it's an enum, and it's
    # important to be able to set this back to "null" if desired:
    if params.get('state_machine_rule_set') == '':
        params['state_machine_rule_set'] = None

    name = params['name']
    release = get_release(client, name)
    if not release:
        result['changed'] = True
        result['stdout_lines'] = ['created %s' % name]
        if not check_mode:
            create_release(client, params)
        return result
    differences = common_errata_tool.diff_settings(release, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        if not check_mode:
            # CLOUDWF-6: we must send product_version_ids in every request,
            # or the server will reset the product versions to an empty list.
            keys = [difference[0] for difference in differences]
            if 'product_versions' not in keys:
                differences.append(('product_versions',
                                    params['product_versions'],
                                    params['product_versions']))
            edit_release(client, release['id'], differences)
    return result


def run_module():
    module_args = dict(
        product=dict(),
        name=dict(required=True),
        description=dict(required=True),
        type=dict(required=True, choices=common_errata_tool.RELEASE_TYPES),
        product_versions=dict(type='list', required=True),
        enabled=dict(type='bool', default=True),
        active=dict(type='bool', default=True),
        enable_batching=dict(type='bool', default=True),
        program_manager=dict(required=True),
        blocker_flags=dict(type='list'),
        internal_target_release=dict(),
        zstream_target_release=dict(),
        ship_date=dict(),
        allow_shadow=dict(type='bool', default=False),
        allow_blocker=dict(type='bool', default=False),
        allow_exception=dict(type='bool', default=False),
        allow_pkg_dupes=dict(type='bool', default=False),
        supports_component_acl=dict(type='bool', default=False),
        limit_bugs_by_product=dict(type='bool', default=False),
        state_machine_rule_set=dict(),
        pelc_product_version_name=dict(),
        brew_tags=dict(type='list', default=[]),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = ensure_release(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
