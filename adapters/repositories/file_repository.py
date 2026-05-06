"""Filesystem-backed repository for raw scraped creator JSON.

Expected layout:
    base_dir/
        <username>/
            userInfo.json
            postInfo.json
"""
from __future__ import annotations
import json
import os
from typing import Iterable, Optional, Set

from ...domain.models import RawCreatorData


class FileCreatorRepository:
    def __init__(self, base_dir: str, exclude: Optional[Set[str]] = None) -> None:
        self.base_dir = base_dir
        self.exclude = {u.lower() for u in (exclude or set())}

    def list_usernames(self) -> Iterable[str]:
        if not os.path.isdir(self.base_dir):
            return []
        out = []
        for name in os.listdir(self.base_dir):
            if not os.path.isdir(os.path.join(self.base_dir, name)):
                continue
            if name.lower() in self.exclude:
                continue
            out.append(name)
        return out

    def load(self, username: str) -> Optional[RawCreatorData]:
        cdir = os.path.join(self.base_dir, username)
        ui = os.path.join(cdir, "userInfo.json")
        pi = os.path.join(cdir, "postInfo.json")
        if not (os.path.exists(ui) and os.path.exists(pi)):
            return None
        try:
            with open(ui, "r", encoding="utf-8") as f:
                user_info = json.load(f)
            with open(pi, "r", encoding="utf-8") as f:
                post_info = json.load(f)
        except Exception:
            return None
        try:
            ts = os.path.getctime(cdir)
        except OSError:
            ts = None
        return RawCreatorData(user_info=user_info, post_info=post_info, scraped_timestamp=ts)
