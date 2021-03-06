from sjpsocket.core import (
    build_http_response, build_regex_url, get_mime_type, get_parent_dir,
    http_client_request_loop, is_file_url, parse_http_request
)

from sjpsunits import Size

from asyncio import run, start_server, TimeoutError, wait_for
from http import HTTPStatus
from inspect import signature, _empty
from json import dumps
from os import listdir
from os.path import exists, join
from socket import AF_INET, SO_REUSEADDR
from types import FunctionType
from urllib.parse import unquote_plus


class AsyncHttpServer:

    def __init__(self, host: str = 'localhost', port: int = 8080, request_handler: FunctionType = None,
                 request_max_size: int = 500 * Size.megabyte, request_buffer_size: int = 4 * Size.kilobyte,
                 request_timeout: float = 0.5):
        
        self.host = host
        self.port = port

        self.request_handler = request_handler or (lambda: build_http_response(404, {}, ''))
        self.request_max_size = request_max_size
        self.request_buffer_size = request_buffer_size
        self.request_timeout = request_timeout
        

    async def read_all(self, reader) -> bytes:

        # TODO: Use selectors to read from the client socket instead! (to avoid timeout)

        result: bytes = bytes()
        
        try:

            while True:

                data = await wait_for(reader.read(self.request_buffer_size), self.request_timeout)

                if len(result) + len(data) <= self.request_max_size:
                    result += data
                else:
                    # Return None to avoid processing the request
                    return None

        except TimeoutError:
            pass

        return result


    async def handle_client(self, reader, writer):

        if (data := await self.read_all(reader)):
            request = parse_http_request(data)
            response = self.request_handler(request)
            writer.write(response)
            await writer.drain()

        writer.close()


    async def server_loop(self):

        server = await start_server(
            self.handle_client, self.host, self.port, family=AF_INET,
            reuse_address=SO_REUSEADDR
        )

        async with server:
            await server.serve_forever()


    def start(self):
        try:
            run(self.server_loop())
        except KeyboardInterrupt:
            pass


def file_server(root_directory: str, port: int = 8080):
    """Serves files from root_directory on specified port"""

    assert exists(root_directory)

    for client, request in http_client_request_loop(port=port):

        headers = {'Connection': 'close'}
        path = join(root_directory, request['path'][1:])

        if exists(path):

            status = HTTPStatus.OK

            if is_file_url(path):
                body = open(path).read()
                headers['Content-Type'] = get_mime_type(path)

            else:
                body = '<meta charset="UTF-8"/>'
                body += f'<h2>Files in {request["path"]}</h2><hr/>'
                headers['Content-Type'] = 'text/html'
                for file in listdir(path):
                    body += f'<a href="{join(request["path"], file)}">{file}</a><br/>'
                body += '<br/><hr/>'
                if request['path'] != '/':
                    parent = get_parent_dir(request['path'])
                    body += f'<a href="{parent}">&lt;&lt;</a>'

        else:
            body = '404 NOT FOUND'
            status = HTTPStatus.NOT_FOUND

        response = build_http_response(status, headers, body)
        client.send(response)
        client.close()


def redirect(url: str, timeout: int = 0, body: str = '', **options) -> tuple:
    """Returns a tuple with response data to redirect"""
    return (HTTPStatus.SEE_OTHER, {'Refresh': f'{timeout}; url={url}'}, body)


def respond(status: [HTTPStatus, int] = HTTPStatus.OK, headers: dict = {}, body: str = '', **options) -> tuple:
    """Builds an HTTP response with default values"""
    return (status, headers, body)


