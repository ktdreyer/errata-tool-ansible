from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils import common_errata_tool
from ansible.module_utils.six import string_types


ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}


DOCUMENTATION = '''
---
module: errata_tool_cdn_repo

short_description: Create and manage CDN repositories in the Errata Tool
description:
   - Create and update CDN repositories within Red Hat's Errata Tool.
options:
   name:
     description:
       - Pulp repo label.
       - "Example: redhat-rhceph-rhceph-4-rhel8"
     required: true
   release_type:
     description:
       - "Example: Primary"
     choices: [Primary, EUS, LongLife]
     required: true
   content_type:
     description:
       - "Binary" for RPMs, "Docker" for containers.
     choices: [Binary, Debuginfo, Source, Docker]
     required: true
   variants:
     description:
       - A list of Variants for this CDN repo.
     required: true
   arch:
     description:
       - The architecture for this CDN repo. You can only set this for
         non-Docker (ie RPM) repos. Docker will always be "multi".
     choices: [i386, ia64, s390, x86_64, s390x, ppc, ppc64, aarch64, ppc64le]
     default: "x86_64" for RPMs, "multi" for Docker.
   use_for_tps:
     description:
       - Use TPS for Scheduling
     choices: [true, false]
     default: false
   packages:
     description:
       - A dict of packages for this CDN repo. Each dict key is the package
         name, and the value is the list of tags for the package.
       - Each tag can be a string or a dict. If the tag is a string, the
         Errata Tool will apply this package's tag to all variants. If the tag
         is a dict, the Errata Tool will apply the package's tag to the single
         variant that you specify in the dict.
       - If you omit this parameter, Ansible will remove all the existing
         packages from this repository. You should omit this parameter for
         repositories that are not content_type: Docker.
     required: false
     default: {} (no packages)
requirements:
  - "python >= 2.7"
  - "lxml"
  - "requests-gssapi"
'''

EXAMPLES = '''
- name: create cdn repositories
  hosts: localhost
  tasks:

  - name: Add rhceph-4-tools-for-rhel-8-x86_64-rpms cdn repo
    errata_tool_cdn_repo:
      name: redhat-rhceph-rhceph-4-rhel8
      release_type: Primary
      content_type: Binary
      use_for_tps: True
      arch: x86_64
      variants:
      - 8Base-RHCEPH-4.0-Tools
      - 8Base-RHCEPH-4.1-Tools

  - name: Add redhat-rhceph-rhceph-4-rhel8 cdn repo
    errata_tool_cdn_repo:
      name: redhat-rhceph-rhceph-4-rhel8
      release_type: Primary
      content_type: Docker
      variants:
      - 8Base-RHCEPH-4.0-Tools
      - 8Base-RHCEPH-4.1-Tools
      packages:
        rhceph-container:
        - latest
        - "{{ '{{' }}version{{ '}}' }}"
        - "{{ '{{' }}version{{ '}}' }}-{{ '{{' }}release{{ '}}' }}"

  - name: Add a repo with a restricted tag
    errata_tool_cdn_repo:
      name: redhat-fooproduct-1-rhel8
      release_type: Primary
      content_type: Docker
      variants:
      - 8Base-FOO-1.0-Tools
      - 8Base-FOO-1.1-Tools
      packages:
        foo-container:
        - latest
        - my-restricted-variant-tag:
            variant: 8Base-FOO-1.0-Tools
'''

CDN_RELEASE_TYPES = [
    'Primary',
    'EUS',
    'LongLife',
]

CDN_CONTENT_TYPES = [
    'Binary',
    'Debuginfo',
    'Source',
    'Docker',
]

# API Pagination
PAGE_SIZE = 100


def normalize_packages(packages):
    """
    Normalize the "packages" values from the Ansible task.

    For each package, users pass in a list of tag templates. The list elements
    can be strings or dicts.

    Normalize this in the following ways:
    1) Translate each tags list to a dict. This ensures that every
       tag is unique.
    2) Transform every tag value to individual dicts. This makes comparisons
       easier with our live data in the ET.

    :param dict packages: Each key is a package name, and each value is a
                          (possibly empty) list of tags. Each tag is either a
                          string or a dict.
    :returns: A dict of packages. Each key is a package name. Each value is a
              dict of tags. Each tag dictionary is empty (to indicate no
              variant restrictions), or has a "variant" key (to indicate a
              variant restriction).
    """
    normalized = {}
    for package_name, tags in packages.items():
        normalized[package_name] = {}
        for tag in tags:
            if isinstance(tag, string_types):
                # No variant restrictions present
                normalized[package_name][tag] = {}
            elif isinstance(tag, dict):
                # Variant restrictions present
                tag_string = next(iter(tag))
                variant_restriction = tag[tag_string]
                normalized[package_name][tag_string] = variant_restriction
            else:
                raise ValueError('unexpected %s' % type(tag))
    return normalized


