from copy import deepcopy
import pytest
from errata_tool_release import get_release
from errata_tool_release import create_release
from errata_tool_release import edit_release
from utils import load_json


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
                # 'pelc_product_version_name': None,  # see issue #94
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
        assert err.value.args == ({'error': 'Some Error Here'},)


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
        assert err.value.args == ({'error': 'Some Error Here'},)
