import React, { useEffect, useState } from "react";
import { Card, Table, Tag, Button, Space, Empty, message } from "antd";
import { useNavigate } from "react-router-dom";
import { getPendingReviews } from "../../api/reviews";
import { DownloadOutlined } from '@ant-design/icons';
import { exportAnnotationsJson, exportAnnotationsCsv } from '../../api/labeler';
import { formatDateTime } from '../../utils/time';

const normalizeList = (res: any): any[] => {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.items)) return res.items;
  if (Array.isArray(res?.data)) return res.data;
  if (Array.isArray(res?.submissions)) return res.submissions;
  if (Array.isArray(res?.reviews)) return res.reviews;
  if (Array.isArray(res?.pending_reviews)) return res.pending_reviews;
  if (Array.isArray(res?.results)) return res.results;
  return [];
};

const normalizeReviewRecord = (record: any) => {
  const submission = record.submission || record.submission_data || record;
  const item = record.dataset_item || record.item || {};
  const aiReview = record.ai_review || record.ai_review_result || {};

  const submissionId =
    record.submission_id ||
    submission.submission_id ||
    submission.id ||
    record.id;

  return {
    raw: record,
    submission_id: submissionId,
    task_id:
      record.task_id ||
      submission.task_id ||
      item.task_id ||
      "-",
    dataset_item_id:
      record.dataset_item_id ||
      submission.dataset_item_id ||
      item.id ||
      item.dataset_item_id ||
      "-",
    work_key:
      record.work_key ||
      submission.work_key ||
      (record.task_id && record.dataset_item_id && (record.labeler_id || submission.labeler_id)
        ? `${record.task_id}:${record.dataset_item_id}:${record.labeler_id || submission.labeler_id}`
        : null) ||
      "-",
    template_name: record.template_name || submission.template_name || "-",
    labeler_id:
      record.labeler_id ||
      submission.labeler_id ||
      "-",
    status:
      record.status ||
      submission.status ||
      "pending",
    created_at:
      record.created_at ||
      submission.created_at ||
      "-",
    updated_at:
      record.updated_at ||
      submission.updated_at ||
      "-",
    has_ai_review: record.has_ai_review || !!(aiReview && aiReview.conclusion),
    ai_review: aiReview,
    is_invalid: record.is_invalid || false,
    invalid_reason: record.invalid_reason || "",
    invalid_remark: record.invalid_remark || ""
  };
};

