import threading
from typing import List
from strenum import StrEnum
import subprocess
import os
import re

def is_safe_arg(arg: str) -> bool:
    # % included for percent-encoded URLs (temporary-short-link's `url` can
    # legitimately contain them); , for comma-joined lists (the apply
    # command's --subsystems) - everything else stays a tight whitelist, no
    # shell metacharacters. subprocess is always invoked with a list (never
    # shell=True) so this is defense-in-depth, not the only thing standing
    # between input and a shell.
    return bool(re.match(r'^[a-zA-Z0-9_.\-/:?=&#%,]+$', arg))


class Command(StrEnum):
    apply = 'apply'
    install = 'install'
    reinstall = 'reinstall'
    update = 'update'
    status = 'status'
    restart_services = 'restart-services'
    temporary_short_link = 'temporary-short-link'
    temporary_access = 'temporary-access'
    update_usage = 'update-usage'
    get_cert = 'get-cert'
    apply_users = 'apply-users'
    update_wg_usage = 'update-wg-usage'
    update_awg_usage = 'update-awg-usage'


def commander(command: Command, run_in_background=True, subsystems: set[str] | frozenset[str] | None = None, **kwargs: str | int) -> str | None:
    """
    Run the commander based on the given command type.
    Args:
        command: The type of command to run.
        run_in_background: Whether to run the command in the background.
        subsystems: For Command.apply only - a set of install.sh subsystem
                    names (see hutils.apply_scope.Subsystem) to selectively
                    touch, skipping everything else. None/empty means touch
                    everything (today's behavior, and the only safe choice
                    when the caller isn't sure what actually needs it).
        **kwargs: Additional arguments to pass to the commander. Accepts the following:
                  url, slug, period for the temporary-short-link command.
                  port for the temporary-access command.
                  domain for the get-cert command
    """
    base_cmd: List[str] = [
        'sudo',
        os.path.join(
            os.environ['HIDDIFY_CONFIG_PATH'], 'common/commander.py')
    ]

    on_success = None
    if command == Command.apply:
        base_cmd.append('apply')
        if subsystems:
            subsystems_arg = ','.join(sorted(subsystems))
            if not is_safe_arg(subsystems_arg):
                raise Exception("Invalid input passed to the run_commander function for apply command's subsystems")
            base_cmd.extend(['--subsystems', subsystems_arg])

        def on_success():
            from hiddifypanel.hutils import apply_scope
            apply_scope.clear_applied_subsystems(subsystems)
    elif command == Command.install:
        base_cmd.append('install')

        def on_success():
            from hiddifypanel.hutils import apply_scope
            apply_scope.clear_applied_subsystems(None)
    elif command == Command.reinstall:
        base_cmd.append('reinstall')

        def on_success():
            from hiddifypanel.hutils import apply_scope
            apply_scope.clear_applied_subsystems(None)
    elif command == Command.update:
        base_cmd.append('update')
    elif command == Command.status:
        base_cmd.append('status')
    elif command == Command.restart_services:
        base_cmd.append('restart-services')
    elif command == Command.apply_users:
        base_cmd.append('apply-users')
    elif command == Command.temporary_short_link:
        url = str(kwargs.get('url', ''))
        slug = str(kwargs.get('slug', ''))
        period = kwargs.get('period', '')

        if not url or not slug or not is_safe_arg(url) or not is_safe_arg(slug):
            raise Exception("Invalid input passed to the run_commander function for temporary-short-link command")

        base_cmd.append('temporary-short-link')
        base_cmd.extend(['--url', url, '--slug', slug])
        if period:
            base_cmd.extend(['--period', str(period)])
    elif command == Command.temporary_access:
        port = str(kwargs.get('port'))
        if not port or not port.isnumeric():
            raise Exception("Invalid input passed to the run_commander function for temporary-access command")

        base_cmd.append('temporary-access')
        base_cmd.extend(['--port', port])
    elif command == Command.update_usage:
        base_cmd.append('update-usage')
    elif command == Command.get_cert:
        domain = str(kwargs.get('domain'))
        if not domain or not is_safe_arg(domain):
            raise Exception("Invalid input passed to the run_commander function for get-cert command")
        base_cmd.extend(['get-cert', '--domain', domain])
    elif command == Command.update_wg_usage:
        base_cmd.append('update-wg-usage')
    elif command == Command.update_awg_usage:
        base_cmd.append('update-awg-usage')
    else:
        raise Exception('WTF is happening!')
    if run_in_background:
        t = threading.Thread(target=cmd_in_back, args=(base_cmd, on_success), daemon=True)
        t.start()
    else:
        output = subprocess.check_output(base_cmd, cwd=str(os.environ['HIDDIFY_CONFIG_PATH'])).decode()
        if on_success:
            on_success()
        return output


def cmd_in_back(cmd, on_success=None):
    p = subprocess.Popen(cmd, cwd=str(os.environ['HIDDIFY_CONFIG_PATH']), start_new_session=True)
    p.wait()
    if p.returncode != 0:
        # Previously any failure here (e.g. install.sh exiting 12 because a
        # lock file from a recent run was still fresh) was completely silent:
        # the thread just died and the panel UI kept showing "waiting for
        # update" forever. Now it's at least logged so it's visible in the
        # panel's own logs instead of vanishing.
        import logging
        logging.getLogger(__name__).error(
            f"Background command failed with exit code {p.returncode}: {' '.join(cmd)}")
    elif on_success:
        on_success()
