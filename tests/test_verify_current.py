import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / 'scripts/verify-current.py'
FIXTURE_FILES = {
    'Makefile': 'all:\n\t@false\n',
    'README.md': '# Fixture\n',
    'USER_DOC.md': '# Users\n',
    'DEV_DOC.md': '# Developers\n',
    'srcs/.env': 'DOMAIN_NAME=fixture.invalid\n',
    'srcs/requirements/mariadb/conf/99-inception.cnf': '[mysqld]\n',
    'srcs/requirements/wordpress/conf/www.conf': '[www]\n',
    'srcs/requirements/nginx/conf/nginx.conf': 'events {}\n',
    'srcs/docker-compose.yml': 'name: inception\nservices: {}\n',
    'srcs/requirements/mariadb/Dockerfile': 'FROM scratch\n',
    'srcs/requirements/wordpress/Dockerfile': 'FROM scratch\n',
    'srcs/requirements/nginx/Dockerfile': 'FROM scratch\n',
    'srcs/requirements/mariadb/tools/entrypoint.sh': '#!/bin/sh\nexit 0\n',
    'srcs/requirements/wordpress/tools/entrypoint.sh': '#!/bin/sh\nexit 0\n',
}
FAKE_DOCKER = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['DOCKER_LOG'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
mode = os.environ.get('DOCKER_MODE', 'healthy')
if mode == 'timeout':
    Path(os.environ['DOCKER_PID']).write_text(str(os.getpid()))
    time.sleep(30)
if mode == 'overflow':
    print('sensitive-output-' * 10000)
    sys.exit(0)
if mode == 'mutate-source':
    Path(os.environ['SOURCE_FILE']).write_text('changed during observation')
if args[0] == 'compose' and args[-2:] == ['config', '--quiet']:
    if mode == 'invalid':
        print('secret-fixture-value', file=sys.stderr)
        sys.exit(3)
    sys.exit(0)
if args[0] == 'compose' and args[-6:] == ['ps', '--all', '--quiet', 'mariadb', 'wordpress', 'nginx']:
    if mode != 'absent':
        print('a' * 64, 'b' * 64, 'c' * 64, sep='\\n')
    sys.exit(0)
if args[:2] == ['inspect', '--format']:
    if '.Config.Env' in args[2] or '{{json .}}' in args[2]:
        sys.exit(90)
    for service in ('mariadb', 'wordpress', 'nginx'):
        print(json.dumps({'project': 'other' if mode == 'wrong-project' else 'inception',
                          'service': service,
                          'status': 'exited' if mode == 'stopped' else 'running',
                          'health': None if service == 'nginx' else
                                    'unhealthy' if mode == 'unhealthy' else 'healthy'}))
    sys.exit(0)
sys.exit(91)
'''


class VerifyCurrentCLI(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='inception verify ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'clone with spaces'
        self.repo.mkdir()
        for name, contents in FIXTURE_FILES.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.commit()
        self.output = self.root / 'new evidence'
        self.log = self.root / 'docker.log'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for executable in ('git', 'sh'):
            (self.bin / executable).symlink_to(shutil.which(executable))
        (self.bin / 'python3').symlink_to(sys.executable)
        docker = self.bin / 'docker'
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        self.environment = dict(os.environ, PATH=str(self.bin),
                                DOCKER_LOG=str(self.log), DOCKER_PID=str(self.root / 'docker.pid'),
                                SOURCE_FILE=str(self.repo / 'README.md'))

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null',
                                        '-c', 'core.excludesFile=/dev/null', *args], cwd=self.repo).decode().strip()

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'Fixture')
        self.sha = self.git('rev-parse', 'HEAD')

    def run_cli(self, *options, expected=None, repo=None, output=None, mode='healthy'):
        result = subprocess.run(
            [sys.executable, str(CLI), '--repo', str(repo or self.repo),
             '--expected-sha', self.sha if expected is None else expected,
             '--output', str(output or self.output), *options],
            cwd=self.root, env=dict(self.environment, DOCKER_MODE=mode),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        self.assertEqual(result.stderr, '')
        return result

    def report(self, output=None):
        return json.loads(((output or self.output) / 'result.json').read_text())

    def check_status(self, name, status):
        checks = {check['name']: check for check in self.report()['checks']}
        self.assertEqual(checks[name]['status'], status)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_source_from_other_directory_with_spaces_preserves_untracked_evidence(self):
        for name in ('output/prior.txt', '.audit/prior.txt'):
            path = self.repo / name
            path.parent.mkdir()
            path.write_bytes(b'old evidence\x00')
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.report()['passed'])
        self.assertEqual(self.report()['expected_sha'], self.sha)
        self.assertEqual(self.report()['image_source_correspondence'], 'unverified')
        self.check_status('runtime', 'not_requested')
        self.assertFalse(self.log.exists())
        for name in ('output/prior.txt', '.audit/prior.txt'):
            self.assertEqual((self.repo / name).read_bytes(), b'old evidence\x00')

    def test_source_succeeds_without_docker(self):
        (self.bin / 'docker').unlink()
        self.assertEqual(self.run_cli().returncode, 0)

    def test_wrong_sha_fails_and_blocks_optional_observation(self):
        self.assertEqual(self.run_cli('--observe-runtime', expected='0' * 40).returncode, 1)
        self.check_status('source_identity', 'fail')
        self.check_status('runtime', 'unavailable')
        self.assertFalse(self.log.exists())

    def test_missing_arguments_rejected_without_invoking_tools(self):
        result = subprocess.run([sys.executable, str(CLI)], cwd=self.root,
                                env=self.environment, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.log.exists())

    def test_invalid_sha_rejected_without_output(self):
        self.assertEqual(self.run_cli(expected='HEAD').returncode, 2)
        self.assertFalse(self.output.exists())

    def test_subdirectory_is_not_actual_git_root(self):
        self.assertEqual(self.run_cli(repo=self.repo / 'srcs').returncode, 2)
        self.assertFalse(self.output.exists())

    def test_non_repository_rejected(self):
        self.assertEqual(self.run_cli(repo=self.root).returncode, 2)
        self.assertFalse(self.output.exists())

    def test_dirty_worktree_fails(self):
        (self.repo / 'README.md').write_text('edited\n')
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertTrue(self.report()['tracked_dirty'])

    def test_configured_clean_filter_is_not_executed(self):
        (self.repo / '.gitattributes').write_text('README.md filter=unsafe\n')
        self.commit()
        marker = self.root / 'filter-executed'
        self.git('config', 'filter.unsafe.clean', 'touch "' + str(marker) + '"')
        self.git('config', 'filter.unsafe.required', 'true')
        (self.repo / 'README.md').write_text('dirty enough to invoke a clean filter\n')
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertFalse(marker.exists())

    def test_staged_change_with_restored_worktree_fails(self):
        path = self.repo / 'README.md'
        path.write_text('staged\n')
        self.git('add', 'README.md')
        path.write_text(FIXTURE_FILES['README.md'])
        self.assertEqual(self.run_cli().returncode, 1)
        self.assertTrue(self.report()['tracked_dirty'])

    def test_missing_required_file_fails(self):
        (self.repo / 'Makefile').unlink()
        self.commit()
        self.assertEqual(self.run_cli().returncode, 1)
        self.check_status('file:Makefile', 'fail')

    def test_invalid_shell_fails_without_executing_entrypoint(self):
        marker = self.root / 'must not execute'
        path = self.repo / 'srcs/requirements/wordpress/tools/entrypoint.sh'
        path.write_text('touch "' + str(marker) + '"\nif then\n')
        self.commit()
        self.assertEqual(self.run_cli().returncode, 1)
        self.check_status('shell_syntax:wordpress', 'fail')
        self.assertFalse(marker.exists())

    def test_tracked_secrets_fail_without_content_disclosure(self):
        path = self.repo / 'secrets/password.txt'
        path.parent.mkdir()
        path.write_text('secret-fixture-value')
        self.commit()
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.check_status('tracked_secrets', 'fail')
        self.assertNotIn('secret-fixture-value', result.stdout + (self.output / 'result.json').read_text())

    def test_symlinked_source_rejected(self):
        path = self.repo / 'Makefile'
        path.unlink()
        path.symlink_to(self.repo / 'README.md')
        self.commit()
        self.assertEqual(self.run_cli().returncode, 1)
        self.check_status('file:Makefile', 'fail')

    def test_existing_output_is_unchanged(self):
        self.output.mkdir()
        previous = self.output / 'result.json'
        previous.write_bytes(b'prior evidence\x00')
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(previous.read_bytes(), b'prior evidence\x00')

    def test_output_inside_repo_and_symlink_escape_rejected(self):
        link = self.root / 'link to clone'
        link.symlink_to(self.repo, target_is_directory=True)
        for output in (self.repo / 'new', link / 'new'):
            with self.subTest(output=output):
                self.assertEqual(self.run_cli(output=output).returncode, 2)
                self.assertFalse((self.repo / 'new').exists())

    def test_dangling_output_symlink_is_unchanged(self):
        self.output.symlink_to(self.root / 'missing')
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertTrue(self.output.is_symlink())

    def test_compose_config_uses_quiet_only(self):
        result = self.run_cli('--validate-compose')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.check_status('compose_config', 'pass')
        self.assertEqual(self.commands(), [['compose', '--project-name', 'inception', '-f',
                                          str(self.repo / 'srcs/docker-compose.yml'), 'config', '--quiet']])

    def test_invalid_compose_suppresses_raw_diagnostics(self):
        result = self.run_cli('--validate-compose', mode='invalid')
        self.assertEqual(result.returncode, 1)
        self.check_status('compose_config', 'fail')
        self.assertNotIn('secret-fixture-value', result.stdout + (self.output / 'result.json').read_text())

    def test_explicit_docker_request_without_docker_fails(self):
        (self.bin / 'docker').unlink()
        self.assertEqual(self.run_cli('--validate-compose', '--observe-runtime').returncode, 1)
        self.check_status('compose_config', 'unavailable')
        self.check_status('runtime', 'unavailable')

    def test_existing_healthy_runtime_observes_selected_fields_only(self):
        result = self.run_cli('--observe-runtime')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.check_status('runtime', 'pass')
        commands = self.commands()
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][-6:], ['ps', '--all', '--quiet', 'mariadb', 'wordpress', 'nginx'])
        self.assertEqual(commands[1][:2], ['inspect', '--format'])
        self.assertNotIn('.Config.Env', commands[1][2])
        self.assertEqual(self.report()['restart_persistence'], 'unverified')

    def test_absent_unhealthy_stopped_and_other_project_fail(self):
        for mode, status in [('absent', 'unavailable'), ('unhealthy', 'fail'),
                             ('stopped', 'fail'), ('wrong-project', 'fail')]:
            with self.subTest(mode=mode):
                self.output = self.root / ('result-' + mode)
                self.assertEqual(self.run_cli('--observe-runtime', mode=mode).returncode, 1)
                self.check_status('runtime', status)
        self.assertTrue(all(command[0] in ('compose', 'inspect') for command in self.commands()))

    def test_changes_during_check_fail_final_identity(self):
        self.assertEqual(self.run_cli('--validate-compose', mode='mutate-source').returncode, 1)
        self.check_status('source_unchanged', 'fail')

    def test_excessive_output_fails_without_disclosure(self):
        result = self.run_cli('--validate-compose', mode='overflow')
        self.assertEqual(result.returncode, 1)
        self.check_status('compose_config', 'unavailable')
        self.assertNotIn('sensitive-output', result.stdout + (self.output / 'result.json').read_text())

    def test_hanging_command_is_killed(self):
        result = self.run_cli('--validate-compose', mode='timeout')
        self.assertEqual(result.returncode, 1)
        self.check_status('compose_config', 'unavailable')
        self.assertIn('timed out', result.stdout)
        pid = int((self.root / 'docker.pid').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == '__main__':
    unittest.main()
