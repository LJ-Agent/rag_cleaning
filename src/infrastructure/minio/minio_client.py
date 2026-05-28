"""MinIO object storage client — read/write for cleaned documents."""
import io
from minio import Minio
from minio.error import S3Error
from common.config_loader import get_config
from common.exception.exceptions import ResourceException
from common.util.logger import get_logger

logger = get_logger()


class MinioClient:
    """MinIO client for reading raw files and writing cleaned results."""

    def __init__(self):
        cfg = get_config()["minio"]
        self._endpoint = cfg["endpoint"]
        self._bucket = cfg["bucket_name"]
        self._output_prefix = cfg.get("output_prefix", "cleaned")
        self._client = Minio(
            endpoint=cfg["endpoint"],
            access_key=cfg["access_key"],
            secret_key=cfg["secret_key"],
            secure=cfg.get("secure", False),
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self._client.bucket_exists(self._bucket):
            raise ResourceException(f"MinIO bucket not found: {self._bucket}")

    def _strip_bucket_prefix(self, object_path: str) -> str:
        prefix = self._bucket + "/"
        if object_path.startswith(prefix):
            return object_path[len(prefix):]
        return object_path

    # ─── Read operations ───────────────────────────────────

    def get_object(self, object_path: str) -> bytes:
        """Read full object content from MinIO."""
        clean_path = self._strip_bucket_prefix(object_path)
        try:
            response = self._client.get_object(self._bucket, clean_path)
            data = response.read()
            response.close()
            response.release_conn()
            logger.info(f"MinIO read: {clean_path} ({len(data)} bytes)")
            return data
        except S3Error as e:
            raise ResourceException(f"MinIO read failed: {clean_path} — {e}")

    def get_object_stream(self, object_path: str, chunk_size: int = 8192):
        """Stream read an object, yielding chunks."""
        clean_path = self._strip_bucket_prefix(object_path)
        try:
            response = self._client.get_object(self._bucket, clean_path)
            for chunk in response.stream(chunk_size):
                yield chunk
            response.close()
            response.release_conn()
        except S3Error as e:
            raise ResourceException(f"MinIO stream failed: {clean_path} — {e}")

    def object_exists(self, object_path: str) -> bool:
        """Check if an object exists."""
        clean_path = self._strip_bucket_prefix(object_path)
        try:
            self._client.stat_object(self._bucket, clean_path)
            return True
        except S3Error:
            return False

    # ─── Write operations ──────────────────────────────────

    def put_object(self, object_path: str, data: bytes, content_type: str = "text/plain"):
        """Write object to MinIO."""
        clean_path = self._strip_bucket_prefix(object_path)
        try:
            self._client.put_object(
                self._bucket, clean_path,
                io.BytesIO(data), len(data),
                content_type=content_type,
            )
            logger.info(f"MinIO write: {clean_path} ({len(data)} bytes)")
        except S3Error as e:
            raise ResourceException(f"MinIO write failed: {clean_path} — {e}")

    def put_cleaned_markdown(self, document_id: str, tenant_id: str, content: str) -> str:
        """Write cleaned Markdown to standardized path. Returns the object path."""
        path = f"{self._output_prefix}/{tenant_id}/{document_id}.md"
        self.put_object(path, content.encode("utf-8"), "text/markdown; charset=utf-8")
        return path

    def put_metadata_json(self, document_id: str, tenant_id: str, metadata: dict) -> str:
        """Write metadata JSON to standardized path. Returns the object path."""
        import json
        path = f"{self._output_prefix}/{tenant_id}/{document_id}.json"
        data = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
        self.put_object(path, data, "application/json; charset=utf-8")
        return path

    def get_presigned_url(self, object_path: str, expires_seconds: int = 604800) -> str:
        """Generate a temporary download URL (default 7 days)."""
        clean_path = self._strip_bucket_prefix(object_path)
        try:
            return self._client.presigned_get_object(self._bucket, clean_path, expires_seconds)
        except S3Error as e:
            raise ResourceException(f"MinIO presigned URL failed: {clean_path} — {e}")

    @property
    def bucket(self) -> str:
        return self._bucket


_minio_client: MinioClient | None = None


def get_minio_client() -> MinioClient:
    global _minio_client
    if _minio_client is None:
        _minio_client = MinioClient()
    return _minio_client
