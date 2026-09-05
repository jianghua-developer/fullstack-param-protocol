"""gen-params.py 两区协议（params + selection）行为测试。

覆盖 SCHEMA.md v2 语义：
- params 区 = copier 派生、与 copier.yml hash 校验（过期 → verify 失败）；
- selection 区 = 人工策展、轮转保留、不参与 hash、仅 schema 校验（未知字段容忍）；
- 无 selection 区合法（向后兼容）。

经 subprocess 跑真实入口（含 argparse），用最小 copier 模板 fixture 驱动 copier 内省。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "tpl"
SCRIPT = REPO / "gen-params.py"


def run(args: list[str]) -> subprocess.CompletedProcess:
    """在装有 copier 的当前解释器下跑 gen-params.py。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_template(tmp_path: Path) -> Path:
    """拷贝 fixture 模板到用例独立目录（改 copier.yml 不互相污染）。"""
    tpl = tmp_path / "tpl"
    shutil.copytree(FIXTURE, tpl)
    return tpl


def generate(tpl: Path, out: Path) -> subprocess.CompletedProcess:
    return run(["--template-dir", str(tpl), "--output", str(out), "--quiet"])


def verify(tpl: Path, out: Path) -> subprocess.CompletedProcess:
    return run(["--template-dir", str(tpl), "--output", str(out), "--verify", "--quiet"])


# ── params 区（copier 派生）──────────────────────────────────


def test_generate_v2_params_no_selection_by_default(tmp_path):
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    r = generate(tpl, out)
    assert r.returncode == 0, r.stderr

    doc = load(out)
    assert doc["schema_version"] == 2
    assert "selection" not in doc  # 无策展 → 省略（向后兼容）

    p = doc["params"]
    # 派生参数：when:false + jinja 默认 → derived=true、default 省略
    assert p["derived_tokens"]["derived"] is True
    assert "default" not in p["derived_tokens"]
    # 必填原生参数：无 default
    assert p["project_name"]["derived"] is False
    assert "default" not in p["project_name"]
    # 原生参数：字面默认 / choices（含 disabled 的 reason）
    assert p["app_title"]["default"] == "demo"
    assert p["with_extra"]["default"] is False
    assert p["flavor"]["choices"] == [
        {"value": "basic"},
        {"value": "pro"},
        {"value": "premium", "disabled": True, "reason": "premium 已设计、暂未实现（见模板 DESIGN.md）"},
    ]


# ── selection 区（策展、轮转保留、schema 校验）────────────────


def test_generate_preserves_hand_curated_selection(tmp_path):
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    assert generate(tpl, out).returncode == 0

    # 手工补 selection（含未知字段 → 验证容忍 + 轮转保留）
    doc = load(out)
    doc["selection"] = {
        "suited_for": ["数据表驱动的中后台业务"],
        "tradeoffs": ["生态大、招人易"],
        "future_note": {"x": 1},
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    r = generate(tpl, out)
    assert r.returncode == 0, r.stderr
    sel = load(out)["selection"]
    assert sel["suited_for"] == ["数据表驱动的中后台业务"]
    assert sel["tradeoffs"] == ["生态大、招人易"]
    assert sel["future_note"] == {"x": 1}  # 未知字段未被丢弃


def test_verify_passes_when_only_selection_edited(tmp_path):
    """只改 selection（copier.yml 未动）→ verify 通过（selection 不参与 copier hash）。"""
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    assert generate(tpl, out).returncode == 0

    doc = load(out)
    doc["selection"] = {"suited_for": ["手改、未 regen"]}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    r = verify(tpl, out)
    assert r.returncode == 0, r.stderr


def test_invalid_selection_rejected(tmp_path):
    """selection 非法形态（suited_for 非数组）→ verify 与 generate 都拒绝。"""
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    assert generate(tpl, out).returncode == 0

    doc = load(out)
    doc["selection"] = {"suited_for": "不是数组"}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rv = verify(tpl, out)
    assert rv.returncode != 0
    assert "selection" in rv.stderr
    rg = generate(tpl, out)
    assert rg.returncode != 0  # generate 不得静默吞掉/改写坏策展
    assert "selection" in rg.stderr


# ── verify：params 过期检测（copier.yml 变更）────────────────


def test_verify_detects_stale_params_then_recovers(tmp_path):
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    assert generate(tpl, out).returncode == 0
    assert verify(tpl, out).returncode == 0

    # 改 copier.yml → params 区过期 → verify 失败
    copier_yml = tpl / "copier.yml"
    copier_yml.write_text(copier_yml.read_text(encoding="utf-8") + "\n# 变更\n", encoding="utf-8")
    r = verify(tpl, out)
    assert r.returncode == 1
    # 非 quiet 模式给可读提示
    r_loud = run(["--template-dir", str(tpl), "--output", str(out), "--verify"])
    assert r_loud.returncode == 1
    assert "copier.yml" in r_loud.stdout  # 过期提示走 stdout（非 quiet 模式）

    # regen（selection 若存在应保留）→ verify 恢复通过
    assert generate(tpl, out).returncode == 0
    assert verify(tpl, out).returncode == 0


def test_verify_detects_stale_but_keeps_selection(tmp_path):
    """copier.yml 变更后 regen：selection 轮转保留，只有 params/hash 区更新。"""
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    assert generate(tpl, out).returncode == 0

    doc = load(out)
    doc["selection"] = {"suited_for": ["保持不变"]}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    copier_yml = tpl / "copier.yml"
    copier_yml.write_text(copier_yml.read_text(encoding="utf-8") + "\n# 又变更\n", encoding="utf-8")
    assert generate(tpl, out).returncode == 0

    after = load(out)
    assert after["selection"] == {"suited_for": ["保持不变"]}
    assert after["source_copier_yml_hash"] != doc["source_copier_yml_hash"]
    assert verify(tpl, out).returncode == 0


# ── 异常路径 ─────────────────────────────────────────────────


def test_corrupt_json_rejected(tmp_path):
    tpl = make_template(tmp_path)
    out = tmp_path / "params.json"
    out.write_text("{ 不是合法 json", encoding="utf-8")
    r = generate(tpl, out)
    assert r.returncode != 0
    assert "JSON" in r.stderr
