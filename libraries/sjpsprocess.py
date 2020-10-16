from os import kill
from signal import SIGTERM
from subprocess import run
from types import FunctionType


WINDOWS_ENCODING = 'iso-8859-1'


def get_processes(**filters) -> list:
    """
    NOTE: Windows only!

    Calls Windows' tasklist command to get a list of running processes.
    
    The command being run:
        tasklist /V /NH /FO:CSV
    
    Where
        /V means verbose
        /NH means no heading
        /FO:CSV means csv format

    The process dict object keys are:
        name (str)
        pid (int)
        session_name (str, usually Service or Console)
        session_number (int)
        memory_usage (int, in kilobytes)
        status (str, usually Unknown or Running)
        user (str, NT AUTHORITY\SYSTEM or Unknown or current user)
        cpu_time (int, in seconds)
        window_title (str, application title bar text)
    
    Filters can be passed to the function as kwargs.
    The keys should match the dict object keys.
    The values can be a single value, a function or a list (or tuple) of search values.
    If the filter value is a function, it should return a boolean.
    """

    result: list = []
    command = run('tasklist /V /NH /FO:CSV', capture_output=True, )
    output = command.stdout.decode(WINDOWS_ENCODING)

    fields = [
        {'key': 'name', 'type': str},
        {'key': 'pid', 'type': int},
        {'key': 'session_name', 'type': str},
        {'key': 'session_number', 'type': int},
        {'key': 'memory_usage', 'type': lambda x: int(x.replace(' K', '').replace('ÿ', ''))},
        {'key': 'status', 'type': str},
        {'key': 'user', 'type': str},
        {'key': 'cpu_time', 'type': str},
        {'key': 'window_title', 'type': lambda x: x[:-1]},
    ]

    for line in output.split('\n'):

        if not line:
            continue

        l = line.split(',')
        p = {f['key']: f['type'](l[i][1:-1]) for i, f in enumerate(fields)}

        for key, value in filters.items():
                
            if key not in p:
                raise Exception(f'Key "{key}" not found in process dict {list(p.keys())}')

            if type(value) in (list, tuple):
                if p[key] not in value:
                    break

            elif type(value) is FunctionType:
                if not value(p[key]):
                    break

            else:
                if p[key] != value:
                    break

        else:
            result.append(p)

    return result


def kill_process(**filters) -> int:
    """
    NOTE: Windows only!

    Calls get_processes with filters and kills them.
    Uses os.kill for terminating the process with signal.SIGTERM.
    Returns boolean for complete success and number of processes killed.
    """

    success = True
    kill_count = 0

    for p in get_processes(**filters):

        try:
            kill(p['pid'], SIGTERM)
            kill_count += 1
        except: # Maybe the process has already been killed?
            success = False

    return success, kill_count
