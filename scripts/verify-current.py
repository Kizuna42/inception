#!/usr/bin/env python3
"""Verify requested source and existing-runtime checks without provisioning."""

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time
from typing import Literal


Status = Literal['pass', 'fail', 'not_requested', 'unavailable']
COMMAND_TIMEOUT = 10
OUTPUT_LIMIT = 65536
REQUIRED_FILES = (
    'Makefile', 'README.md', 'USER_DOC.md', 'DEV_DOC.md',
    'srcs/.env', 'srcs/docker-compose.yml',
    'srcs/requirements/mariadb/conf/99-inception.cnf',
    'srcs/requirements/wordpress/conf/www.conf',
    'srcs/requirements/nginx/conf/nginx.conf',
    'srcs/requirements/mariadb/Dockerfile',
    'srcs/requirements/wordpress/Dockerfile',
    'srcs/requirements/nginx/Dockerfile',
    'srcs/requirements/mariadb/tools/entrypoint.sh',
    'srcs/requirements/wordpress/tools/entrypoint.sh',
)
SERVICES = ('mariadb', 'wordpress', 'nginx')
INSPECT_FORMAT = (
    '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"status":{{json .State.Status}},'
    '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}'
)


@dataclass(frozen=True)
class Request:
    repo: Path
    expected_sha: str
    output: Path
    validate_compose: bool = False
    observe_runtime: bool = False


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    reason: str


@dataclass(frozen=True)
class Report:
    expected_sha: str
    actual_sha: str | None
    tracked_dirty: bool | None
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(check.status in ('pass', 'not_requested') for check in self.checks)


def _run(argv: list[str], cwd: Path) -> tuple[int | None, bytes, str]:
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_') and key not in ('ENV', 'BASH_ENV')}
    environment['GIT_OPTIONAL_LOCKS'] = '0'
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        return None, b'', 'command unavailable'
    output = bytearray()
    total = 0
    failure = ''
    deadline = time.monotonic() + COMMAND_TIMEOUT
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, True)
        selector.register(process.stderr, selectors.EVENT_READ, False)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = 'command timed out'
                break
            for key, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > OUTPUT_LIMIT:
                    failure = 'command output limit exceeded'
                    break
                if key.data:
                    output.extend(chunk)
            if failure:
                break
        if not failure:
            try:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                failure = 'command timed out'
        if failure:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    process.stdout.close()
    process.stderr.close()
    if failure:
        return None, b'', failure
    return process.returncode, bytes(output), 'command failed' if process.returncode else ''


