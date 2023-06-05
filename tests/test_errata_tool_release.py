from copy import deepcopy
import pytest
import errata_tool_release
from ansible.module_utils import common_errata_tool
from ansible.module_utils.common_errata_tool import UserNotFoundError
from ansible.module_utils.six import PY2
from errata_tool_release import get_release
from errata_tool_release import api_data
from errata_tool_release import create_release
from errata_tool_release import edit_release
from errata_tool_release import ensure_release
from errata_tool_release import main
from errata_tool_release import ProgramManagerNotFoundError
from utils import load_json
from utils import load_html
from utils import exit_json
from utils import fail_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import AnsibleFailJson
from utils import Mock


PROD = 'https://errata.devel.redhat.com'
RELEASE = load_json('rhceph-4.0.release.json')


@pytest.fixture
def params():
    return {
        'product': 'RHCEPH',
        'name': 'rhceph-4.0',
        'type': 'QuarterlyUpdate',
        'description': 'Red Hat Ceph Storage 4.0',
        'product_versions': ['RHCEPH-4.0-RHEL-8', 'RHEL-7-RHCEPH-4.0'],
        'enabled': True,
        'active': True,
        'enable_batching': False,
        'program_manager': 'coolmanager@redhat.com',
        'blocker_flags': ['ceph-4'],
        'internal_target_release': "",
        'zstream_target_release': None,
        'ship_date': '2020-01-31',
        'allow_shadow': False,
        'allow_blocker': False,
        'allow_exception': False,
        'allow_pkg_dupes': True,
        'supports_component_acl': True,
        'limit_bugs_by_product': False,
        'state_machine_rule_set': None,
        'pelc_product_version_name': None,
        'brew_tags': [],
    }


class TestGetRelease(object):

    def test_not_found(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=missing-release-1.0',
            json={'data': []})
        result = get_release(client, 'missing-release-1.0')
        assert result is None

    def test_simple(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=rhceph-4.0',
            json=RELEASE)
        result = get_release(client, 'rhceph-4.0')
        expected = {
            'id': 1017,
            'name': 'rhceph-4.0',
            'description': 'Red Hat Ceph Storage 4.0',
            'type': 'QuarterlyUpdate',
            'allow_pkg_dupes': True,
            'ship_date': '2020-01-31',
            'pelc_product_version_name': '',
            'active': True,
            'enabled': True,
            'enable_batching': False,
            'is_async': False,
            'is_deferred': False,
            'allow_shadow': False,
            'allow_blocker': False,
            'allow_exception': False,
            'limit_bugs_by_product': False,
            'supports_component_acl': True,
            'blocker_flags': ['ceph-4'],
            'internal_target_release': '',
            'zstream_target_release': None,
            'product': 'RHCEPH',
            'program_manager': 'coolmanager@redhat.com',
            'state_machine_rule_set': None,
            'brew_tags': [],
            'product_versions': ['RHCEPH-4.0-RHEL-8', 'RHEL-7-RHCEPH-4.0'],
        }
        assert result == expected

    @pytest.mark.parametrize('relationship', [
        'product',
        'program_manager',
        'state_machine_rule_set'
    ])
    def test_null_relationship(self, client, relationship):
        """ Some relationships might be null. Exercise these code paths """
        json = deepcopy(RELEASE)
        json['data'][0]['relationships'][relationship] = None
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=rhceph-4.0',
            json=json)
        result = get_release(client, 'rhceph-4.0')
        assert result[relationship] is None

    def test_plus_character_in_name(self, client):
        """ Quote "+" characters in release name HTTP request """
        json = load_json('rhel-8.4.0.z+eus.release.json')
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=RHEL-8.4.0.Z.MAIN%2BEUS',
            json=json)
        result = get_release(client, 'RHEL-8.4.0.Z.MAIN+EUS')
        assert result['name'] == 'RHEL-8.4.0.Z.MAIN+EUS'


