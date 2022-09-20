from utils import Mock
from requests.exceptions import HTTPError
import pytest

from errata_tool_product_version import get_product_version, handle_form_errors


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
        "use_quay_for_containers": False,
        "use_quay_for_containers_stage": False
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
    }
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
            'use_quay_for_containers': False,
            'use_quay_for_containers_stage': False,
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
            'sig_key_name': 'redhatrelease2',
            'container_sig_key_name': 'redhatrelease2'
        }
        assert product_version == expected


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
