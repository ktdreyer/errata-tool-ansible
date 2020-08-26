import pytest
import errata_tool_request
from errata_tool_request import main
from utils import exit_json
from utils import fail_json
from utils import set_module_args
from utils import AnsibleExitJson


class TestMain(object):

    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(errata_tool_request.AnsibleModule,
                            'exit_json', exit_json)
        monkeypatch.setattr(errata_tool_request.AnsibleModule,
                            'fail_json', fail_json)

    @pytest.fixture
    def client(self, monkeypatch, client):
        """
        Monkeypatch the Client class with our requests-mock class so we can
        fake HTTP responses.
        """
        monkeypatch.setattr(errata_tool_request, 'Client', lambda: client)
        return client

    def test_get_json(self, client):
        url = 'https://errata.devel.redhat.com/api/v1/user/cooldeveloper'
        client.adapter.register_uri(
            'GET',
            url,
            json={'login_name': 'cooldeveloper@redhat.com'})
        set_module_args({'path': '/api/v1/user/cooldeveloper'})
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True
        assert result['status'] == 200
        assert result['url'] == url
        assert result['json'] == {'login_name': 'cooldeveloper@redhat.com'}

    def test_get_html(self, client):
        url = 'https://errata.devel.redhat.com/products/new'
        client.adapter.register_uri(
            'GET',
            url,
            text='<html>new products form</html>')
        set_module_args({'path': '/products/new'})
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['changed'] is True
        assert result['status'] == 200
        assert result['url'] == url
        assert 'content' not in result

    def test_get_contents(self, client):
        url = 'https://errata.devel.redhat.com/products/new'
        client.adapter.register_uri(
            'GET',
            url,
            text='<html>new products form</html>')
        set_module_args({
            'path': '/products/new',
            'return_content': True,
        })
        with pytest.raises(AnsibleExitJson) as exit:
            main()
        result = exit.value.args[0]
        assert result['content'] == '<html>new products form</html>'
