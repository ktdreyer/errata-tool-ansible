import pytest
import errata_tool_variant
from errata_tool_variant import create_variant
from errata_tool_variant import edit_variant
from errata_tool_variant import ensure_variant
from errata_tool_variant import html_form_data
from errata_tool_variant import main
from errata_tool_variant import normalize_scraped
from errata_tool_variant import scrape_error_explanation
from errata_tool_variant import scrape_error_message
from utils import exit_json
from utils import fail_json
from utils import load_json
from utils import set_module_args
from utils import AnsibleExitJson
try:
    from urllib.parse import parse_qs
except ImportError:
    # Python 2
    from urlparse import parse_qs

PROD = 'https://errata.devel.redhat.com'


class FakeErrorResponse(object):
    """ Fake requests.Response """
    pass


@pytest.mark.parametrize('test_input,expected', [
    ('none', None),
    ('Cdn', 'cdn'),
    ('Cdn, Cdn Docker', ['cdn', 'cdn_docker']),
])
def test_normalize_scraped(test_input, expected):
    result = normalize_scraped(test_input)
    assert result == expected


def test_scrape_error_explanation():
    response = FakeErrorResponse()
    response.text = '''
    <div id="errorExplanation" class="errorExplanation">
    <h2>1 error prohibited this variant from being saved</h2>
    <p>There were problems with the following fields:</p>
    <ul><li>Variant push targets is invalid</li></ul></div>
'''
    result = scrape_error_explanation(response)
    expected = ['Variant push targets is invalid']
    assert result == expected


def test_scrape_error_message():
    response = FakeErrorResponse()
    response.text = '''
    <div class="site_message">
    <div class="alert alert-error">
    <img src="/images/icon_alert.gif"
    style="vertical-align:middle;"/>&nbsp;<b>Error</b>
    <div id="error-message" class="just_text pre-wrap">
    You do not have permission to edit CPE, need a secalert role
    </div></div>
    </div>
    '''
    result = scrape_error_message(response)
    expected = ['You do not have permission to edit CPE, need a secalert role']
    assert result == expected


def ceph_tools_variant_json_response():
    return load_json('8Base-RHCEPH-4.0-Tools.variant.json')


def rhel8_variant_json_response():
    return load_json('8Base.variant.json')


def rhel8_variant_html_response():
    html = '''
    <table class="fields">
    <tr>
    <td>Name</td>
    <td>8Base</td>
    </tr>
    <tr>
    <td>Allowable Push Targets</td>
    <td>none</td>
    </tr>
    </table>
    '''
    return html


def ceph_tools_variant_html_response():
    html = '''
    <table class="fields">
    <tr>
    <td>Name</td>
    <td>8Base-RHCEPH-4.0-Tools</td>
    </tr>
    <tr>
    <td>Allowable Push Targets</td>
    <td>Cdn</td>
    </tr>
    </table>
    '''
    return html


