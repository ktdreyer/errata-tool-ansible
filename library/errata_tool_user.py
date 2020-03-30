import re
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
     required: false
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
     required: false
     default: The ET server chooses a default email address.
   roles:
     description:
       - A list of roles for this user, for example ["pm"]
     required: false
'''


def scrape_user_id(client, login_name):
    """
    Screen-scrape the user ID number for this account.

    Sometimes we cannot load the user account by name, but it exists.
    Delete this method when ERRATA-9723 is resolved in prod.
    """
    data = {'user[login_name]': login_name}
    response = client.post('user/find_user', data=data, allow_redirects=False)
    if response.status_code != 302:
        return None
    location = response.headers['Location']
    # location is a URL like https://errata...com/user/3002859
    m = re.search(r'\d+$', location)
    if not m:
        return None
    user_id = m.group()
    return int(user_id)


def get_user(client, login_name):
    url = 'api/v1/user/%s' % login_name
    r = client.get(url)
    if r.status_code == 500:
        # We will get an HTTP 500 error if the user does not exist yet.
        # Delete this condition once ERRATA-9723 is resolved.
        return None
    if r.status_code == 404:
        # It's possible this user has already been created, but they have a
        # newer Kerberos account, and the ET API endpoint does not process
        # those (see ERRATA-9723). Hack: screen-scrape the UID and try again
        # with the number instead.
        user_id = scrape_user_id(client, login_name)
        if not user_id:
            return None
        return get_user(client, user_id)
    if r.status_code == 400:
        data = r.json()
        errors = data.get('errors', {})
        if errors:
            login_name_errors = errors.get('login_name', [])
            expected = '%s not found.' % login_name
            if expected in login_name_errors:
                return None
            # Unknown error(s). Raise what we have:
            raise ValueError(errors)
    r.raise_for_status()
    user = r.json()
    return user


def create_user(client, params):
    endpoint = 'api/v1/user'
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

    # This seems to match what the ET does when the client does not specify a
    # value:
    if params['email_address'] is None:
        account_name, _ = params['login_name'].split('@', 1)
        params['email_address'] = '%s@redhat.com' % account_name

    client = common_errata_tool.Client()

    result = ensure_user(client, params, check_mode)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
