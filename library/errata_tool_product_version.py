from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_product_version

short_description: Create and manage Product Versions in the Errata Tool
description:
   - Create, update, and delete Product Versions within Red Hat's Errata Tool.
options:
   product:
     description:
       - Product for this Product Version
       - "example: RHCEPH"
     required: true
   name:
     description:
       - "example: RHCEPH-4.0-RHEL-8"
     required: true
   description:
     description:
       - "example: Red Hat Ceph Storage 4.0"
     required: true
   rhel_release_name:
     description:
       - "example: RHEL-8"
     required: true
   sig_key_name:
     description:
       - Release key (eg. robosignatory uses this value)
       - You almost certainly never want to change this value.
     choices: [master, fedora, beta, test, none, redhatrelease, rhx,
               redhatrelease2, redhatengsystems]
     required: false
     default: redhatrelease2
   ima_sig_key_name:
     description:
       - Signing key for IMA (Integrity Measurement Architecture)
       - "example: redhatimarelease"
     required: false
   use_quay_for_containers:
     description:
       - The Errata Tool no longer uses this parameter. It is a no-op.
         Remove it from your playbooks.
     required: false
   use_quay_for_containers_stage:
     description:
       - The Errata Tool no longer uses this parameter. It is a no-op.
         Remove it from your playbooks.
     required: false
   default_brew_tag:
     description:
       - The default brew tag to use when validating that a build can be added
         to an advisory
       - "example: ceph-4.0-rhel-8-candidate"
       - You must specify this tag as one of the elements in the brew_tags
         list (see CLOUDWF-2)
     required: true
   is_server_only:
     description:
       - true if this product version only supports RHEL server
     choices: [true, false]
     required: true
   enabled:
     description:
       - Is this Product Version enabled (developers can file new advisories?)
     choices: [true, false]
     default: true
   allow_rhn_debuginfo:
     description:
       - '"true" if -debuginfo rpms from this product version can be shipped to
         RHN'
     choices: [true, false]
     required: true
   allow_buildroot_push:
     description:
       - If True, "Push to Buildroots" may be triggered on builds using this
         product version. Only makes sense with certain Brew configurations.
     choices: [true, false]
     required: true
   is_oval_product:
     description:
       - true if this product version supports OVAL generation
     choices: [true, false]
     required: true
   is_rhel_addon:
     description:
       - true if this is some form of RHEL Extras, Addon, Optional, etc
     choices: [true, false]
     required: true
   push_targets:
     description:
       - One or more push targets (specify a list)
       - See /developer-guide/push-push-targets-options-and-tasks.html
         for more explanation about these push targets.
       - This list must be a subset of the push targets that are set at the
         parent product level.
     choices: [rhn_live, rhn_stage, ftp, cdn, cdn_stage, altsrc, cdn_docker,
               cdn_docker_stage]
     required: true
   brew_tags:
     description:
       - An optional list of Brew tags. Developers must ensure that their
         builds are tagged with this Brew tag in order to attach to an
         advisory.
       - You must specify the default_brew_tag as one of the elements
         in this list (see CLOUDWF-2)
       - What are the consequences of a completely empty brew_tag list? This
         might be answered in CLOUDWF-2.
     required: true
   suppress_push_request_jira:
     description:
       - Set to true to suppress creating push request jira tickets.
       - Set to false to allow push request jira tickets.
       - If this value is different from the product's setting
         it will override it.
     choices: [true, false]
     required: false
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''

# The REST API requires that clients know the product name before querying the
# product version, so we have pass the "product" variable through to the
# get/create/edit methods. SPMM-6319 tracks improving that so that we could
# get/create/edit without the product name.


def get_product_version(client, product, name, check_mode):
    # We cannot query directly by name yet if the name has a "." character.
    # See CLOUDWF-3.
    # url = 'api/v1/products/%s/product_versions/%s' % (product, name)
    # ... this would also change the returned data structure slightly (the
    # results would not be in a list.)
    url = 'api/v1/products/%s/product_versions/' % product
    r = client.get(url, params={'filter[name]': name})
    # If the product does not exist but we're running in check mode it could
    # be that the product is going to be setup in the subsequent run mode
    # run. In this case the query will return 404 but that would be expected
    # and this task should not fail as a result.
    if r.status_code == 404 and check_mode:
        return None
    # If the product does not exist yet, we'll get a 404 error for this GET
    # request. It's nice that raise_for_status() gives us the full URL that we
    # tried because then users can verify they are using the proper ET
    # environment. Maybe we could log a more specific error message for that
    # condition so that it's easier for the user to understand the problem,
    # like "does https://errata.devel.redhat.com/products/RHCEPH exist yet?"
    r.raise_for_status()
    data = r.json()
    product_versions = data['data']
    if not product_versions:
        return None
    if len(product_versions) > 1:
        raise ValueError('multiple PVs named %s' % name)
    # Reformat the data into something we can compare with Ansible params
    data = product_versions[0]
    product_version = data['attributes']
    product_version['brew_tags'] = data['brew_tags']
    rhel_release = data['relationships']['rhel_release']['name']
    product_version['rhel_release_name'] = rhel_release
    product_version['sig_key_name'] = data['relationships']['sig_key']['name']
    product_version['ima_sig_key_name'] = \
        data['relationships'].get('ima_sig_key', {'name': None})['name']
    # push_targets
    push_targets = [t['name'] for t in data['relationships']['push_targets']]
    product_version['push_targets'] = push_targets
    # Add in our product name, to simplify diff_settings().
    product_version['product'] = product
    # Add in our product_version id, to support edit_product_version()
    product_version['id'] = data['id']
    return product_version


