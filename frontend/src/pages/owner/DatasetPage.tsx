import React, { useState, useEffect } from 'react';
import { PageHeader } from '../../components/common/PageHeader';
import { Card, Table, Button, Modal, Tag, Spin, Empty, Statistic, Row, Col } from 'antd';
import { EyeOutlined, DatabaseOutlined, FileTextOutlined, CalendarOutlined } from '@ant-design/icons';
import { apiClient } from '../../api/client';
import { formatDate } from '../../utils/time';

interface Dataset {
  id: number;
  name: string;
  dataset_type: string;
  description: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

interface DatasetItem {
  id: number;
  task_id: number;
  dataset_type: string;
  status: string;
  raw_data_json: {
    prompt?: string;
    model_answer?: string;
    reference?: string;
    [key: string]: any;
  };
  created_at: string;
}

const DatasetPage: React.FC = () => {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [visibleModal, setVisibleModal] = useState(false);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [datasetItems, setDatasetItems] = useState<DatasetItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);

  useEffect(() => {
    fetchDatasets();
  }, []);

  const fetchDatasets = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/datasets/list');
      setDatasets(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch datasets:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDatasetItems = async (datasetType: string) => {
    setItemsLoading(true);
    try {
      const response = await apiClient.get('/datasets', {
        params: { dataset_type: datasetType, limit: 50 }
      });
      setDatasetItems(response.data.items || []);
    } catch (error) {
      console.error('Failed to fetch dataset items:', error);
    } finally {
      setItemsLoading(false);
    }
  };

  const handleViewItems = (dataset: Dataset) => {
    setSelectedDataset(dataset);
    fetchDatasetItems(dataset.dataset_type);
    setVisibleModal(true);
  };

  const statusColors: Record<string, string> = {
    imported: 'blue',
    unclaimed: 'gray',
    claimed: 'orange',
    drafting: 'yellow',
    submitted: 'green',
    approved: 'green',
    rejected: 'red',
    rejected_to_modify: 'red'
  };

  const statusLabels: Record<string, string> = {
    imported: '已导入',
    unclaimed: '未领取',
    claimed: '已领取',
    drafting: '草稿',
    submitted: '已提交',
    approved: '已通过',
    rejected: '已拒绝',
    rejected_to_modify: '待修改'
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '数据集名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'dataset_type',
      key: 'dataset_type',
      render: (text: string) => (
        <Tag color="purple">{text}</Tag>
      ),
    },
    {
      title: '数据项数量',
      dataIndex: 'item_count',
      key: 'item_count',
      render: (count: number) => (
        <span className="font-semibold">{count}</span>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string) => (
        text ? formatDate(text) : '-'
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: Dataset) => (
        <Button
          type="primary"
          icon={<EyeOutlined />}
          onClick={() => handleViewItems(record)}
        >
          查看数据项
        </Button>
      ),
    },
  ];

  const totalItems = datasets.reduce((sum, ds) => sum + ds.item_count, 0);

  return (
    <div className="p-6">
      <PageHeader title="数据集" subtitle="管理数据集" />
      
      {/* 统计卡片 */}
      <Row gutter={16} className="mb-6">
        <Col span={8}>
          <Card>
            <Statistic
              title="数据集总数"
              value={datasets.length}
              prefix={<DatabaseOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="数据项总数"
              value={totalItems}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="更新时间"
              value={datasets.length > 0 ? formatDate(new Date().toISOString()) : '-'}
              prefix={<CalendarOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* 数据集表格 */}
      <Card title="数据集列表" variant="borderless">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spin size="large" />
          </div>
        ) : datasets.length === 0 ? (
          <Empty description="暂无数据集" />
        ) : (
          <Table
            dataSource={datasets}
            columns={columns}
            rowKey="id"
            pagination={false}
          />
        )}
      </Card>

      {/* 查看数据项弹窗 */}
      <Modal
        title={selectedDataset ? `${selectedDataset.name} - 数据项` : '数据项列表'}
        open={visibleModal}
        onCancel={() => setVisibleModal(false)}
        width={1000}
        footer={null}
      >
        {itemsLoading ? (
          <div className="flex justify-center py-8">
            <Spin size="large" />
          </div>
        ) : datasetItems.length === 0 ? (
          <Empty description="该数据集暂无数据项，请先导入数据" />
        ) : (
          <Table
            dataSource={datasetItems}
            columns={[
              {
                title: 'ID',
                dataIndex: 'id',
                key: 'id',
                width: 60,
              },
              {
                title: '类型',
                dataIndex: 'dataset_type',
                key: 'dataset_type',
                width: 120,
                render: (text: string) => <Tag color="purple">{text || '-'}</Tag>,
              },
              {
                title: '题目/Prompt',
                dataIndex: 'raw_data_json',
                key: 'prompt',
                width: 180,
                render: (data: any) => (
                  <span style={{ maxWidth: 180, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data?.prompt || data?.question || data?.source_text || '-'}</span>
                ),
              },
              {
                title: '待评估模型回答',
                dataIndex: 'raw_data_json',
                key: 'model_answer',
                width: 180,
                render: (data: any) => (
                  <span style={{ maxWidth: 180, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data?.model_answer || data?.candidate_answer || data?.answer || '-'}</span>
                ),
              },
              {
                title: '参考答案',
                dataIndex: 'raw_data_json',
                key: 'reference',
                width: 160,
                render: (data: any) => (
                  <span style={{ maxWidth: 160, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data?.reference || data?.reference_answer || '-'}</span>
                ),
              },
              {
                title: '难度',
                dataIndex: 'raw_data_json',
                key: 'difficulty',
                width: 80,
                render: (data: any) => data?.difficulty || '-',
              },
              {
                title: '状态',
                dataIndex: 'status',
                key: 'status',
                width: 90,
                render: (status: string) => (
                  <Tag color={statusColors[status] || 'gray'}>
                    {statusLabels[status] || status || '-'}
                  </Tag>
                ),
              },
            ]}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            scroll={{ y: 400 }}
          />
        )}
      </Modal>
    </div>
  );
};

export default DatasetPage;