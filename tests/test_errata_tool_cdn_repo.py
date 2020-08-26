from copy import deepcopy
import re
import sys
import pytest
import errata_tool_cdn_repo
from errata_tool_cdn_repo import CDN_RELEASE_TYPES
from errata_tool_cdn_repo import CDN_CONTENT_TYPES
from errata_tool_cdn_repo import add_package_tag
from errata_tool_cdn_repo import cdn_repo_api_data
from errata_tool_cdn_repo import create_cdn_repo
from errata_tool_cdn_repo import edit_cdn_repo
from errata_tool_cdn_repo import ensure_cdn_repo
from errata_tool_cdn_repo import ensure_packages_tags
from errata_tool_cdn_repo import get_cdn_repo
from errata_tool_cdn_repo import get_package_tags
from errata_tool_cdn_repo import normalize_packages
from errata_tool_cdn_repo import main
from utils import exit_json
from utils import fail_json
from utils import set_module_args
from utils import AnsibleExitJson
from utils import AnsibleFailJson


PROD = 'https://errata.devel.redhat.com'

# From /api/v1/cdn_repos/?filter[name]=redhat-rhceph-rhceph-4-rhel8
# See CLOUDWF-316
CDN_REPO = {
    "id": 11010,
    "type": "cdn_repos",
    "attributes": {
        "name": "redhat-rhceph-rhceph-4-rhel8",
        "release_type": "Primary",
        "use_for_tps": False,
        "content_type": "Docker"
    },
    "relationships": {
        "arch": {
            "id": 28,
            "name": "multi"
        },
        "variants": [
            {
                "id": 2341,
                "name": "8Base-RHCEPH-4.0-Tools"
            },
            {
                "id": 2918,
                "name": "8Base-RHCEPH-4.1-Tools"
            }
        ],
        "packages": [
            {
                "id": 45969,
                "name": "rhceph-container",
                "cdn_repo_package_tags": [
                    {
                        "id": 13858,
                        "tag_template": "{{version}}-{{release}}"
                    },
                    {
                        "id": 13859,
                        "tag_template": "{{version}}"
                    },
                    {
                        "id": 13860,
                        "tag_template": "latest"
                    },
                    {
                        "id": 99999,
                        "tag_template": "my-variant-restricted-tag"
                    },
                ]
            }
        ]
    }
}

# From
# /api/v1/cdn_repo_package_tags?filter[cdn_repo_name]=redhat-rhceph-rhceph-4-rhel8
CDN_REPO_PACKAGE_TAGS = [
    {
        "id": 13860,
        "type": "cdn_repo_package_tags",
        "attributes": {
            "tag_template": "latest"
        },
        "relationships": {
            "cdn_repo": {
                "id": 11010,
                "name": "redhat-rhceph-rhceph-4-rhel8"
            },
            "package": {
                "id": 45969,
                "name": "rhceph-container"
            }
        }
    },
    {
        "id": 13859,
        "type": "cdn_repo_package_tags",
        "attributes": {
            "tag_template": "{{version}}"
        },
        "relationships": {
            "cdn_repo": {
                "id": 11010,
                "name": "redhat-rhceph-rhceph-4-rhel8"
            },
            "package": {
                "id": 45969,
                "name": "rhceph-container"
            }
        }
    },
    {
        "id": 13858,
        "type": "cdn_repo_package_tags",
        "attributes": {
            "tag_template": "{{version}}-{{release}}"
        },
        "relationships": {
            "cdn_repo": {
                "id": 11010,
                "name": "redhat-rhceph-rhceph-4-rhel8"
            },
            "package": {
                "id": 45969,
                "name": "rhceph-container"
            }
        }
    },
    {
        "id": 99999,
        "type": "cdn_repo_package_tags",
        "attributes": {
            "tag_template": "my-variant-restricted-tag"
        },
        "relationships": {
            "cdn_repo": {
                "id": 11010,
                "name": "redhat-rhceph-rhceph-4-rhel8"
            },
            "package": {
                "id": 45969,
                "name": "rhceph-container"
            },
            "variant": {
                "id": 9999,
                "name": "8Base-RHCEPH-4.0-Tools"
            },
        }
    },
]


