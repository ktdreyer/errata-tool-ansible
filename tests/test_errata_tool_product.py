import pytest
import errata_tool_product
from ansible.module_utils import common_errata_tool
from ansible.module_utils.common_errata_tool import UserNotFoundError
from errata_tool_product import BUGZILLA_STATES
from errata_tool_product import InvalidInputError
from errata_tool_product import DocsReviewerNotFoundError
from errata_tool_product import validate_params
from errata_tool_product import get_product
from errata_tool_product import scrape_error_message
from errata_tool_product import scrape_error_explanations
from errata_tool_product import handle_form_errors
from errata_tool_product import create_product
from errata_tool_product import ensure_product
from errata_tool_product import prepare_diff_data
from errata_tool_product import main
from ansible.module_utils.six import PY2
from ansible.module_utils.six.moves.urllib.parse import parse_qs
from utils import exit_json
from utils import fail_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import AnsibleFailJson
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


@pytest.fixture(autouse=True)
def fake_scraper_pages(client):
    """ Several tests use these fake responses """
    client.adapter.register_uri(
        'GET',
        'https://errata.devel.redhat.com/products/new',
        text=load_html('products_new.html'))
    client.adapter.register_uri(
        'GET',
        'https://errata.devel.redhat.com/workflow_rules',
        text=load_html('workflow_rules.html'))


def bugzilla_product_name_hack():
    # XXX BUG: 'bugzilla_product_name' default value is an empty string,
    # rather than "None". We need to alter the default bugzilla_product_name
    # value to None, but to do that, more analysis is required. See
    # https://github.com/ktdreyer/errata-tool-ansible/issues/129
    # The unit tests that call this method work around this behavior by
    # setting bugzilla_product_name directly to "None".
    return None


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


class TestScrapeErrorExplanations(object):

    def test_found_explanations(self, client):
        """ Verify that we can scrape the error explanations. """
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            text=load_html('products_create_form_errors.html'))
        response = client.post('products')
        result = scrape_error_explanations(response)
        assert result == ["Name can't be blank", "Short name can't be blank"]


class TestHandleFormErrors(object):

    def test_500_response(self, client):
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=500,
            text=load_html('products_create_500_error.html'))
        response = client.post('products')
        with pytest.raises(RuntimeError) as e:
            handle_form_errors(response)
        result = str(e.value)
        assert result == ('ERROR: Mysql2::Error: Cannot add or update a child '
                          'row: a foreign key constraint fails (... longer '
                          'error message here ...)')

    def test_200_response(self, client):
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            text=load_html('products_create_form_errors.html'))
        response = client.post('products')
        with pytest.raises(RuntimeError) as e:
            handle_form_errors(response)
        assert e.value.args == ("Name can't be blank",
                                "Short name can't be blank")


