from ipc.client import analyze_command as send_to_daemon


def analyze_command(command: str) -> dict:
    return send_to_daemon(command)