# AI Quality Agent 文档

## 1. 概述

AI 预审 Agent 是 LabelHub 的核心 AI 组件，在人工提交前给出结构化质量建议。

## 2. 输入

| 输入项 | 说明 |
|--------|------|
| 原始数据 | `prompt`, `model_answer`, `reference` |
| 人工标注结果 | `relevance`, `accuracy`, `completeness`, `safety`, `reason` |
| Rubric 维度定义 | 各维度的评分等级与对应描述 |
| 模板 schema | 标注模板的结构定义 |

## 3. 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `overall_score` | `0-100` | 综合评分 |
| `risk_level` | `low / medium / high` | 风险等级 |
| `suggested_action` | `submit / reject / rework / manual_review` | 建议动作 |
| `confidence` | `0-1` | 置信度 |
| `dimension_scores` | `object` | 各维度评分（见下方结构） |
| `reason` | `string` | 质检原因说明 |
| `summary` | `string` | 质量摘要 |
| `issue_tags` | `string[]` | 问题标签列表 |

### dimension_scores 结构

```json
{
  "relevance": { "value": "high", "score": 85 },
  "accuracy": { "value": "correct", "score": 90 },
  "completeness": { "value": "complete", "score": 95 },
  "safety": { "value": "safe", "score": 100 }
}
```

## 4. 评分维度

| 维度 | 可选值 | 对应分数 |
|------|--------|----------|
| relevance（相关性） | `high` / `medium` / `low` | 85 / 70 / 50 |
| accuracy（准确性） | `correct` / `partially_correct` / `incorrect` | 90 / 65 / 30 |
| completeness（完整性） | `complete` / `partial` / `incomplete` | 95 / 60 / 25 |
| safety（安全性） | `safe` / `risky` / `unsafe` | 100 / 50 / 0 |

## 5. 风险等级判定

| 风险等级 | 条件 |
|----------|------|
| `low` | `overall_score >= 80` |
| `medium` | `60 <= overall_score < 80` |
| `high` | `overall_score < 60` |

## 6. 建议动作逻辑

| 建议动作 | 条件 |
|----------|------|
| `submit` | `score >= 80` 且 `risk = low` |
| `manual_review` | `score >= 60` 且 `risk = medium` |
| `reject` / `rework` | `score < 60` 或 `risk = high` |

## 7. 当前模式说明

当前使用 **Mock 模式** 保证演示稳定。Mock 模式基于规则引擎模拟 AI 输出，**不调用真实大模型**。

接口结构已设计为可替换真实模型，只需替换 `ai_provider.py` 中的实现即可接入 OpenAI / Claude 等大模型 API。

> ⚠️ **重要**: 当前系统未集成真实 LLM，所有 AI 预审结果均由 Mock 规则引擎生成，仅用于演示流程与接口结构验证。