def new_product_html_response():
    html = '''
    <input
     type="checkbox"
     name="product[push_targets][]"
     id="product_push_targets_"
     value="4"
     class="external_true" />&nbsp;
     Push to CDN Live <span class='light'>(Pub Target: cdn)
     </span>
    '''
    return html


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

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base',
            json=rhel8_variant_json_response())
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHEL-8/variants/8Base',
            text=rhel8_variant_html_response())
        client.adapter.register_uri(
            'GET',
            PROD + '/products/new',
            text=new_product_html_response())
        return client

    @pytest.mark.parametrize('cpe', (None,
                                     'cpe:/a:redhat:ceph_storage:4::el8'))
    def test_html_form_data(self, client, params, cpe):
        params['cpe'] = cpe
        data = html_form_data(client, params)
        expected = {
            'variant[buildroot]': 0,
            'variant[description]': 'Red Hat Ceph Storage 4.0 Tools',
            'variant[name]': '8Base-RHCEPH-4.0-Tools',
            'variant[push_targets][]': [4],
            'variant[rhel_variant_id]': 2235
        }
        if cpe:
            expected['variant[cpe]'] = cpe
        assert data == expected

    def test_create_variant(self, client, params):
        client.adapter.register_uri(
            'POST',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8/variants')
        create_variant(client, params)
        history = client.adapter.request_history
        request = history[-1]
        qs = parse_qs(request.text)
        expected = {
            'variant[rhel_variant_id]': ['2235'],
            'variant[name]': ['8Base-RHCEPH-4.0-Tools'],
            'variant[description]': ['Red Hat Ceph Storage 4.0 Tools'],
            'variant[cpe]': ['cpe:/a:redhat:ceph_storage:4::el8'],
            'variant[push_targets][]': ['4'],
            'variant[buildroot]': ['0']
        }
        assert qs == expected

    def test_edit_variant(self, client, params):
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8/variants')
        client.adapter.register_uri(
            'POST',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8/variants/2341')
        # Very Cool Tools
        params['description'] = 'Red Hat Ceph Storage 4.0 Cool Tools',
        edit_variant(client, 'RHCEPH-4.0-RHEL-8', 2341, params)
        history = client.adapter.request_history
        request = history[-1]
        qs = parse_qs(request.text)
        expected = {
            '_method': ['patch'],
            'variant[rhel_variant_id]': ['2235'],
            'variant[name]': ['8Base-RHCEPH-4.0-Tools'],
            'variant[description]': ['Red Hat Ceph Storage 4.0 Cool Tools'],
            'variant[cpe]': ['cpe:/a:redhat:ceph_storage:4::el8'],
            'variant[push_targets][]': ['4'],
            'variant[buildroot]': ['0']
        }
        assert qs == expected


class TestEnsureVariant(object):

    @pytest.fixture
    def client(self, client):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base',
            json=rhel8_variant_json_response())
        client.adapter.register_uri(
            'GET',
            PROD + '/product_versions/RHEL-8/variants/8Base',
            text=rhel8_variant_html_response())
        client.adapter.register_uri(
            'GET',
            PROD + '/products/new',
            text=new_product_html_response())
        return client

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_unchanged(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        client.adapter.register_uri(
            'GET',
            PROD +
            '/product_versions/RHCEPH-4.0-RHEL-8/variants/8Base-RHCEPH-4.0-Tools',  # noqa E501
            text=ceph_tools_variant_html_response())
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is False

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_create(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json={'data': []})
        client.adapter.register_uri(
            'GET',
            PROD +
            '/product_versions/RHCEPH-4.0-RHEL-8/variants/8Base-RHCEPH-4.0-Tools',  # noqa E501
            text=ceph_tools_variant_html_response())
        client.adapter.register_uri(
            'POST',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8/variants')
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is True
        expected = ['created 8Base-RHCEPH-4.0-Tools variant']
        assert result['stdout_lines'] == expected

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_edit(self, client, params, check_mode):
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        client.adapter.register_uri(
            'GET',
            PROD +
            '/product_versions/RHCEPH-4.0-RHEL-8/variants/8Base-RHCEPH-4.0-Tools',  # noqa E501
            text=ceph_tools_variant_html_response())
        client.adapter.register_uri(
            'POST',
            PROD + '/product_versions/RHCEPH-4.0-RHEL-8/variants/2341')
        params['description'] = 'Really Cool Tools'
        result = ensure_variant(client, params, check_mode)
        assert result['changed'] is True
        expected = ['changing description from Red Hat Ceph Storage 4.0 Tools'
                    ' to Really Cool Tools']
        assert result['stdout_lines'] == expected

    @pytest.mark.parametrize('check_mode', (True, False))
    def test_edit_no_cpe(self, client, params, check_mode):
        # Setting cpe to "None" for an existing variant should not reset the
        # cpe.
        client.adapter.register_uri(
            'GET',
            PROD + '/api/v1/variants?filter%5Bname%5D=8Base-RHCEPH-4.0-Tools',
            json=ceph_tools_variant_json_response())
        client.adapter.register_uri(
            'GET',
            PROD +
            '/product_versions/RHCEPH-4.0-RHEL-8/variants/8Base-RHCEPH-4.0-Tools',  # noqa E501
            text=ceph_tools_variant_html_response())
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
