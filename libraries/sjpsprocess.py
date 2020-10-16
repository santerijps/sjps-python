from subprocess import run


def get_running_processes() -> list:
    """WINDOWS ONLY"""
    result = []
    output = run('tasklist', capture_output=True).stdout
    for line in output.split(b'\r\n')[3:]:
        task_name = line.split(b' ')[0].decode()
        if task_name:
            result.append(task_name)
    return result


def is_process_running(name: str) -> bool:
    """WINDOWS ONLY"""
    return name in get_running_processes()
