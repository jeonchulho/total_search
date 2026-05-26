import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.settings import settings


class WebhardRouterTests(unittest.TestCase):
    class _DummyPutResult:
        etag = "dummy-etag"

    class _DummyStorageClient:
        def put_object(self, **kwargs):
            return WebhardRouterTests._DummyPutResult()

    @contextmanager
    def _client(self):
        with tempfile.NamedTemporaryFile(prefix="webhard_test_", suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        original_db_path = settings.webhard_db_path
        settings.webhard_db_path = db_path

        try:
            with (
                patch("app.main.get_client", return_value=self._DummyStorageClient()),
                patch("app.main.ensure_bucket", return_value=None),
                patch("app.routers.files.get_client", return_value=self._DummyStorageClient()),
                patch("app.routers.files.ensure_bucket", return_value=None),
            ):
                with TestClient(main.app) as client:
                    yield client
        finally:
            settings.webhard_db_path = original_db_path
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_register_login_and_accessible_folders(self):
        with self._client() as client:
            register_res = client.post(
                "/nc/auth/register",
                json={"username": "alice_test", "password": "pass1234"},
            )
            self.assertEqual(register_res.status_code, 200)

            login_res = client.post(
                "/nc/auth/login",
                json={"username": "alice_test", "password": "pass1234"},
            )
            self.assertEqual(login_res.status_code, 200)
            token = login_res.json()["access_token"]

            create_folder_res = client.post(
                "/nc/folders",
                headers={"Authorization": f"Bearer {token}"},
                json={"path": "team"},
            )
            self.assertEqual(create_folder_res.status_code, 200)

            accessible_res = client.get(
                "/nc/folders/accessible",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(accessible_res.status_code, 200)
            items = accessible_res.json().get("accessible_folders", [])
            self.assertTrue(any(x["folder_path"] == "team" and x["source"] == "owned" for x in items))

    def test_shared_folder_listing_and_shared_owner_file_listing(self):
        with self._client() as client:
            alice_res = client.post(
                "/nc/auth/register",
                json={"username": "alice_shared", "password": "pass1234"},
            )
            self.assertEqual(alice_res.status_code, 200)
            alice_id = alice_res.json()["user_id"]

            bob_res = client.post(
                "/nc/auth/register",
                json={"username": "bob_shared", "password": "pass1234"},
            )
            self.assertEqual(bob_res.status_code, 200)
            bob_id = bob_res.json()["user_id"]

            alice_token = client.post(
                "/nc/auth/login",
                json={"username": "alice_shared", "password": "pass1234"},
            ).json()["access_token"]
            bob_token = client.post(
                "/nc/auth/login",
                json={"username": "bob_shared", "password": "pass1234"},
            ).json()["access_token"]

            mk_folder = client.post(
                "/nc/folders",
                headers={"Authorization": f"Bearer {alice_token}"},
                json={"path": "team"},
            )
            self.assertEqual(mk_folder.status_code, 200)

            share_res = client.post(
                "/nc/folders/team/share",
                headers={"Authorization": f"Bearer {alice_token}"},
                json={
                    "folder_path": "team",
                    "subject_type": "user",
                    "subject_id": bob_id,
                    "can_read": True,
                    "can_upload": True,
                    "can_manage": False,
                    "apply_existing_files": True,
                },
            )
            self.assertEqual(share_res.status_code, 200)

            shared_folders_res = client.get(
                "/nc/folders/shared",
                headers={"Authorization": f"Bearer {bob_token}"},
            )
            self.assertEqual(shared_folders_res.status_code, 200)
            self.assertTrue(any(x["folder_path"] == "team" for x in shared_folders_res.json().get("shared_folders", [])))

            upload_res = client.post(
                "/nc/files/upload?path=team/docs/hello.txt",
                headers={"Authorization": f"Bearer {bob_token}"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            self.assertEqual(upload_res.status_code, 200)

            list_res = client.get(
                f"/nc/files?owner_id={alice_id}&prefix=team",
                headers={"Authorization": f"Bearer {bob_token}"},
            )
            self.assertEqual(list_res.status_code, 200)
            self.assertTrue(any(x["logical_path"] == "team/docs/hello.txt" for x in list_res.json().get("files", [])))


if __name__ == "__main__":
    unittest.main()
