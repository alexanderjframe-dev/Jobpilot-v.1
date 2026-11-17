"""Security regression tests for optional hosted deployment."""
import base64
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mobile_security import install_security


class MobileSecurityTests(unittest.TestCase):
    def test_requires_strong_password_when_hosted(self):
        with patch.dict(os.environ, {'JOBPILOT_HOSTED': '1', 'JOBPILOT_ACCESS_PASSWORD': 'short'}):
            with self.assertRaises(RuntimeError):
                install_security(FastAPI())

    def test_render_hosting_requires_password_even_without_manual_flag(self):
        with patch.dict(os.environ, {
            'RENDER': 'true',
            'JOBPILOT_HOSTED': '0',
            'JOBPILOT_ACCESS_PASSWORD': ''
        }):
            with self.assertRaises(RuntimeError):
                install_security(FastAPI())

    def test_hosted_auth_and_cross_site_protection(self):
        with patch.dict(os.environ, {'JOBPILOT_HOSTED': '1', 'JOBPILOT_ACCESS_PASSWORD': 'long-password-here-1234'}):
            app = FastAPI()
            install_security(app)

            @app.get('/private')
            def private():
                return {'secret': True}

            @app.post('/private')
            def update():
                return {'ok': True}

            client = TestClient(app)
            self.assertEqual(client.get('/private').status_code, 401)
            auth = 'Basic ' + base64.b64encode(b'jobpilot:long-password-here-1234').decode()
            self.assertEqual(client.get('/private', headers={'Authorization': auth}).status_code, 200)
            self.assertEqual(client.post('/private', headers={'Authorization': auth, 'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/private', headers={'Authorization': auth, 'Origin': 'https://testserver'}).status_code, 200)
            self.assertEqual(client.get('/private', headers={'Authorization': auth}).headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
