import pytest
import errata_tool_product
from ansible.module_utils import common_errata_tool
from ansible.module_utils.common_errata_tool import UserNotFoundError
from errata_tool_product import BUGZILLA_STATES
from errata_tool_product import InvalidInputError
from errata_tool_product import validate_params
from errata_tool_product import get_product
from errata_tool_product import create_product
from errata_tool_product import edit_product
from errata_tool_product import ensure_product
from errata_tool_product import prepare_diff_data
from errata_tool_product import main
from ansible.module_utils.six import PY2
from ansible.module_utils.six.moves.urllib.parse import parse_qs
from utils import exit_json
from utils import fail_json
from utils import load_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import AnsibleFailJson
from utils import Mock


PROD = 'https://errata.devel.redhat.com'


def bugzilla_product_name_hack():
    # XXX BUG: 'bugzilla_product_name' default value is an empty string,
    # rather than "None". We need to alter the default bugzilla_product_name
    # value to None, but to do that, more analysis is required. See
    # https://github.com/ktdreyer/errata-tool-ansible/issues/129
    # The unit tests that call this method work around this behavior by
    # setting bugzilla_product_name directly to "None".
    return None


def rhceph_product_response():
    return load_json('RHCEPH.product.json')


@pytest.fixture
def params():
    return {
        'short_name': 'RHCEPH',
        'name': 'Red Hat Ceph Storage',
        'active': True,
        'bugzilla_product_name': '',
        'default_docs_reviewer': None,
        'default_solution': 'enterprise',
        'description': 'Red Hat Ceph Storage',
        'exd_org_group': 'Cloud',
        'ftp_path': '',
        'ftp_subdir': None,
        'internal': False,
        'move_bugs_on_qe': False,
        'push_targets': ['ftp', 'cdn_stage', 'cdn_docker_stage', 'cdn_docker', 'cdn'],
        'state_machine_rule_set': 'Optional BugsGuard',
        'valid_bug_states': ['VERIFIED', 'ON_QA', 'MODIFIED', 'ASSIGNED', 'NEW', 'ON_DEV', 'POST'],
        'show_bug_package_mismatch_warning': True,
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
        params = {
            'valid_bug_states': [bugzilla_state],
            'default_solution': 'enterprise',
        }
        validate_params(params)

    def test_invalid_bugzilla_states(self):
        params = {
            'valid_bug_states': ['NEW', 'BOGUS_STATE_LOL'],
            'default_solution': 'enterprise',
        }
        with pytest.raises(InvalidInputError) as e:
            validate_params(params)
        assert e.value.param == 'valid_bug_states'
        assert e.value.value == 'BOGUS_STATE_LOL'

    def test_invalid_solution(self):
        params = {
            'valid_bug_states': ['NEW'],
            'default_solution': 'enterprize lol',
        }
        with pytest.raises(InvalidInputError) as e:
            validate_params(params)
        assert e.value.param == 'default_solution'
        assert e.value.value == 'ENTERPRIZE LOL'


class TestResponses(object):

    def test_product_missing(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            status_code=404)
        product = get_product(client, 'RHCEPH')
        assert product is None

    def test_get_product(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json=rhceph_product_response())
        product = get_product(client, 'RHCEPH')
        expected = {
            'id': 104,
            'name': 'Red Hat Ceph Storage',
            'description': 'Red Hat Ceph Storage',
            'short_name': 'RHCEPH',
            'bugzilla_product_name': '',
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
            'state_machine_rule_set': 'Optional BugsGuard',
            'exd_org_group': 'Cloud',
            'suppress_push_request_jira': True,
            'show_bug_package_mismatch_warning': True,
        }
        assert product == expected

    def test_create_product(self, client, params):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/products',
            # XXX - what data to return?
            # XXX - what headers/body does the server send on creation?
            status_code=201)
        create_product(client, params)
        history = client.adapter.request_history
        assert len(history) == 1
        assert history[0].method == 'POST'
        assert history[0].url == 'https://errata.devel.redhat.com/api/v1/products'
        expected_json = {
            'product': {
                'name': 'Red Hat Ceph Storage',
                'description': 'Red Hat Ceph Storage',
                'short_name': 'RHCEPH',
                'bugzilla_product_name': '',
                'default_docs_reviewer': None,
                'default_solution': 'enterprise',
                'description': 'Red Hat Ceph Storage',
                'exd_org_group': 'Cloud',
                'ftp_path': '',
                'ftp_subdir': None,
                'is_internal': False,
                'isactive': True,
                'move_bugs_on_qe': False,
                'push_targets': [
                    'ftp',
                    'cdn_stage',
                    'cdn_docker_stage',
                    'cdn_docker',
                    'cdn',
                ],
                'state_machine_rule_set': 'Optional BugsGuard',
                'valid_bug_states': [
                    'VERIFIED',
                    'ON_QA',
                    'MODIFIED',
                    'ASSIGNED',
                    'NEW',
                    'ON_DEV',
                    'POST'
                ],
                'show_bug_package_mismatch_warning': True,
            }
        }
        assert history[0].json() == expected_json

    def test_edit_product(self, client, params):
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/products/104')
        differences = [('description',
                        'Red Hat Ceph Storage',
                        'Red Hat Ceph Storage Is Cool')]
        edit_product(client, 104, differences)
        history = client.adapter.request_history
        assert len(history) == 1
        expected_json = {
            'product': {
                'description': 'Red Hat Ceph Storage Is Cool',
            }
        }
        assert history[0].json() == expected_json


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
        }

        after_data = {
            'short_name': 'RHDIFF',
            'description': 'bar',
        }

        expected_output = {
            'before': {
                'short_name': 'RHDIFF',
                'description': 'foo',
            },
            'after': {
                'short_name': 'RHDIFF',
                'description': 'bar',
            },
            'before_header': "Original product 'RHDIFF'",
            'after_header': "Modified product 'RHDIFF'",
        }

        assert prepare_diff_data(before_data, after_data) == expected_output

    def test_diff_data_consistent_lists(self):
        before_data = {
            'id': 123,
            'short_name': 'RHDIFF',
            'description': 'foo',
            'push_targets': ['ftp', 'cdn', 'cdn_stage'],
        }

        after_data = {
            'short_name': 'RHDIFF',
            'description': 'bar',
            'push_targets': ['ftp', 'cdn_stage', 'cdn'],
        }

        expected_output = {
            'before': {
                'short_name': 'RHDIFF',
                'description': 'foo',
                'push_targets': ['cdn', 'cdn_stage', 'ftp'],
            },
            'after': {
                'short_name': 'RHDIFF',
                'description': 'bar',
                'push_targets': ['cdn', 'cdn_stage', 'ftp'],
            },
            'before_header': "Original product 'RHDIFF'",
            'after_header': "Modified product 'RHDIFF'",
        }

        assert prepare_diff_data(before_data, after_data) == expected_output


