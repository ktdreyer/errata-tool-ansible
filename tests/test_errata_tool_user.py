import pytest
import errata_tool_user
from errata_tool_user import create_user
from errata_tool_user import edit_user
from errata_tool_user import ensure_user
from errata_tool_user import main
from utils import exit_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import Mock
from ansible.module_utils.six import PY2


class TestCreateUser(object):

    def test_basic(self, client, user):
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        create_user(client, user)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'email_address': 'me@redhat.com',
            'enabled': True,
            'id': 123456,
            'login_name': 'me@redhat.com',
            'organization': 'Engineering',
            'realname': 'Me Myself',
            'receives_mail': False,
            'roles': ['devel']
        }
        assert history[0].json() == expected

    def test_receives_mail_includes_email_address(self, client, user):
        """
        When the user wants to set "receives_mail: true", we must always send
        the email_address attribute in the POST call. CLOUDWF-2817
        """
        user['receives_mail'] = True
        # Ansible will default "email_address" to "None":
        user['email_address'] = None
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        create_user(client, user)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'email_address': 'me@redhat.com',
            'enabled': True,
            'id': 123456,
            'login_name': 'me@redhat.com',
            'organization': 'Engineering',
            'realname': 'Me Myself',
            'receives_mail': True,
            'roles': ['devel']
        }
        assert history[0].json() == expected


class TestEditUser(object):

    def test_change_roles(self, client):
        differences = [('roles', ['devel'], ['pm'])]
        client.adapter.register_uri(
            'PUT',
            'https://errata.devel.redhat.com/api/v1/user/123456',
            status_code=200)
        edit_user(client, 123456, differences)
        history = client.adapter.request_history
        assert len(history) == 1
        assert history[0].json() == {'roles': ['pm']}


class TestEnsureUser(object):

    @pytest.fixture
    def params(self):
        return {
            'login_name': 'me@redhat.com',
            'realname': 'Me Myself',
            'organization': 'Engineering',
            'enabled': True,
            'receives_mail': False,
            'email_address': 'me@redhat.com',
            'roles': ['devel'],
        }

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode, user):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=user)
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_create_check_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json={'errors': {'login_name': 'me@redhat.com not found.'}},
            status_code=400)
        check_mode = True
        result = ensure_user(client, params, check_mode)
        expected = {'changed': True,
                    'stdout_lines': ['created me@redhat.com user']}
        assert result == expected

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json={'errors': {'login_name': 'me@redhat.com not found.'}},
            status_code=400)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        check_mode = False
        result = ensure_user(client, params, check_mode)
        expected = {'changed': True,
                    'stdout_lines': ['created me@redhat.com user']}
        assert result == expected

    def test_edit(self, client, params, user):
        user['roles'] = ['pm']
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=user)
        client.adapter.register_uri(
            'PUT',
            'https://errata.devel.redhat.com/api/v1/user/123456',
            status_code=200)
        check_mode = False
        result = ensure_user(client, params, check_mode)
        expected_stdout_lines = ["changing roles from ['pm'] to ['devel']"]
        if PY2:
            expected_stdout_lines = [
                "changing roles from [u'pm'] to ['devel']"
            ]
        assert result['changed'] is True
        assert set(result['stdout_lines']) == set(expected_stdout_lines)

    def test_no_organization_change(self, client, params, user):
        """
        If a playbook author omits "organization", we should not change
        the existing value on the server.
        """
        # Ansible will default "organization" to "None":
        params['organization'] = None
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=user)
        # On the server, "organization" is "Engineering":
        assert user['organization'] == 'Engineering'
        check_mode = False
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_no_roles_change(self, client, params, user):
        """
        If a playbook author omits "roles", we should not change the existing
        value on the server.
        """
        # Ansible will default "roles" to "None":
        params['roles'] = None
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=user)
        # On the server, "roles" is ['devel']:
        assert user['roles'] == ['devel']
        check_mode = False
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_receives_mail_includes_email_address(self, client, params, user):
        """
        When the user wants to keep "receives_mail: true", we must always send
        the email_address attribute in every PUT call. CLOUDWF-2817
        """
        user['receives_mail'] = True
        params['receives_mail'] = True
        # Test changing an unrelated attribute (realname) here:
        params['realname'] = 'Mr. Name Changer'
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=user)
        client.adapter.register_uri(
            'PUT',
            'https://errata.devel.redhat.com/api/v1/user/123456',
            status_code=200)
        check_mode = False
        result = ensure_user(client, params, check_mode)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['changing realname from Me Myself '
                                          'to Mr. Name Changer']
        history = client.adapter.request_history
        assert len(history) == 2
        expected = {
            'email_address': 'me@redhat.com',
            'realname': 'Mr. Name Changer',
        }
        assert history[1].json() == expected


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_user.AnsibleModule,
                            'exit_json', exit_json)

    @pytest.fixture
    def mock_ensure_user(self, monkeypatch):
        """
        Fake this large method, since we unit-test it individually elsewhere.
        """
        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_user, 'ensure_user', mock_ensure)
        return mock_ensure

    def test_simple(self, mock_ensure_user):
        module_args = {
            'login_name': 'cooldev@redhat.com',
            'realname': 'Dr. Cool Developer',
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is True
        ensure_user_args = mock_ensure_user.call_args[0][1]
        assert ensure_user_args == {
            'email_address': None,
            'enabled': True,
            'login_name': 'cooldev@redhat.com',
            'organization': None,
            'realname': 'Dr. Cool Developer',
            'receives_mail': None,
            'roles': None
        }
