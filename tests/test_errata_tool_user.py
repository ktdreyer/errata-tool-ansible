from errata_tool_user import get_user
from errata_tool_user import create_user


USER = {
    "login_name": "me@redhat.com",
    "realname": "Me Myself",
    "organization": "Engineering",
    "enabled": True,
    "receives_mail": False,
    "email_address": "me@redhat.com",
    "roles": [
        "devel"
    ],
    "id": 123456,
}


class TestGetUser(object):

    def test_not_found_http_500(self, client):
        # ET currently returns HTTP 500 for missing users.
        # Delete this test when ERRATA-9723 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            status_code=500)
        user = get_user(client, 'me@redhat.com')
        assert user is None

    def test_not_found(self, client):
        # This test will match the ET server once ERRATA-9723 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json={'errors': {'login_name': 'me@redhat.com not found.'}},
            status_code=400)
        user = get_user(client, 'me@redhat.com')
        assert user is None

    def test_basic(self, client):
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            json=USER)
        user = get_user(client, 'me@redhat.com')
        assert user == USER


class TestCreateUser(object):

    def test_basic(self, client):
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/api/v1/user',
            status_code=201)
        create_user(client, USER)
