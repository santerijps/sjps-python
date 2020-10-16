from http import HTTPStatus
from json import loads, JSONDecodeError
from mimetypes import guess_type
from pathlib import Path
from re import compile as compile_regex
from select import select
from socket import socket
from urllib.parse import unquote_plus


def build_http_response(status: [HTTPStatus, int], headers: dict, body: str) -> bytes:
    """
    Returns a bytes object representing an HTTP response.
    status should be an http.HTTPStatus object or an int representing an HTTP status code.
    """

    r: str = 'HTTP/1.1 '

    if type(status) is HTTPStatus:
        r += f'{status.value} {status.phrase}\r\n'
    else:
        r += f'{status} {get_http_status_code_phrase(status)}\r\n'

    r+= '\r\n'.join(f'{key}: {value}' for key, value in headers.items())
    r += f'\r\n\r\n{body}'

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


def is_file_url(url: str) -> bool:
    """Returns True if url ends with a file extension"""
    return bool(Path(url).suffix)


def parse_http_body(body: str) -> dict:
    """Parses the body of a request to a dict object"""

    r: dict = {}

    # Try load JSON from string
    try:
        r = loads(body)

    # Parse form data from string
    except JSONDecodeError:
        for pair in body.split('&'):
            if pair:
                key, value = pair.split('=', 1)
                r[unquote_plus(key)] = unquote_plus(value)

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


def parse_http_request(data: bytes) -> dict:
    """
    Parses an HTTP request into a dict object.
    Adds empty dict as value for cookie if no cookie found in request.
    """

    r: dict = {}

    headers, body = data.decode().split('\r\n\r\n')
    headers = headers.split('\r\n')
    method, path_with_parameters, http_version = headers[0].split()

    if '?' in path_with_parameters:
        path, parameter_string = path_with_parameters.split('?', 1)
        parameters = parse_url_parameters(parameter_string)

    else:
        path = path_with_parameters
        parameters = {}

    r['body'] = parse_http_body(body)
    r['method'] = method
    r['http_version'] = http_version
    r['path'] = unquote_plus(path)
    r['parameters'] = parameters

    for header in headers[1:]:
        key, value = header.split(': ', 1)
        r[key.lower()] = value

    r['cookie'] = parse_http_cookies(r.get('cookie', ''))

    return r


def parse_url_parameters(parameter_string: str) -> dict:
    """Parses URL parameters to a dict object"""

    r: dict = {}
    parameter_string = unquote_plus(parameter_string)

    for pair in parameter_string.split('&'):
        key, value = pair.split('=', 1)
        r[key] = value

    return r


def request_loop(host: str = 'localhost', port: int = 8080, **socket_options):
    """
    Listens on specified host and port for connections and receives messages.
    The connection is a regular socket connection. Client sockets and messages are yielded.
    Client sockets are closed automatically if they send an empty message.
    Otherwise the client socket must be closed manually.
    Loops forever. SIGINT is handled gracefully.
    https://stackoverflow.com/questions/5308080/python-socket-accept-nonblocking
    """

    try:

        with socket(**socket_options) as server:

            server.bind((host, port))
            server.listen()
            read_list = [server]

            while True:
                
                # timeout is set (0.1, 100 ms) to help with SIGINT, otherwise blocks
                readables, writeables, errors = select(read_list, [], [], 0.1)

                for readable in readables:

                    if readable == server:
                        read_list.append(server.accept()[0])

                    else:

                        # Read data from client socket and yield it
                        if (data := readable.recv(4096)):
                            yield readable, data
                        
                        # Close the client socket if no data was received
                        # Realistically this code block is never executed
                        # Client socket should be closed manually
                        else:
                            readable.close()

                        # Remove client socket if it has been closed
                        if readable.fileno() == -1:
                            read_list.remove(readable)

    except KeyboardInterrupt:
        pass