def verify(request: Request) -> Report:
    if not re.fullmatch(r'[0-9a-fA-F]{40}', request.expected_sha):
        raise ValueError('expected SHA must contain exactly 40 hexadecimal characters')
    repo = request.repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError('repo must be a Git root directory')
    git = ['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null']
    code, root, _ = _run(git + ['rev-parse', '--show-toplevel'], repo)
    if code != 0 or Path(os.fsdecode(root).strip()).resolve() != repo:
        raise ValueError('repo must be the actual Git root directory')
    code, filter_keys, _ = _run(git + ['config', '--null', '--name-only', '--get-regexp',
                                      r'^filter\..*\.(clean|smudge|process|required)$'], repo)
    if code not in (0, 1):
        raise ValueError('Git filter configuration could not be inspected')
    for key in os.fsdecode(filter_keys).split('\0'):
        if key:
            driver, _, setting = key.rpartition('.')
            git += ['-c', key + ('=false' if setting == 'required' else '='),
                    '-c', driver + '.required=false']
    destination = request.output.absolute()
    if destination.is_symlink() or destination.exists():
        raise ValueError('output must be a new directory')
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    if destination == repo or repo in destination.parents:
        raise ValueError('output must be outside the repository')
    destination.mkdir(mode=0o700)
    checks = []
    actual_sha = None
    dirty = None

    def check(name: str, status: Status, reason: str) -> None:
        checks.append(Check(name, status, reason))

    def identity() -> tuple[str | None, bool | None]:
        code, head, _ = _run(git + ['rev-parse', '--verify', 'HEAD'], repo)
        sha = head.decode('ascii', errors='replace').strip()
        if code != 0 or not re.fullmatch(r'[0-9a-f]{40}', sha):
            return None, None
        statuses = [_run(git + ['diff', '--no-ext-diff', '--no-textconv',
                               '--quiet'] + extra + ['--'], repo)[0]
                    for extra in ([], ['--cached'])]
        if any(status not in (0, 1) for status in statuses):
            return sha, None
        return sha, any(status == 1 for status in statuses)

    actual_sha, dirty = identity()
    check('source_identity', 'pass' if actual_sha == request.expected_sha.lower()
          and dirty is False else 'fail',
          'HEAD matches expected SHA and tracked index/worktree are clean'
          if actual_sha == request.expected_sha.lower() and dirty is False
          else 'HEAD mismatch, tracked changes, or Git inspection failure')
    code, tracked_output, _ = _run(git + ['ls-files', '-z'], repo)
    tracked = set(os.fsdecode(tracked_output).split('\0')) if code == 0 else set()
    required_ok = code == 0
    for relative in REQUIRED_FILES:
        path = repo / relative
        safe = (relative in tracked and path.is_file()
                and not any(part.is_symlink() for part in (path, *path.parents)
                            if part != repo and repo in part.parents))
        required_ok = required_ok and safe
        check('file:' + relative, 'pass' if safe else 'fail',
              'required tracked regular file present' if safe
              else 'required tracked regular file missing or symlinked')
    secrets_ok = code == 0 and not any(
        part.lower() == 'secrets' for name in tracked for part in Path(name).parts)
    check('tracked_secrets', 'pass' if secrets_ok else 'fail',
          'no tracked secrets directory' if secrets_ok else 'tracked secrets or Git inspection failure')
    for service in ('mariadb', 'wordpress'):
        if required_ok:
            code, _, error = _run(['sh', '-n', str(repo / 'srcs' / 'requirements'
                                                  / service / 'tools' / 'entrypoint.sh')], repo)
            check('shell_syntax:' + service, 'pass' if code == 0 else 'fail',
                  'shell syntax parses' if code == 0 else error)
        else:
            check('shell_syntax:' + service, 'unavailable', 'required source files did not pass')
    source_ok = all(item.status == 'pass' for item in checks)
    compose = ['docker', 'compose', '--project-name', 'inception',
               '-f', str(repo / 'srcs/docker-compose.yml')]
    if not request.validate_compose:
        check('compose_config', 'not_requested', 'Compose validation not requested')
    elif not source_ok:
        check('compose_config', 'unavailable', 'source checks did not pass')
    else:
        code, _, error = _run(compose + ['config', '--quiet'], repo)
        check('compose_config', 'pass' if code == 0 else 'unavailable' if code is None else 'fail',
              'Compose configuration parses' if code == 0 else error)
    if not request.observe_runtime:
        check('runtime', 'not_requested', 'existing runtime observation not requested')
    elif not source_ok:
        check('runtime', 'unavailable', 'source checks did not pass')
    else:
        code, ids, error = _run(compose + ['ps', '--all', '--quiet', *SERVICES], repo)
        container_ids = ids.decode('ascii', errors='replace').split()
        if code != 0:
            check('runtime', 'unavailable', error)
        elif not container_ids:
            check('runtime', 'unavailable', 'no matching existing containers')
        elif len(container_ids) != len(SERVICES) or not all(
                re.fullmatch(r'[0-9a-f]{12,64}', item) for item in container_ids):
            check('runtime', 'fail', 'unexpected existing container set')
        else:
            code, selected, error = _run(['docker', 'inspect', '--format', INSPECT_FORMAT,
                                         *container_ids], repo)
            if code != 0:
                check('runtime', 'unavailable', error)
            else:
                try:
                    rows = [json.loads(line) for line in selected.splitlines()]
                    healthy = (len(rows) == len(SERVICES)
                               and {row['service'] for row in rows} == set(SERVICES)
                               and all(row['project'] == 'inception' and row['status'] == 'running'
                                       and (row['health'] == 'healthy' if row['service'] != 'nginx'
                                            else row['health'] in (None, 'healthy')) for row in rows))
                except (ValueError, TypeError, KeyError):
                    healthy = False
                check('runtime', 'pass' if healthy else 'fail',
                      'all requested services running with expected project labels and health'
                      if healthy else 'missing service, wrong project, stopped, unhealthy, or invalid observation')
    after_sha, after_dirty = identity()
    check('source_unchanged', 'pass' if (after_sha, after_dirty) == (actual_sha, dirty)
          and after_dirty is False else 'fail',
          'HEAD and clean tracked state unchanged during checks'
          if (after_sha, after_dirty) == (actual_sha, dirty) and after_dirty is False
          else 'source changed or tracked state could not be verified')
    report = Report(request.expected_sha.lower(), actual_sha, dirty, tuple(checks))
    document = asdict(report)
    document.update(passed=report.passed, requested={
        'source': True, 'compose_config': request.validate_compose,
        'runtime': request.observe_runtime},
        image_source_correspondence='unverified', restart_persistence='unverified')
    temporary = destination / 'result.json.tmp'
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=2)
        stream.write('\n')
    temporary.rename(destination / 'result.json')
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--output', required=True, type=Path,
                        help='new directory outside the repository; parent must exist')
    parser.add_argument('--validate-compose', action='store_true')
    parser.add_argument('--observe-runtime', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = verify(Request(**vars(args)))
    except (OSError, ValueError):
        print('Verification rejected. Check repository, full SHA, and new external output directory.')
        return 2
    for check in report.checks:
        print(f'{check.status} {check.name}. {check.reason}.')
    print('Image-source correspondence and restart persistence remain unverified.')
    return 0 if report.passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
