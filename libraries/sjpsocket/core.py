from http import HTTPStatus
from json import loads, JSONDecodeError
from mimetypes import guess_type
from pathlib import Path
from re import compile as compile_regex
from select import select
from socket import socket, SOL_SOCKET, SO_REUSEADDR
from urllib.parse import unquote_plus

from sjpsmp import spawn_piped_process


def build_http_response(status: [HTTPStatus, int], headers: dict, body: str) -> bytes:
    """
    Returns a bytes object representing an HTTP response.
    status should be an http.HTTPStatus object or an int representing an HTTP status code.
    """

    r: str = 'HTTP/1.1 '

    if type(status) is HTTPStatus:
        code = status.value
        phrase = status.phrase

    else:
        code = status
        phrase = get_http_status_code_phrase(code)

    r += f'{code} {phrase}\r\n'
    r += '\r\n'.join(f'{key}: {value}' for key, value in headers.items())
    r += ('\r\n' if r.endswith('\r\n') else '\r\n\r\n') + body

    return bytes(r, encoding='UTF-8')


def build_regex_url(url: str, prefix: str = ':') -> object:
    """
    Builds a regex Pattern object with re.compile.
    url should not be a regular expression, but instead a simple path string.
    prefix determines the prefix of a path variable.

    url format:
        /path/to/some/page      =>      ^/path/to/some/page$
        /countries/:country     =>      ^/countries/(?P<country>\w+)$
    
    etc.
    """

    r: str = '^'

    if len(url) == 1:
        r += url

    else:
        parts = url.split('/')
        for part in parts:
            if part:
                if part.startswith(prefix):
                    r += f'/(?P<{part[1:]}>\w+)'
                else:
                    r += '/' + part

    return compile_regex(r + '$')


def client_loop(host: str = 'localhost', port: int = 8080, **socket_options):
    """
    Runs a socket server and accepts connections.
    Yields a client if a client is trying to connect.
    Otherwise yields None.
    Runs forever.
    """

    try:

        with socket(**socket_options) as server:

            server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen()
            read_list = [server]

            while True:
                
                # timeout is set (0.05, 50 ms) to help with SIGINT, otherwise blocks
                readables = select(read_list, [], [], 0.05)[0]
                
                if readables:
                    for readable in readables:
                        yield server.accept()[0]
                
                else:
                    yield None

    except KeyboardInterrupt:
        pass
    
    except Exception as e:
        print('sjpsocket.core.client_loop ERROR:', e)


def get_http_status_code_phrase(code: int) -> str:
    """Returns a string representation of an HTTP status code"""

    if not code in list(HTTPStatus):
        raise Exception(f'HTTP response code "{code}" is not valid!')

    for status in list(HTTPStatus):
        if status.value == code:
            return status.phrase


def get_mime_type(url: str) -> str:
    """Returns the mime type of a file. Returns None if there are no matches."""
    return guess_type(url)[0]


def get_parent_dir(url: str) -> str:
    """Returns the parent directory in the given URL"""
    return str(Path(url).parent)


def http_client_request_loop(host: str = 'localhost', port: int = 8080, **socket_options):
    """
    NOTE: Not for production! (yet)
    Runs a socket server that parses HTTP requests.
    Yields clients (socket) and HTTP requests (dict).
    Automatically closes the client socket.
    Runs forever.
    WARNING: Blocks new connections when reading data.
    """
    for client in client_loop(host, port, **socket_options):
        if client:
            if (data := recv_all(client)):
                yield client, parse_http_request(data)
            client.close()


def _piped_process_recv_all(pipe, sock, data_limit):
        """
        Reads all data from a socket.
        Sends the received data in the pipe.
        Used exclusively by http_client_request_loop_async.
        """
        data = recv_all(sock, data_limit)
        pipe.send(data)


def http_client_request_loop_async(host: str = 'localhost', port: int = 8080, data_limit: int = 16_000, **socket_options):
    """
    NOTE: NOT FOR PRODUCTION!
    Runs a socket server that parses HTTP requests.
    Connected clients are read from in a sjpsmp.PipedProcess instance.
    Yields clients (socket) and HTTP requests (dict).
    Automatically closes the client socket.
    Runs forever.
    NOTE: Must be called in if __name__ == '__main__' block.
    TODO: File uploads really slow / don't work for slightly larger files
    """

    clients = []

    for client in client_loop(host, port, **socket_options):

        if client:
            clients.append((client, spawn_piped_process(_piped_process_recv_all, client, data_limit)))

        for c, p in clients:
            if not p.is_alive():
                if (data := p.try_recv()):
                    yield c, parse_http_request(data)
                c.close()
                clients.remove((c, p))


def is_file_url(url: str) -> bool:
    """Returns True if url ends with a file extension"""
    return bool(Path(url).suffix)


def is_http_request(data: bytes) -> bool:
    """Checks whether a received message is an HTTP request"""
    header_row = data.split(b'\r\n', 1)[0].decode()
    regex = compile_regex(r'(GET|POST|PUT|DELETE|HEAD)\s([\/\w\S]+)\s(HTTP\/\d\.\d)')
    return bool(regex.match(header_row))