def get_package_tags_page(client, name, page_number):
    """
    Get api/v1/cdn_repo_package_tags for a named CDN repository.
    """
    params = {
        'page[size]': PAGE_SIZE,
        'page[number]': page_number,
        'filter[cdn_repo_name]': name,
    }
    endpoint = 'api/v1/cdn_repo_package_tags'
    response = client.get(endpoint, params=params)
    response.raise_for_status()
    data = response.json()
    return data['data']


def get_package_tags(client, name):
    """
    Look up the variant restrictions for all packages/tags for this repo.

    Note it's possible that the ET team could consider other package/tag
    restrictions in the future. See ERRATA-5644 for one example of
    how this might possibly change in the future.

    :param str name: CDN Repository name
    :returns: dict of "packages: tag_templates". Each tag_template is a dict.
              If it has a "variant" key, then it is restricted to a variant.
              If it has no "variant" key, there are no restrictions for this
              repo's package's tag_template.
    """
    # We will query all the packages for this repo.
    # Example for looking up one single package in one single repo:
    # https://errata.devel.redhat.com/api/v1/cdn_repo_package_tags?filter[package_name]=ubi8-container&filter[cdn_repo_name]=redhat-ubi8
    page_number = 0
    elements = []
    found = []
    while (page_number == 0 or found == PAGE_SIZE):
        page_number += 1
        found = get_package_tags_page(client, name, page_number)
        elements += found
    packages = {}
    for element in elements:
        id_ = element['id']
        package_name = element['relationships']['package']['name']
        tag_template = element['attributes']['tag_template']
        if package_name not in packages:
            packages[package_name] = {}
        if 'variant' in element['relationships']:
            variant_name = element['relationships']['variant']['name']
            packages[package_name][tag_template] = {'variant': variant_name,
                                                    'id': id_}
        else:
            packages[package_name][tag_template] = {'id': id_}
    return packages


def get_cdn_repo(client, name, cdn_repo_data=None):
    """
    Get information about a CDN repo in the Errata Tool, and simplify it into
    a format we can compare with our Ansible parameters.

    :param client: Errata Client
    :param str name: CDN Repository name
    :param dict cdn_repo_data: data about this CDN repository (eg. from an
                               earlier POST response).
    :returns: dict of information about this CDN repository
    """
    if cdn_repo_data is None:
        # ERRATA-9728 to get cdn_repos directly by name.
        response = client.get('api/v1/cdn_repos?filter[name]=%s' % name)
        response.raise_for_status()
        json = response.json()
        results = json['data']
        if not results:
            return None
        if len(results) > 1:
            raise ValueError('multiple %s cdn_repos found' % name)
        cdn_repo_data = results[0]
    cdn_repo = {}
    cdn_repo['id'] = cdn_repo_data['id']
    cdn_repo.update(cdn_repo_data['attributes'])
    cdn_repo['arch'] = cdn_repo_data['relationships']['arch']['name']

    # variants
    variants = [variant['name'] for variant in
                cdn_repo_data['relationships']['variants']]
    cdn_repo['variants'] = variants

    # packages (names only)
    packages = cdn_repo_data['relationships'].get('packages', [])
    package_names = [package['name'] for package in packages]
    cdn_repo['package_names'] = package_names
    return cdn_repo


def cdn_repo_api_data(params):
    """
    Transform our Ansible params into JSON data for POST'ing or PUT'ing.
    to /api/v1/cdn_repo.
    """
    cdn_repo = params.copy()
    # Update the values for ones that the REST API will accept:
    if 'arch' in cdn_repo:
        cdn_repo['arch_name'] = cdn_repo.pop('arch')
    if 'variants' in cdn_repo:
        cdn_repo['variant_names'] = cdn_repo.pop('variants')
    data = {'cdn_repo': cdn_repo}
    return data


def create_cdn_repo(client, params):
    data = cdn_repo_api_data(params)
    response = client.post('api/v1/cdn_repos', json=data)
    data = response.json()
    if response.status_code != 201:
        raise ValueError(data['error'])
    name = params['name']
    cdn_repo_data = data['data']
    return get_cdn_repo(client, name, cdn_repo_data=cdn_repo_data)


