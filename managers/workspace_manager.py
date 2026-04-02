"""
WorkspaceManager - 解决方案持久化管理器

负责解决方案的创建、读取、删除和列表管理，与 UI 解耦。
"""

import json
import os
import shutil
from datetime import datetime


class WorkspaceManager:
    """管理 workspaces/ 目录下的解决方案"""

    # 非法字符集合：\ / : * ? " < > |
    ILLEGAL_CHARS = set('\\/: *?"<>|')

    def __init__(self, workspaces_root: str):
        self.workspaces_root = workspaces_root

    @staticmethod
    def validate_name(name: str) -> bool:
        """
        验证解决方案名称是否合法。
        合法条件：非空字符串，且不含 \\ / : * ? " < > | 任意字符，且不含控制字符。
        """
        if not name:
            return False
        illegal = set('\\/: *?"<>|')
        if any(ch in illegal for ch in name):
            return False
        # 拒绝控制字符（ASCII 0-31 及 127）
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            return False
        return True

    def list_workspaces(self) -> list:
        """
        扫描 workspaces/ 目录，返回所有子目录名称（按字母排序）。
        若目录不存在则自动创建并返回空列表。
        """
        if not os.path.exists(self.workspaces_root):
            os.makedirs(self.workspaces_root)
            return []

        entries = []
        for entry in os.scandir(self.workspaces_root):
            if entry.is_dir():
                entries.append(entry.name)
        return sorted(entries)

    def workspace_exists(self, name: str) -> bool:
        """检查指定名称的解决方案是否存在"""
        workspace_path = os.path.join(self.workspaces_root, name)
        return os.path.isdir(workspace_path)

    def save_workspace(
        self,
        name: str,
        font_solution_path: str,
        sensor_settings: dict,
        script_settings: dict,
        tcp_settings: dict,
        overwrite: bool = False,
        preview_image=None,
    ) -> None:
        """
        创建/覆盖解决方案目录。
        preview_image: 可选，numpy BGR/灰度图，保存为 preview.jpg
        """
        if not self.validate_name(name):
            raise ValueError(f"解决方案名称非法：{name!r}")

        if not os.path.isdir(font_solution_path):
            raise ValueError(f"字体库方案路径不存在：{font_solution_path!r}")

        workspace_path = os.path.join(self.workspaces_root, name)

        if overwrite and os.path.isdir(workspace_path):
            shutil.rmtree(workspace_path)

        try:
            shutil.copytree(font_solution_path, workspace_path)

            config = {
                "version": 1,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "font_solution_name": os.path.basename(font_solution_path),
                "sensor": sensor_settings,
                "scripts": script_settings,
                "tcp": tcp_settings,
            }
            config_path = os.path.join(workspace_path, "workspace_config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            # 保存预览图片（用 PIL 避免 cv2 中文路径问题）
            if preview_image is not None:
                try:
                    import numpy as np
                    from PIL import Image
                    preview_path = os.path.join(workspace_path, "preview.jpg")
                    if len(preview_image.shape) == 2:
                        pil_img = Image.fromarray(preview_image)
                    else:
                        import cv2
                        pil_img = Image.fromarray(cv2.cvtColor(preview_image, cv2.COLOR_BGR2RGB))
                    pil_img.save(preview_path, "JPEG")
                except Exception:
                    pass

        except OSError:
            if os.path.isdir(workspace_path):
                shutil.rmtree(workspace_path, ignore_errors=True)
            raise

    def load_workspace(self, name: str) -> dict:
        """
        读取解决方案，返回：
        {
          "sensor": {...},
          "scripts": {...},
          "tcp": {...},
          "layout_config": {...}
        }
        抛出 FileNotFoundError：解决方案目录或 workspace_config.json 不存在
        抛出 json.JSONDecodeError：workspace_config.json 格式错误
        """
        workspace_path = os.path.join(self.workspaces_root, name)
        if not os.path.isdir(workspace_path):
            raise FileNotFoundError(f"解决方案目录不存在：{workspace_path!r}")

        config_path = os.path.join(workspace_path, "workspace_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        layout_config = {}
        layout_path = os.path.join(workspace_path, "layout_config.json")
        if os.path.isfile(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                layout_config = json.load(f)

        return {
            "sensor": config.get("sensor", {}),
            "scripts": config.get("scripts", {}),
            "tcp": config.get("tcp", {}),
            "layout_config": layout_config,
            "font_solution_name": config.get("font_solution_name", ""),
            "preview_image": self._load_preview_image(workspace_path),
        }

    def _load_preview_image(self, workspace_path: str):
        """读取 preview.jpg，返回 numpy array，不存在则返回 None"""
        preview_path = os.path.join(workspace_path, "preview.jpg")
        if not os.path.isfile(preview_path):
            return None
        try:
            import numpy as np
            from PIL import Image
            pil_img = Image.open(preview_path).convert("L")  # 灰度
            return np.array(pil_img)
        except Exception:
            return None

    def delete_workspace(self, name: str) -> None:
        """删除解决方案目录（shutil.rmtree）"""
        workspace_path = os.path.join(self.workspaces_root, name)
        shutil.rmtree(workspace_path)
