"""No live access: verify requests with HTTP mock transport, never remote writes."""
import base64
import json

import httpx
import pytest

import edge_storage as S

PROJECT = 'https://exampleproject.supabase.co'


def jwt(role):
    data = base64.urlsafe_b64encode(json.dumps({'role': role}).encode()).decode().rstrip('=')
    return 'header.' + data + '.signature'


def test_read_object_uses_one_authenticated_get_to_the_fixed_bucket():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.url.host == 'exampleproject.supabase.co'
        assert request.url.path == '/storage/v1/object/authenticated/spx-snapshots/folder/SPX snapshot.json.gz'
        assert request.headers['apikey'] == 'sb_publishable_example'
        assert request.headers['authorization'] == 'Bearer ' + jwt('authenticated')
        return httpx.Response(200, content=b'data')
    result = S.read_object(PROJECT, 'folder/SPX snapshot.json.gz', 'sb_publishable_example',
                           jwt('authenticated'), read_only_confirmed=True, transport=httpx.MockTransport(handler))
    assert result == b'data' and len(requests) == 1


@pytest.mark.parametrize('credential', ['sb_secret_example', jwt('service_role'), jwt('postgres'), jwt('supabase_admin')])
def test_privileged_key_or_token_is_rejected_before_network(credential):
    for key, token in ((credential, jwt('authenticated')), ('sb_publishable_example', credential)):
        with pytest.raises(S.StorageReadError):
            S.read_object(PROJECT, 'x.json', key, token, read_only_confirmed=True)


def test_read_privileges_must_be_confirmed_by_the_owner():
    with pytest.raises(S.StorageReadError, match='conferma'):
        S.read_object(PROJECT, 'x.json', 'sb_publishable_example', jwt('authenticated'))


@pytest.mark.parametrize('url', ['http://exampleproject.supabase.co', 'https://evil.example',
                                 'https://exampleproject.supabase.co@evil.example',
                                 'https://exampleproject.supabase.co:443', 'https://exampleproject.supabase.co/other'])
def test_non_project_urls_are_rejected(url):
    with pytest.raises(S.StorageReadError):
        S.read_object(url, 'x.json', 'sb_publishable_example', jwt('authenticated'), read_only_confirmed=True)


@pytest.mark.parametrize('path', ['../x.json','a/../x.json','/x.json','a//x.json',r'a\x.json','%2e%2e/x.json',
                                  'a%2Fx.json','x.csv',''])
def test_path_traversal_and_non_snapshot_paths_are_rejected(path):
    with pytest.raises(S.StorageReadError):
        S.read_object(PROJECT, path, 'sb_publishable_example', jwt('authenticated'), read_only_confirmed=True)


def test_signed_url_sends_no_api_key_or_bearer_header():
    def handler(request):
        assert request.method == 'GET'
        assert 'apikey' not in request.headers and 'authorization' not in request.headers
        return httpx.Response(200, content=b'json')
    result = S.read_signed_snapshot(PROJECT + '/storage/v1/object/sign/spx-snapshots/x.json?token=example',
                                    project_url=PROJECT, transport=httpx.MockTransport(handler))
    assert result == b'json'


@pytest.mark.parametrize('url', [PROJECT + '/storage/v1/object/public/spx-snapshots/x.json?token=example',
                                 PROJECT + '/storage/v1/object/sign/other-bucket/x.json?token=example',
                                 PROJECT + '/storage/v1/object/sign/spx-snapshots/x.json',
                                 'https://evil.example/x.json?token=example',
                                 PROJECT + '/storage/v1/object/sign/spx-snapshots/../x.json?token=example'])
def test_signed_urls_cannot_change_bucket_or_destination(url):
    with pytest.raises(S.StorageReadError):
        S.read_signed_snapshot(url)


def test_redirects_are_not_followed_and_secret_response_bodies_are_not_exposed():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={'Location': 'https://evil.example'}, text='SECRET_RESPONSE')
    with pytest.raises(S.StorageReadError) as exc:
        S.read_signed_snapshot(PROJECT + '/storage/v1/object/sign/spx-snapshots/x.json?token=SECRET_TOKEN',
                               transport=httpx.MockTransport(handler))
    message = str(exc.value)
    assert len(requests) == 1
    assert 'SECRET' not in message and 'evil' not in message


def test_connection_errors_do_not_disclose_signed_url():
    def handler(request):
        raise httpx.ConnectError('SECRET_TOKEN at ' + str(request.url), request=request)
    with pytest.raises(S.StorageReadError) as exc:
        S.read_signed_snapshot(PROJECT + '/storage/v1/object/sign/spx-snapshots/x.json?token=SECRET_TOKEN',
                               transport=httpx.MockTransport(handler))
    assert 'SECRET_TOKEN' not in str(exc.value)


def test_large_download_is_rejected(monkeypatch):
    monkeypatch.setattr(S, 'MAX_UPLOAD_BYTES', 2)
    with pytest.raises(S.StorageReadError, match='limite'):
        S.read_signed_snapshot(PROJECT + '/storage/v1/object/sign/spx-snapshots/x.json?token=example',
                               transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'123')))