def test_release_types():
    expected = ['Primary', 'EUS', 'LongLife']
    assert set(CDN_RELEASE_TYPES) == set(expected)


def test_content_types():
    expected = ['Binary', 'Debuginfo', 'Source', 'Docker']
    assert set(CDN_CONTENT_TYPES) == set(expected)


class TestCdnRepoApiData(object):
    def test_simple(self):
        result = cdn_repo_api_data({'name': 'my-cool-repo'})
        assert result == {'cdn_repo': {'name': 'my-cool-repo'}}

    def test_complex(self):
        params = {
            'name': 'my-cool-repo',
            'release_type': 'Primary',
            'content_type': 'Binary',
            'variants': ['7Client'],
            'arch': 'x86_64',
            'use_for_tps': True,
        }
        result = cdn_repo_api_data(params)
        expected = {
            'cdn_repo': {
                'name': 'my-cool-repo',
                'release_type': 'Primary',
                'content_type': 'Binary',
                'variant_names': ['7Client'],
                'arch_name': 'x86_64',
                'use_for_tps': True,
            }
        }
        assert result == expected


class TestCreateCdnRepo(object):

    def test_basic(self, client):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repos',
            status_code=201,
            json={'data': CDN_REPO})
        params = {
            'name': 'redhat-rhceph-rhceph-4-rhel8',
            'release_type': 'Primary',
            'content_type': 'Docker',
            'arch': 'multi',
            'variants': ['8Base-RHCEPH-4.0-Tools'],
            'package_names': ['rhceph-container'],
        }
        create_cdn_repo(client, params)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'cdn_repo': {
                'name': 'redhat-rhceph-rhceph-4-rhel8',
                'release_type': 'Primary',
                'content_type': 'Docker',
                'arch_name': 'multi',
                'variant_names': ['8Base-RHCEPH-4.0-Tools'],
                'package_names': ['rhceph-container'],
            }
        }
        assert history[0].json() == expected

    def test_failure(self, client):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repos',
            status_code=400,
            json={'status': 400, 'error': 'Bad Request'}
        )
        with pytest.raises(ValueError) as err:
            create_cdn_repo(client, {})
        assert str(err.value) == 'Bad Request'


class TestEditCdnRepo(object):

    def test_basic(self, client):
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/cdn_repos/11010',
            status_code=200)
        # Add one new variant.
        differences = [
            ('variants', ['8Base-RHCEPH-4.0-Tools'],
             ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools'])
        ]
        edit_cdn_repo(client, 11010, differences)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'cdn_repo': {
                'variant_names': ['8Base-RHCEPH-4.0-Tools',
                                  '8Base-RHCEPH-4.1-Tools'],
            }
        }
        assert history[0].json() == expected

    def test_failure(self, client):
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/cdn_repos/11010',
            status_code=400,
            json={'status': 400, 'error': 'Bad Request'}
        )
        differences = [('my-bogus-setting', 'foo', 'bar')]
        with pytest.raises(ValueError) as err:
            edit_cdn_repo(client, 11010, differences)
        assert str(err.value) == 'Bad Request'


