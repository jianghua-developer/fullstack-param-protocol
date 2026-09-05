#!/usr/bin/env python3
"""gen-params.py — 底座 copier.yml → params.json（对齐协议）生成/校验工具。

协议 schema 见同仓 SCHEMA.md（两区：params 派生区 + selection 策展区）。经 copier
内省（Template.questions_data）读取参数 schema，避免自解析 copier.yml 的语义分叉。

selection 区（人工策展的选择事实）不参与 copier hash：regen 时从既有 params.json
**轮转保留**原样写回；verify 只对其做 **schema 校验**，不要求与 copier.yml 一致。

用法（底座 pre-commit 钩子 / CI 调用，需在装有 copier 的 python 下运行）：
  gen-params.py --template-dir <dir>                  # generate：写 params.json
  gen-params.py --template-dir <dir> --verify         # verify：params 与 copier.yml 比对
                                                      #   + selection schema 校验，违规退出 1
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# copier.yml 里 jinja 表达式默认值/条件值的定界符（前端 _envops 用 [[]]，后端用 {{}}）
JINJA_MARKERS = ("{{", "}}", "{%", "%}", "[[", "]]", "[%", "%]")

SCHEMA_VERSION = 2  # v2 = 引入 selection 区（v1 文件缺省合法，见 SCHEMA.md）
# selection 区已知字段（策展、不参与 copier hash）；未知字段容忍并轮转保留
SELECTION_FIELDS = ("suited_for", "tradeoffs")


def copier_version() -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version("copier")
    except Exception:
        return "unknown"


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def is_derived(spec: dict) -> bool:
    """when 为字面 False = 派生参数（不向用户提问、由默认值计算，如 child_apps）。"""
    return spec.get("when") is False


def is_expression(value) -> bool:
    return isinstance(value, str) and any(m in value for m in JINJA_MARKERS)


def normalize_choices(raw) -> list[dict] | None:
    """choices 归一化为结构化列表：{value} 启用 / {value, disabled, reason} 禁用。

    copier 三种形态：
      - list[str]                      → 全部启用
      - dict[label: str]               → 全部启用（value = dict 的 value）
      - dict[label: {value, validator}]→ validator 存在 = 禁用（已设计未实现）
    """
    if raw is None:
        return None
    out = []
    if isinstance(raw, list):
        for v in raw:
            out.append({"value": v})
    elif isinstance(raw, dict):
        for _label, v in raw.items():
            if isinstance(v, dict):
                entry = {"value": v.get("value")}
                validator = v.get("validator")
                if validator:
                    entry["disabled"] = True
                    entry["reason"] = validator
                out.append(entry)
            else:
                out.append({"value": v})
    return out


def validate_selection(selection) -> None:
    """selection 区 schema 校验（策展、不参与 copier hash）。

    规则（SCHEMA.md）：可选对象；suited_for / tradeoffs 出现时必须是字符串数组；
    未知字段容忍（策展区允许演进，轮转保留）。
    """
    if selection is None:
        return
    if not isinstance(selection, dict):
        raise ValueError('selection 区应为对象（如 {"suited_for": [], "tradeoffs": []}）')
    for field in SELECTION_FIELDS:
        val = selection.get(field)
        if val is None:
            continue
        if not isinstance(val, list) or not all(isinstance(s, str) for s in val):
            raise ValueError(f"selection.{field} 应为字符串数组（list[str]）")


def load_existing_selection(output: Path) -> dict | None:
    """读回已提交 params.json 的 selection 区（轮转保留用）。

    文件不存在 / 无 selection 键 → None（输出省略该区）；存在则 schema 校验，
    非法即报错（generate 与 verify 同：防止静默吞掉/改写坏策展）。
    """
    if not output.exists():
        return None
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"❌ {output} 不是合法 JSON（无法轮转保留 selection）: {exc}")
    selection = data.get("selection")
    if selection is None:
        return None
    try:
        validate_selection(selection)
    except ValueError as exc:
        raise SystemExit(f"❌ {output} 的 selection 区非法（修复后重新 generate）: {exc}")
    return selection


def build_params(questions_data: dict) -> dict:
    params = {}
    for name, spec in questions_data.items():
        entry = {"type": spec.get("type", "str")}
        choices = normalize_choices(spec.get("choices"))
        if choices is not None:
            entry["choices"] = choices
        # 只记录字面默认；jinja 表达式默认（多为派生值）不记录
        if "default" in spec and not is_expression(spec.get("default")):
            entry["default"] = spec["default"]
        entry["derived"] = is_derived(spec)
        params[name] = entry
    return params


def render_schema(
    template_dir: Path, copier_yml_bytes: bytes, existing_selection: dict | None
) -> dict:
    from copier._template import Template  # 内部 API，钉 copier 版本（见 SCHEMA.md）

    t = Template(url=str(template_dir))
    doc = {
        "schema_version": SCHEMA_VERSION,
        "source_copier_yml_hash": sha256_hex(copier_yml_bytes),
        "generated_by": f"copier-introspect@{copier_version()}",
        "params": build_params(t.questions_data),
    }
    if existing_selection is not None:
        doc["selection"] = existing_selection  # 策展区轮转保留，不参与 copier hash
    return doc


def find_copier_yml(template_dir: Path) -> Path:
    for name in ("copier.yml", "copier.yaml"):
        p = template_dir / name
        if p.exists():
            return p
    raise SystemExit(f"❌ 模板目录缺少 copier.yml/copier.yaml: {template_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成/校验底座 params.json（对齐协议）")
    ap.add_argument("--template-dir", required=True, help="copier 模板目录（含 copier.yml）")
    ap.add_argument("--output", default="params.json", help="输出/比对文件（默认 params.json）")
    ap.add_argument("--verify", action="store_true", help="校验模式：与已提交比对，不一致退出 1")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    template_dir = Path(args.template_dir)
    if not template_dir.is_dir():
        raise SystemExit(f"❌ 模板目录不存在: {template_dir}")

    output = Path(args.output)
    # selection 区轮转保留：regen / verify 都先读回既有策展（schema 校验在此发生）
    existing_selection = load_existing_selection(output)
    copier_yml = find_copier_yml(template_dir)
    rendered = render_schema(template_dir, copier_yml.read_bytes(), existing_selection)
    text = json.dumps(rendered, ensure_ascii=False, indent=2) + "\n"

    if args.verify:
        if not output.exists():
            raise SystemExit(f"❌ {output} 不存在——未生成过 params.json？")
        if output.read_text(encoding="utf-8").strip() != text.strip():
            if not args.quiet:
                print("❌ params.json 与当前 copier.yml 不一致（请重新 generate 并提交）")
                print(f"   模板: {template_dir}")
            sys.exit(1)
        if not args.quiet:
            print("✓ params.json 与 copier.yml 一致")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    if not args.quiet:
        print(f"✓ 已生成 {output}（{len(rendered['params'])} 参数）")
        print(f"   schema_version={rendered['schema_version']}  "
              f"copier_yml_hash={rendered['source_copier_yml_hash'][:16]}…")


if __name__ == "__main__":
    main()
