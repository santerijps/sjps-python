from argparse import ArgumentParser
from datetime import datetime
from os import getcwd, getppid, kill, listdir
from os.path import basename, isdir, join, splitext
import shlex
from signal import SIGTERM
from subprocess import run, Popen, PIPE, TimeoutExpired
from time import sleep


parser = ArgumentParser(
    prog='hotreload',
    description='Reloads a script on change.'
)

parser.add_argument(
    '-t', '--types',
    nargs='+',
    default='.py',
    help='File types, .py files by default',
    dest='types'
)

parser.add_argument(
    '-p', '--path',
    default=getcwd(),
    help='Path to parent directory to be monitored',
    dest='path'
)

parser.add_argument(
    '-s', '--scripts',
    help='Path(s) to script(s) to be executed and reloaded.',
    nargs='*',
    dest='scripts',
    default=[]
)

parser.add_argument(
    '-l', '--log',
    dest='log',
    help='Log STDOUT of scripts to console. Default is 1.',
    default=1,
    type=int,
    choices=[1, 0]
)

args = parser.parse_args()
root_directory = join(getcwd(), args.path)
file_types = args.types
scripts = args.scripts

root_directory = root_directory.replace("'", '')
root_directory = root_directory.replace('"', '')
root_directory = root_directory.replace('\\.', '')


def get_files(path: str, file_types: list) -> list:
    result: list = []
    try:
        for file in listdir(path):
            file_path = join(path, file)
            if isdir(file_path):
                result += get_files(file_path, file_types)
            elif splitext(file_path)[1] in file_types:
                result.append(file_path)
    except PermissionError:
        print('No permission:', path)
    except Exception as e:
        print(e)
    return result


def get_and_read_files(path: str, file_types: list) -> dict:
    result: dict = {}
    for file in get_files(path, file_types):
        result[file] = open(file).read()
    return result


def run_scripts(scripts: list, log_stdout: bool) -> list:
    procs = []
    now = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    print(f'{now}: Changes observed, running scripts...')
    for script in scripts:
        """completed = run(script, encoding='UTF-8', capture_output=True)
        if log_stdout:
            print(basename(script), completed.stdout or None, end='')
            if not completed.stdout.endswith('\n'):
                print()"""
        proc = Popen(script, stdout=PIPE)
        procs.append(proc)
    return procs


def kill_procs(procs):
    for i in range(len(procs)):
        p = procs[i]
        p.kill()
        del procs[i]


procs: list = []

try:

    procs = run_scripts(scripts, bool(args.log))
    old_files = get_and_read_files(root_directory, file_types)

    while True:

        new_files = get_and_read_files(root_directory, file_types)

        if new_files != old_files:
            kill_procs(procs)
            procs = run_scripts(scripts, bool(args.log))

        old_files = {**new_files}
        sleep(0.2)

except KeyboardInterrupt:
    pass

except Exception as e:
    print(e)