def handle_form_errors(response):
    # If there are incorrect or missing fields, we will receive a HTTP 200
    # with a list of the wrong fields, or just an HTTP 500 error.
    if response.status_code == 500:
        raise RuntimeError(
            'The request to %s had a status code of %d and failed with: %s'
            % (response.url, response.status_code, response.text)
        )
    if 'errorExplanation' in response.text:
        raise RuntimeError(response.text)
    response.raise_for_status()


def create_product_version(client, product, params):
    # TODO: test this without casting the bools to ints. Since we're passing
    # JSON and that has real "true"/"false" values, it should be ok.
    pv = {}
    pv['name'] = params['name']
    pv['description'] = params['description']
    pv['allow_rhn_debuginfo'] = int(params['allow_rhn_debuginfo'])
    pv['default_brew_tag'] = params['default_brew_tag']
    pv['enabled'] = int(params['enabled'])
    pv['is_oval_product'] = int(params['is_oval_product'])
    pv['is_rhel_addon'] = int(params['is_rhel_addon'])
    pv['is_server_only'] = int(params['is_server_only'])
    pv['brew_tags'] = params['brew_tags']
    pv['rhel_release_name'] = params['rhel_release_name']
    pv['sig_key_name'] = params['sig_key_name']
    pv['ima_sig_key_name'] = params.get('ima_sig_key_name')
    pv['allow_buildroot_push'] = params['allow_buildroot_push']
    pv['push_targets'] = params['push_targets']
    data = {'product_version': pv}
    endpoint = 'api/v1/products/%s/product_versions' % product
    response = client.post(endpoint, json=data)
    if response.status_code != 201:
        raise common_errata_tool.ErrataToolError(response)


def edit_product_version(client, product_version, differences):
    """
    Edit an existing product.

    :param client: Errata Client
    :param dict product_version: Product Version to change
    :param list differences: Settings to change for this Product Version. This
                             is a list of three-element tuples from
                             diff_settings().
    """
    pv = {}
    for difference in differences:
        key, _, new = difference
        pv[key] = new
    if not pv:
        return
    data = {'product_version': pv}
    pv_id = product_version['id']
    product = product_version['product']
    endpoint = 'api/v1/products/%s/product_versions/%d' % (product, pv_id)
    response = client.put(endpoint, json=data)
    if response.status_code != 200:
        raise common_errata_tool.ErrataToolError(response)


def prepare_diff_data(before, after):
    return common_errata_tool.task_diff_data(
        before=before,
        after=after,
        item_name=after['name'],
        item_type='product version',
    )


def ensure_product_version(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    params = {param: val for param, val in params.items() if val is not None}
    product = params['product']
    name = params['name']
    product_version = get_product_version(client, product, name, check_mode)
    if not product_version:
        result['changed'] = True
        result['stdout_lines'] = ['created %s product version' % name]
        result['diff'] = prepare_diff_data(product_version, params)
        if not check_mode:
            create_product_version(client, product, params)
        return result
    differences = common_errata_tool.diff_settings(product_version, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        result['diff'] = prepare_diff_data(product_version, params)
        if not check_mode:
            edit_product_version(client, product_version, differences)
    return result


def run_module():
    module_args = dict(
        product=dict(required=True),
        name=dict(required=True),
        description=dict(required=True),
        rhel_release_name=dict(required=True),
        sig_key_name=dict(default='redhatrelease2'),
        ima_sig_key_name=dict(type='str'),
        default_brew_tag=dict(required=True),
        is_server_only=dict(type='bool', required=True),
        enabled=dict(type='bool', default=True),
        allow_rhn_debuginfo=dict(type='bool', required=True),
        allow_buildroot_push=dict(type='bool', required=True),
        is_oval_product=dict(type='bool', required=True),
        is_rhel_addon=dict(type='bool', required=True),
        push_targets=dict(type='list', required=True),
        brew_tags=dict(type='list', required=True),
        use_quay_for_containers=dict(type='bool'),
        use_quay_for_containers_stage=dict(type='bool'),
        suppress_push_request_jira=dict(type='bool'),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    # 'use_quay_for_containers' and 'use_quay_for_containers_stage' are
    # deprecated.
    params.pop('use_quay_for_containers')
    params.pop('use_quay_for_containers_stage')

    result = ensure_product_version(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