const ReviewQueuePage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await getPendingReviews();
      
      const rawList = normalizeList(res);
      const rows = rawList.map(normalizeReviewRecord);
      
      setItems(rows);
    } catch (error) {
      console.error("Load pending reviews failed", error);
      message.error("加载审核队列失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleExport = async (format: 'json' | 'csv') => {
    try {
      const blob = format === 'json' ? await exportAnnotationsJson() : await exportAnnotationsCsv();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `annotations_export.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      message.success(`已导出 ${format.toUpperCase()} 文件`);
    } catch (error) {
      message.error('导出失败');
      console.error(error);
    }
  };

  const columns = [
    {
      title: "标注ID",
      dataIndex: "submission_id",
      key: "submission_id",
      width: 90,
      ellipsis: true,
      render: (value: any, _record: any) => {
        if (!value || value === "-") {
          return <span style={{ color: "red" }}>缺少</span>;
        }
        return `#${value}`;
      }
    },
    {
      title: "任务ID",
      dataIndex: "task_id",
      key: "task_id",
      width: 80,
      ellipsis: true,
      render: (value: any) => value !== "-" ? `#${value}` : "-"
    },
    {
      title: "数据项ID",
      dataIndex: "dataset_item_id",
      key: "dataset_item_id",
      width: 90,
      ellipsis: true,
      render: (value: any) => value !== "-" ? `#${value}` : "-"
    },
    {
      title: "模板名称",
      dataIndex: "template_name",
      key: "template_name",
      width: 180,
      ellipsis: true,
      render: (value: string) => value || "-"
    },
    {
      title: "标注员ID",
      dataIndex: "labeler_id",
      key: "labeler_id",
      width: 90,
      ellipsis: true,
      render: (value: any) => value !== "-" ? `#${value}` : "-"
    },
    {
      title: "work_key",
      dataIndex: "work_key",
      key: "work_key",
      width: 140,
      ellipsis: true,
      render: (value: any) => value !== "-" && value ? <span style={{ fontSize: 12, wordBreak: 'break-all' }}>{value}</span> : "-"
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: string, record: any) => {
        let color = "blue";
        let label = status;
        if (status === "invalid_submitted") {
          color = "red";
          label = "无效待审";
        } else if (record.is_invalid && status === "submitted") {
          color = "red";
          label = "无效待审";
        } else if (status === "human_reviewing" || status === "人工审核中") {
          color = "orange";
          label = "待审核";
        } else if (status === "approved" || status === "已通过") {
          color = "green";
          label = "审核通过";
        } else if (status === "rejected" || status === "rejected_to_modify" || status === "需修改") {
          color = "red";
          label = "已打回";
        } else if (status === "submitted") {
          label = "待审核";
        } else if (status === "ai_passed") {
          color = "cyan";
          label = "AI通过";
        } else if (status === "returned_to_modify" || status === "needs_revision") {
          color = "orange";
          label = "待返修";
        } else if (status === "rework_submitted" || status === "rework") {
          color = "blue";
          label = "返修已提交";
        }
        return <Tag color={color}>{label}</Tag>;
      }
    },
    {
      title: "AI预审",
      dataIndex: "ai_review",
      key: "ai_review",
      width: 120,
      render: (aiReview: any, record: any) => {
        if (record.is_invalid) {
          return <Tag color="gray">无效提交</Tag>;
        }
        const hasAiReview = record.has_ai_review || (aiReview && (aiReview.overall_score !== undefined || aiReview.score !== undefined || aiReview.conclusion));
        if (!hasAiReview) {
          return <Tag color="gray">未预审</Tag>;
        }
        const score = aiReview?.overall_score ?? aiReview?.score;
        const riskLevel = aiReview?.risk_level;
        if (score !== undefined) {
          const riskColor = riskLevel === 'high' ? 'red' : riskLevel === 'medium' ? 'orange' : 'green';
          const riskText = riskLevel === 'high' ? '高' : riskLevel === 'medium' ? '中' : '低';
          return <Tag color={riskColor}>{score}分 / {riskText}风险</Tag>;
        }
        return <Tag color="green">已完成</Tag>;
      }
    },
    {
      title: "无效原因",
      dataIndex: "invalid_reason",
      key: "invalid_reason",
      width: 120,
      ellipsis: true,
      render: (_: any, record: any) => {
        return record.is_invalid ? (record.invalid_reason || "-") : "-";
      }
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (value: string) => value ? formatDateTime(value) : "-"
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (value: string) => value ? formatDateTime(value) : "-"
    },
    {
      title: "操作",
      key: "action",
      width: 100,
      fixed: 'right' as const,
      render: (_: any, record: any) => {
        const submissionId = record.submission_id;
        const isDisabled = !submissionId || submissionId === "-";

        return (
          <Space>
            <Button
              type="link"
              onClick={() => navigate(`/reviewer/reviews/${submissionId}`)}
              disabled={isDisabled}
            >
              审核详情
            </Button>
          </Space>
        );
      }
    }
  ];

  return (
    <div>
      <h1>审核队列</h1>
      <p>审核标注提交</p>
      <div style={{ marginBottom: 16 }}>
        <Button onClick={() => handleExport('json')} icon={<DownloadOutlined />} style={{ marginRight: 8 }}>导出 JSON</Button>
        <Button onClick={() => handleExport('csv')} icon={<DownloadOutlined />}>导出 CSV</Button>
      </div>
      <Card>
        {items.length === 0 && !loading ? (
          <Empty description="暂无待审核提交" />
        ) : (
          <Table
            rowKey={(record) => String(record.submission_id ?? `${record.task_id}_${record.dataset_item_id}`)}
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1400 }}
          />
        )}
      </Card>
    </div>
  );
};

export default ReviewQueuePage;