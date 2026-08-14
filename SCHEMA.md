# params.json schema 规范

底座仓库根目录 `params.json`，由本仓 `gen-params.py`（底座钩子经 copier 内省）生成、底座自维护、与 copier.yml 原子提交。fullstack-bridge 与各底座按此协议对齐。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int | 本协议版本（当前 1）；区别于 combos.yaml 里底座的 git `version` |
| `source_copier_yml_hash` | str | `sha256:` + 生成时 copier.yml 的 SHA-256——base CI 据此校验 params.json 与 copier.yml 一致（防静默过期） |
| `generated_by` | str | `copier-introspect@<copier 版本>`——交叉核对生成器版本 |
| `params` | object | 参数名 → 参数定义 |

## `params` 条目

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | str | copier 类型（`str` / `bool` / `yaml` / …） |
| `choices` | list | **有则列出**（结构化，见下）；无选择项的参数省略 |
| `default` | any | **字面默认值**才记录（`str` / `bool` / `int`）；必填参数或 jinja 表达式默认（多为派生值）省略 |
| `derived` | bool | `true` = `when: false` 派生参数（不向用户提问、由默认值计算） |

## `choices` 条目

- `{ "value": "x" }` —— 启用的选择
- `{ "value": "x", "disabled": true, "reason": "…" }` —— **禁用**选择（copier.yml 里带 validator 的「已设计未实现」选项）

> 检查链据此**只对 enabled choices** 做契约覆盖校验，不会误要求覆盖未实现取值。

## 示例

```json
{
  "schema_version": 1,
  "source_copier_yml_hash": "sha256:abc...",
  "generated_by": "copier-introspect@9.17.0",
  "params": {
    "auth_mode": {
      "type": "str",
      "choices": [
        { "value": "none" },
        { "value": "opaque" },
        { "value": "jwt", "disabled": true, "reason": "已设计、暂未实现（见模板 DESIGN.md）" }
      ],
      "default": "opaque",
      "derived": false
    },
    "with_db":    { "type": "bool", "default": true,  "derived": false },
    "child_apps": { "type": "yaml",                    "derived": true  },
    "child_apps_raw": { "type": "str", "default": "backend", "derived": false }
  }
}
```

## 依赖说明

`gen-params.py` 经 **copier 内省**（`copier._template.Template.questions_data`）读取参数 schema，不解析 copier.yml。该入口是 copier 的 deprecated 内部 API——**脆弱点隔离在底座钩子（生成时）**：底座在装有 copier 的环境运行（钉 copier 版本），桥只消费稳定的已提交 JSON。
