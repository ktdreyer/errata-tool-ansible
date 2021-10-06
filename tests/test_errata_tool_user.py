from copy import deepcopy
import pytest
import errata_tool_user
from errata_tool_user import get_user
from errata_tool_user import create_user
from errata_tool_user import edit_user
from errata_tool_user import ensure_user
from errata_tool_user import main
from utils import exit_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import Mock
from ansible.module_utils.six import PY2


USER = {
    "login_name": "me@redhat.com",
    "realname": "Me Myself",
    "organization": "Engineering",
    "enabled": True,
    "receives_mail": False,
    "email_address": "me@redhat.com",
    "roles": [
        "devel"
    ],
    "id": 123456,
}


class TestGetUser(object):

    def test_not_found_http_500(self, client):
        # ET currently returns HTTP 500 for missing users.
        # Delete this test when CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            status_code=500)
        user = get_user(client, 'me@redhat.com')
        assert user is None

    def test_found_http_404(self, client):
        # ET currently returns HTTP 404 for users with some Kerberos realm
        # suffixes.
        # Delete this test when CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@IPA.REDHAT.COM',
            status_code=404)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/user/find_user',
            headers={
                'Location': 'https://errata.devel.redhat.com/user/123456',
            },
            status_code=302)
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/123456',
            json=USER)
        user = get_user(client, 'me@IPA.REDHAT.COM')
        assert user == USER

    def test_not_found(self, client):
        # This test will match the ET server once CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json={'errors': {'login_name': 'me@redhat.com not found.'}},
            status_code=400)
        user = get_user(client, 'me@redhat.com')
        assert user is None

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=USER)
        user = get_user(client, 'me@redhat.com')
        assert user == USER


class TestCreateUser(object):

    def test_basic(self, client):
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        create_user(client, USER)
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

    def test_receives_mail_includes_email_address(self, client):
        """
        When the user wants to set "receives_mail: true", we must always send
        the email_address attribute in the POST call. CLOUDWF-2817
        """
        params = deepcopy(USER)
        params['receives_mail'] = True
        # Ansible will default "email_address" to "None":
        params['email_address'] = None
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        create_user(client, params)
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
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=USER)
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_create_check_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            status_code=500)
        check_mode = True
        result = ensure_user(client, params, check_mode)
        expected = {'changed': True,
                    'stdout_lines': ['created me@redhat.com user']}
        assert result == expected

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            status_code=500)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        check_mode = False
        result = ensure_user(client, params, check_mode)
        expected = {'changed': True,
                    'stdout_lines': ['created me@redhat.com user']}
        assert result == expected

    def test_edit(self, client, params):
        user = deepcopy(USER)
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

    def test_no_organization_change(self, client, params):
        """
        If a playbook author omits "organization", we should not change
        the existing value on the server.
        """
        # Ansible will default "organization" to "None":
        params['organization'] = None
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=USER)
        # On the server, "organization" is "Engineering":
        assert USER['organization'] == 'Engineering'
        check_mode = False
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_no_roles_change(self, client, params):
        """
        If a playbook author omits "roles", we should not change the existing
        value on the server.
        """
        # Ansible will default "roles" to "None":
        params['roles'] = None
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=USER)
        # On the server, "roles" is ['devel']:
        assert USER['roles'] == ['devel']
        check_mode = False
        result = ensure_user(client, params, check_mode)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_receives_mail_includes_email_address(self, client, params):
        """
        When the user wants to keep "receives_mail: true", we must always send
        the email_address attribute in every PUT call. CLOUDWF-2817
        """
        user = deepcopy(USER)
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
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True
        ensure_user_args = mock_ensure_user.call_args[0][1]
        assert ensure_user_args == {
            'email_address': None,
            'enabled': True,
            'login_name': 'cooldev@redhat.com',
            'organization': None,
            'realname': 'Dr. Cool Developer',
            'receives_mail': True,
            'roles': None
        }
