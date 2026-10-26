import os
import sys
import tempfile
import unittest
import json
from email import message_from_string
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from werkzeug.security import check_password_hash, generate_password_hash

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR / 'src'))

import database
import fake_shell
import honeypot
import paths
import web_app


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        data_dir = Path(self.temp_dir.name)

        self.db_path_patcher = patch.object(
            database,
            'DB_PATH',
            str(data_dir / 'honeypot.db')
        )
        self.archive_path_patcher = patch.object(
            database,
            'ARCHIVE_PATH',
            str(data_dir / 'archive.db')
        )
        self.db_path_patcher.start()
        self.archive_path_patcher.start()
        self.addCleanup(self.db_path_patcher.stop)
        self.addCleanup(self.archive_path_patcher.stop)
        self.auth_path_patcher = patch.object(
            web_app,
            'AUTH_CONFIG_PATH',
            str(data_dir / 'auth.json')
        )
        self.auth_path_patcher.start()
        self.addCleanup(self.auth_path_patcher.stop)
        self.auth_config_patcher = patch.multiple(
            web_app,
            JWT_SECRET_KEY='test-only-jwt-secret-that-is-at-least-32-bytes',
            ADMIN_USERNAME='admin',
            ADMIN_PASSWORD_HASH=generate_password_hash('test-password'),
            ALLOWED_ORIGINS=['http://localhost:5173']
        )
        self.auth_config_patcher.start()
        self.addCleanup(self.auth_config_patcher.stop)
        database.init_db()

    def login(self, client):
        return client.post(
            '/api/login',
            json={'username': 'admin', 'password': 'test-password'},
            headers={'Origin': 'http://localhost:5173'}
        )

    def test_api_requires_authentication_and_login_sets_http_only_cookie(self):
        client = web_app.app.test_client()

        unauthenticated_response = client.get('/api/attacks')
        self.assertEqual(unauthenticated_response.status_code, 401)
        unauthenticated_write_response = client.post(
            '/api/honeypots',
            json={'port': 23456},
            headers={'Origin': 'http://localhost:5173'}
        )
        self.assertEqual(unauthenticated_write_response.status_code, 401)

        login_response = self.login(client)
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.get_json(), {'username': 'admin'})
        self.assertIn('HttpOnly', login_response.headers['Set-Cookie'])

        session_response = client.get('/api/session')
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.get_json(), {'username': 'admin'})
        self.assertEqual(client.get('/api/attacks').status_code, 200)

        logout_response = client.post(
            '/api/logout',
            headers={'Origin': 'http://localhost:5173'}
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(client.get('/api/attacks').status_code, 401)

    def test_api_fails_closed_when_authentication_is_not_configured(self):
        client = web_app.app.test_client()
        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            login_response = self.login(client)
            protected_response = client.get('/api/attacks')

        self.assertEqual(login_response.status_code, 503)
        self.assertEqual(protected_response.status_code, 503)

    def test_first_admin_setup_is_persistent_and_one_time(self):
        client = web_app.app.test_client()
        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            status_response = client.get('/api/auth-status')
            self.assertEqual(status_response.get_json(), {'setup_required': True})

            setup_response = client.post(
                '/api/setup',
                json={
                    'username': 'new-admin',
                    'password': 'a-secure-password',
                    'email': 'new-admin@example.com'
                },
                headers={'Origin': 'http://localhost:5173'}
            )
            self.assertEqual(setup_response.status_code, 201)
            self.assertIn('HttpOnly', setup_response.headers['Set-Cookie'])
            stored_config = json.loads(
                Path(web_app.AUTH_CONFIG_PATH).read_text(encoding='utf-8')
            )
            self.assertEqual(stored_config['admin_username'], 'new-admin')
            self.assertEqual(stored_config['admin_email'], 'new-admin@example.com')
            self.assertNotEqual(stored_config['admin_password_hash'], 'a-secure-password')
            self.assertGreaterEqual(len(stored_config['jwt_secret']), 32)
            self.assertEqual(
                client.get('/api/session').get_json(),
                {'username': 'new-admin'}
            )

            login_response = client.post(
                '/api/login',
                json={'username': 'new-admin', 'password': 'a-secure-password'},
                headers={'Origin': 'http://localhost:5173'}
            )
            self.assertEqual(login_response.status_code, 200)

            duplicate_setup_response = client.post(
                '/api/setup',
                json={'username': 'attacker', 'password': 'another-secure-password'},
                headers={'Origin': 'http://localhost:5173'}
            )

        self.assertEqual(duplicate_setup_response.status_code, 409)

    def test_api_rejects_untrusted_origins(self):
        client = web_app.app.test_client()
        response = client.post(
            '/api/login',
            json={'username': 'admin', 'password': 'test-password'},
            headers={'Origin': 'https://attacker.example'}
        )
        self.assertEqual(response.status_code, 403)

    def test_api_requires_trusted_origin_for_cookie_authenticated_writes(self):
        client = web_app.app.test_client()
        self.login(client)

        missing_origin_response = client.post('/api/ban', json={'ip': '192.0.2.10'})
        self.assertEqual(missing_origin_response.status_code, 403)

        trusted_origin_response = client.post(
            '/api/ban',
            json={'ip': 'invalid-ip'},
            headers={'Origin': 'http://localhost:5173'}
        )
        self.assertEqual(trusted_origin_response.status_code, 400)

    def test_listener_and_api_share_one_port_configuration(self):
        expected_path = (SERVER_DIR / 'data' / 'config.json').resolve()
        self.assertEqual(Path(paths.CONFIG_PATH), expected_path)

        test_config = Path(self.temp_dir.name) / 'config.json'
        with patch.object(honeypot, 'CONFIG_PATH', str(test_config)):
            with patch.object(web_app, 'CONFIG_PATH', str(test_config)):
                web_app.save_configured_port(23456)

                self.assertEqual(web_app.get_current_port(), 23456)
                self.assertEqual(honeypot.get_configured_port(), 23456)

    def test_api_paginates_records_and_rejects_invalid_limits(self):
        with database._connect() as conn:
            conn.executemany(
                '''
                INSERT INTO attacks
                    (timestamp, ip_address, username, password, country, port)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                [
                    (
                        '2026-10-15T12:00:00Z',
                        f'192.0.2.{index % 255}',
                        'test-user',
                        'test-password',
                        None,
                        2222,
                    )
                    for index in range(503)
                ],
            )

        client = web_app.app.test_client()
        self.login(client)
        first_page_response = client.get('/api/attacks?limit=500')
        self.assertEqual(first_page_response.status_code, 200)
        first_page = first_page_response.get_json()
        self.assertEqual(len(first_page), 500)

        oldest_id = min(record['id'] for record in first_page)
        second_page_response = client.get(
            f'/api/attacks?before_id={oldest_id}&limit=500'
        )
        self.assertEqual(second_page_response.status_code, 200)
        second_page = second_page_response.get_json()
        self.assertEqual(len(second_page), 3)
        self.assertFalse(
            {record['id'] for record in first_page}
            & {record['id'] for record in second_page}
        )

        invalid_limit_response = client.get('/api/attacks?limit=0')
        self.assertEqual(invalid_limit_response.status_code, 400)

    def test_dashboard_data_routes_return_paginated_lists_and_port_filter(self):
        attack_2222 = database.log_attack(
            '192.0.2.10', 'user-a', 'pass-a', None, port=2222
        )
        attack_2223 = database.log_attack(
            '192.0.2.11', 'user-b', 'pass-b', None, port=2223
        )
        database.log_command(
            '192.0.2.10', 'whoami', '/root', 'root', port=2222
        )
        database.update_attack_country(attack_2222, 'Example')

        client = web_app.app.test_client()
        self.login(client)

        attacks_response = client.get('/api/attacks?port=2223&limit=1')
        self.assertEqual(attacks_response.status_code, 200)
        self.assertEqual(
            [attack['id'] for attack in attacks_response.get_json()],
            [attack_2223]
        )
        commands_response = client.get('/api/commands?limit=1')
        self.assertEqual(commands_response.status_code, 200)
        self.assertEqual(len(commands_response.get_json()), 1)
        latest_update_response = client.get('/api/country-updates/latest')
        self.assertEqual(latest_update_response.status_code, 200)
        latest_update_id = latest_update_response.get_json()['id']
        updates_response = client.get('/api/country-updates?after_id=0&limit=1')
        self.assertEqual(updates_response.status_code, 200)
        self.assertEqual(updates_response.get_json()[0]['country'], 'Example')
        self.assertEqual(updates_response.get_json()[0]['id'], latest_update_id)

    def test_account_recovery_email_can_be_configured_from_authenticated_account(self):
        Path(web_app.AUTH_CONFIG_PATH).write_text(
            json.dumps({
                'jwt_secret': 'a-test-signing-secret-that-is-at-least-32-bytes',
                'admin_username': 'admin',
                'admin_password_hash': generate_password_hash('test-password')
            }),
            encoding='utf-8'
        )
        client = web_app.app.test_client()
        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            login_response = self.login(client)
            self.assertEqual(login_response.status_code, 200)
            response = client.patch(
                '/api/account',
                json={
                    'email': 'admin@example.com',
                    'smtp_host': 'smtp.example.com',
                    'smtp_port': '587',
                    'smtp_user': 'mailer@example.com',
                    'smtp_from': 'mailer@example.com',
                    'smtp_password': 'smtp-app-password'
                },
                headers={'Origin': 'http://localhost:5173'}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['email'], 'admin@example.com')
        self.assertTrue(response.get_json()['smtp_password_configured'])
        self.assertNotIn('smtp_password', response.get_json())
        stored_config = json.loads(
            Path(web_app.AUTH_CONFIG_PATH).read_text(encoding='utf-8')
        )
        self.assertEqual(stored_config['admin_email'], 'admin@example.com')
        self.assertEqual(stored_config['smtp_host'], 'smtp.example.com')
        self.assertEqual(stored_config['smtp_port'], 587)
        self.assertEqual(stored_config['smtp_password'], 'smtp-app-password')

    def test_password_recovery_sends_frontend_link_and_rotates_session_key(self):
        auth_path = Path(web_app.AUTH_CONFIG_PATH)
        config = {
            'jwt_secret': 'a-test-signing-secret-that-is-at-least-32-bytes',
            'admin_username': 'admin',
            'admin_password_hash': generate_password_hash('old-password'),
            'admin_email': 'admin@example.com'
        }
        auth_path.write_text(json.dumps(config), encoding='utf-8')
        client = web_app.app.test_client()
        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            with patch.dict(os.environ, {
                'HONEYPOT_SMTP_HOST': 'smtp.example.com',
                'HONEYPOT_SMTP_PORT': '587',
                'HONEYPOT_SMTP_USERNAME': 'mailer@example.com',
                'HONEYPOT_SMTP_PASSWORD': 'test-smtp-password',
                'HONEYPOT_SMTP_FROM': 'mailer@example.com'
            }):
                self.assertEqual(
                    client.post(
                        '/api/login',
                        json={'username': 'admin', 'password': 'old-password'},
                        headers={'Origin': 'http://localhost:5173'}
                    ).status_code,
                    200
                )
                with patch('web_app.smtplib.SMTP') as smtp_factory:
                    smtp_server = smtp_factory.return_value.__enter__.return_value
                    forgot_response = client.post(
                        '/api/auth/forgot-password',
                        json={'username': 'admin'},
                        headers={'Origin': 'http://localhost:5173'}
                    )

                self.assertEqual(forgot_response.status_code, 200)
                self.assertEqual(
                    smtp_server.sendmail.call_args.args[1],
                    'admin@example.com'
                )
                sent_message = message_from_string(
                    smtp_server.sendmail.call_args.args[2]
                )
                message_body = sent_message.get_payload()[0].get_payload(
                    decode=True
                ).decode()
                reset_url = next(
                    line for line in message_body.splitlines()
                    if 'token=' in line
                )
                parsed_reset_url = urlparse(reset_url)
                self.assertEqual(
                    f'{parsed_reset_url.scheme}://{parsed_reset_url.netloc}',
                    'http://localhost:5173'
                )
                token = parse_qs(parsed_reset_url.query)['token'][0]
                with database._connect() as connection:
                    stored_token = connection.execute(
                        'SELECT token FROM password_resets'
                    ).fetchone()[0]
                self.assertNotEqual(stored_token, token)

                reset_response = client.post(
                    '/api/auth/reset-password',
                    json={'token': token, 'password': 'new-secure-password'},
                    headers={'Origin': 'http://localhost:5173'}
                )
                self.assertEqual(reset_response.status_code, 200)
                self.assertEqual(client.get('/api/attacks').status_code, 401)
                self.assertEqual(
                    client.post(
                        '/api/auth/reset-password',
                        json={'token': token, 'password': 'another-password'},
                        headers={'Origin': 'http://localhost:5173'}
                    ).status_code,
                    400
                )

                updated_config = json.loads(auth_path.read_text(encoding='utf-8'))
                self.assertNotEqual(updated_config['jwt_secret'], config['jwt_secret'])
                self.assertTrue(
                    check_password_hash(
                        updated_config['admin_password_hash'],
                        'new-secure-password'
                    )
                )
                self.assertEqual(
                    client.post(
                        '/api/login',
                        json={
                            'username': 'admin',
                            'password': 'new-secure-password'
                        },
                        headers={'Origin': 'http://localhost:5173'}
                    ).status_code,
                    200
                )

    def test_password_recovery_uses_smtp_settings_saved_in_account_page(self):
        auth_path = Path(web_app.AUTH_CONFIG_PATH)
        auth_path.write_text(json.dumps({
            'jwt_secret': 'a-test-signing-secret-that-is-at-least-32-bytes',
            'admin_username': 'admin',
            'admin_password_hash': generate_password_hash('old-password'),
            'admin_email': 'admin@example.com',
            'smtp_host': 'smtp.example.com',
            'smtp_port': 587,
            'smtp_user': 'mailer@example.com',
            'smtp_from': 'mailer@example.com',
            'smtp_password': 'saved-app-password'
        }), encoding='utf-8')
        client = web_app.app.test_client()

        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            with patch.dict(os.environ, {}, clear=True):
                with patch('web_app.smtplib.SMTP') as smtp_factory:
                    response = client.post(
                        '/api/auth/forgot-password',
                        json={'username': 'admin'},
                        headers={'Origin': 'http://localhost:5173'}
                    )

        self.assertEqual(response.status_code, 200)
        smtp_server = smtp_factory.return_value.__enter__.return_value
        smtp_server.login.assert_called_once_with(
            'mailer@example.com',
            'saved-app-password'
        )

    def test_password_recovery_rejects_untrusted_origins_and_missing_mail_setup(self):
        client = web_app.app.test_client()
        untrusted_response = client.post(
            '/api/auth/forgot-password',
            json={'username': 'admin'},
            headers={'Origin': 'https://attacker.example'}
        )
        self.assertEqual(untrusted_response.status_code, 403)

        missing_mail_response = client.post(
            '/api/auth/forgot-password',
            json={'username': 'admin'},
            headers={'Origin': 'http://localhost:5173'}
        )
        self.assertEqual(missing_mail_response.status_code, 503)

    def test_password_recovery_uses_username_and_does_not_reveal_unknown_users(self):
        auth_path = Path(web_app.AUTH_CONFIG_PATH)
        auth_path.write_text(json.dumps({
            'jwt_secret': 'a-test-signing-secret-that-is-at-least-32-bytes',
            'admin_username': 'admin',
            'admin_password_hash': generate_password_hash('old-password'),
            'admin_email': 'admin@example.com'
        }), encoding='utf-8')
        client = web_app.app.test_client()

        with patch.multiple(
            web_app,
            JWT_SECRET_KEY='',
            ADMIN_USERNAME='',
            ADMIN_PASSWORD_HASH=''
        ):
            with patch.dict(os.environ, {
                'HONEYPOT_SMTP_HOST': 'smtp.example.com',
                'HONEYPOT_SMTP_PORT': '587',
                'HONEYPOT_SMTP_USERNAME': 'mailer@example.com',
                'HONEYPOT_SMTP_PASSWORD': 'test-smtp-password',
                'HONEYPOT_SMTP_FROM': 'mailer@example.com'
            }):
                response = client.post(
                    '/api/auth/forgot-password',
                    json={'username': 'unknown-user'},
                    headers={'Origin': 'http://localhost:5173'}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()['message'],
            'Si un compte est associé à cet identifiant, un lien de réinitialisation a été envoyé.'
        )
        with database._connect() as connection:
            self.assertEqual(
                connection.execute('SELECT COUNT(*) FROM password_resets').fetchone()[0],
                0
            )

    def test_archiving_moves_all_old_records_and_removes_country_updates(self):
        with database._connect() as conn:
            conn.executemany(
                '''
                INSERT INTO attacks
                    (timestamp, ip_address, username, password, country, port)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                [
                    ('2000-01-01T00:00:00Z', '192.0.2.1', 'user', 'pass', None, 2222)
                    for _ in range(501)
                ],
            )
            conn.executemany(
                '''
                INSERT INTO commands
                    (timestamp, ip_address, command, current_dir, response, port)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                [
                    (
                        '2000-01-01T00:00:00Z',
                        '192.0.2.1',
                        'whoami',
                        '/root',
                        'root\\r\\n',
                        2222,
                    )
                    for _ in range(501)
                ],
            )
            conn.execute(
                'INSERT INTO attack_country_updates (attack_id, country) VALUES (1, ?)',
                ('Example',),
            )

        database.archive_old_data(days=30)

        with database._connect() as conn:
            self.assertEqual(
                conn.execute('SELECT COUNT(*) FROM attacks').fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute('SELECT COUNT(*) FROM commands').fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    'SELECT COUNT(*) FROM attack_country_updates'
                ).fetchone()[0],
                0,
            )

        with database._connect(database.ARCHIVE_PATH) as conn:
            self.assertEqual(
                conn.execute('SELECT COUNT(*) FROM attacks').fetchone()[0],
                501,
            )
            self.assertEqual(
                conn.execute('SELECT COUNT(*) FROM commands').fetchone()[0],
                501,
            )

    def test_fake_shell_rejects_oversized_input_and_keeps_serving(self):
        class TestChannel:
            def __init__(self, data):
                self.data = data
                self.offset = 0
                self.closed = False

            def settimeout(self, timeout):
                self.timeout = timeout

            def recv(self, size):
                chunk = self.data[self.offset:self.offset + size]
                self.offset += len(chunk)
                return chunk

            def send(self, data):
                return len(data)

            def close(self):
                self.closed = True

        channel = TestChannel(
            b'x' * (fake_shell.MAX_COMMAND_LENGTH + 1) + b'\rid\r'
        )
        with patch.object(fake_shell, 'log_command') as log_command:
            with patch('builtins.print'):
                fake_shell.handle_fake_shell(channel, '192.0.2.1')

        self.assertTrue(channel.closed)
        self.assertEqual(log_command.call_count, 2)
        oversized_call, normal_call = log_command.call_args_list
        self.assertEqual(
            len(oversized_call.args[1]),
            fake_shell.MAX_COMMAND_LENGTH,
        )
        self.assertIn('exceeds', oversized_call.args[3])
        self.assertEqual(normal_call.args[1], 'id')
        self.assertIn('uid=0(root)', normal_call.args[3])


if __name__ == '__main__':
    unittest.main()
