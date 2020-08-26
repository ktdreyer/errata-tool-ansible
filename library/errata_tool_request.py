from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common_errata_tool import Client


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_request

short_description: Perform low-level HTTP requests to Errata Tool
description:
  - Perform direct HTTP requests to the Errata Tool.
  - This module is like Ansible's core "uri" module, except this respects the
    ERRATA_TOOL_URL and ERRATA_TOOL_AUTH variables and can perform SPENEGO
    (GSSAPI) authentication.
  - Why would you use this module instead of the higher level modules like
    errata_tool_product, errata_tool_user, etc? This errata_tool_request
    module has two main uses-cases.
  - 1. You may want to do something that the higher level modules do not yet
    support. It can be easier to use this module to quickly prototype out your
    ideas for what actions you need, and then write the Python code to do it
    in a better way later. If you find that you need to use
    errata_tool_request to achieve functionality that is not yet present in
    the other errata-tool-ansible modules, please file a Feature Request issue
    in GitHub with your use case.
  - 2. You want to write some tests that verify ET's data at a very low level.
    For example, you may want to write an integration test to verify that
    you've set up your ET configuration in the way you expect.
options:
   path:
     description:
       - The path to request, eg. /api/v1/user/kdreyer
     required: true
   method:
     description:
       - The HTTP method to use.
     required: false
     default: GET
   return_content:
     description:
       - If true, this module will return a "content" key with the body of the
         HTTP response. Independent of this setting, if python-requests can
         decode JSON from the HTTP response body, this module will return a
         "json" key with the parsed JSON data from the HTTP response.
     required: false
     default: false
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''


def run_module():
    module_args = dict(
        path=dict(required=True),
        method=dict(default='GET'),
        return_content=dict(type='bool', default=False),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )

    params = module.params

    client = Client()

    path = params['path'].lstrip('/')
    response = client.request(params['method'], path)
    json = None
    try:
        json = response.json()
    except ValueError:
        pass

    result = {
        'changed': True,
        'status': response.status_code,
        'url': response.url,
    }

    if params['return_content']:
        result['content'] = response.text

    if json is not None:
        result['json'] = json

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