class TestCreateProduct(object):

    @pytest.fixture
    def params(self):
        return {
            'short_name': 'RHCEPH',
            'name': 'Red Hat Ceph Storage',
            'description': 'Red Hat Ceph Storage',
            'bugzilla_product_name': '',
            'valid_bug_states': ['MODIFIED', 'VERIFIED'],
            'active': True,
            'ftp_path': '',
            'ftp_subdir': None,
            'internal': False,
            'default_docs_reviewer': None,
            'push_targets': ['cdn_docker', 'cdn'],
            'default_solution': 'enterprise',
            'state_machine_rule_set': 'Default',
            'move_bugs_on_qe': False,
            'exd_org_group': None,
        }

    @pytest.fixture(autouse=True)
    def fake_responses(self, client):
        """ Register all the endpoints that we will load """
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com'
            '/api/v1/user/superwriter@redhat.com',
            json={'id': 1001})
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/noexist@redhat.com',
            json={'errors': {'login_name': 'noexist@redhat.com not found.'}},
            status_code=400)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/123'})
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/products/123')
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products/123',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/123'})

    def test_create(self, client, params):
        create_product(client, params)
        history = client.adapter.request_history
        # Requests 0 and 1 are GET requests for the scrapers:
        assert history[0].method == 'GET'
        assert history[1].method == 'GET'
        # This request creates the product:
        assert history[2].method == 'POST'
        assert history[2].url == 'https://errata.devel.redhat.com/products'
        body = parse_qs(history[2].text)
        expected = {
            'product[default_solution_id]': ['2'],
            'product[description]': ['Red Hat Ceph Storage'],
            'product[is_internal]': ['0'],
            'product[isactive]': ['1'],
            'product[move_bugs_on_qe]': ['0'],
            'product[name]': ['Red Hat Ceph Storage'],
            'product[short_name]': ['RHCEPH'],
            'product[state_machine_rule_set_id]': ['1'],
            'product[valid_bug_states][]': ['MODIFIED', 'VERIFIED'],
        }
        assert body == expected
        # GET requests for the scrapers again:
        assert history[4].method == 'GET'
        assert history[5].method == 'GET'
        # This request edits push_targets on the new product:
        assert history[6].method == 'POST'
        assert history[6].url == 'https://errata.devel.redhat.com/products/123'
        body = parse_qs(history[6].text)
        expected['_method'] = ['patch']
        expected['product[push_targets][]'] = ['8', '4']
        assert body == expected

    def test_with_docs_reviewer(self, client, params):
        params['default_docs_reviewer'] = 'superwriter@redhat.com'
        create_product(client, params)
        history = client.adapter.request_history
        # Requests 0 and 1 are GET requests for the scrapers,
        # request 2 is for the docs_reviewer user ID.
        # This request creates the product:
        assert history[3].method == 'POST'
        assert history[3].url == 'https://errata.devel.redhat.com/products'
        body = parse_qs(history[3].text)
        assert body['product[default_docs_reviewer_id]'] == ['1001']

    def test_docs_reviewer_missing(self, client, params):
        params['default_docs_reviewer'] = 'noexist@redhat.com'
        with pytest.raises(DocsReviewerNotFoundError) as e:
            create_product(client, params)
        assert str(e.value) == 'noexist@redhat.com'

    def test_with_exd_org_group(self, client, params):
        params['exd_org_group'] = 'Cloud'
        create_product(client, params)
        history = client.adapter.request_history
        # Requests 0 and 1 are GET requests for the scrapers.
        # This request creates the product:
        assert history[2].method == 'POST'
        assert history[2].url == 'https://errata.devel.redhat.com/products'
        body = parse_qs(history[2].text)
        assert body['product[exd_org_group_id]'] == ['2']

    def test_broken_redirect(self, client, params):
        """
        Test the purely hypothetical case of the Errata Tool developers
        inadvertently alterting the web form so that it redirects in a
        different way than we expected with create_product().
        """
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/some/other/redirect'})
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/some/other/redirect')
        with pytest.raises(RuntimeError) as e:
            create_product(client, params)
        # Assert that we have a sane error message so we will know how to
        # update the "find new product ID" regex code going forward:
        expected = ('could not find new product ID from '
                    'https://errata.devel.redhat.com/some/other/redirect')
        assert str(e.value) == expected


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


