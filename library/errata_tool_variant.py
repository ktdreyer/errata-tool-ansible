from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_variant

short_description: Create and manage variants in the Errata Tool
description:
   - Create, update, and delete variants within Red Hat's Errata Tool.
options:
   name:
     description:
       - example: 8Base-RHCEPH-4.0-Tools
     required: true
   description:
     description:
       - example: Red Hat Ceph Storage 4.0 Tools
     required: true
   cpe:
     description:
       - This requires secalert or admin permissions. Very few people have
         permissions to configure the cpe text value. If you omit this value,
         Ansible will not set it during variant creation or edit it on an
         existing variant.
       - example: "cpe:/a:redhat:ceph_storage:4::el8"
     required: false
   enabled:
     required: false
     default: true
   buildroot:
     required: false
     default: false
   product_version:
     description:
       - example: RHCEPH-4.0-RHEL-8
     required: true
   rhel_variant:
     description:
       - example: 8Base
       - I'm guessing that only Layered Products require this, so it should
         not really be mandatory, but I'm unfamiliar with how RHEL itself is
         configured in the Errata Tool.
     required: true
   push_targets:
     description:
       - One or more push targets (specify a list)
       - See /developer-guide/push-push-targets-options-and-tasks.html
         for more explanation about these push targets.
       - This list must be a subset of the push targets that are set at the
         parent product version level.
     choices: [rhn_live, rhn_stage, cdn, cdn_stage, altsrc, cdn_docker,
               cdn_docker_stage]
     required: true
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


def get_variant(client, name):
    """
    Get information about a variant in the Errata Tool, and simplify it into
    a format we can compare with our Ansible parameters.

    :param client: Errata Client
    :param str name: Variant name to search
    :returns: dict of information about this variant, or None
    """
    # We cannot get the name directly yet, ERRATA-9715
    # r = client.get('api/v1/variants/%s' % name)
    r = client.get('api/v1/variants?filter[name]=%s' % name)
    r.raise_for_status()
    data = r.json()
    results = data['data']
    if not results:
        return None
    if len(results) > 1:
        raise ValueError('multiple %s variants found' % name)
    variant_data = results[0]
    variant = {}
    variant['id'] = variant_data['id']
    # Unique to this variants API endpoint:
    # "relationships" are nested inside "attributes".
    # API Doc fix at ERRATA-9716
    attributes = variant_data['attributes']
    variant.update(attributes)
    relationships = variant.pop('relationships')
    variant['product'] = relationships['product']['short_name']
    variant['product_version'] = relationships['product_version']['name']
    variant['rhel_variant'] = relationships['rhel_variant']['name']
    push_targets = [pt['name'] for pt in relationships['push_targets']]
    variant['push_targets'] = push_targets
    return variant


def create_variant(client, params):
    """
    Create a new ET variant

    :param client: Errata Client
    :param dict params: ansible module params
    """
    data = {'variant': params}
    response = client.post('api/v1/variants', json=data)
    if response.status_code != 201:
        data = response.json()
        raise ValueError(data['error'])


def edit_variant(client, variant_id, differences):
    """
    Edit an existing variant.

    See ERRATA-9717 for official edit API.

    :param client: Errata Client
    :param int variant_id: ID number for the variant
    :param list differences: changes to make
    """
    # Create a Ansible params-like dict for the API.
    params = {}
    for difference in differences:
        key, _, new = difference
        params[key] = new
    endpoint = 'api/v1/variants/%d' % variant_id
    data = {'variant': params}
    response = client.put(endpoint, json=data)
    # TODO: verify 200 is the right code to expect here?
    if response.status_code != 200:
        data = response.json()
        raise ValueError(data['error'])


def ensure_variant(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    name = params['name']
    variant = get_variant(client, name)
    if not variant:
        result['changed'] = True
        result['stdout_lines'] = ['created %s variant' % name]
        if not check_mode:
            create_variant(client, params)
        return result
    # Don't print a diff for CPE if it was omitted
    if params['cpe'] is None:
        params.pop('cpe')
    differences = common_errata_tool.diff_settings(variant, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        if not check_mode:
            edit_variant(client, variant['id'], differences)
    return result


def run_module():
    module_args = dict(
        name=dict(required=True),
        description=dict(required=True),
        cpe=dict(),
        enabled=dict(type='bool', default=True),
        buildroot=dict(type='bool', default=False),
        product_version=dict(required=True),
        rhel_variant=dict(required=True),
        push_targets=dict(type='list', required=True),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = ensure_variant(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
