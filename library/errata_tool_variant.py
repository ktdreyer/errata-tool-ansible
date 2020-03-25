from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six import string_types
from ansible.module_utils import common_errata_tool
from lxml import html
import re


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
       - Leave this as an empty list in order to inherit the push targets from
         the parent product or product_version.
     choices: [rhn_live, rhn_stage, ftp, cdn, cdn_stage, altsrc, cdn_docker,
               cdn_docker_stage]
     required: true
'''


def normalize_scraped(text):
    """
    Transform human-readable values that we've scraped from the webpage
    """
    lower = text.lower()
    if lower == 'none':
        return None
    if ',' in lower:
        sections = re.split(', *', lower)
        return [normalize_scraped(section) for section in sections]
    return re.sub(r'[^a-z0-9]', '_', lower)


def scrape_variant_view(client, product_version, variant):
    """
    Scrape the one attribute we need: push_targets.

    ERRATA-9708

    :returns: a single key dict, {'push_targets': [...]}
    """
    keys_to_scrape = [
        'allowable_push_targets',
    ]
    url = 'product_versions/%s/variants/%s' % (product_version, variant)
    r = client.get(url)
    r.raise_for_status()
    content = r.text
    doc = html.document_fromstring(content)
    rows = doc.xpath('//table[@class="fields"]/tr')
    data = {}
    for row in rows:
        items = row.xpath('td//text()')
        items = [item.strip() for item in items]
        name = normalize_scraped(items[0])
        if name not in keys_to_scrape:
            continue
        if len(items) == 1:
            value = None
        else:
            value = items[1]
        if name == 'allowable_push_targets':
            name = 'push_targets'
            value = normalize_scraped(value)
            if value is None:
                value = []
            if isinstance(value, string_types):
                value = [value]
        data[name] = value
    if not data:
        raise RuntimeError('scraper found nothing')
    return data


def get_variant(client, name):
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
    # push_targets is not yet available (ERRATA-9708)
    if 'push_targets' in relationships:
        push_targets = [pt['name'] for pt in relationships['push_targets']]
        variant['push_targets'] = push_targets
    else:
        # screen-scrape push_targets
        additional = scrape_variant_view(client, variant['product_version'],
                                         name)
        variant.update(additional)
    return variant


def scrape_pre(response):
    """
    Return the text inside "<pre> ... </pre>" in this HTML response.

    :param response: Requests.response object
    :returns: message text (str)
    """
    content = response.text
    doc = html.document_fromstring(content)
    pres = doc.xpath('//pre')
    if len(pres) != 1:
        print('expected 1 <pre>, found %s' % len(pres))
        raise ValueError(response.text)
    pre = pres[0]
    message = pre.text_content().strip()
    return message


def scrape_error_explanation(response):
    """
    Return the text inside "<div class="errorExplanation"> ... </div>" in this HTML response.

    :param response: Requests.response object
    :returns: message text (str)
    """
    content = response.text
    doc = html.document_fromstring(content)
    lis = doc.xpath('//div[@class="errorExplanation"]/li')
    errors = [li.text_content.strip() for li in lis]
    return errors


def html_form_data(client, params):
    """ Transform our Ansible params into an HTML form "data" for POST'ing.
    """
    data = {}
    rhel_variant = get_variant(client, params['rhel_variant'])
    data['variant[rhel_variant_id]'] = rhel_variant['id']
    data['variant[name]'] = params['name']
    data['variant[description]'] = params['description']
    if params['cpe'] is not None:
        data['variant[cpe]'] = params['cpe']
    # push targets need scraper
    push_target_scraper = common_errata_tool.PushTargetScraper(client)
    push_target_ints = push_target_scraper.convert_to_ints(params['push_targets'])
    data['variant[push_targets][]'] = push_target_ints
    data['variant[buildroot]'] = int(params['buildroot'])
    return data


def handle_form_errors(response):
    # If there are incorrect or missing fields, we will receive a HTTP 200
    # with a list of the wrong fields, or just an HTTP 500 error.
    if response.status_code == 500:
        message = scrape_pre(response)
        raise RuntimeError(message)
    if 'errorExplanation' in response.text:
        errors = scrape_error_explanation(response)
        if errors:
            raise RuntimeError(errors)
        # scrape_error_explanation() failed in some way. Fall back to raising
        # the entire HTML body:
        raise RuntimeError(response.text)
    if response.status_code == 403:
        # Possibly a lack of permissions (eg. setting the CPE text).
        # Not sure what exactly to screen-scrape here, so we'll raise the
        # whole response body for logging for now.
        raise RuntimeError(response.text)
    response.raise_for_status()


def create_variant(client, params):
    """ See ERRATA-9717 for official create API """
    # Form is /product_versions/RHCEPH-4.0-RHEL-8/variants/new
    data = html_form_data(client, params)
    url = 'product_versions/%s/variants' % params['product_version']
    response = client.post(url, data=data)
    handle_form_errors(response)


def edit_variant(client, product_version, variant_id, params):
    """
    Edit an existing variant.

    See ERRATA-9717 for official edit API.

    :param client: Errata Client
    :param str product_version: name of the PV for this variant
    :param int variant_id: ID number for the variant
    :param dict params: ansible module params
    """
    endpoint = 'product_versions/%s/variants/%d' % (product_version,
                                                    variant_id)
    data = html_form_data(client, params)
    data['_method'] = 'patch'
    response = client.post(endpoint, data=data)
    handle_form_errors(response)


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
    differences = common_errata_tool.diff_settings(variant, params)
    if differences:
        result['changed'] = True
        changes = common_errata_tool.describe_changes(differences)
        result['stdout_lines'].extend(changes)
        if not check_mode:
            edit_variant(client, variant['product_version'], variant['id'],
                         params)
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
