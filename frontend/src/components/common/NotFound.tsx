import { Result, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

const NotFound: React.FC = () => {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="404"
      subTitle="页面不存在或路由未配置，请返回任务详情。"
      extra={<Button type="primary" onClick={() => navigate(-1)}>返回上一页</Button>}
    />
  );
};

export default NotFound;