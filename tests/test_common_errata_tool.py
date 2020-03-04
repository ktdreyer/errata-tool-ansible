import pytest
from requests.exceptions import HTTPError
from ansible.module_utils.common_errata_tool import RELEASE_TYPES
from ansible.module_utils.common_errata_tool import DefaultSolutions
from ansible.module_utils.common_errata_tool import diff_settings
from ansible.module_utils.common_errata_tool import describe_changes
from ansible.module_utils.common_errata_tool import user_id


@pytest.mark.parametrize("name,expected", [
    ('DEFAULT', 1),
    ('ENTERPRISE', 2),
    ('RHN_TOOLS', 3),
])
def test_default_solutions(name, expected):
    assert DefaultSolutions[name] == expected


def test_release_types():
    expected = set(['QuarterlyUpdate', 'Zstream', 'Async'])
    assert RELEASE_TYPES == expected


class TestDiffSettings(object):

    def test_simple(self):
        settings = {'active': False, 'push_targets': ['cdn']}
        params = {'active': True, 'push_targets': ['cdn']}
        differences = diff_settings(settings, params)
        assert differences == [('active', False, True)]

    def test_list(self):
        settings = {'active': True, 'push_targets': ['cdn']}
        params = {'active': True, 'push_targets': ['cdn', 'cdn_stage']}
        differences = diff_settings(settings, params)
        assert differences == [('push_targets', ['cdn'], ['cdn', 'cdn_stage'])]


class TestDescribeChanges(object):

    def test_simple(self):
        differences = [('active', False, True)]
        result = describe_changes(differences)
        assert result == ['changing active from False to True']


class TestUserID(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/cooluser@redhat.com',
            json={'login_name': 'cooluser@redhat.com', 'id': 123456})
        return client

    def test_simple(self, client):
        result = user_id(client, 'cooluser@redhat.com')
        assert result == 123456

    def test_errors_pre_errata_9723(self, client):
        # This test simulates the HTTP 500 error described in ERRATA-9723.
        # Delete this test after ERRATA-9723 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/noexist@redhat.com',
            status_code=500,
            text='')
        with pytest.raises(HTTPError):
            user_id(client, 'noexist@redhat.com')

    def test_errors(self, client):
        # This test simulates the expected HTTP 400 error after ERRATA-9723 is
        # resolved.
        json = {'errors': {'login_name': ['noexist@redhat.com not found.']}}
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/noexist@redhat.com',
            status_code=400,
            json=json)
        with pytest.raises(RuntimeError):
            user_id(client, 'noexist@redhat.com')


class TestClient(object):

    @pytest.mark.parametrize('verb', ['get', 'post', 'put'])
    def test_request(self, client, verb):
        client.adapter.register_uri(
            verb.upper(),
            'https://errata.devel.redhat.com/api/v1/foobar',
            text='success')
        method = getattr(client, verb)
        response = method('api/v1/foobar')
        assert response.text == 'success'

    @pytest.mark.parametrize('verb', ['post', 'put'])
    def test_json(self, client, verb):
        client.adapter.register_uri(
            verb.upper(),
            'https://errata.devel.redhat.com/api/v1/foobar')
        method = getattr(client, verb)
        response = method('api/v1/foobar', json={'mykey': 'myval'})
        assert response.request.body == b'{"mykey": "myval"}'
