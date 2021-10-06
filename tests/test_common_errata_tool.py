import pytest
from requests.exceptions import HTTPError
from ansible.module_utils.common_errata_tool import RELEASE_TYPES
from ansible.module_utils.common_errata_tool import PushTargetScraper
from ansible.module_utils.common_errata_tool import WorkflowRulesScraper
from ansible.module_utils.common_errata_tool import DefaultSolutions
from ansible.module_utils.common_errata_tool import diff_settings
from ansible.module_utils.common_errata_tool import describe_changes
from ansible.module_utils.common_errata_tool import user_id
from ansible.module_utils.six import PY2
from utils import load_html


@pytest.mark.parametrize("name,expected", [
    ('DEFAULT', 1),
    ('ENTERPRISE', 2),
    ('RHN_TOOLS', 3),
])
def test_default_solutions(name, expected):
    assert DefaultSolutions[name] == expected


def test_release_types():
    expected = frozenset(['QuarterlyUpdate', 'Zstream', 'Async'])
    assert RELEASE_TYPES == expected


class TestPushTargetScraper(object):
    @pytest.fixture(autouse=True)
    def fake_response(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/products/new',
            text=load_html('products_new.html'))

    @pytest.fixture
    def scraper(self, client):
        return PushTargetScraper(client)

    @pytest.fixture
    def enum(self, scraper):
        return scraper.enum

    @pytest.mark.parametrize('name,expected_id', [
        ('rhn_live', 1),
        ('rhn_stage', 2),
        ('ftp', 3),
        ('cdn', 4),
        ('cdn_stage', 5),
        ('altsrc', 6),
        ('cdn_docker', 8),
        ('cdn_docker_stage', 9),
    ])
    def test_name_to_id(self, enum, name, expected_id):
        assert int(enum[name]) == expected_id

    def test_convert_to_ints(self, scraper):
        result = scraper.convert_to_ints(['cdn', 'cdn_stage'])
        assert result == [4, 5]


class TestWorkflowRulesScraper(object):
    @pytest.fixture
    def enum(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/workflow_rules',
            text=load_html('workflow_rules.html'))
        scraper = WorkflowRulesScraper(client)
        return scraper.enum

    @pytest.mark.parametrize('name,expected_id', [
        ('Default', 1),
        ('Unrestricted', 2),
        ('CDN Push Only', 3),
        ('Covscan', 4),
        ('Non-blocking TPS', 7),
        ('Optional TPS DistQA', 9),
        ('Non-blocking rpmdiff for RHEL-8', 14),
        ('Ansible', 15),
        ('Non-blocking TPS & Covscan', 17),
        ('Non-blocking Push target & Covscan', 18),
    ])
    def test_name_to_id(self, enum, name, expected_id):
        assert int(enum[name]) == expected_id


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

    def test_errors_pre_cloudwf_8(self, client):
        # This test simulates the HTTP 500 error described in CLOUDWF-8.
        # Delete this test after CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/noexist@redhat.com',
            status_code=500,
            text='')
        with pytest.raises(HTTPError):
            user_id(client, 'noexist@redhat.com')

    def test_errors(self, client):
        # This test simulates the expected HTTP 400 error after CLOUDWF-8 is
        # resolved.
        json = {'errors': {'login_name': ['noexist@redhat.com not found.']}}
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/noexist@redhat.com',
            status_code=400,
            json=json)
        with pytest.raises(RuntimeError) as e:
            user_id(client, 'noexist@redhat.com')
        expected = "{'login_name': ['noexist@redhat.com not found.']}"
        if PY2:
            expected = "{u'login_name': [u'noexist@redhat.com not found.']}"
        assert str(e.value) == expected


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

    def test_delete(self, client):
        client.adapter.register_uri(
            'DELETE',
            'https://errata.devel.redhat.com/api/v1/foobar',
            status_code=204)
        response = client.delete('api/v1/foobar')
        assert response.request.method == 'DELETE'
