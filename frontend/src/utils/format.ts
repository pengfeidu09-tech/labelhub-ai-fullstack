import dayjs from 'dayjs';

export const formatDate = (date: string) => {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss');
};

export const formatTaskName = (task: { name?: string; task_name?: string; id?: number }): string => {
  const raw = String(task.name || task.task_name || '').trim();
  if (!raw || raw === '????' || raw === '???') return `未命名任务 #${task.id || '?'}`;
  return raw;
};

export const formatPercent = (value: number | null | undefined): string => {
  if (value == null || isNaN(value)) return '0%';
  const pct = value * 100;
  if (Number.isInteger(pct)) return `${pct}%`;
  const rounded = Math.round(pct * 10) / 10;
  if (Number.isInteger(rounded)) return `${rounded}%`;
  return `${rounded}%`;
};

export const normalizeList = <T,>(res: any): T[] => {
  if (Array.isArray(res)) return res;
  if (Array.isArray(res?.items)) return res.items;
  if (Array.isArray(res?.data)) return res.data;
  if (Array.isArray(res?.tasks)) return res.tasks;
  if (Array.isArray(res?.templates)) return res.templates;
  if (Array.isArray(res?.datasets)) return res.datasets;
  if (Array.isArray(res?.exports)) return res.exports;
  if (Array.isArray(res?.results)) return res.results;
  if (Array.isArray(res?.dimensions)) return res.dimensions;
  if (Array.isArray(res?.rubrics)) return res.rubrics;
  return [];
};

const _lastErrorMessage = new Map<string, number>();

export const dedupMessage = {
  error: (content: string, cooldown = 3000) => {
    const now = Date.now();
    const last = _lastErrorMessage.get(content);
    if (last && now - last < cooldown) return;
    _lastErrorMessage.set(content, now);
    import('antd').then(({ message }) => message.error(content));
  },
  warning: (content: string, cooldown = 3000) => {
    const now = Date.now();
    const last = _lastErrorMessage.get(content);
    if (last && now - last < cooldown) return;
    _lastErrorMessage.set(content, now);
    import('antd').then(({ message }) => message.warning(content));
  },
};
