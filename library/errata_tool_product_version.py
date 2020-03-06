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
       - Product for this Product Version - example: RHCEPH
     required: true
   name:
     description:
       - example: RHCEPH-4.0-RHEL-8
     required: true
   description:
     description:
       - example: Red Hat Ceph Storage 4.0
     required: true
   rhel_release_name:
     description:
       - example: RHEL-8
     required: true
   sig_key_name:
     description:
       - Release key (eg. robosignatory uses this value)
       - You almost certainly never want to change this value.
     choices: [master, fedora, beta, test, none, redhatrelease, rhx,
               redhatrelease2, redhatengsystems]
     required: false
     default: redhatrelease2
   default_brew_tag:
     description:
       - The default brew tag to use when validating that a build can be added
         to an advisory
       - example: ceph-4.0-rhel-8-candidate
       - You must specify this tag as one of the elements in the brew_tags
         list (see ERRATA-9713)
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
       - "true" if -debuginfo rpms from this product version can be shipped to
         RHN
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
     choices: [rhn_live, rhn_stage, ftp, cdn, cdn_stage, altsrc, cdn_docker,
               cdn_docker_stage]
     required: true
   brew_tags:
     description:
       - An optional list of Brew tags. Developers must ensure that their
         builds are tagged with this Brew tag in order to attach to an
         advisory.
       - You must specify the default_brew_tag as one of the elements
         in this list (see ERRATA-9713)
       - What are the consequences of a completely empty brew_tag list? This
         might be answered in ERRATA-9713.
     required: true
'''


class InvalidInputError(Exception):
    """ Invalid user input for a parameter """
    def __init__(self, param, value):
        self.param = param
        self.value = value


def get_product_version(client, product, name):
    # We cannot query directly by name yet if the name as a "." character.
    # See ERRATA-9712.
    # url = 'api/v1/products/%s/product_versions/%s' % (product, name)
    # ... this would also change the returned data structure slightly (the
    # results would not be in a list.)
    url = 'api/v1/products/%s/product_versions/?filter[name]=%s' % (product, name)
    r = client.get(url)
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
    product_version['rhel_release_name'] = data['relationships']['rhel_release']['name']
    product_version['sig_key_name'] = data['relationships']['sig_key']['name']
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
        raise RuntimeError(response)
    if 'errorExplanation' in response.text:
        raise RuntimeError(response.text)
    response.raise_for_status()


def set_push_targets(client, product, product_version, push_targets):
    """
    Set push targest through the web form.

    This is a temporary hack until we have API support in ERRATA-9714

    :param str product: product name
    :param str product_version: product version name (or id)
    :param list push_targets: Push Target names
    """
    if not push_targets:
        # Not implemented: not sure how to un-set all push_targets.
        # Just skip this case for now.
        return
    scraper = common_errata_tool.PushTargetScraper(client)
    push_target_ints = scraper.convert_to_ints(push_targets)
    endpoint = 'products/%s/product_versions/%s' % (product, product_version)
    data = {
        '_method': 'patch',
        'product_version[push_targets][]': push_target_ints
    }
    response = client.post(endpoint, data=data)
    handle_form_errors(response)


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
    pv['allow_buildroot_push'] = params['allow_buildroot_push']
    pv['push_targets'] = params['push_targets']
    data = {'product_version': pv}
    endpoint = 'api/v1/products/%s/product_versions' % product
    response = client.post(endpoint, json=data)
    if response.status_code != 201:
        raise ValueError(response.json())
    set_push_targets(client, product, params['name'], params['push_targets'])


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
        raise ValueError(response.json())
    if 'push_targets' in pv:
        set_push_targets(client, product, pv_id, pv['push_targets'])


def ensure_product_version(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    product = params['product']
    name = params['name']
    product_version = get_product_version(client, product, name)
    if not product_version:
        result['changed'] = True
        result['stdout_lines'] = ['created %s product version' % name]
        if not check_mode:
            create_product_version(client, product, params)
        return result
    differences = common_errata_tool.diff_settings(product_version, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
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
        default_brew_tag=dict(required=True),
        is_server_only=dict(type='bool', required=True),
        enabled=dict(type='bool', default=True),
        allow_rhn_debuginfo=dict(type='bool', required=True),
        allow_buildroot_push=dict(type='bool', required=True),
        is_oval_product=dict(type='bool', required=True),
        is_rhel_addon=dict(type='bool', required=True),
        push_targets=dict(type='list', required=True),
        brew_tags=dict(type='list', required=True),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = ensure_product_version(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