class TestReleaseApiData(object):
    def test_simple(self, client):
        result = api_data(client, {'name': 'my-cool-release'})
        assert result == {'release': {'name': 'my-cool-release'}}

    def test_program_manager(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/user/coolmanager@redhat.com',
            json={'id': 123456})
        params = {'program_manager': 'coolmanager@redhat.com'}
        result = api_data(client, params)
        assert result == {'release': {'program_manager_id': 123456}}

    def test_no_program_manager(self, client):
        json = {'errors': {'login_name': ['noexist@redhat.com not found.']}}
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/user/noexist@redhat.com',
            status_code=400,
            json=json)
        params = {'program_manager': 'noexist@redhat.com'}
        with pytest.raises(ProgramManagerNotFoundError) as e:
            api_data(client, params)
        assert str(e.value) == 'noexist@redhat.com'


class TestCreateRelease(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json={'data': {'id': 104}})
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/user/coolmanager@redhat.com',
            json={'id': 123456})
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8.json',
            json={'id': 929})
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHEL-7-RHCEPH-4.0.json',
            json={'id': 1108})
        return client

    def test_create_release(self, client, params):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/releases',
            status_code=201)
        create_release(client, params)
        history = client.adapter.request_history
        expected = {
            'release': {
                'name': 'rhceph-4.0',
                'description': 'Red Hat Ceph Storage 4.0',
                'brew_tags': [],
                'product_id': 104,
                'program_manager_id': 123456,
                'product_version_ids': [929, 1108],
                'state_machine_rule_set_id': None,
                'isactive': True,
                'enable_batching': False,
                'ship_date': '2020-01-31',
                'zstream_target_release': None,
                'type': 'QuarterlyUpdate',  # Not needed, todo: remove
                'allow_shadow': False,
                'allow_blocker': False,
                'internal_target_release': '',
                'pelc_product_version_name': None,
                'disable_acl': False,
                'allow_pkg_dupes': True,
                'limit_bugs_by_product': False,
                'blocker_flags': 'ceph-4',
                'enabled': True,
                'allow_exception': False,
            },
            'type': 'QuarterlyUpdate',
        }
        assert history[-1].url == PROD + '/api/v1/releases'
        assert history[-1].method == 'POST'
        assert history[-1].json() == expected

    def test_error(self, client, params):
        """ Ensure that we raise any server message to the user. """
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/releases',
            status_code=500,
            json={'error': 'Some Error Here'})
        with pytest.raises(ValueError) as err:
            create_release(client, params)
        error = str(err.value)
        assert 'Unexpected response from Errata Tool: Some Error Here' in error
        assert '\n  Request: POST /api/v1/releases' in error
        assert '\n  Status code: 500' in error

    def test_create_async_no_product(self, client, params):
        params['product'] = None
        params['type'] = 'Async'
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/releases',
            status_code=201)
        create_release(client, params)
        history = client.adapter.request_history
        expected = {
            'release': {
                'name': 'rhceph-4.0',
                'description': 'Red Hat Ceph Storage 4.0',
                'brew_tags': [],
                'program_manager_id': 123456,
                'product_version_ids': [929, 1108],
                'state_machine_rule_set_id': None,
                'isactive': True,
                'enable_batching': False,
                'ship_date': '2020-01-31',
                'zstream_target_release': None,
                'type': 'Async',  # Not needed, todo: remove
                'allow_shadow': False,
                'allow_blocker': False,
                'internal_target_release': '',
                'pelc_product_version_name': None,
                'disable_acl': False,
                'allow_pkg_dupes': True,
                'limit_bugs_by_product': False,
                'blocker_flags': 'ceph-4',
                'enabled': True,
                'allow_exception': False,
            },
            'type': 'Async',
        }
        assert history[-1].url == PROD + '/api/v1/releases'
        assert history[-1].method == 'POST'
        assert history[-1].json() == expected


