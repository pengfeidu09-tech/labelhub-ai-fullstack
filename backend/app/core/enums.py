from enum import Enum


class UserRole(str, Enum):
    OWNER = "owner"
    LABELER = "labeler"
    REVIEWER = "reviewer"
    SYSTEM = "system"


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    ENDED = "ended"


class DatasetType(str, Enum):
    QA_QUALITY = "qa_quality"
    PREFERENCE_COMPARE = "preference_compare"
    CUSTOM = "custom"


class ItemStatus(str, Enum):
    IMPORTED = "imported"
    UNCLAIMED = "unclaimed"
    CLAIMED = "claimed"
    DRAFTING = "drafting"
    SUBMITTED = "submitted"
    AI_REVIEWING = "ai_reviewing"
    AI_REVIEWED = "ai_reviewed"
    HUMAN_REVIEWING = "human_reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORT_READY = "export_ready"
    INVALID = "invalid"


class SubmissionStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AI_REVIEWING = "ai_reviewing"
    AI_PASSED = "ai_passed"
    AI_REJECTED = "ai_rejected"
    AI_NEED_HUMAN = "ai_need_human"
    HUMAN_REVIEWING = "human_reviewing"
    APPROVED = "approved"
    REJECTED_TO_MODIFY = "rejected_to_modify"
    REVISED_SUBMITTED = "revised_submitted"


class AIReviewStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class AIReviewDecision(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    HUMAN_REVIEW = "human_review"


class HumanReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"


class ExportStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ExportFormat(str, Enum):
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    XLSX = "xlsx"


class AuditAction(str, Enum):
    TASK_CREATE = "task_create"
    TASK_PUBLISH = "task_publish"
    TASK_PAUSE = "task_pause"
    TASK_RESUME = "task_resume"
    TASK_END = "task_end"
    TEMPLATE_CREATE = "template_create"
    TEMPLATE_UPDATE = "template_update"
    ITEM_IMPORT = "item_import"
    ITEM_CLAIM = "item_claim"
    ITEM_UNCLAIM = "item_unclaim"
    DRAFT_SAVE = "draft_save"
    SUBMISSION_SUBMIT = "submission_submit"
    SUBMISSION_REVISE = "submission_revise"
    AI_REVIEW_START = "ai_review_start"
    AI_REVIEW_COMPLETE = "ai_review_complete"
    AI_PRECHECK_RUN = "ai_precheck_run"
    AI_PRECHECK_SUCCESS = "ai_precheck_success"
    AI_PRECHECK_FAILED = "ai_precheck_failed"
    OPEN_ITEM = "open_item"
    SESSION_HEARTBEAT = "session_heartbeat"
    SESSION_CLOSE = "session_close"
    HUMAN_REVIEW_START = "human_review_start"
    HUMAN_REVIEW_APPROVE = "human_review_approve"
    HUMAN_REVIEW_REJECT = "human_review_reject"
    HUMAN_REVIEW_REVISE = "human_review_revise"
    REVIEW_APPROVE = "review_approve"
    REVIEW_REJECT = "review_reject"
    EXPORT_CREATE = "export_create"
    EXPORT_COMPLETE = "export_complete"
    EXPORT_FAILED = "export_failed"
    MARK_INVALID = "mark_invalid"
    SKIP_ITEM = "skip_item"
    SAVE_VERSION = "save_version"
    QUALITY_INSIGHT_VIEW = "quality_insight_view"
    RUBRIC_ANALYSIS_VIEW = "rubric_analysis_view"
    QUALITY_REPORT_GENERATE = "quality_report_generate"
    PRIORITY_REVIEW_LIST_VIEW = "priority_review_list_view"
    DASHBOARD_VIEW = "dashboard_view"
    DEMO_WALKTHROUGH_VIEW = "demo_walkthrough_view"
    DEMO_MODE_ENABLE = "demo_mode_enable"
    DEMO_MODE_DISABLE = "demo_mode_disable"
    SYSTEM_HEALTH_CHECK = "system_health_check"
    DEMO_DATA_DOC_VIEW = "demo_data_doc_view"
    QUALITY_POLICY_VIEW = "quality_policy_view"
    REVIEW_STRATEGY_VIEW = "review_strategy_view"
    SNAPSHOT_SUMMARY_VIEW = "snapshot_summary_view"
    EXPORT_SNAPSHOT_CREATE = "export_snapshot_create"
    EXPORT_SNAPSHOT_COMPLETE = "export_snapshot_complete"
    AGENT_ENQUEUE = "agent_enqueue"
    AGENT_RUN_START = "agent_run_start"
    AGENT_RUN_SUCCESS = "agent_run_success"
    AGENT_RUN_FAILED = "agent_run_failed"
    AGENT_RETRY = "agent_retry"
    AGENT_FALLBACK_REQUIRED = "agent_fallback_required"
    AGENT_CONFIG_VIEW = "agent_config_view"
    AGENT_CONFIG_UPDATE = "agent_config_update"
    AGENT_QUEUE_VIEW = "agent_queue_view"
    AGENT_PROVIDER_CONFIG_UPDATE = "agent_provider_config_update"
    AI_REVIEW_RERUN = "ai_review_rerun"
    REVIEW_RULE_UPDATE = "review_rule_update"
    OFFICIAL_DATASET_HEALTH_CHECK = "official_dataset_health_check"
    DEFAULT_DEMO_TASK_SWITCH = "default_demo_task_switch"
    GOLD_COMPARE_VIEW = "gold_compare_view"
    TASK_LLM_ASSIST_ENABLED = "task_llm_assist_enabled"
    TASK_LLM_ASSIST_DISABLED = "task_llm_assist_disabled"
    TEMPLATE_BIND = "template_bind"
    TEMPLATE_ARCHIVE = "template_archive"


class AuditTargetType(str, Enum):
    TASK = "task"
    TEMPLATE = "template"
    DATASET_ITEM = "dataset_item"
    SUBMISSION = "submission"
    ANNOTATION = "annotation"
    AI_REVIEW = "ai_review"
    HUMAN_REVIEW = "human_review"
    EXPORT = "export"