def parse_form_multipart_form_data(body_section: bytes, content_type: str) -> dict:
    """
    Parses multipart/form-data body of an HTTP request.
    Files are always inserted into a list object.
    Returns a dict object.
    {
        'name': 'Alice',
        'uploadFiles': [
            {'name': 'hello.txt', 'type': 'text/plain', 'data': b'hello, world!'},
            ...
        ]
    }
    """
    r: dict = {}
    items: list = []
    content_type, boundary_string = content_type.split('; ', 1)
    boundary = boundary_string.split('=', 1)[1]
    for part in body_section.split(bytes('--' + boundary, 'utf-8'))[1:-1]:
        meta, data = part.lstrip().split(b'\r\n\r\n', 1)
        meta = meta.replace(b'\r\n', b'; ').replace(b': ', b'=').replace(b'"', b'')
        item: dict = {'data': data[:-2]}
        for pair in meta.split(b'; '):
            key, value = pair.split(b'=', 1)
            item[key.decode()] = value.decode()
        items.append(item)
    
    for item in items:
        if 'name' in item:
            if 'filename' in item and 'Content-Type' in item:
                if item['name'] not in r:
                    r[item['name']] = []
                r[item['name']].append({'type': item['Content-Type'], 'name': item['filename'], 'data': item['data']})
            else:
                r[item['name']] = item['data'].decode()

    return r


def parse_form_urlencoded(body_section: bytes) -> dict:
    """Parses application/x-www-form-urlencoded body of an HTTP request"""
    r: dict = {}
    for pair in body_section.decode().split('&'):
        if pair:
            key, value = pair.split('=', 1)
            r[unquote_plus(key)] = unquote_plus(value)
    return r


def parse_http_body(body_section: bytes, content_type: str = 'text/plain') -> dict:
    """
    Parses the body of a request to a dict object.
    content_type defines how the body is parsed.
        text/plain
        application/x-www-form-urlencoded
        multipart/form-data
    """

    r: dict = {}

    if len(body_section):

        if content_type == 'application/x-www-form-urlencoded':
            r = parse_form_urlencoded(body_section)

        elif content_type.startswith('multipart/form-data'):
            r = parse_form_multipart_form_data(body_section, content_type)
        
        else: # Possibly JSON
            try:
                r = loads(body_section.decode())
            except JSONDecodeError:
                print('Failed to parse HTTP body:')
                print(body_section)

    return r


def parse_http_cookies(cookie_string: str) -> dict:
    """
    Parses cookies from a given cookie string.
    Cookie string should be the value extracted from the request header.
    Returns a dictionary.
    """

    r: dict = {}
    pairs = cookie_string.split('; ')

    for pair in pairs:
        if pair:
            key, value = pair.split('=', 1)
            r[key] = value

    return r


def parse_http_headers(header_section: bytes) -> dict:
    """Parse the header section of an HTTP request"""

    r: dict = {}
    headers = header_section.decode().split('\r\n')
    method, path_with_parameters, http_version = headers[0].split()

    if '?' in path_with_parameters:
        path, parameter_string = path_with_parameters.split('?', 1)
        parameters = parse_url_parameters(parameter_string)

    else:
        path = path_with_parameters
        parameters = {}

    r['method'] = method
    r['http_version'] = http_version
    r['path'] = unquote_plus(path)
    r['parameters'] = parameters

    for header in headers[1:]:
        key, value = header.split(': ', 1)
        r[key.lower()] = value

    if 'cookie' in r:
        r['cookie'] = parse_http_cookies(r['cookie'])

    return r


def parse_http_request(data: bytes) -> dict:
    """Parses an HTTP request into a dict object {**headers, 'body': body}"""

    if not is_http_request(data):
        raise Exception(f'Not an HTTP request!\nType={type(data)}\n{data}')
    header_section, body_section = data.split(b'\r\n\r\n', 1)
    
    headers = parse_http_headers(header_section)
    body = parse_http_body(body_section, headers.get('content-type', 'text/plain'))

    return {**headers, 'body': body}


def parse_url_parameters(parameter_string: str) -> dict:
    """Parses URL parameters to a dict object"""

    r: dict = {}
    parameter_string = unquote_plus(parameter_string)

    for pair in parameter_string.split('&'):
        key, value = pair.split('=', 1)
        r[key] = value

    return r


def recv_all(sock, buffer_size: int = 8192, data_limit: int = None, timeout: float = 0.1) -> bytes:
    """
    Read all data from socket until nothing can be read.
    Utilizes select.select to deduce readability.
    Returns bytes.
    """

    data: bytes = b''

    try:
        while (readables := select([sock], [], [], timeout)[0]):
            data += readables[0].recv(buffer_size)
            if data_limit:
                if len(data) >= data_limit:
                    break

    except KeyboardInterrupt:
        pass

    return data