class TestEditRelease(object):

    def test_edit_release(self, client):
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/releases/1017')
        # Very Cool
        differences = [('description',
                        'Red Hat Ceph Storage 4.0',
                        'Red Hat Ceph Storage 4.0 Is Cool')]
        edit_release(client, 1017, differences)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'release': {
                'description': 'Red Hat Ceph Storage 4.0 Is Cool',
            }
        }
        assert history[0].json() == expected

    def test_error(self, client):
        """ Ensure that we raise any server message to the user. """
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/releases/1017',
            status_code=500,
            json={'error': 'Some Error Here'})
        differences = [('description',
                        'Red Hat Ceph Storage 4.0',
                        'Red Hat Ceph Storage 4.0 Is Cool')]
        with pytest.raises(ValueError) as err:
            edit_release(client, 1017, differences)
        error = str(err.value)
        assert 'Unexpected response from Errata Tool: Some Error Here' in error
        assert '\n  Request: PUT /api/v1/releases/1017' in error
        assert '\n  Status code: 500' in error
        expected_request_body = (
            '\n  Request body: {"release": {'
            '"description": "Red Hat Ceph Storage 4.0 Is Cool"}}'
        )
        assert expected_request_body in error

    def test_state_machine_rule_set(self, client):
        """ Ensure that we send the ID number, not the name. CLOUDWF-298 """
        client.adapter.register_uri(
            'GET',
            PROD + '/workflow_rules',
            text=load_html('workflow_rules.html'))
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/releases/1017')
        differences = [('state_machine_rule_set', None, 'Unrestricted')]
        edit_release(client, 1017, differences)
        history = client.adapter.request_history
        expected = {
            'release': {
                'state_machine_rule_set_id': 2,
            }
        }
        assert history[-1].json() == expected


