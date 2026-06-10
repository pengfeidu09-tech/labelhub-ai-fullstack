import React, { useEffect } from 'react';
import { Badge } from 'antd';
import { checkHealth } from '../../api/health';
import { useAppStore } from '../../stores/appStore';

export const ConnectionStatus: React.FC = () => {
  const isConnected = useAppStore((state) => state.isConnected);
  const setIsConnected = useAppStore((state) => state.setIsConnected);

  useEffect(() => {
    const check = async () => {
      try {
        await checkHealth();
        setIsConnected(true);
      } catch (_) {
        setIsConnected(false);
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, [setIsConnected]);

  return (
    <Badge status={isConnected ? 'success' : 'error'} text={isConnected ? '后端 API 正常' : '后端未连接，请启动 uvicorn'} />
  );
};
