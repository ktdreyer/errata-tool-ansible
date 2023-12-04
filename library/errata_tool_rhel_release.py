from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: errata_tool_rhel_release

short_description: Create and manage Rhel Releases in the Errata Tool
description:
   - Create, update, and delete Rhel Releases within Red Hat's Errata Tool.
options:
   name:
     description:
       - Name of the RHEL release
       - "example: RHEL-8.2.0.Z.E4S"
     required: true
   description:
     description:
       - Description for the RHEL release.
       - "example: Release for RHEL-8.2.0.Z.E4S"
     required: true
   exclude_ftp_debuginfo:
     description:
       - If true, debuginfo rpms will not be shipped to public FTP.
     required: false
     default: true
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


def get_rhel_release(client, name):
    """
    Get a single RHEL release by name.

    :param client: Errata Client
    :param str name: RHEL release name
    """

    # Find the RHEL release using the name filter since the api doesn't support
    # finding by name yet, even though it claims it can.
    # TODO - update this once the endpoint allows finding by name.
    response = client.get('api/v1/rhel_releases', params={'filter[name]': name})
    response.raise_for_status()

    data = response.json()
    rhel_releases = data['data']
    if not rhel_releases:
        return None
    if len(rhel_releases) > 1:
        raise ValueError('multiple rhel releases named %s' % name)

    data = rhel_releases[0]
    rhel_release = data['attributes']
    rhel_release['id'] = data['id']

    return rhel_release


def create_rhel_release(client, params):
    """
    Create a new ET rhel release

    :param client: Errata Client
    :param dict params: ansible module params
    """
    # In errata tool, there seems to be 2 formats
    # for the params when creating or updating a rhel release:
    # - creating: { 'key': 'val', ... }
    # - updating: { 'rhel_release': { 'key': 'val', ... } }
    rhel_release = params.copy()
    response = client.post('api/v1/rhel_releases', json=rhel_release)
    if response.status_code != 201:
        raise common_errata_tool.ErrataToolError(response)


def edit_rhel_release(client, rhel_release_id, differences):
    """
    Edit an existing rhel release.
    :param client: Errata client
    :param int rhel_release_id: ID of rhel release we will edit
    : param list differences: changes to make
    """

    # Create an Ansible params-like dict for the API.
    params = {}
    for difference in differences:
        key, _, new = difference
        params[key] = new

    endpoint = 'api/v1/rhel_releases/%d' % rhel_release_id
    data = {'rhel_release': params}
    response = client.put(endpoint, json=data)

    if response.status_code != 200:
        raise common_errata_tool.ErrataToolError(response)


def prepare_diff_data(before, after):
    return common_errata_tool.task_diff_data(
        before=before,
        after=after,
        item_name=after['name'],
        item_type='rhel_release',
        keys_to_copy=[
            # Any field listed here exists in ET but is not
            # yet supported by this ansible module
        ],
    )


def ensure_rhel_release(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    params = {param: val for param, val in params.items() if val is not None}
    name = params['name']
    rhel_release = get_rhel_release(client, name)
    if not rhel_release:
        result['changed'] = True
        result['stdout_lines'] = ['created %s' % name]
        result['diff'] = prepare_diff_data(rhel_release, params)
        if not check_mode:
            create_rhel_release(client, params)
        return result
    differences = common_errata_tool.diff_settings(rhel_release, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        result['diff'] = prepare_diff_data(rhel_release, params)
        if not check_mode:
            edit_rhel_release(client, rhel_release['id'], differences)
    return result


def run_module():
    module_args = dict(
        name=dict(required=True),
        description=dict(required=True),
        exclude_ftp_debuginfo=dict(type='bool')
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = ensure_rhel_release(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
