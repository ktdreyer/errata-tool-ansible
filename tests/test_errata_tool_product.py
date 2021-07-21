from errata_tool_product import BUGZILLA_STATES
from errata_tool_product import get_product
from errata_tool_product import prepare_diff_data


PRODUCT = {
    "id": 104,
    "type": "products",
    "attributes": {
        "name": "Red Hat Ceph Storage",
        "description": "Red Hat Ceph Storage",
        "short_name": "RHCEPH",
        "bugzilla_product_name": None,
        "valid_bug_states": [
            "VERIFIED",
            "ON_QA",
            "MODIFIED",
            "ASSIGNED",
            "NEW",
            "ON_DEV",
            "POST"
        ],
        "ftp_path": "",
        "ftp_subdir": "RHCEPH",
        "is_internal": False,
        "isactive": True,
        "move_bugs_on_qe": False,
        "text_only_advisories_require_dists": True
    },
    "relationships": {
        "default_docs_reviewer": {
            "id": 1,
            "login_name": "docs-errata-list@redhat.com"
        },
        "default_solution": {
            "id": 2,
            "title": "enterprise"
        },
        "product_versions": [
            {
                "id": 929,
                "name": "RHCEPH-4.0-RHEL-8"
            },
            {
                "id": 1108,
                "name": "RHEL-7-RHCEPH-4.0"
            }
        ],
        "push_targets": [
            {
                "id": 3,
                "name": "ftp"
            },
            {
                "id": 7,
                "name": "cdn_stage"
            },
            {
                "id": 10,
                "name": "cdn_docker_stage"
            },
            {
                "id": 9,
                "name": "cdn_docker"
            },
            {
                "id": 4,
                "name": "cdn"
            }
        ],
        "state_machine_rule_set": {
            "id": 1,
            "name": "Default"
        },
        "exd_org_group": {
            "id": 2,
            "name": "Cloud",
            "short_name": "Cloud",
            "jira_key": "SPCLOUD",
            "jira_ticket_project_keys": {
                "push_request": "CLOUDDST",
                "listings_change": "CLOUDWF"
            }
        }
    }
}


def test_bugzilla_states():
    expected = set([
        'ASSIGNED',
        'CLOSED',
        'MODIFIED',
        'NEW',
        'ON_DEV',
        'ON_QA',
        'POST',
        'RELEASE_PENDING',
        'VERIFIED',
    ])
    assert BUGZILLA_STATES == expected


class TestGetProduct(object):

    def test_not_found(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH',
            status_code=404)
        product = get_product(client, 'RHCEPH')
        assert product is None

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH',
            json={'data': PRODUCT})
        product = get_product(client, 'RHCEPH')
        expected = {
            'id': 104,
            'name': 'Red Hat Ceph Storage',
            'description': 'Red Hat Ceph Storage',
            'short_name': 'RHCEPH',
            'bugzilla_product_name': None,
            'valid_bug_states': [
                'VERIFIED',
                'ON_QA',
                'MODIFIED',
                'ASSIGNED',
                'NEW',
                'ON_DEV',
                'POST'
            ],
            'ftp_path': '',
            'ftp_subdir': 'RHCEPH',
            'internal': False,
            'active': True,
            'move_bugs_on_qe': False,
            'text_only_advisories_require_dists': True,
            'default_docs_reviewer': 'docs-errata-list@redhat.com',
            'default_solution': 'enterprise',
            'push_targets': [
                'ftp',
                'cdn_stage',
                'cdn_docker_stage',
                'cdn_docker',
                'cdn',
            ],
            'state_machine_rule_set': 'Default',
            'exd_org_group': 'Cloud',
        }
        assert product == expected


class TestPrepareDiffData(object):

    def test_diff_from_none(self):
        after_data = {
            'short_name': 'RHNEW',
            'description': 'new thing',
        }

        expected_output = {
            'before': {},
            'after': after_data,
            'before_header': "Not present",
            'after_header': "New product 'RHNEW'",
        }

        assert prepare_diff_data(None, after_data) == expected_output

    def test_diff_data(self):
        before_data = {
            'id': 123,
            'short_name': 'RHDIFF',
            'description': 'foo',
            'show_bug_package_mismatch_warning': True,
        }

        after_data = {
            'short_name': 'RHDIFF',
            'description': 'bar',
        }

        expected_output = {
            'before': {
                'short_name': 'RHDIFF',
                'description': 'foo',
                'show_bug_package_mismatch_warning': True,
            },
            'after': {
                'short_name': 'RHDIFF',
                'description': 'bar',
                'show_bug_package_mismatch_warning': True,
            },
            'before_header': "Original product 'RHDIFF'",
            'after_header': "Modified product 'RHDIFF'",
        }

        assert prepare_diff_data(before_data, after_data) == expected_output
