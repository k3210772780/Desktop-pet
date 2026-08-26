from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk


class SpritePlayer:
    """Standard-library-only sprite sheet loader using Tk's native image engine."""

    def __init__(self, master: tk.Misc):
        self.asset_dir = Path(__file__).resolve().parent.parent / "assets" / "pixelpaws"
        self.available = False
        self.frames: dict[int, tk.PhotoImage] = {}
        self.mirrored_frames: dict[int, tk.PhotoImage] = {}
        self.animations = {}
        self._source = None
        self._bbox_cache = {}
        manifest_path = self.asset_dir / "manifest.json"
        sheet_path = self.asset_dir / "spritesheet.png"
        if not sheet_path.exists():
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.animations = manifest["animations"]
            self._source = tk.PhotoImage(master=master, file=str(sheet_path))
            cell_w, cell_h = manifest["cellWidth"], manifest["cellHeight"]
            columns = manifest["columns"]
            indices = {i for spec in self.animations.values() for i in spec["frames"]}
            # Original cells are large; 2x subsampling keeps detail and needs no Pillow.
            for index in indices:
                x, y = (index % columns) * cell_w, (index // columns) * cell_h
                frame = tk.PhotoImage(master=master, width=cell_w, height=cell_h)
                frame.tk.call(frame, "copy", self._source, "-from", x, y, x + cell_w, y + cell_h)
                self.frames[index] = frame.subsample(2, 2)
                self.mirrored_frames[index] = frame.subsample(-2, 2)
            self.available = bool(self.frames)
        except (OSError, ValueError, tk.TclError):
            self.available = False

    def frame(self, animation: str, elapsed: float, facing: str = "right") -> tk.PhotoImage | None:
        spec = self.animations.get(animation)
        if not self.available or not spec:
            return None
        sequence = spec["frames"]
        offset = int(elapsed * float(spec["fps"]))
        if spec.get("loop", True):
            offset %= len(sequence)
        else:
            offset = min(offset, len(sequence) - 1)
        bank = self.mirrored_frames if facing == "left" else self.frames
        return bank.get(sequence[offset])

    def opaque_bbox(self, animation: str, facing: str = "right") -> tuple[int, int, int, int] | None:
        """Union of non-transparent pixels for an animation, in rendered frame coordinates."""
        key = (animation, facing)
        if key in self._bbox_cache:
            return self._bbox_cache[key]
        spec = self.animations.get(animation)
        bank = self.mirrored_frames if facing == "left" else self.frames
        images = [bank[i] for i in spec["frames"] if i in bank] if spec else []
        if not images:
            return None
        left, top = images[0].width(), images[0].height()
        right = bottom = -1
        for image in images:
            for y in range(image.height()):
                for x in range(image.width()):
                    if not bool(int(image.tk.call(image, "transparency", "get", x, y))):
                        left=min(left,x); top=min(top,y); right=max(right,x+1); bottom=max(bottom,y+1)
        bbox = None if right < 0 else (left, top, right, bottom)
        self._bbox_cache[key] = bbox
        return bbox
