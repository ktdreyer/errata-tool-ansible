import pytest
import errata_tool_variant
from errata_tool_variant import create_variant
from errata_tool_variant import edit_variant
from errata_tool_variant import ensure_variant
from errata_tool_variant import main
from utils import exit_json
from utils import fail_json
from utils import load_json
from utils import set_module_args
from utils import AnsibleExitJson

PROD = 'https://errata.devel.redhat.com'


def ceph_tools_variant_json_response():
    return load_json('8Base-RHCEPH-4.0-Tools.variant.json')


def rhel8_variant_json_response():
    return load_json('8Base.variant.json')


@pytest.fixture
def params():
    return {
        'rhel_variant': '8Base',
        'name': '8Base-RHCEPH-4.0-Tools',
        'description': 'Red Hat Ceph Storage 4.0 Tools',
        'cpe': 'cpe:/a:redhat:ceph_storage:4::el8',
        'push_targets': ['cdn'],
        'buildroot': False,
        'product_version': 'RHCEPH-4.0-RHEL-8',
    }


class TestResponses(object):

    def test_create_variant(self, client, params):
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/variants',
            status_code=201)
        create_variant(client, params)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'variant': {
                'name': '8Base-RHCEPH-4.0-Tools',
                'rhel_variant': '8Base',
                'description': 'Red Hat Ceph Storage 4.0 Tools',
                'cpe': 'cpe:/a:redhat:ceph_storage:4::el8',
                'product_version': 'RHCEPH-4.0-RHEL-8',
                'push_targets': ['cdn'],
                'buildroot': False,
            }
        }
        assert history[0].json() == expected

    def test_edit_variant(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/variants/2341')
        # Very Cool Tools
        differences = [('description',
                        'Red Hat Ceph Storage 4.0 Tools',
                        'Red Hat Ceph Storage 4.0 Cool Tools')]
        edit_variant(client, 2341, differences)
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'variant': {
                'description': 'Red Hat Ceph Storage 4.0 Cool Tools',
            }
        }
        assert history[0].json() == expected


class TestEnsureVariant(object):

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is False

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_create(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json={'data': []})
        client.adapter.register_uri(
            'POST',
            PROD + '/api/v1/variants',
            status_code=201)
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is True
        expected = ['created 8Base-RHCEPH-4.0-Tools variant']
        assert result['stdout_lines'] == expected
        history = client.adapter.request_history
        assert history[0].method == 'GET'
        if check_mode:
            assert len(history) == 1
        else:
            assert len(history) == 2

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_edit(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        client.adapter.register_uri(
            'PUT',
            PROD + '/api/v1/variants/2341')
        params['description'] = 'Really Cool Tools'
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is True
        expected = ['changing description from Red Hat Ceph Storage 4.0 Tools'
                    ' to Really Cool Tools']
        assert result['stdout_lines'] == expected
        history = client.adapter.request_history
        assert history[0].method == 'GET'
        if check_mode:
            assert len(history) == 1
        else:
            assert len(history) == 2
            expected = {'variant': {'description': 'Really Cool Tools'}}
            assert history[1].json() == expected

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_edit_no_cpe(self, client, params, check_mode):
        # Setting cpe to "None" for an existing variant should not reset the
        # cpe.
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        params['cpe'] = None
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is False


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_variant.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_variant.AnsibleModule,
                            'fail_json', fail_json)

    @pytest.fixture(autouse=True)
    def fake_ensure_variant(self, monkeypatch):
        """
        Fake this large method, since we unit-test it individually elsewhere.
        """
        class FakeMethod(object):
            def __call__(self, *args, **kwargs):
                self.args = args
                return {'changed': True}

        fake = FakeMethod()
        monkeypatch.setattr(errata_tool_variant, 'ensure_variant', fake)
        return fake

    def test_simple_layered(self):
        module_args = {
            'name': '8Base-RHCEPH-4.0-Tools',
            'description': 'Red Hat Ceph Storage 4.0 Tools',
            'cpe': None,
            'rhel_variant': '8Base',
            'push_targets': ['cdn'],
            'buildroot': False,
            'product_version': 'RHCEPH-4.0-RHEL-8',
        }
        set_module_args(module_args)
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True
