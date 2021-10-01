import errata_tool_user_info
import pytest
from errata_tool_user_info import get_user, main
from utils import AnsibleExitJson, exit_json, set_module_args

USER = {
    "login_name": "me@redhat.com",
    "realname": "Me Myself",
    "organization": "Engineering",
    "enabled": True,
    "receives_mail": False,
    "email_address": "me@redhat.com",
    "roles": ["devel"],
    "id": 123456,
}


class TestGetUserInfo(object):
    def test_not_found(self, client):
        client.adapter.register_uri(
            "GET",
            "https://errata.devel.redhat.com/api/v1/user/me@redhat.com",
            json={"errors": {"login_name": "me@redhat.com not found."}},
            status_code=400,
        )
        user = get_user(client, "me@redhat.com")
        assert user == {
            "exists": False,
            "data": {},
        }

    def test_basic(self, client):
        client.adapter.register_uri(
            "GET",
            "https://errata.devel.redhat.com/api/v1/user/me@redhat.com",
            json=USER,
        )
        user = get_user(client, "me@redhat.com")
        assert user == {"exists": True, "data": USER}


class TestMain(object):
    @pytest.fixture(autouse=True)
    def fake_exits(self, monkeypatch):
        monkeypatch.setattr(
            errata_tool_user_info.AnsibleModule, "exit_json", exit_json
        )

    @pytest.fixture
    def fake_get_user(self, monkeypatch):
        """
        Fake this large method, since we unit-test it individually elsewhere.
        """

        class FakeMethod(object):
            def __call__(self, *args, **kwargs):
                self.args = args
                return {
                    "exists": True,
                    "data": {"login_name": "cooldev@redhat.com"},
                }

        fake = FakeMethod()
        monkeypatch.setattr(errata_tool_user_info, "get_user", fake)
        return fake

    def test_simple(self, fake_get_user):
        module_args = {
            "login_name": "cooldev@redhat.com",
        }
        set_module_args(module_args)

        with pytest.raises(AnsibleExitJson) as exit:
            main()

        result = exit.value.args[0]
        assert result == {
            "changed": False,
            "exists": True,
            "data": {"login_name": "cooldev@redhat.com"},
        }

        get_user_args = fake_get_user.args[1]
        assert get_user_args == "cooldev@redhat.com"