class TestEnsureProduct(object):

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json=rhceph_product_response())
        params['bugzilla_product_name'] = bugzilla_product_name_hack()
        result = ensure_product(client, params, check_mode)
        assert result['changed'] is False

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            status_code=404)
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/products',
            # XXX - what data to return?
            # XXX - what headers/body does the server send on creation?
            status_code=201)
        result = ensure_product(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created RHCEPH product']

    def test_edit_check_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json=rhceph_product_response())
        params['bugzilla_product_name'] = bugzilla_product_name_hack()
        params['description'] = 'Red Hat Ceph Storage Is Cool'
        result = ensure_product(client, params, check_mode=True)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage ' \
                   'to Red Hat Ceph Storage Is Cool'
        assert result['stdout_lines'] == [expected]

    def test_edit_live(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json=rhceph_product_response())
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/products/104')
        params['description'] = 'Red Hat Ceph Storage Is Cool'
        result = ensure_product(client, params, check_mode=False)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage ' \
                   'to Red Hat Ceph Storage Is Cool'
        if PY2:
            expected = u'changing description from Red Hat Ceph Storage ' \
                'to Red Hat Ceph Storage Is Cool'
        assert set(result['stdout_lines']) == set([expected])
        history = client.adapter.request_history
        assert len(history) == 2
        assert history[1].method == 'PUT'
        assert history[1].url == 'https://errata.devel.redhat.com/api/v1/products/104'
        expected_json = {
            'product': {
                'description': 'Red Hat Ceph Storage Is Cool',
            }
        }
        assert history[1].json() == expected_json


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

    def test_strict_user_check_disabled(self, monkeypatch, module_args):
        """
        Test that the module fails when in strict user check mode
        and the user account is disabled.
        """
        monkeypatch.setenv('ANSIBLE_STRICT_USER_CHECK_MODE', 'True')

        module_args['default_docs_reviewer'] = 'retired@redhat.com'
        module_args['_ansible_check_mode'] = True
        set_module_args(module_args)

        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_product, 'ensure_product', mock_ensure)

        mock_get_user = Mock()
        mock_get_user.return_value = {'roles': ['docs'], 'enabled': False}
        monkeypatch.setattr(common_errata_tool, 'get_user', mock_get_user)

        with pytest.raises(AnsibleFailJson) as ex:
            main()

        result = ex.value.args[0]
        assert result['changed'] is False

        expected = "default_docs_reviewer retired@redhat.com is not enabled"
        assert result['msg'] == expected