def edit_cdn_repo(client, cdn_repo_id, differences):
    # Create a Ansible params-like dict for the api_data() method.
    params = {}
    for difference in differences:
        key, _, new = difference
        params[key] = new
    data = cdn_repo_api_data(params)
    response = client.put('api/v1/cdn_repos/%d' % cdn_repo_id, json=data)
    if response.status_code != 200:
        data = response.json()
        raise ValueError(data['error'])


def add_package_tag(client, repo_name, package_name, tag_template, variant):
    """
    Create a new package tag for this CDN repo.

    :param client: Errata Client
    :param str repo_name: CDN Repo name
    :param str package_name: eg. "rhceph-container"
    :param str tag_template: tag template, eg. "latest" or "{{version}}"
    :param str variant: Restrict this tag to this variant. If this value is
                        None, do not set a variant restriction on this tag.
    """
    endpoint = 'api/v1/cdn_repo_package_tags'
    json_settings = {'cdn_repo_name': repo_name,
                     'package_name': package_name,
                     'tag_template': tag_template}
    if variant:
        json_settings['variant_name'] = variant
    json = {'cdn_repo_package_tag': json_settings}
    response = client.post(endpoint, json=json)
    if response.status_code != 201:
        data = response.json()
        raise ValueError(data['error'])


def edit_package_tag(client, tag_id, desired_tag):
    """
    Edit the settings (variant) for a package tag.

    :param client: Errata Client
    :param int tag_id: ID of the package tag to edit.
    :param dict desired_tag: dict describing the desired tag. If this dict has
                             a "variant" key, then we will set variant_name on
                             the tag. If the dict does not have a "variant"
                             key, then we will remove the variant for this
                             tag.
    """
    variant = desired_tag.get('variant')
    if variant:
        settings = {'variant_name': variant}
    else:
        settings = {'variant_id': None}
    json = {'cdn_repo_package_tag': settings}
    endpoint = 'api/v1/cdn_repo_package_tags/%d' % tag_id
    response = client.put(endpoint, json=json)
    if response.status_code != 200:
        data = response.json()
        raise ValueError(data['error'])


def delete_package_tag(client, tag_id):
    """
    Delete a tag for this package.

    :param client: Errata Client
    :param int tag_id: ID number of the tag to delete.
    """
    response = client.delete('api/v1/cdn_repo_package_tags/%d' % tag_id)
    if response.status_code != 204:
        data = response.json()
        raise ValueError(data['error'])


def compare_package_tags(package_name, tag_template, current, desired):
    """
    Compare the (variant) settings for a tag_template.

    Describe the changes from "current" to "desired".
    If there are no differences, return an empty list.

    :param str package_name: The package name, eg "rhceph-container"
    :param str tag_template: The tag_template value, eg "latest".
    :param dict current: The "current" tag template settings stored in the ET.
    :param dict desired: The tag template settings that the user wants to
                         have in the ET.
    :returns: list of human-readable changes.
    """
    # This is not a generalized dict diff tool, because we only look at one
    # single key ("variant") here for now.
    current_variant = current.get('variant')
    desired_variant = desired.get('variant')
    if current_variant == desired_variant:
        return []
    if current_variant and not desired_variant:
        return ['removing "%s" variant from %s "%s" tag template' %
                (current_variant, package_name, tag_template)]
    if not current_variant and desired_variant:
        return ['adding "%s" variant to %s "%s" tag template' %
                (desired_variant, package_name, tag_template)]
    if current_variant != desired_variant:
        return ['changing %s "%s" variant from "%s" to "%s"' %
                (package_name, tag_template, current_variant, desired_variant)]


