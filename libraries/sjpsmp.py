from multiprocessing import Process, Pipe, Value, Queue


class PipedProcess:

    """
    A Process with a Pipe. 
    The pipe is unique to this process.
    """

    def __init__(self, process, pipe):
        self.process = process
        self.pipe = pipe

    @property
    def id(self):
        return self.process.pid
    
    def is_alive(self) -> bool:
        return self.process.is_alive()

    def close(self):
        self.pipe.close()
        self.process.close()
    
    def join(self, timeout = 0):
        self.process.join(timeout)

    def kill(self):
        self.process.kill()

    def quit(self):
        self.process.terminate()
        self.kill()
        self.close()

    def start(self):
        if not self.process.is_alive():
            self.process.start()

    def poll(self, timeout = 0):
        return self.pipe.poll(timeout)

    def recv(self):
        """Blocks until data is available"""
        return self.pipe.recv()

    def send(self, data):
        try:
            self.pipe.send(data)
        except BrokenPipeError:
            pass
        except Exception as e:
            raise e
    
    def try_recv(self, default=None):
        try:
            if self.poll():
                return self.recv()
            else:
                return default
        except BrokenPipeError:
            return default
        except EOFError:
            return default
        except Exception:
            raise


class PipedProcessPool:

    def __init__(self, processes: dict = {}):
        assert type(processes) is dict
        assert len(processes)
        for p in processes.values():
            assert type(p) is PipedProcess

        self.processes: dict = processes
        self.coms = {}
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args, **kwargs):
        self.quit()
    
    def __getitem__(self, identifier) -> PipedProcess:
        return self.processes[identifier]
    
    def __contains__(self, identifier) -> bool:
        return identifier in self.processes
    
    def is_alive(self, identifier = None) -> bool:
        if identifier is not None:
            return self.processes[identifier].is_alive()
        else:
            for p in self.processes.values():
                if p.is_alive():
                    return True
            return False

    def join(self, identifier = None, timeout = None):
        if identifier is not None:
            self.processes[identifier].join(timeout)
        else:
            for p in self.processes.values():
                p.join(timeout)

    def quit(self, identifier = None):
        if identifier is not None:
            self.processes[identifier].quit()
        else:
            for p in self.processes.values():
                p.quit()
    
    def poll(self, identifier = None, timeout = 0) -> bool:
        # See link below for a possibly better solution
        # https://docs.python.org/3/library/multiprocessing.html?highlight=multiprocessing#multiprocessing.connection.wait
        if identifier is not None:
            if self.processes[identifier].poll(timeout):
                return True
        else:
            for p in self.processes.values():
                if p.poll(timeout):
                    return True
        return False
    
    def recv(self, identifier = None, timeout = 0) -> any:
        if identifier is not None:
            return self.processes[identifier].recv()
        else:
            result = {}
            for identifier, p in self.processes.items():
                while p.poll(timeout):
                    data = result.get(identifier, [])
                    data.append(p.recv())
                    result[identifier] = data
            return result
    
    def send(self, data: any, identifier = None):
        if identifier is not None:
            self.processes[identifier].send(data)
        else:
            for p in self.processes.values():
                p.send(data)

    def start(self, identifier = None):
        # TODO: Make it LAZY
        # Only create Process instances when they need to be started.
        # Then the user can pass parameters only when running the start method.
        if identifier is not None:
            self.processes[identifier].start()
        else:
            for p in self.processes.values():
                p.start()
    
    def try_recv(self, identifier = None, timeout = 0) -> any:
        if identifier is not None:
            if self.processes[identifier].poll(timeout):
                return self.processes[identifier].recv()
            else:
                return None
        else:
            result = {}
            for identifier, p in self.processes.items():
                while p.poll(timeout):
                    data = result.get(identifier, [])
                    data.append(p.recv())
                    result[identifier] = data
            return result or None
    
    def try_send(self, data: any, identifier = None):
        if identifier is not None:
            if identifier in self.processes:
                self.processes[identifier].send(data)
        else:
            for p in self.processes.values():
                p.send(data)


def pprint(*args, **kwargs):
    print('\r', end='')
    print(*args, **kwargs, flush=True)


def create_process(function, *args, **kwargs) -> Process:
    p = Process(target=function, args=args, kwargs=kwargs)
    return p


def spawn_process(function, *args, **kwargs) -> Process:
    p = Process(target=function, args=args, kwargs=kwargs)
    p.start()
    return p


def create_piped_process(function, *args, **kwargs) -> PipedProcess:
    server, client = Pipe()
    p = Process(target=function, args=(client, *args), kwargs=kwargs)
    return PipedProcess(p, server)


def spawn_piped_process(function, *args, **kwargs) -> PipedProcess:
    p = create_piped_process(function, *args, **kwargs)
    p.start()
    return p