class TestGetCdnRepo(object):

    def test_not_found(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': []})
        name = 'redhat-rhceph-rhceph-4-rhel8'
        cdn_repo = get_cdn_repo(client, name)
        assert cdn_repo is None

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': [CDN_REPO]})
        name = 'redhat-rhceph-rhceph-4-rhel8'
        cdn_repo = get_cdn_repo(client, name)
        expected = {
            'id': 11010,
            'name': 'redhat-rhceph-rhceph-4-rhel8',
            'release_type': 'Primary',
            'use_for_tps': False,
            'content_type': 'Docker',
            'arch': 'multi',
            'variants': [
                '8Base-RHCEPH-4.0-Tools',
                '8Base-RHCEPH-4.1-Tools',
            ],
            'package_names': [
                'rhceph-container',
            ],
        }
        assert cdn_repo == expected

    def test_no_packages(self, client):
        cdn_repo = deepcopy(CDN_REPO)
        del cdn_repo['relationships']['packages']
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': [cdn_repo]})
        name = 'redhat-rhceph-rhceph-4-rhel8'
        cdn_repo = get_cdn_repo(client, name)
        expected = {
            'id': 11010,
            'name': 'redhat-rhceph-rhceph-4-rhel8',
            'release_type': 'Primary',
            'use_for_tps': False,
            'content_type': 'Docker',
            'arch': 'multi',
            'variants': [
                '8Base-RHCEPH-4.0-Tools',
                '8Base-RHCEPH-4.1-Tools',
            ],
            'package_names': []
        }
        assert cdn_repo == expected


class TestGetPackageTags(object):

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': CDN_REPO_PACKAGE_TAGS})
        name = 'redhat-rhceph-rhceph-4-rhel8'
        cdn_repo = get_package_tags(client, name)
        expected = {
            'rhceph-container': {
                '{{version}}-{{release}}': {'id': 13858},
                '{{version}}': {'id': 13859},
                'latest': {'id': 13860},
                'my-variant-restricted-tag': {
                    'variant': '8Base-RHCEPH-4.0-Tools',
                    'id': 99999,
                }
            },
        }
        assert cdn_repo == expected


class TestAddPackageTag(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repo_package_tags',
            status_code=201)
        return client

    @pytest.fixture
    def repo_name(self):
        return 'redhat-rhceph-rhceph-4-rhel8'

    @pytest.fixture
    def package_name(self):
        return 'rhceph-container'

    def test_basic(self, client, repo_name, package_name):
        tag_template = 'latest'
        variant = None
        add_package_tag(client, repo_name, package_name, tag_template, variant)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {'cdn_repo_package_tag':
                    {'cdn_repo_name': 'redhat-rhceph-rhceph-4-rhel8',
                     'package_name': 'rhceph-container',
                     'tag_template': 'latest'}}
        assert history[0].json() == expected

    def test_variant_restriction(self, client, repo_name, package_name):
        tag_template = 'restricted-tag'
        variant = 'Product-Foo'
        add_package_tag(client, repo_name, package_name, tag_template, variant)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {'cdn_repo_package_tag':
                    {'cdn_repo_name': 'redhat-rhceph-rhceph-4-rhel8',
                     'package_name': 'rhceph-container',
                     'tag_template': 'restricted-tag',
                     'variant_name': 'Product-Foo'}}
        assert history[0].json() == expected

    def test_failure(self, client):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repo_package_tags',
            status_code=400,
            json={'status': 400, 'error': 'Bad Request'})
        with pytest.raises(ValueError) as err:
            add_package_tag(client, '', '', 'latest', None)
        request = {'cdn_repo_package_tag':
                   {'cdn_repo_name': '',
                    'package_name': '',
                    'tag_template': 'latest'}}
        expected = 'request: %s, error: Bad Request' % request
        assert str(err.value) == expected


class TestNormalize(object):

    def test_no_tags(self):
        packages = {'rhceph-container': []}
        expected = {'rhceph-container': {}}
        results = normalize_packages(packages)
        assert results == expected

    def test_one_tag(self):
        packages = {'rhceph-container': ['latest']}
        expected = {'rhceph-container': {'latest': {}}}
        results = normalize_packages(packages)
        assert results == expected

    def test_multiple_tags(self):
        packages = {'rhceph-container': ['latest', '{{version}}']}
        expected = {'rhceph-container': {'latest': {}, '{{version}}': {}}}
        results = normalize_packages(packages)
        assert results == expected

    def test_variant_restriction(self):
        packages = {'rhceph-container': [
            'latest',
            {'my-restricted-tag': {'variant': '8Base-RHCEPH-4.0-Tools'}},
        ]}
        expected = {'rhceph-container': {
            'latest': {},
            'my-restricted-tag': {'variant': '8Base-RHCEPH-4.0-Tools'},
        }}
        results = normalize_packages(packages)
        assert results == expected

    def test_multiple_packages(self):
        packages = {'rhceph-container': ['latest'],
                    'rhceph-dashboard-container': ['latest']}
        expected = {'rhceph-container': {'latest': {}},
                    'rhceph-dashboard-container': {'latest': {}}}
        results = normalize_packages(packages)
        assert results == expected