class TestEnsureProduct(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH',
            json={'data': PRODUCT})
        return client

    @pytest.fixture
    def params(self):
        return {
            'short_name': 'RHCEPH',
            'name': 'Red Hat Ceph Storage',
            'description': 'Red Hat Ceph Storage',
            'bugzilla_product_name': '',
            'valid_bug_states': ['VERIFIED', 'ON_QA', 'MODIFIED', 'ASSIGNED',
                                 'NEW', 'ON_DEV', 'POST'],
            'active': True,
            'ftp_path': '',
            'ftp_subdir': None,
            'internal': False,
            'default_docs_reviewer': None,
            'push_targets': ['ftp', 'cdn_stage', 'cdn_docker_stage',
                             'cdn_docker', 'cdn'],
            'default_solution': 'enterprise',
            'state_machine_rule_set': 'Default',
            'move_bugs_on_qe': False,
            'exd_org_group': None,
        }

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        params['bugzilla_product_name'] = bugzilla_product_name_hack()
        result = ensure_product(client, params, check_mode)
        assert result['changed'] is False

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH',
            status_code=404)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/104'})
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/products/104')
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products/104',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/104'})
        result = ensure_product(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created RHCEPH product']

    def test_edit_check_mode(self, client, params):
        params['bugzilla_product_name'] = bugzilla_product_name_hack()
        params['description'] = 'Red Hat Ceph Storage Is Cool'
        result = ensure_product(client, params, check_mode=True)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage ' \
                   'to Red Hat Ceph Storage Is Cool'
        assert result['stdout_lines'] == [expected]

    def test_edit_live(self, client, params):
        params['description'] = 'Red Hat Ceph Storage Is Cool'
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/104'})
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/products/104',
            status_code=302,
            headers={'Location':
                     'https://errata.devel.redhat.com/products/104'})
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/products/104')
        result = ensure_product(client, params, check_mode=False)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage ' \
                   'to Red Hat Ceph Storage Is Cool'
        if PY2:
            expected = u'changing description from Red Hat Ceph Storage ' \
                'to Red Hat Ceph Storage Is Cool'
        # XXX BUG, issue 129
        bz_name_hack = 'changing bugzilla_product_name from None to '
        assert result['stdout_lines'] == [expected, bz_name_hack]
        history = client.adapter.request_history
        assert history[-2].method == 'POST'
        assert history[-2].url == \
            'https://errata.devel.redhat.com/products/104'
        body = parse_qs(history[-2].text)
        expected = {
            '_method': ['patch'],
            'product[default_solution_id]': ['2'],
            'product[description]': ['Red Hat Ceph Storage Is Cool'],
            'product[is_internal]': ['0'],
            'product[isactive]': ['1'],
            'product[move_bugs_on_qe]': ['0'],
            'product[name]': ['Red Hat Ceph Storage'],
            'product[push_targets][]': ['3', '5', '9', '8', '4'],
            'product[short_name]': ['RHCEPH'],
            'product[state_machine_rule_set_id]': ['1'],
            'product[valid_bug_states][]': ['VERIFIED',
                                            'ON_QA',
                                            'MODIFIED',
                                            'ASSIGNED',
                                            'NEW',
                                            'ON_DEV',
                                            'POST']
        }
        assert body == expected


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_product.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_product.AnsibleModule,
                            'fail_json', fail_json)

    @pytest.fixture
    def module_args(self):
        # Minimal required module args
        return {
            'short_name': 'RHCEPH',
            'name': 'Red Hat Ceph Storage',
            'description': 'Red Hat Ceph Storage',
            'default_solution': 'enterprise',
            'state_machine_rule_set': 'Default',
            'push_targets': [],
        }

    def test_simple(self, monkeypatch, module_args):
        """ Create a simple minimal product. """
        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_product, 'ensure_product', mock_ensure)
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is True

    def test_invalid_input(self, monkeypatch, module_args):
        """
        When validate_params() raises InvalidInputError, the
        Ansible module exits with the proper error message.
        """
        module_args['valid_bug_states'] = ['BOGUS_STATE_LOL']
        set_module_args(module_args)
        with pytest.raises(AnsibleFailJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is False
        expected = 'invalid valid_bug_states value "BOGUS_STATE_LOL"'
        assert result['msg'] == expected

    def test_missing_doc_reviewer(self, monkeypatch, module_args):
        """
        When ensure_product() raises DocsReviewerNotFoundError, the
        Ansible module exits with the proper error message.
        """
        mock_ensure = Mock()
        mock_ensure.side_effect = \
            DocsReviewerNotFoundError('noexist@redhat.com')
        monkeypatch.setattr(errata_tool_product, 'ensure_product', mock_ensure)
        module_args['default_docs_reviewer'] = 'noexist@redhat.com',
        set_module_args(module_args)
        with pytest.raises(AnsibleFailJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is False
        expected = 'default_docs_reviewer noexist@redhat.com account not found'
        assert result['msg'] == expected

    def test_strict_user_check_missing_user(self, monkeypatch, module_args):
        """
        Test that the module fails when in strict user check mode
        and the user doesn't exist.
        """
        monkeypatch.setenv('ANSIBLE_STRICT_USER_CHECK_MODE', 'True')

        module_args['default_docs_reviewer'] = 'noexist@redhat.com'
        module_args['_ansible_check_mode'] = True
        set_module_args(module_args)

        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_product, 'ensure_product', mock_ensure)

        mock_get_user = Mock()
        mock_get_user.side_effect = UserNotFoundError('noexist@redhat.com')
        monkeypatch.setattr(common_errata_tool, 'get_user', mock_get_user)

        with pytest.raises(AnsibleFailJson) as ex:
            main()

        result = ex.value.args[0]
        assert result['changed'] is False

        expected = 'default_docs_reviewer noexist@redhat.com account not found'
        assert result['msg'] == expected

    def test_strict_user_check_missing_role(self, monkeypatch, module_args):
        """
        Test that the module fails when in strict user check mode
        and the user doesn't have the 'docs' role.
        """
        monkeypatch.setenv('ANSIBLE_STRICT_USER_CHECK_MODE', 'True')

        module_args['default_docs_reviewer'] = 'nodocsrole@redhat.com'
        module_args['_ansible_check_mode'] = True
        set_module_args(module_args)

        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_product, 'ensure_product', mock_ensure)

        mock_get_user = Mock()
        mock_get_user.return_value = {
            'roles': [
                'qa'
            ]
        }
        monkeypatch.setattr(common_errata_tool, 'get_user', mock_get_user)

        with pytest.raises(AnsibleFailJson) as ex:
            main()

        result = ex.value.args[0]
        assert result['changed'] is False

        expected = "User nodocsrole@redhat.com does not have 'docs' role in ET"
        assert result['msg'] == expected
