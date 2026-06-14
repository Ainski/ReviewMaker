"""临时脚本：从 JSON 快照加载输入并调用 generate_poster 生成海报。"""

import base64
import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models import Paper, Author
from src.poster_generator import generate_poster


def load_poster_input(json_path: str) -> dict:
    """从 JSON 快照文件加载 generate_poster 的输入参数。"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ---- 重建 Paper 对象列表 ----
    papers = []
    for p_dict in data["papers"]:
        # 重建嵌套的 Author 对象
        authors = [Author(**a) for a in p_dict.pop("authors", [])]
        papers.append(Paper(authors=authors, **p_dict))

    # ---- 重建 paper_figures（base64 → bytes） ----
    paper_figures = None
    if data.get("paper_figures"):
        paper_figures = []
        for fd in data["paper_figures"]:
            fd_copy = {k: v for k, v in fd.items() if k != "image_bytes_base64"}
            b64 = fd.get("image_bytes_base64")
            fd_copy["image_bytes"] = base64.b64decode(b64) if b64 else None
            paper_figures.append(fd_copy)

    return {
        "papers": papers,
        "topic": data["topic"],
        "review_summary": data["review_summary"],
        "evolution_diagram_path": data["evolution_diagram_path"],
        "output_path": data["output_path"],
        "dpi": data.get("dpi", 200),
        "paper_figures": paper_figures,
    }


if __name__ == "__main__":
    json_path = "output/gui_runs/247617641970/poster_input_20260614_160702.json"
    kwargs = load_poster_input(json_path)
    result_path = generate_poster(**kwargs)
    print(f"海报生成完成: {result_path}")