class TestEnsureRelease(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=rhceph-4.0',
            json=RELEASE)
        return client

    @pytest.fixture
    def client_with_brew_tags(self, client):
        release = dict(RELEASE)
        release['data'][0]['relationships']['brew_tags'] = [
            {'id': 100, 'name': 'test-1'},
        ]
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=rhceph-4.0',
            json=release)
        return client

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        result = ensure_release(client, params, check_mode)
        assert result['changed'] is False

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH',
            json={'data': {'id': 104}})
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/user/coolmanager@redhat.com',
            json={'id': 123456})
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/releases?filter%5Bname%5D=rhceph-4.0',
            json={'data': []})
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8.json',
            json={'id': 929})
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHEL-7-RHCEPH-4.0.json',
            json={'id': 1108})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/releases',
            status_code=201)
        result = ensure_release(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created rhceph-4.0']
        history = client.adapter.request_history
        expected = {
            'release': {
                'name': 'rhceph-4.0',
                'description': 'Red Hat Ceph Storage 4.0',
                'brew_tags': [],
                'product_id': 104,
                'program_manager_id': 123456,
                'product_version_ids': [929, 1108],
                'isactive': True,
                'enable_batching': False,
                'ship_date': '2020-01-31',
                'type': 'QuarterlyUpdate',  # Not needed, todo: remove
                'allow_shadow': False,
                'allow_blocker': False,
                'internal_target_release': '',
                'disable_acl': False,
                'allow_pkg_dupes': True,
                'limit_bugs_by_product': False,
                'blocker_flags': 'ceph-4',
                'enabled': True,
                'allow_exception': False,
            },
            'type': 'QuarterlyUpdate',
        }
        assert history[-1].url == PROD + '/api/v1/releases'
        assert history[-1].method == 'POST'
        assert history[-1].json() == expected

    def test_edit_check_mode(self, client, params):
        params['description'] = 'Red Hat Ceph Storage 4.0 Is Cool'
        result = ensure_release(client, params, check_mode=True)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage 4.0 ' \
                   'to Red Hat Ceph Storage 4.0 Is Cool'
        assert result['stdout_lines'] == [expected]

    def test_edit_live(self, client, params):
        params['description'] = 'Red Hat Ceph Storage 4.0 Is Cool'
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8.json',
            json={'id': 929})
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHEL-7-RHCEPH-4.0.json',
            json={'id': 1108})
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/releases/1017')
        result = ensure_release(client, params, check_mode=False)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage 4.0 ' \
                   'to Red Hat Ceph Storage 4.0 Is Cool'
        assert result['stdout_lines'] == [expected]
        history = client.adapter.request_history
        expected = {'release': {
            'description': 'Red Hat Ceph Storage 4.0 Is Cool',
            # Note: we must always include product_version_ids (CLOUDWF-6)
            'product_version_ids': [929, 1108],
        }}
        assert history[-1].url == PROD + '/api/v1/releases/1017'
        assert history[-1].method == 'PUT'
        assert history[-1].json() == expected

    def test_edit_product_versions(self, client, params):
        params['product_versions'] = ['RHCEPH-4.0-RHEL-8']
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8.json',
            json={'id': 929})
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/releases/1017')
        result = ensure_release(client, params, check_mode=False)
        assert result['changed'] is True
        assert 'changing product_versions' in result['stdout_lines'][0]
        history = client.adapter.request_history
        expected = {'release': {'product_version_ids': [929]}}
        assert history[-1].url == PROD + '/api/v1/releases/1017'
        assert history[-1].method == 'PUT'
        assert history[-1].json() == expected

    def test_edit_check_mode_with_brew_tags(
            self, client_with_brew_tags, params):
        params['brew_tags'] = ['test-2']
        result = ensure_release(client_with_brew_tags, params, check_mode=True)
        assert result['changed'] is True
        if PY2:
            expected = "changing brew_tags from [u'test-1'] to ['test-2']"
        else:
            expected = "changing brew_tags from ['test-1'] to ['test-2']"
        assert result['stdout_lines'] == [expected]

    def test_unchanged_with_brew_tags(self, client_with_brew_tags, params):
        params['brew_tags'] = ['test-1']
        result = ensure_release(client_with_brew_tags, params, check_mode=True)
        assert result['changed'] is False


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_release.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_release.AnsibleModule,
                            'fail_json', fail_json)

    @pytest.fixture
    def module_args(self):
        # Minimal required module args
        return {
            'name': 'Test release',
            'description': 'Test release',
            'type': 'QuarterlyUpdate',
            'product_versions': ['1.0.0'],
            'enabled': False,
            'active': False,
            'enable_batching': False,
        }

    def test_simple_async(self, monkeypatch):
        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_release, 'ensure_release', mock_ensure)
        module_args = {
            'name': 'rhceph-5.0',
            'type': 'Async',
            'description': 'Red Hat Ceph Storage 5.0',
            'program_manager': 'coolmanager@redhat.com',
            'product_versions': [],
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is True

    def test_missing_program_manager(self, monkeypatch):
        mock_ensure = Mock()
        mock_ensure.side_effect = \
            ProgramManagerNotFoundError('noexist@redhat.com')
        monkeypatch.setattr(errata_tool_release, 'ensure_release', mock_ensure)
        module_args = {
            'name': 'rhceph-5.0',
            'type': 'Async',
            'description': 'Red Hat Ceph Storage 5.0',
            'program_manager': 'noexist@redhat.com',
            'product_versions': [],
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleFailJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is False
        expected = 'program_manager noexist@redhat.com account not found'
        assert result['msg'] == expected

    def test_strict_user_check_missing_user(self, monkeypatch, module_args):
        """
        Test that the module fails when in strict user check mode
        and the user doesn't exist.
        """
        monkeypatch.setenv('ANSIBLE_STRICT_USER_CHECK_MODE', 'True')

        module_args['program_manager'] = 'noexist@redhat.com'
        module_args['_ansible_check_mode'] = True
        set_module_args(module_args)

        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_release, 'ensure_release', mock_ensure)

        mock_get_user = Mock()
        mock_get_user.side_effect = UserNotFoundError('noexist@redhat.com')
        monkeypatch.setattr(common_errata_tool, 'get_user', mock_get_user)

        with pytest.raises(AnsibleFailJson) as ex:
            main()

        result = ex.value.args[0]
        assert result['changed'] is False

        expected = 'program_manager noexist@redhat.com account not found'
        assert result['msg'] == expected

    def test_strict_user_check_disabled(self, monkeypatch, module_args):
        """
        Test that the module fails when in strict user check mode
        and the user account is disabled.
        """
        monkeypatch.setenv('ANSIBLE_STRICT_USER_CHECK_MODE', 'True')

        module_args['program_manager'] = 'retired@redhat.com'
        module_args['_ansible_check_mode'] = True
        set_module_args(module_args)

        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_release, 'ensure_release', mock_ensure)

        mock_get_user = Mock()
        mock_get_user.return_value = {'enabled': False}
        monkeypatch.setattr(common_errata_tool, 'get_user', mock_get_user)

        with pytest.raises(AnsibleFailJson) as ex:
            main()

        result = ex.value.args[0]
        assert result['changed'] is False

        expected = 'program_manager retired@redhat.com is not enabled'
        assert result['msg'] == expected
