
class View:
    """
    Subclasses should implement get, post etc. methods
    """

    template: str = None

    def __init__(self, request: dict):
        self.request = request

    def delete(self, **parameters) -> tuple:
        raise NotImplementedError('You must implement the delete method!')

    def get(self, **parameters) -> tuple:
        raise NotImplementedError('You must implement the get method!')

    def head(self, **parameters) -> tuple:
        raise NotImplementedError('You must implement the head method!')

    def post(self, **parameters) -> tuple:
        raise NotImplementedError('You must implement the post method!')

    def put(self, **parameters) -> tuple:
        raise NotImplementedError('You must implement the put method!')


class Model:
    pass
