import hashlib
import json
import threading
from pathlib import Path


class JsonCache:
    """One JSON file per key. Re-runs read from disk instead of calling an API again."""

    def __init__(self, root: Path | None, read_only: bool = False):
        self.root = Path(root) if root else None
        self.read_only = read_only
        self._lock = threading.Lock()

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str):
        if not self.root:
            return None
        path = self._path(namespace, key)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def put(self, namespace: str, key: str, value) -> None:
        if not self.root or self.read_only:
            return
        path = self._path(namespace, key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
