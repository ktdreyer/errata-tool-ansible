from copy import deepcopy
from utils import Mock
from requests.exceptions import HTTPError
import pytest
from ansible.module_utils.six import PY2

from errata_tool_product_version import (
    ensure_product_version,
    get_product_version,
    handle_form_errors,
)


PROD = 'https://errata.devel.redhat.com'
PRODUCT = 'RHCEPH'
NAME = 'RHCEPH-4.0-RHEL-8'

# From /api/v1/products/RHCEPH/product_versions/?filter[name]=RHCEPH-4.0-RHEL-8
# See CLOUDWF-3
PRODUCT_VERSION = {
    "id": 929,
    "type": "product_versions",
    "attributes": {
        "name": "RHCEPH-4.0-RHEL-8",
        "description": "Red Hat Ceph Storage 4.0",
        "default_brew_tag": "ceph-4.0-rhel-8-candidate",
        "allow_rhn_debuginfo": False,
        "allow_buildroot_push": False,
        "is_oval_product": False,
        "is_rhel_addon": False,
        "is_server_only": False,
        "enabled": True,
        "suppress_push_request_jira": False,
        "allow_unreleased_rpms": True,
    },
    "brew_tags": ["ceph-4.0-rhel-8-candidate"],
    "relationships": {
        "push_targets": [
            {"id": 3, "name": "ftp"},
            {"id": 4, "name": "cdn"},
            {"id": 7, "name": "cdn_stage"},
            {"id": 9, "name": "cdn_docker"},
            {"id": 10, "name": "cdn_docker_stage"},
        ],
        "rhel_release": {"id": 87, "name": "RHEL-8"},
        "sig_key": {"id": 8, "name": "redhatrelease2"},
        "container_sig_key": {"id": 8, "name": "redhatrelease2"},
        "ima_sig_key": {"id": 15, "name": "redhatimarelease"},
    }
}


@pytest.fixture
def params():
    return {
        "product": "RHCEPH",
        "name": "RHCEPH-4.0-RHEL-8",
        "description": "Red Hat Ceph Storage 4.0",
        "default_brew_tag": "ceph-4.0-rhel-8-candidate",
        "brew_tags": ["ceph-4.0-rhel-8-candidate"],
        "allow_rhn_debuginfo": False,
        "allow_buildroot_push": False,
        "is_oval_product": False,
        "is_rhel_addon": False,
        "is_server_only": False,
        "enabled": True,
        "suppress_push_request_jira": False,
        "allow_unreleased_rpms": True,
        "push_targets": [
            "ftp",
            "cdn",
            "cdn_stage",
            "cdn_docker",
            "cdn_docker_stage",
        ],
        "rhel_release_name": "RHEL-8",
        "sig_key_name": "redhatrelease2",
        "container_sig_key_name": "redhatrelease2",
        "ima_sig_key_name": "redhatimarelease",
    }


class TestGetProductVersion(object):

    def test_not_found(self, client):
        check_mode = False
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': []})
        product_version = get_product_version(
            client, PRODUCT, NAME, check_mode)
        assert product_version is None

    def test_not_found_404(self, client):
        """Test when query returns 404"""
        check_mode = False
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': []},
            status_code=404)
        with pytest.raises(HTTPError):
            get_product_version(client, PRODUCT, NAME, check_mode)

    def test_not_found_404_check_mode(self, client):
        """Test when query returns 404 but check_mode is true"""
        check_mode = True
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': []},
            status_code=404)
        product_version = get_product_version(
            client, PRODUCT, NAME, check_mode)
        assert product_version is None

    def test_basic(self, client):
        check_mode = False
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': [PRODUCT_VERSION]})
        product_version = get_product_version(
            client, PRODUCT, NAME, check_mode)
        expected = {
            'allow_buildroot_push': False,
            'allow_rhn_debuginfo': False,
            'brew_tags': ['ceph-4.0-rhel-8-candidate'],
            'default_brew_tag': 'ceph-4.0-rhel-8-candidate',
            'description': 'Red Hat Ceph Storage 4.0',
            'enabled': True,
            'id': 929,
            'is_oval_product': False,
            'is_rhel_addon': False,
            'is_server_only': False,
            'name': 'RHCEPH-4.0-RHEL-8',
            'product': 'RHCEPH',
            'push_targets': ['ftp', 'cdn', 'cdn_stage',
                             'cdn_docker', 'cdn_docker_stage'],
            'rhel_release_name': 'RHEL-8',
            'suppress_push_request_jira': False,
            'allow_unreleased_rpms': True,
            'sig_key_name': 'redhatrelease2',
            'container_sig_key_name': 'redhatrelease2',
            'ima_sig_key_name': 'redhatimarelease',
        }
        assert product_version == expected

    def test_plus_character_in_name(self, client):
        """ Quote "+" characters in product version name HTTP request """
        name = NAME + '+EUS'
        product_version = deepcopy(PRODUCT_VERSION)
        product_version['attributes']['name'] = name
        check_mode = False
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/'
            + '?filter%5Bname%5D=' + NAME + '%2BEUS',
            json={'data': [product_version]})
        product_version = get_product_version(
            client, PRODUCT, name, check_mode)
        assert product_version.get('name') == name


