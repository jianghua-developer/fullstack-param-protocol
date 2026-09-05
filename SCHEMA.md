# params.json schema 规范

底座仓库根目录 `params.json`，由本仓 `gen-params.py`（底座钩子经 copier 内省）生成、底座自维护、与 copier.yml 原子提交。fullstack-bridge 与各底座按此协议对齐。

**协议分两区（schema_version = 2）**：

| 区 | 来源 | 校验 | 轮转 |
|---|---|---|---|
| `params` | copier 派生（内省 copier.yml） | 与 copier.yml **hash 校验**（`source_copier_yml_hash`） | regen 全量重算 |
| `selection` | **人工策展**（技术栈/底座的选择事实） | **schema 校验**（见下），**不参与 copier hash** | regen **轮转保留**原样写回 |

> `selection` 是选择/引导元数据（`suited_for`/`tradeoffs`），copier.yml 无法派生，故不参与 hash；可缺省（无策展 = 合法，阅读方按缺省处理）。底座 CI 两区各自校验。

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | int | 本协议版本（当前 **2**）；区别于 combos.yaml 里底座的 git `version`。v2 = 引入 `selection` 区（v1 文件缺省合法） |
| `source_copier_yml_hash` | str | `sha256:` + 生成时 copier.yml 的 SHA-256——base CI 据此校验 `params` 区与 copier.yml 一致（防静默过期） |
| `generated_by` | str | `copier-introspect@<copier 版本>`——交叉核对生成器版本 |
| `params` | object | 参数名 → 参数定义（copier 派生区） |
| `selection` | object \| 缺省 | 人工策展的选择事实（可选；见下） |

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

## `selection` 条目

可选对象；含选择事实的自然语言条目，供技术栈/形态选择（L2）做推理地基。**人工策展、不参与 copier hash**。

| 字段 | 类型 | 说明 |
|---|---|---|
| `suited_for` | list[str] \| 缺省 | 适用场景描述（如「数据表驱动的中后台业务」） |
| `tradeoffs` | list[str] \| 缺省 | 相对同类底座的取舍（供推荐理由引用） |

- 规则：两字段均可选；出现时**必须是字符串数组**。未知字段**容忍并轮转保留**（策展区允许演进）。
- 新增/修改选择事实：手改 params.json 的 `selection` 区后跑一次 `gen-params.py`（pre-commit 会做）让格式归一；**不触发 copier 过期**（`selection` 不在 hash 内）。
- 非法形态（如 `suited_for` 不是数组）→ `gen-params.py` 拒绝并报错（generate / verify 同）。

## 示例

```json
{
  "schema_version": 2,
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
  },
  "selection": {
    "suited_for": ["数据表驱动的中后台业务 / 快速 API 服务"],
    "tradeoffs": ["Python 生态、开发快；相对 Java/Go 栈运行密度与延迟不占优"]
  }
}
```

## 依赖说明

`gen-params.py` 经 **copier 内省**（`copier._template.Template.questions_data`）读取参数 schema，不解析 copier.yml。该入口是 copier 的 deprecated 内部 API——**脆弱点隔离在底座钩子（生成时）**：底座在装有 copier 的环境运行，桥只消费稳定的已提交 JSON。

**copier 全链统一钉 `9.17.1`**（协议仓 venv / 底座钩子 `uv run --with copier==9.17.1` / 底座 CI `pip install copier==9.17.1`）：`generated_by` 含 copier patch 版本且参与 verify 全文本比对，任何环境漂版本都会让全文本比对误判——故精确钉版本，不用范围。
