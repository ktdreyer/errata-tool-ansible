from errata_tool_product_version import get_product_version


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
    }
}


class TestGetProductVersion(object):

    def test_not_found(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': []})
        product_version = get_product_version(client, PRODUCT, NAME)
        assert product_version is None

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/products/RHCEPH/product_versions/',
            json={'data': [PRODUCT_VERSION]})
        product_version = get_product_version(client, PRODUCT, NAME)
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
            'sig_key_name': 'redhatrelease2'
        }
        assert product_version == expected
