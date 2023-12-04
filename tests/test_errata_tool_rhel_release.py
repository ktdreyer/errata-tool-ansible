import pytest
import errata_tool_rhel_release
from errata_tool_rhel_release import get_rhel_release
from errata_tool_rhel_release import create_rhel_release
from errata_tool_rhel_release import edit_rhel_release
from errata_tool_rhel_release import ensure_rhel_release
from errata_tool_rhel_release import main
from utils import load_json
from utils import exit_json
from utils import fail_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import Mock


PROD = 'https://errata.devel.redhat.com'
RHEL_RELEASE = load_json('rhel-2.1.rhel_release.json')


@pytest.fixture
def params():
    return {
        'name': 'RHEL-2.1',
        'description': 'Red Hat Advanced Server 2.1',
        'version_number': 2,
        'exclude_ftp_debuginfo': False,
        'is_zstream': False
    }


class TestGetRhelRelease(object):

    def test_not_found(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/rhel_releases?filter%5Bname%5D=missing-rhel-release-1.0',
            json={'data': []})
        result = get_rhel_release(client, 'missing-rhel-release-1.0')
        assert result is None

    def test_simple(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/rhel_releases?filter%5Bname%5D=rhel-2.1',
            json=RHEL_RELEASE)
        result = get_rhel_release(client, 'rhel-2.1')
        expected = {
            "id": 1,
            "name": "RHEL-2.1",
            "description": "Red Hat Advanced Server 2.1",
            "version_number": 2,
            "exclude_ftp_debuginfo": False,
            "is_zstream": False
        }
        assert result == expected

    def test_plus_character_in_name(self, client):
        """ Quote "+" characters in rhel release name HTTP request """
        json = load_json('rhel-8.1.0.z.main+eus.rhel_release.json')
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/rhel_releases?filter[name]=RHEL-8.1.0.Z.MAIN%2BEUS',
            json=json)
        result = get_rhel_release(client, 'RHEL-8.1.0.Z.MAIN+EUS')
        assert result['name'] == 'RHEL-8.1.0.Z.MAIN+EUS'


class TestCreateRhelRelease(object):
    def test_create_rhel_release(self, client, params):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/rhel_releases',
            status_code=201)

        create_rhel_release(client, params)
        history = client.adapter.request_history
        expected = {
            'name': 'RHEL-2.1',
            'description': 'Red Hat Advanced Server 2.1',
            'version_number': 2,
            'exclude_ftp_debuginfo': False,
            'is_zstream': False
        }

        assert history[-1].url == PROD + '/api/v1/rhel_releases'
        assert history[-1].method == 'POST'
        assert history[-1].json() == expected

    @pytest.mark.parametrize('response_text,response_json', [
        (None, {'error': 'Some Error Here'}),
        ('Some Error Here', None),
    ])
    def test_error(self, client, params, response_text, response_json):
        """ Ensure that we raise any server message to the user. """
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/rhel_releases',
            status_code=500,
            text=response_text,
            json=response_json,
        )
        with pytest.raises(ValueError) as err:
            create_rhel_release(client, params)
        error = str(err.value)
        assert 'Unexpected response from Errata Tool: Some Error Here' in error
        assert '\n  Request: POST /api/v1/rhel_releases' in error
        assert '\n  Status code: 500' in error


class TestEditRhelRelease(object):

    def test_edit_rhel_release(self, client):
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/rhel_releases/1')

        differences = [('description',
                        'Red Hat Advanced Server 2.1',
                        'Red Hat Advanced Server version 2.1')]
        edit_rhel_release(client, 1, differences)

        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'rhel_release': {
                'description': 'Red Hat Advanced Server version 2.1'
            }
        }
        assert history[0].json() == expected

    def test_error(self, client):
        """ Ensure that we raise any server message to the user. """
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/rhel_releases/1',
            status_code=500,
            json={'error': 'Some Error Here'})
        differences = [('description',
                        'Red Hat Advanced Server 2.1',
                        'Red Hat Advanced Server version 2.1')]
        with pytest.raises(ValueError) as err:
            edit_rhel_release(client, 1, differences)
        error = str(err.value)
        assert 'Unexpected response from Errata Tool: Some Error Here' in error
        assert '\n  Request: PUT /api/v1/rhel_releases/1' in error
        assert '\n  Status code: 500' in error
        expected_request_body = (
            '\n  Request body: {"rhel_release": {'
            '"description": "Red Hat Advanced Server version 2.1"}}'
        )
        assert expected_request_body in error


class TestEnsureRhelRelease(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/rhel_releases?filter%5Bname%5D=RHEL-2.1',
            json=RHEL_RELEASE)
        return client

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        result = ensure_rhel_release(client, params, check_mode)
        assert result['changed'] is False

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/rhel_releases?filter%5Bname%5D=RHEL-2.1',
            json={'data': []})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/rhel_releases',
            status_code=201)
        result = ensure_rhel_release(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created RHEL-2.1']
        history = client.adapter.request_history
        expected = {
            'name': 'RHEL-2.1',
            'description': 'Red Hat Advanced Server 2.1',
            'version_number': 2,
            'exclude_ftp_debuginfo': False,
            'is_zstream': False
        }
        assert history[-1].url == PROD + '/api/v1/rhel_releases'
        assert history[-1].method == 'POST'
        assert history[-1].json() == expected

    def test_edit_check_mode(self, client, params):
        params['description'] = 'Red Hat Advanced Server Version 2.1'
        result = ensure_rhel_release(client, params, check_mode=True)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Advanced Server 2.1 ' \
                   'to Red Hat Advanced Server Version 2.1'
        assert result['stdout_lines'] == [expected]

    def test_edit_live(self, client, params):
        params['description'] = 'Red Hat Advanced Server Version 2.1'
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/rhel_releases/1')
        result = ensure_rhel_release(client, params, check_mode=False)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Advanced Server 2.1 ' \
                   'to Red Hat Advanced Server Version 2.1'
        assert result['stdout_lines'] == [expected]
        expected = {
            'rhel_release': {
                'description': 'Red Hat Advanced Server Version 2.1'
            }
        }
        history = client.adapter.request_history
        assert history[-1].url == PROD + '/api/v1/rhel_releases/1'
        assert history[-1].method == 'PUT'
        assert history[-1].json() == expected


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_rhel_release.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_rhel_release.AnsibleModule,
                            'fail_json', fail_json)

    def module_args(self):
        # Minimal required module args
        return {
            'name': 'Test rhel release',
            'description': 'Test rhel release',
            'exclude_ftp_debuginfo': True
        }

    def test_simple_async(self, monkeypatch):
        mock_ensure = Mock()
        mock_ensure.return_value = {'changed': True}
        monkeypatch.setattr(errata_tool_rhel_release,
                            'ensure_rhel_release', mock_ensure)
        module_args = {
            'name': 'RHEL-7000',
            'description': 'Red Hat Advanced Server 7000',
            'exclude_ftp_debuginfo': True
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as ex:
            main()
        result = ex.value.args[0]
        assert result['changed'] is True
