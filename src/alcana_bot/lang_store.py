import json
import os

class LangStore:
    def __init__(self, file_path: str):
        self._file_path = file_path
        if not os.path.exists(self._file_path):
            self._write({})

    def _read(self) -> dict:
        with open(self._file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        tmp_path = self._file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, self._file_path)

    def get_language(self, user_id: int, default: str = "uz") -> str:
        data = self._read()
        return data.get(str(user_id), default)

    def set_language(self, user_id: int, lang: str) -> None:
        data = self._read()
        data[str(user_id)] = lang
        self._write(data)
