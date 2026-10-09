import json
import os
from pathlib import Path
from typing import List
from chennalink.models.code_file import CodeFile

import json
import os
import shutil
import asyncio
from pathlib import Path
from typing import List
from chennalink.models.code_file import CodeFile

class LocalStorage:
    def __init__(self, db_path: str = None):
        profile = os.environ.get("FLUXLINK_PROFILE") or os.environ.get("CHENNALINK_PROFILE", "default")
        if db_path is None:
            chennalink_dir = Path.home() / ".chennalink" / profile
            fluxlink_dir = Path.home() / ".fluxlink" / profile
            if chennalink_dir.exists() and not fluxlink_dir.exists():
                self.base_dir = chennalink_dir
            else:
                self.base_dir = fluxlink_dir
        else:
            self.base_dir = Path(db_path).parent
            
        self.db_path = self.base_dir / "history.json"
        self.config_path = self.base_dir / "config.json"
            
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            self._save_sync([])

    def get_device_id(self) -> str:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("device_id")
            except Exception:
                pass
        return None

    def save_device_id(self, device_id: str):
        config = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                pass
        config["device_id"] = device_id
        
        tmp_path = self.config_path.with_suffix('.tmp')
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        os.replace(tmp_path, self.config_path)

    def _load_sync(self) -> List[dict]:
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            if self.db_path.exists():
                backup_path = self.db_path.with_suffix('.corrupt.bak')
                shutil.copy2(self.db_path, backup_path)
            return []

    def _save_sync(self, data: List[dict]):
        tmp_path = self.db_path.with_suffix('.tmp')
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, self.db_path)

    async def save_file(self, file: CodeFile):
        def _do_save():
            data = self._load_sync()
            # update if exists
            for idx, item in enumerate(data):
                if item["id"] == file.id:
                    data[idx] = file.model_dump()
                    self._save_sync(data)
                    return
            data.append(file.model_dump())
            self._save_sync(data)
        await asyncio.to_thread(_do_save)

    async def get_all(self) -> List[CodeFile]:
        def _do_load():
            data = self._load_sync()
            return [CodeFile(**item) for item in data]
        return await asyncio.to_thread(_do_load)

    async def delete_file(self, file_id: str):
        def _do_delete():
            data = self._load_sync()
            data = [item for item in data if item["id"] != file_id]
            self._save_sync(data)
        await asyncio.to_thread(_do_delete)
