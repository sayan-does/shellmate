from shellmate.ipc.client import analyze_command as send_to_daemon


def analyze_command(command: str, user_queries=None, overrides=None, directives=None) -> dict:
    return send_to_daemon(command, user_queries=user_queries, overrides=overrides, directives=directives)