class TestEnsureProductVersion(object):

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': [PRODUCT_VERSION]})
        result = ensure_product_version(client, params, check_mode)
        assert result['changed'] is False

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/'
            + '?filter%5Bname%5D=' + NAME,
            json={'data': []})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/products/RHCEPH/product_versions',
            status_code=201)
        result = ensure_product_version(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created RHCEPH-4.0-RHEL-8 product version']

    def test_edit_check_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': [PRODUCT_VERSION]})
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/products/RHCEPH/product_versions/929')
        params['description'] = 'Red Hat Ceph Storage 4.0 Is Cool'
        result = ensure_product_version(client, params, check_mode=True)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage 4.0 ' \
                   'to Red Hat Ceph Storage 4.0 Is Cool'
        if PY2:
            expected = u'changing description from Red Hat Ceph Storage 4.0 ' \
                'to Red Hat Ceph Storage 4.0 Is Cool'
        assert set(result['stdout_lines']) == set([expected])

    def test_edit_live_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': [PRODUCT_VERSION]})
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/products/RHCEPH/product_versions/929')
        params['description'] = 'Red Hat Ceph Storage 4.0 Is Cool'
        result = ensure_product_version(client, params, check_mode=False)
        assert result['changed'] is True
        expected = 'changing description from Red Hat Ceph Storage 4.0 ' \
                   'to Red Hat Ceph Storage 4.0 Is Cool'
        if PY2:
            expected = u'changing description from Red Hat Ceph Storage 4.0 ' \
                'to Red Hat Ceph Storage 4.0 Is Cool'
        assert set(result['stdout_lines']) == set([expected])

        history = client.adapter.request_history
        assert len(history) == 2
        assert history[1].method == 'PUT'
        assert history[1].url == \
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH/product_versions/929'
        expected_json = {
            'product_version': {
                'description': 'Red Hat Ceph Storage 4.0 Is Cool',
            }
        }
        assert history[1].json() == expected_json

    def test_create_ima_sig_key_optional(self, client, params):
        del params['ima_sig_key_name']
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/'
            + '?filter%5Bname%5D=' + NAME,
            json={'data': []})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/products/RHCEPH/product_versions',
            status_code=201)
        result = ensure_product_version(client, params, check_mode=False)
        assert result['changed'] is True
        assert result['stdout_lines'] == ['created RHCEPH-4.0-RHEL-8 product version']

        history = client.adapter.request_history
        assert len(history) == 2
        assert history[1].method == 'POST'
        assert history[1].url == \
            'https://errata.devel.redhat.com/api/v1/products/RHCEPH/product_versions'
        assert 'ima_sig_key_name' not in history[1].json()['product_version']


class TestFormErrors(object):

    def test_handle_form_error_500(self, client):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.url = PROD
        mock_response.text = 'Some error'
        expected = (
            'The request to https://errata.devel.redhat.com had a status code '
            'of 500 and failed with: Some error'
        )
        with pytest.raises(RuntimeError, match=expected):
            handle_form_errors(mock_response)
