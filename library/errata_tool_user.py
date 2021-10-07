from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_user

short_description: Create and manage Users in the Errata Tool
description:
   - Create and update Users within Red Hat's Errata Tool.
options:
   login_name:
     description:
       - The user's login name, like kdreyer@redhat.com
     required: true
   realname:
     description:
       - The user's real name, like Ken Dreyer
     required: true
   organization:
     description:
       - The user's organization, like "Engineering"
       - If you specify no "organization" setting and the user does not
         already exist, the Errata Tool will default the brand new user
         account's organization to "Engineering".
       - If you specify no "organization" setting and the user account already
         exists, Ansible will not edit the existing organization value.
     required: false
     default: The ET server defaults to "Engineering" for new users
   receives_mail:
     description:
       - Whether the user will receive email or not.
     required: false
     default: true
   enabled:
     description:
       - Whether the user is enabled or not.
     required: false
     default: true
   email_address:
     description:
       - The email address for this user.
       - If you do not set this parameter and the user does not yet exist,
         Ansible will create the user by selecting the login_name string
         before "@" and appending a redhat.com domain for an email address.
         For example, if a new user's login_name is "kdreyer@redhat.com", the
         default email_address will be "kdreyer@redhat.com".
       - If you do not set this parameter and the user already exists on the
         server, Ansible will not edit the existing email address for this
         user account.
     required: false
   roles:
     description:
       - A list of roles for this user, for example ["pm"]
       - If you do not set this parameter and the user does not yet exist, the
         ET will create the new user with no roles. If you do not set this
         parameter and the user already exists on the server, Ansible will not
         edit the existing roles for this user account.
     required: false
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


def get_user(client, login_name):
    response = client.get('api/v1/user/%s' % login_name)
    data = response.json()
    if response.status_code == 400 and 'errors' in data:
        login_name_errors = data['errors'].get('login_name', [])
        if '%s not found.' % login_name in login_name_errors:
            return None
    response.raise_for_status()
    return data


def create_user(client, params):
    endpoint = 'api/v1/user'

    # Hack for CLOUDWF-2817 - If the user's receives_mail attribute is true,
    # we must always send the intended email_address as well.
    if params['receives_mail'] and params.get('email_address') is None:
        # The user wanted the ET to choose a default email address, so we
        # approximate that here:
        account_name, _ = params['login_name'].split('@', 1)
        params['email_address'] = '%s@redhat.com' % account_name

    response = client.post(endpoint, json=params)
    if response.status_code != 201:
        response_data = response.json()
        if 'errors' not in response_data:
            raise ValueError(response_data)
        errors = response_data['errors']
        raise ValueError(errors)


def edit_user(client, user_id, differences):
    """
    Edit an existing user.

    :param client: Errata Client
    :param int user_id: User to change
    :param list differences: Settings to change for this User. This is a list
                             of three-element tuples from diff_settings().
    """
    user = {}
    for difference in differences:
        key, _, new = difference
        user[key] = new
    endpoint = 'api/v1/user/%d' % user_id
    response = client.put(endpoint, json=user)
    if response.status_code != 200:
        raise ValueError(response.json())


def ensure_user(client, params, check_mode):
    result = {'changed': False, 'stdout_lines': []}
    params = {param: val for param, val in params.items() if val is not None}
    login_name = params['login_name']
    user = get_user(client, login_name)
    if not user:
        result['changed'] = True
        result['stdout_lines'] = ['created %s user' % login_name]
        if not check_mode:
            create_user(client, params)
        return result
    user_id = user.pop('id')

    differences = common_errata_tool.diff_settings(user, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        if not check_mode:
            # Hack for CLOUDWF-2817 - If the user's receives_mail attribute is
            # true, we must always send the intended email_address as well.
            if params['receives_mail']:
                keys = [difference[0] for difference in differences]
                if 'email_address' not in keys:
                    differences.append(('email_address', '',
                                        user['email_address']))
            edit_user(client, user_id, differences)
    return result


def run_module():
    module_args = dict(
        login_name=dict(required=True),
        realname=dict(required=True),
        organization=dict(),
        receives_mail=dict(type='bool', default=True),
        roles=dict(type='list'),
        enabled=dict(type='bool', default=True),
        email_address=dict(),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = ensure_user(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
