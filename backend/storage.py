import os
import mimetypes
import uuid
import logging
from typing import Optional, Tuple
from supabase import create_client, Client

logger = logging.getLogger("chennalink.storage")

class StorageService:
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        from backend.config import settings
        self.settings = settings
        self.bucket_name = bucket_name or settings.supabase_storage_bucket
        self.client: Optional[Client] = None
        self.local_storage_dir = os.path.join(os.path.dirname(__file__), "storage_local")
        
        # Load from environment or settings
        url = supabase_url or settings.supabase_url or os.environ.get("SUPABASE_URL")
        key = (
            supabase_key 
            or settings.supabase_service_role_key 
            or settings.supabase_anon_key 
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") 
            or os.environ.get("SUPABASE_ANON_KEY")
        )
        
        is_prod = settings.is_production() or settings.storage_backend == "supabase"
        
        if url and key and key not in ["dummy", ""]:
            try:
                self.client = create_client(url, key)
                logger.info(f"Initialized Supabase Storage client for bucket '{self.bucket_name}'")
            except Exception as e:
                logger.error(f"Could not connect to Supabase Storage: {e}")
                if is_prod and not settings.allow_local_fallback:
                    raise RuntimeError(
                        f"Production storage initialization failed: Could not connect to Supabase Storage ({e}). "
                        "Local storage fallback is strictly prohibited in production."
                    )
        else:
            if is_prod and not settings.allow_local_fallback:
                raise RuntimeError(
                    "PRODUCTION STORAGE ERROR: Missing SUPABASE_URL or Supabase credentials for private bucket 'chennalink-files'. "
                    "Local storage fallback is strictly prohibited in production."
                )

    def upload_file(
        self,
        session_id: str,
        filename: str,
        data: bytes,
        content_type: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Uploads file to private Supabase Storage bucket.
        Guarantees exact byte preservation and unique safe path.
        Returns (storage_path, storage_bucket).
        """
        # Sanitize filename and create unique, safe object path (prevent path traversal)
        safe_name = os.path.basename(filename).replace(" ", "_").replace("/", "_").replace("\\", "_")
        unique_prefix = uuid.uuid4().hex[:12]
        storage_path = f"{session_id}/{unique_prefix}_{safe_name}"
        
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        if self.client:
            try:
                # Upload directly to private Supabase bucket
                self.client.storage.from_(self.bucket_name).upload(
                    path=storage_path,
                    file=data,
                    file_options={"content-type": content_type}
                )
                logger.info(f"Uploaded {len(data)} bytes to Supabase Storage: {self.bucket_name}/{storage_path}")
                return storage_path, self.bucket_name
            except Exception as e:
                logger.error(f"Supabase Storage upload failed: {e}")
                if self.settings.is_production() or not self.settings.allow_local_fallback:
                    raise RuntimeError(
                        f"Supabase Storage upload failed for {self.bucket_name}/{storage_path}: {e}. "
                        "Local disk fallback is strictly prohibited in production."
                    )
        else:
            if self.settings.is_production() or not self.settings.allow_local_fallback:
                raise RuntimeError(
                    "Production storage error: Supabase Storage client is not connected. "
                    "Cannot persist file to storage."
                )

        # Fallback local store ONLY in non-production test/dev mode when explicitly permitted
        logger.warning(f"Non-production fallback: Saving {len(data)} bytes to local disk: {storage_path}")
        target_dir = os.path.join(self.local_storage_dir, session_id)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, f"{unique_prefix}_{safe_name}")
        with open(file_path, "wb") as f:
            f.write(data)
        return storage_path, self.bucket_name

    def download_file(self, storage_path: str) -> bytes:
        """
        Downloads exact file bytes from storage.
        """
        if self.client:
            try:
                data = self.client.storage.from_(self.bucket_name).download(storage_path)
                return data
            except Exception as e:
                logger.error(f"Supabase download failed for {storage_path}: {e}")
                if self.settings.is_production() or not self.settings.allow_local_fallback:
                    raise RuntimeError(f"Failed to download file from Supabase Storage: {e}")

        # Local fallback only in non-production when allowed
        if not self.settings.allow_local_fallback and self.settings.is_production():
            raise RuntimeError(f"Production storage error: File not found in Supabase Storage: {storage_path}")

        # Check local fallback
        parts = storage_path.split("/")
        if len(parts) >= 2:
            session_id, fname = parts[0], parts[1]
            local_path = os.path.join(self.local_storage_dir, session_id, fname)
            if os.path.isfile(local_path):
                with open(local_path, "rb") as f:
                    return f.read()

        raise FileNotFoundError(f"File not found in storage: {storage_path}")

    def create_signed_url(self, storage_path: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generates short-lived signed URL for private bucket access.
        """
        if self.client:
            try:
                res = self.client.storage.from_(self.bucket_name).create_signed_url(
                    path=storage_path,
                    expires_in=expires_in
                )
                if isinstance(res, dict) and "signedURL" in res:
                    return res["signedURL"]
            except Exception as e:
                logger.warning(f"Failed to generate signed URL from Supabase: {e}")

        # Backend proxy endpoint fallback
        return f"/api/files/download/{storage_path}"


_storage_instance: Optional[StorageService] = None

def get_storage_service() -> StorageService:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageService()
    return _storage_instance

def reset_storage_service() -> None:
    global _storage_instance
    _storage_instance = None
