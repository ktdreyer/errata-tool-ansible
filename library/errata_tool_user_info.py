from ansible.module_utils import common_errata_tool
from ansible.module_utils.basic import AnsibleModule

ANSIBLE_METADATA = {
    "metadata_version": "1.0",
    "status": ["preview"],
    "supported_by": "community",
}


DOCUMENTATION = """
---
module: errata_tool_user_info

short_description: Query users in the Errata Tool
description:
   - Query users within Red Hat's Errata Tool.
options:
   login_name:
     description:
       - The user's login name, like kdreyer@redhat.com
     required: true
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
"""

EXAMPLES = """
- name: Get user info
  errata_tool_user_info:
    login_name: "jdoe"
  register: user_info

- name: Check that user exists
  fail:
    msg: "User 'jdoe' does not exist"
  when: not user_info["exists"]

- name: Check required role
  fail:
    msg: "User 'jdoe' does not have role 'admin'"
  when: not 'admin' in user_info["data"]["roles"]
"""

RETURN = """
---
exists:
    description: Whether the user exists in the Errata Tool
    type: bool
    returned: always
    sample: True
data:
    description: User data returned from ET API
    type: dict
    returned: always
    sample: {
        "login_name": "jdoe",
        "realname": "John Doe",
        "roles": [
            "admin"
        ]
    }
"""


def get_user(client, login_name):
    """Get user info from ET API.

    Args:
        client: Requests client
        login_name (str): User's login name

    Returns:
        dict: {"exists": bool, "data": dict}
    """
    url = "api/v1/user/%s" % login_name
    r = client.get(url)

    if r.status_code == 400:
        data = r.json()
        errors = data.get("errors", {})

        if errors:
            login_name_errors = errors.get("login_name", [])
            expected = "%s not found." % login_name

            if expected in login_name_errors:
                return {"exists": False, "data": {}}

            # Unknown error(s). Raise what we have:
            raise ValueError(errors)

    r.raise_for_status()
    user = r.json()

    return {"exists": True, "data": user}


def run_module():
    module_args = dict(
        login_name=dict(type="str", required=True),
    )
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    check_mode = module.check_mode
    params = module.params

    client = common_errata_tool.Client()

    result = get_user(client, params["login_name"])

    if check_mode and not result["exists"]:
        result["warnings"] = [
            "User %s does not exist in the Errata Tool" % params["login_name"]
        ]

    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
