import pytest
from errata_tool_product import BUGZILLA_STATES
from errata_tool_product import InvalidInputError
from errata_tool_product import validate_params
from errata_tool_product import get_product
from errata_tool_product import scrape_error_message
from errata_tool_product import prepare_diff_data
from utils import Mock
from utils import load_html


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
        "move_bugs_on_qe": False
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


class TestValidateParams(object):

    @pytest.mark.parametrize('bugzilla_state', BUGZILLA_STATES)
    def test_valid_params(self, bugzilla_state):
        module = Mock()
        params = {
            'valid_bug_states': [bugzilla_state],
            'default_solution': 'enterprise',
        }
        validate_params(module, params)

    def test_invalid_bugzilla_states(self):
        module = Mock()
        params = {
            'valid_bug_states': ['NEW', 'BOGUS_STATE_LOL'],
            'default_solution': 'enterprise',
        }
        with pytest.raises(InvalidInputError) as e:
            validate_params(module, params)
        assert e.value.param == 'valid_bug_states'
        assert e.value.value == 'BOGUS_STATE_LOL'

    def test_invalid_solution(self):
        module = Mock()
        params = {
            'valid_bug_states': ['NEW'],
            'default_solution': 'enterprize lol',
        }
        with pytest.raises(InvalidInputError) as e:
            validate_params(module, params)
        assert e.value.param == 'default_solution'
        assert e.value.value == 'ENTERPRIZE LOL'


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


class TestScrapeErrorMessage(object):

    def test_found_message(self, client):
        """ Verify that we can scrape an error message. """
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=500,
            text=load_html('products_create_500_error.html'))
        response = client.post('products')
        result = scrape_error_message(response)
        assert result == ('ERROR: Mysql2::Error: Cannot add or update a child '
                          'row: a foreign key constraint fails (... longer '
                          'error message here ...)')

    def test_message_not_found(self, client):
        """
        If we do not find the expected <div>, raise ValueError with the
        entire HTTP response body text.

        Note: I have not been able to hit this condition on a live server,
        because it always prints the <div> for HTTP 500 errors, but this unit
        test covers it anyway.
        """
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=500,
            text='Something went wrong!')
        response = client.post('products')
        with pytest.raises(ValueError) as e:
            scrape_error_message(response)
        assert str(e.value) == 'Something went wrong!'


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