def ensure_package_tags(client, repo_name, package_name, check_mode,
                        current_tags, desired_tags):
    """
    Ensure all tags are set for one package in this CDN repo.

    This method makes the "current_tags" match "desired_tags", and returns a
    human-readable list of the changes performed.

    :param client: Errata Client
    :param str repo_name: CDN Repo name
    :param str package_name: The package name, eg "rhceph-container"
    :param bool check_mode: describe what would happen, but don't do it.
    :param dict current_tags: Each key is a tag template, and each value is
                              a dict (the settings for those tag templates).
                              Each value dict has an "id" key that provides
                              the current ID number of this tag template. They
                              also may havee a "variant" key.
    :param dict desired_tags: Each key is a tag template, and each value is
                              a dict (the settings for those tag templates).
                              The value dicts may have a "variant" key if the
                              user wants to restrict thist tag to a single
                              variant, or else the value dicts are empty if
                              the tag is unrestricted.
    :returns: a (possibly-empty) list of human-readable changes.
    """
    changes = []
    # Find tags to remove.
    tag_templates_to_delete = set(current_tags) - set(desired_tags)
    for tag_template in tag_templates_to_delete:
        change = 'removing "%s" tag template from "%s"' \
                 % (tag_template, package_name)
        changes.append(change)
        if check_mode:
            continue
        id_to_delete = current_tags[tag_template]['id']
        delete_package_tag(client, id_to_delete)

    # Find tags to modify (ie change the variant).
    tag_templates_to_modify = set(current_tags) & set(desired_tags)
    for tag_template in tag_templates_to_modify:
        current_tag = current_tags[tag_template].copy()
        desired_tag = desired_tags[tag_template].copy()
        tag_template_id = current_tag.pop('id')
        differences = compare_package_tags(package_name,
                                           tag_template,
                                           current_tag,
                                           desired_tag)
        if differences:
            changes.extend(differences)
            if check_mode:
                continue
            edit_package_tag(client, tag_template_id, desired_tag)

    # Find tags to add.
    tag_templates_to_add = set(desired_tags) - set(current_tags)
    for tag_template in tag_templates_to_add:
        changes.append('adding "%s" tag template to "%s"' %
                       (tag_template, package_name))
        if check_mode:
            continue
        tag = desired_tags[tag_template]
        variant = tag.get('variant')
        add_package_tag(client, repo_name, package_name, tag_template, variant)
    return changes


def ensure_packages_tags(client, name, check_mode, packages):
    """
    Create:
    POST /api/v1/cdn_repo_package_tags POST
    DELETE /api/v1/cdn_repo_package_tags/{id} DELETE
    GET /api/v1/cdn_repo_package_tags/{id} GET
    PUT /api/v1/cdn_repo_package_tags/{id} PUT

    :param client: Errata Client
    :param str name: CDN Repo name
    :param bool check_mode: describe what would happen, but don't do it.
    :param dict packages: Normalized Ansible "packages" paramater (see
                          normalize_packages())
    :returns: a (possibly-empty) list of human-readable changes.
    """
    changes = []
    current = get_package_tags(client, name)

    for package_name in packages:
        current_tags = current[package_name]
        desired_tags = packages[package_name]

        package_changes = ensure_package_tags(client,
                                              name,
                                              package_name,
                                              check_mode,
                                              current_tags,
                                              desired_tags)

        changes.extend(package_changes)
    return changes


def ensure_cdn_repo(client, check_mode, params):
    """
    Ensure that this CDN repo exists in the Errata Tool.

    :param client: Errata Client
    :param bool check_mode: describe what would happen, but don't do it.
    :param dict params: Parameters from ansible
    """
    result = {'changed': False, 'stdout_lines': []}
    name = params['name']

    # Special handling for packages parameter:
    params = params.copy()
    packages = params.pop('packages')
    package_names = list(packages.keys())
    params['package_names'] = package_names
    packages = normalize_packages(packages)

    # main cdn_repo
    cdn_repo = get_cdn_repo(client, name)
    if not cdn_repo:
        result['changed'] = True
        result['stdout_lines'] = ['created %s' % name]
        if check_mode:
            return result
        cdn_repo = create_cdn_repo(client, params)

    differences = common_errata_tool.diff_settings(cdn_repo, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        if not check_mode:
            # ERRATA-9728 to access cdn_repos directly by name.
            edit_cdn_repo(client, cdn_repo['id'], differences)

    # packages (from /api/v1/cdn_repo_package_tags):
    package_tag_changes = ensure_packages_tags(client, name, check_mode,
                                               packages)
    if package_tag_changes:
        result['changed'] = True
        result['stdout_lines'].extend(package_tag_changes)
    return result


def run_module():
    module_args = dict(
        name=dict(required=True),
        release_type=dict(choices=CDN_RELEASE_TYPES, required=True),
        content_type=dict(choices=CDN_CONTENT_TYPES, required=True),
        arch=dict(),
        use_for_tps=dict(type='bool', default=False),
        variants=dict(type='list', required=True),
        packages=dict(type='dict', default={}),
    )
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    check_mode = module.check_mode
    params = module.params

    # The arch default value depends on content_type.
    # The reason we hard-code this here is to match the ET's behavior so that
    # we preserve idempotency on subsequent runs.
    if params['arch'] is None:
        if params['content_type'] == 'Docker':
            params['arch'] = 'multi'
        else:
            params['arch'] = 'x86_64'

    # The ET server does not stop users from setting Docker repos to other
    # arches (ERRATA-9726). We will guard that here for now.
    if params['content_type'] == 'Docker' and params['arch'] != 'multi':
        module.fail_json(msg='arch must be "multi" for Docker repos')

    client = common_errata_tool.Client()

    result = ensure_cdn_repo(client, check_mode, params)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