def single_page_application_server(root_directory: str, port: int = 8080, urls: dict = {}):
    """
    Serves files from root_directory on a specified port.
    If no urls are specified, every request returns index.html.
    SPA routing should be handled in the front end.
    index.html should be in the root_directory, this is te access point to the SPA.
    urls should be a dictionary where keys are URL paths and values are functions.
    The functions should at least take the request parameter, but if the url in urls
    specifies a variable, the same variable name will be passed to the url function.

    NOTE: This function never responds with 404s! The SPA front end should handle this instead.

    """

    root_file = join(root_directory, 'index.html')

    assert exists(root_directory)
    assert exists(root_file)

    for client, data in http_client_request_loop(port=port):

        headers = {'Connection': 'close'}
        status = HTTPStatus.OK

        if is_file_url(request['path']):

            path = join(root_directory, request['path'][1:])

            if exists(path):
                body = open(path).read()
                headers['Content-Type'] = get_mime_type(path)

            else:
                body = 'File not found'
                status = HTTPStatus.NOT_FOUND

        else:

            for url, handler in urls.items():
                regex = build_regex_url(url)
                if (match := regex.match(request['path'])):
                    body = handler(request, **match.groupdict()) or open(root_file).read()
                    break
            else:
                body = open(root_file).read()
                headers['Content-Type'] = get_mime_type(root_file)

        response = build_http_response(status, headers, body)
        client.send(response)
        client.close()

        print(status.value, request['method'], request['path'])


def web_server(port: int, root_directory: str, urls: dict, static_directory: str = 'static', template_directory: str = 'templates'):

    assert exists(root_directory)

    file_uploads = {} # client socket FD => boundary

    for client, request in http_client_request_loop(port=port):

        status = HTTPStatus.NOT_FOUND
        headers = {'Connection': 'close'}
        body = ''

        #
        # Serve static file
        #

        if is_file_url(request['path']) and request['path'].startswith('/' + static_directory + '/'):

            path = join(root_directory, request['path'][1:])

            if exists(path):
                status = HTTPStatus.OK
                headers['Content-Type'] = get_mime_type(path)
                body = open(path).read()

        #
        # Serve path
        #

        else:

            for url, handler in urls.items():

                regex = build_regex_url(url)

                if (match := regex.match(request['path'])):

                    match_group_dict = match.groupdict()
                    client_parameters = {**match_group_dict, **request['body']}

                    #
                    # Handle the handler
                    #
                    
                    if callable(handler):

                        function_args = []
                        function_kwargs = {}

                        if type(handler) is FunctionType:
                            function = handler
                            function_args.append(request)

                        else: # Class

                            instance = handler(request)
                            method = request['method'].lower()
                            function = getattr(instance, method)

                            if hasattr(instance, 'template'):
                                if (template_name := getattr(instance, 'template')):
                                    template_path = join(root_directory, template_directory, template_name)
                                    body = open(template_path).read()

                        try:
                            func_sig = signature(function)
                        except ValueError as error:
                            raise Exception('Missing self in view method!')

                        for name, param in func_sig.parameters.items():
                            if name in client_parameters:
                                value = client_parameters[name]
                                if param.annotation is not _empty:
                                    value = param.annotation(value)
                                function_kwargs[name] = value

                        try:
                            handler_response = function(*function_args, **function_kwargs)
                        except TypeError as error:
                            # Occurs when incorrect function args and/or kwargs were provided
                            print(error)
                            handler_response = (HTTPStatus.INTERNAL_SERVER_ERROR, {}, '')
                        except NotImplementedError:
                            # Occurs when no view method or template was provided
                            if not body:
                                raise
                            else:
                                handler_response = (HTTPStatus.OK, {}, body)

                    else:
                        handler_response = (HTTPStatus.OK, {}, str(handler))

                    #
                    # Handle the handler response
                    #

                    if body: # Template is set
                        if type(handler_response) is tuple and len(handler_response) == 3:
                            status = handler_response[0]
                            headers = {**headers, **handler_response[1]}
                            body = handler_response[2] if handler_response[2] else body
                        elif handler_response:
                            status = HTTPStatus.OK
                            body = handler_response
                        else:
                            status = HTTPStatus.OK

                    else:
                        if type(handler_response) is tuple and len(handler_response) == 3:
                            status = handler_response[0]
                            headers = {**headers, **handler_response[1]}
                            body = handler_response[2]
                        else:
                            status = HTTPStatus.OK if handler_response else HTTPStatus.NOT_IMPLEMENTED
                            body = str(handler_response) or ''

                    break

            else:
                status = HTTPStatus.NOT_FOUND
                body = ''

        #
        # Final touches to the response
        #

        if type(body) in (list, dict):
            body = dumps(body, indent=2)

        headers['Content-Length'] = len(body)
        response = build_http_response(status, headers, body)
        client.send(response)

        print(int(status), request['method'], request['path'])
