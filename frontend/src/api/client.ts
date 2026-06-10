import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 统一中文错误提示拦截器
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 不在这里弹 toast，只转换 error.message 为中文，方便各页面 catch 块使用
    if (error.response) {
      const status = error.response.status;
      const detail = error.response.data?.detail || error.response.data?.message || '';
      switch (status) {
        case 401:
          error.message = '鉴权失败，请重新登录';
          break;
        case 403:
          error.message = '无访问权限';
          break;
        case 404:
          error.message = detail || '请求接口不存在，请检查后端服务';
          break;
        case 400:
          error.message = detail || '请求参数不正确';
          break;
        case 429:
          error.message = '请求过于频繁，请稍后重试';
          break;
        case 500:
          error.message = detail || '服务器内部错误，请稍后重试';
          break;
        case 502:
        case 503:
          error.message = '服务暂时不可用，请稍后重试';
          break;
        default:
          if (status >= 500) error.message = detail || '服务器错误，请稍后重试';
          else if (status >= 400) error.message = detail || `请求失败 (${status})`;
      }
    } else if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      error.message = '请求超时，请稍后重试';
    } else if (error.message === 'Network Error') {
      error.message = '网络连接失败，请检查后端服务是否启动';
    }
    return Promise.reject(error);
  }
);