class EnsurePackageTagsBase(object):
    @property
    def repo(self):
        return {'id': 13860,
                'type': 'cdn_repo_package_tags',
                'attributes': {'tag_template': 'latest'},
                'relationships': {
                    'cdn_repo': {'id': 11010,
                                 'name': 'redhat-rhceph-rhceph-4-rhel8'},
                    'package': {'id': 45969, 'name': 'rhceph-container'},
                }
                }

    @property
    def repo_with_variant(self):
        # Set a pre-existing variant on our package's tag
        repo = self.repo
        repo['relationships']['variant'] = {'id': 9999,
                                            'name': '8Base-RHCEPH-4.0-Tools'}
        return repo

    @pytest.fixture
    def name(self):
        return 'redhat-rhceph-rhceph-4-rhel8'


class TestEnsurePackageTags(EnsurePackageTagsBase):
    """
    Assert ensure_package_tags() behavior with "check_mode=False".
    """

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': [self.repo]})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repo_package_tags',
            status_code=201)
        exiting_url_re = re.compile(
            r'^https:\/\/errata.devel.redhat.com\/'
            r'api\/v1\/cdn_repo_package_tags/\d+')
        client.adapter.register_uri(
            'PUT',
            exiting_url_re,
            status_code=200)
        client.adapter.register_uri(
            'DELETE',
            exiting_url_re,
            status_code=204)
        return client

    @pytest.fixture
    def check_mode(self):
        return False

    def test_unchanged(self, client, name, check_mode):
        packages = {'rhceph-container': {'latest': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        assert result == []
        assert len(client.adapter.request_history) == 1
        assert client.adapter.request_history[0].method == 'GET'

    def test_add_one(self, client, name, check_mode):
        packages = {'rhceph-container': {'latest': {}, 'new-tag': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['adding "new-tag" tag template to "rhceph-container"']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'POST'

    def test_remove_one(self, client, name, check_mode):
        packages = {'rhceph-container': {}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['removing "latest" tag template from "rhceph-container"']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'DELETE'

    def test_remove_and_add(self, client, name, check_mode):
        packages = {'rhceph-container': {'new-tag': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['removing "latest" tag template from "rhceph-container"',
                    'adding "new-tag" tag template to "rhceph-container"']
        assert result == expected
        assert len(client.adapter.request_history) == 3
        assert client.adapter.request_history[1].method == 'DELETE'
        assert client.adapter.request_history[2].method == 'POST'

    def test_add_variant(self, client, name, check_mode):
        packages = {'rhceph-container':
                    {'latest': {'variant': '8Base-RHCEPH-4.0-Tools'}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['adding "8Base-RHCEPH-4.0-Tools" variant to'
                    ' rhceph-container "latest" tag template']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'PUT'

    def test_remove_variant(self, client, name, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': [self.repo_with_variant]})
        packages = {'rhceph-container': {'latest': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['removing "8Base-RHCEPH-4.0-Tools" variant from'
                    ' rhceph-container "latest" tag template']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'PUT'

    def test_update_variant(self, client, name, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': [self.repo_with_variant]})
        packages = {'rhceph-container':
                    {'latest': {'variant': '8Base-RHCEPH-4.1-Tools'}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['changing rhceph-container "latest" variant from'
                    ' "8Base-RHCEPH-4.0-Tools" to "8Base-RHCEPH-4.1-Tools"']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'PUT'

    def test_add_one_from_zero(self, client, name, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': []})
        packages = {'rhceph-container': {'latest': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['adding "latest" tag template to "rhceph-container"']
        assert result == expected
        assert len(client.adapter.request_history) == 2
        assert client.adapter.request_history[1].method == 'POST'


class TestEnsurePackageTagsCheckMode(EnsurePackageTagsBase):
    """
    Assert ensure_package_tags() behavior with "check_mode=True".
    """

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': [self.repo]})
        return client

    @pytest.fixture
    def check_mode(self):
        return True

    def assert_readonly_history(self, test_client):
        for entry in test_client.adapter.request_history:
            assert entry.method == 'GET'

    def test_add(self, client, name, check_mode):
        packages = {'rhceph-container': {'latest': {}, 'new-tag': {}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['adding "new-tag" tag template to "rhceph-container"']
        assert result == expected
        self.assert_readonly_history(client)

    def test_remove(self, client, name, check_mode):
        packages = {'rhceph-container': {}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['removing "latest" tag template from "rhceph-container"']
        assert result == expected
        self.assert_readonly_history(client)

    def test_edit(self, client, name, check_mode):
        packages = {'rhceph-container':
                    {'latest': {'variant': '8Base-RHCEPH-4.0-Tools'}}}
        result = ensure_packages_tags(client, name, check_mode, packages)
        expected = ['adding "8Base-RHCEPH-4.0-Tools" variant to'
                    ' rhceph-container "latest" tag template']
        assert result == expected
        self.assert_readonly_history(client)


class TestEnsureCdnRepo(object):
    """
    Assert ensure_package_tags() behavior.
    """

    @pytest.fixture
    def params(self):
        return {
            'name': 'redhat-rhceph-rhceph-4-rhel8',
            'release_type': 'Primary',
            'content_type': 'Docker',
            'use_for_tps': False,
            'arch': 'multi',
            'variants': ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools'],
            'packages': {'rhceph-container': [
                'latest',
                '{{version}}',
                '{{version}}-{{release}}',
                {'my-variant-restricted-tag':
                    {'variant': '8Base-RHCEPH-4.0-Tools'}}
            ]},
        }

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': [CDN_REPO]})
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': CDN_REPO_PACKAGE_TAGS})
        result = ensure_cdn_repo(client, check_mode, params)
        assert result == {'changed': False, 'stdout_lines': []}

    def test_create_check_mode(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': []})
        check_mode = True
        result = ensure_cdn_repo(client, check_mode, params)
        expected = {'changed': True,
                    'stdout_lines': ['created redhat-rhceph-rhceph-4-rhel8']}
        assert result == expected

    def test_create(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': []})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repos',
            status_code=201,
            json={'data': CDN_REPO})
        # When we create a new cdn_repo with some package_names, the ET
        # automatically creates a new tag of "{{version}}-{{release}}" for
        # each of those. Represent that here:
        cdn_repo_package_tags = {
            "id": 13858,
            "type": "cdn_repo_package_tags",
            "attributes": {"tag_template": "{{version}}-{{release}}"},
            "relationships": {
                "cdn_repo": {
                    "id": 11010,
                    "name": "redhat-rhceph-rhceph-4-rhel8"
                },
                "package": {"id": 45969, "name": "rhceph-container"}
            }
        }
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': [cdn_repo_package_tags]})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/cdn_repo_package_tags',
            status_code=201)
        check_mode = False
        result = ensure_cdn_repo(client, check_mode, params)
        expected_stdout_lines = [
            'created redhat-rhceph-rhceph-4-rhel8',
            'adding "{{version}}" tag template to "rhceph-container"',
            ('adding "my-variant-restricted-tag" tag template'
             ' to "rhceph-container"'),
            'adding "latest" tag template to "rhceph-container"',
        ]
        assert result['changed'] is True
        assert set(result['stdout_lines']) == set(expected_stdout_lines)

    def test_edit(self, client, params):
        cdn_repo = deepcopy(CDN_REPO)
        del cdn_repo['relationships']['variants'][1]
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': [cdn_repo]})
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/cdn_repos/11010',
            status_code=200)
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repo_package_tags',
            json={'data': CDN_REPO_PACKAGE_TAGS})
        check_mode = False
        result = ensure_cdn_repo(client, check_mode, params)
        expected_stdout_lines = [
            "changing variants from ['8Base-RHCEPH-4.0-Tools'] to"
            " ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools']"
        ]
        if sys.version_info.major == 2:
            expected_stdout_lines = [
                "changing variants from [u'8Base-RHCEPH-4.0-Tools'] to"
                " ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools']"
            ]
        assert result['changed'] is True
        assert set(result['stdout_lines']) == set(expected_stdout_lines)

    def test_no_packages(self, client):
        params = {
            'name': 'rhceph-4-tools-for-rhel-8-x86_64-rpms',
            'release_type': 'Primary',
            'content_type': 'Binary',
            'use_for_tps': True,
            'arch': 'x86_64',
            'variants': ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools'],
            'packages': {},
        }
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/cdn_repos',
            json={'data': []})
        check_mode = True
        result = ensure_cdn_repo(client, check_mode, params)
        expected = {
            'changed': True,
            'stdout_lines': ['created rhceph-4-tools-for-rhel-8-x86_64-rpms'],
        }
        assert result == expected


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_cdn_repo.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_cdn_repo.AnsibleModule,
                            'fail_json', fail_json)

    @pytest.fixture(autouse=True)
    def fake_ensure_cdn_repo(self, monkeypatch):
        """
        Fake this large method, since we unit-test it individually elsewhere.
        """
        class FakeMethod(object):
            def __call__(self, *args, **kwargs):
                self.args = args
                return {'changed': True}

        fake = FakeMethod()
        monkeypatch.setattr(errata_tool_cdn_repo, 'ensure_cdn_repo', fake)
        return fake

    @pytest.fixture
    def container_module_args(self):
        return {
            'name': 'redhat-rhceph-rhceph-4-rhel8',
            'release_type': 'Primary',
            'content_type': 'Docker',
            'use_for_tps': False,
            'arch': 'multi',
            'variants': ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools'],
            'packages': {'rhceph-container': [
                'latest',
                '{{version}}',
                '{{version}}-{{release}}',
                {'my-variant-restricted-tag':
                    {'variant': '8Base-RHCEPH-4.0-Tools'}}
            ]},
        }

    def test_simple_rpms(self):
        module_args = {
            'name': 'rhceph-4-tools-for-rhel-8-x86_64-rpms',
            'release_type': 'Primary',
            'content_type': 'Binary',
            'use_for_tps': True,
            'arch': 'x86_64',
            'variants': ['8Base-RHCEPH-4.0-Tools', '8Base-RHCEPH-4.1-Tools'],
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True

    def test_simple_container(self, container_module_args):
        set_module_args(container_module_args)
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True

    @pytest.mark.parametrize('content_type,expected', [
        ('Docker',    'multi'),
        ('Binary',    'x86_64'),
        ('Debuginfo', 'x86_64'),
        ('Source',    'x86_64'),
    ])
    def test_default_arch(self, container_module_args, fake_ensure_cdn_repo,
                          content_type, expected):
        container_module_args['arch'] = None
        container_module_args['content_type'] = content_type
        set_module_args(container_module_args)
        with pytest.raises(AnsibleExitJson):
            main()
        _, _, params = fake_ensure_cdn_repo.args
        assert params['arch'] == expected

    def test_docker_arch_fail(self, container_module_args):
        container_module_args['content_type'] = 'Docker'
        container_module_args['arch'] = 'x86_64'
        set_module_args(container_module_args)
        with pytest.raises(AnsibleFailJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['msg'] == 'arch must be "multi" for Docker repos'
