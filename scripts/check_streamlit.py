"""Check Edge startup and synthetic calculation through its actual WebSocket.

Run: python scripts/check_streamlit.py --base-url http://127.0.0.1:8501
This checks the server protocol, not browser JavaScript or real CBOE data.
"""
import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect
from websockets.exceptions import WebSocketException


def receive_run(socket):
    deadline = time.monotonic() + 30
    result = {'radio_id': '', 'script_hash': '', 'metrics': [], 'titles': []}
    while time.monotonic() < deadline:
        raw = socket.recv(timeout=max(.1, deadline - time.monotonic()))
        if not isinstance(raw, bytes):
            continue
        message = ForwardMsg.FromString(raw)
        kind = message.WhichOneof('type')
        if kind == 'new_session':
            result['script_hash'] = message.new_session.page_script_hash
        if kind == 'delta' and message.delta.WhichOneof('type') == 'new_element':
            element = message.delta.new_element
            element_type = element.WhichOneof('type')
            if element_type == 'exception':
                raise RuntimeError('Server returned an application exception; inspect deployment logs.')
            if element_type == 'radio' and element.radio.label in ('Sorgente dati','Sorgente alternativa'):
                result['radio_id'] = element.radio.id
            if element_type == 'heading':
                result['titles'].append(element.heading.body)
            if element_type == 'metric':
                result['metrics'].append({'label': element.metric.label, 'value': element.metric.body})
        if kind == 'script_finished':
            return result
    raise TimeoutError('Script did not finish within 30 seconds.')


def check(base_url):
    parts = urlsplit(base_url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Use an HTTP(S) app URL without credentials or query parameters.')
    base = base_url.rstrip('/')
    with urlopen(base + '/_stcore/health', timeout=15) as response:
        if response.status != 200 or response.read(1024) != b'ok':
            raise RuntimeError('Health check did not return HTTP 200 and ok.')
    address = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                          parts.path.rstrip('/') + '/_stcore/stream', '', ''))
    with connect(address, origin=base, subprotocols=['streamlit'], open_timeout=15, close_timeout=3) as socket:
        request = BackMsg()
        request.rerun_script.query_string = ''
        socket.send(request.SerializeToString())
        first = receive_run(socket)
        if not first['radio_id'] or 'SPX · Edge GEX Lab' not in first['titles']:
            raise RuntimeError('Edge initial page was not received.')
        request = BackMsg()
        request.rerun_script.page_script_hash = first['script_hash']
        widget = request.rerun_script.widget_states.widgets.add()
        widget.id = first['radio_id']
        widget.string_value = 'Esempio sintetico (test)'
        socket.send(request.SerializeToString())
        second = receive_run(socket)
        metrics = second['metrics']
        if len(metrics) != 5 or metrics[0]['value'] != '6,000.00':
            raise RuntimeError('Synthetic calculation did not return the five expected metrics.')
    return {'health': 'passed', 'websocket_startup': 'passed',
            'synthetic_calculation': 'passed', 'metrics': metrics,
            'scope': 'server protocol; browser rendering and real data not verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8501')
    args = parser.parse_args()
    try:
        result = check(args.base_url)
    except (ValueError, RuntimeError, TimeoutError, HTTPError, URLError, OSError, WebSocketException) as error:
        # Connection error text can contain URLs; keep output free of such details.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
