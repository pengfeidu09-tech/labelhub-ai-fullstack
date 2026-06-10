import React, { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Button, Input, Select, Space, Spin, Collapse, message, Empty, Alert } from 'antd';
import { apiClient } from '../../api/client';
import { dedupMessage } from '../../utils/format';

interface Rubric {
  rubric_id: string;
  criterion: string;
  dimension: string;
  type: 'objective' | 'subjective';
  necessity: 'explicit' | 'implicit';
  priority: 'must_have' | 'nice_to_have';
  version: number;
  health_score: number;
  risk_level: 'low' | 'medium' | 'high';
  issues: string[];
}

const normalizeList = (payload: any): any[] => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.results)) return payload.results;
  if (Array.isArray(payload?.dimensions)) return payload.dimensions;
  if (Array.isArray(payload?.rubrics)) return payload.rubrics;
  return [];
};

const RubricLibraryPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [healthChecking, setHealthChecking] = useState(false);
  const [rubrics, setRubrics] = useState<Rubric[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([]);
  const [stats, setStats] = useState({
    total: 0,
    healthy_count: 0,
    risk_count: 0,
    avg_health_score: 0,
  });

  const [searchText, setSearchText] = useState('');
  const [filterDimension, setFilterDimension] = useState<string | undefined>(undefined);
  const [filterPriority, setFilterPriority] = useState<string | undefined>(undefined);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);

  const fetchDimensions = async () => {
    try {
      const res = await apiClient.get('/rubrics/dimensions');
      setDimensions(normalizeList(res.data));
    } catch (error) {
      console.error(error);
    }
  };

  const fetchRubrics = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {};
      if (searchText) params.search = searchText;
      if (filterDimension) params.dimension = filterDimension;
      if (filterPriority) params.priority = filterPriority;
      if (filterType) params.type = filterType;
      const res = await apiClient.get('/rubrics', { params });
      const rubricList = normalizeList(res.data);
      setRubrics(rubricList);
      const total = rubricList.length;
      const healthyCount = rubricList.filter((r: Rubric) => r.health_score >= 80).length;
      const riskCount = rubricList.filter((r: Rubric) => r.risk_level === 'medium' || r.risk_level === 'high').length;
      const avgScore = total > 0 ? Math.round(rubricList.reduce((sum: number, r: Rubric) => sum + r.health_score, 0) / total) : 0;
      setStats({
        total,
        healthy_count: healthyCount,
        risk_count: riskCount,
        avg_health_score: avgScore,
      });
    } catch (error) {
      dedupMessage.error('获取 Rubric 数据失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [searchText, filterDimension, filterPriority, filterType]);

  const handleHealthCheck = async () => {
    setHealthChecking(true);
    try {
      const res = await apiClient.post('/rubrics/health-check');
      const data = res.data;
      const rubricList = normalizeList(data);
      setRubrics(rubricList);
      setStats({
        total: data.total ?? rubricList.length,
        healthy_count: data.healthy_count ?? rubricList.filter((r: Rubric) => r.health_score >= 80).length,
        risk_count: data.at_risk_count ?? rubricList.filter((r: Rubric) => r.risk_level === 'medium' || r.risk_level === 'high').length,
        avg_health_score: data.average_health_score ?? 0,
      });
      message.success('健康检查完成');
    } catch (error: any) {
      if (error?.response?.status !== 405) {
        dedupMessage.error('健康检查失败');
      }
      console.error(error);
    } finally {
      setHealthChecking(false);
    }
  };

  useEffect(() => {
    fetchDimensions();
  }, []);

  useEffect(() => {
    fetchRubrics();
  }, [fetchRubrics]);

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#52c41a';
    if (score >= 60) return '#fa8c16';
    return '#f5222d';
  };

  const getTypeTag = (type: string) => {
    if (type === 'objective') return <Tag color="blue">objective</Tag>;
    return <Tag color="purple">subjective</Tag>;
  };

  const getNecessityTag = (necessity: string) => {
    if (necessity === 'explicit') return <Tag color="green">explicit</Tag>;
    return <Tag color="default">implicit</Tag>;
  };

  const getPriorityTag = (priority: string) => {
    if (priority === 'must_have') return <Tag color="red">must_have</Tag>;
    return <Tag color="blue">nice_to_have</Tag>;
  };

  const getRiskTag = (risk: string) => {
    if (risk === 'low') return <Tag color="green">low</Tag>;
    if (risk === 'medium') return <Tag color="orange">medium</Tag>;
    return <Tag color="red">high</Tag>;
  };

  const columns = [
    {
      title: 'rubric_id',
      dataIndex: 'rubric_id',
      key: 'rubric_id',
      width: 120,
    },
    {
      title: 'criterion',
      dataIndex: 'criterion',
      key: 'criterion',
      ellipsis: true,
    },
    {
      title: 'dimension',
      dataIndex: 'dimension',
      key: 'dimension',
      width: 120,
    },
    {
      title: 'type',
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (type: string) => getTypeTag(type),
    },
    {
      title: 'necessity',
      dataIndex: 'necessity',
      key: 'necessity',
      width: 100,
      render: (necessity: string) => getNecessityTag(necessity),
    },
    {
      title: 'priority',
      dataIndex: 'priority',
      key: 'priority',
      width: 120,
      render: (priority: string) => getPriorityTag(priority),
    },
    {
      title: 'version',
      dataIndex: 'version',
      key: 'version',
      width: 80,
    },
    {
      title: 'health_score',
      dataIndex: 'health_score',
      key: 'health_score',
      width: 110,
      render: (score: number) => (
        <span style={{ color: getScoreColor(score), fontWeight: 'bold' }}>{score}</span>
      ),
    },
    {
      title: 'risk_level',
      dataIndex: 'risk_level',
      key: 'risk_level',
      width: 100,
      render: (risk: string) => getRiskTag(risk),
    },
    {
      title: 'issues',
      dataIndex: 'issues',
      key: 'issues',
      width: 100,
      render: (issues: string[]) => (
        <span>{issues?.length ?? 0}</span>
      ),
    },
  ];

  const expandedRowRender = (record: Rubric) => {
    if (!record.issues || record.issues.length === 0) {
      return <div style={{ padding: 8, color: '#999' }}>无问题</div>;
    }
    return (
      <Collapse
        items={record.issues.map((issue, idx) => ({
          key: idx,
          label: `Issue ${idx + 1}`,
          children: <div>{issue}</div>,
        }))}
      />
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Rubric 标准库 / 规则中心</h2>
        <Button type="primary" onClick={handleHealthCheck} loading={healthChecking}>
          健康检查
        </Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title="Rubric 总数" value={stats.total} valueStyle={{ color: '#1890ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="健康标准数" value={stats.healthy_count} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="风险标准数" value={stats.risk_count} valueStyle={{ color: '#fa8c16' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均健康分"
              value={stats.avg_health_score}
              valueStyle={{ color: getScoreColor(stats.avg_health_score) }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card>
            <Space wrap>
              <Input
                placeholder="搜索 criterion 文本"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                style={{ width: 240 }}
                allowClear
              />
              <Select
                placeholder="选择 dimension"
                value={filterDimension}
                onChange={setFilterDimension}
                style={{ width: 180 }}
                allowClear
              >
                {dimensions.map((d) => (
                  <Select.Option key={d} value={d}>{d}</Select.Option>
                ))}
              </Select>
              <Select
                placeholder="选择 priority"
                value={filterPriority}
                onChange={setFilterPriority}
                style={{ width: 160 }}
                allowClear
              >
                <Select.Option value="must_have">must_have</Select.Option>
                <Select.Option value="nice_to_have">nice_to_have</Select.Option>
              </Select>
              <Select
                placeholder="选择 type"
                value={filterType}
                onChange={setFilterType}
                style={{ width: 160 }}
                allowClear
              >
                <Select.Option value="objective">objective</Select.Option>
                <Select.Option value="subjective">subjective</Select.Option>
              </Select>
            </Space>
          </Card>
        </Col>
      </Row>

      <Spin spinning={loading || healthChecking}>
        {rubrics.length === 0 && !loading ? (
          <Empty description="暂无标准库数据">
            <Alert type="info" message="可从任务模板或标注结果中沉淀 Rubric 标准。当前模板中的评估维度（相关性、准确性、完整性、安全性）会自动识别为 Rubric。" style={{ marginTop: 8 }} />
          </Empty>
        ) : (
          <Table
            rowKey="rubric_id"
            columns={columns}
            dataSource={rubrics}
            expandable={{ expandedRowRender }}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 1200 }}
          />
        )}
      </Spin>
    </div>
  );
};

export default RubricLibraryPage;
