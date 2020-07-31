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
        # Delete this test when CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@redhat.com',
            status_code=500)
        user = get_user(client, 'me@redhat.com')
        assert user is None

    def test_found_http_404(self, client):
        # ET currently returns HTTP 404 for users with some Kerberos realm
        # suffixes.
        # Delete this test when CLOUDWF-8 is resolved.
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/me@IPA.REDHAT.COM',
            status_code=404)
        client.adapter.register_uri(
            'POST',
            'https://errata.devel.redhat.com/user/find_user',
            headers={
                'Location': 'https://errata.devel.redhat.com/user/123456',
            },
            status_code=302)
        client.adapter.register_uri(
            'GET',
            'https://errata.devel.redhat.com/api/v1/user/123456',
            json=USER)
        user = get_user(client, 'me@IPA.REDHAT.COM')
        assert user == USER

    def test_not_found(self, client):
        # This test will match the ET server once CLOUDWF-8 is resolved.
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
        history = client.adapter.request_history
        assert len(history) == 1
        expected = {
            'email_address': 'me@redhat.com',
            'enabled': True,
            'id': 123456,
            'login_name': 'me@redhat.com',
            'organization': 'Engineering',
            'realname': 'Me Myself',
            'receives_mail': False,
            'roles': ['devel']
        }
        assert history[0].json() == expected
