import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

const DISPLAY_TIMEZONE = 'Asia/Shanghai';

/**
 * 解析后端返回的时间字符串为 dayjs 对象。
 * 如果字符串没有时区信息（无 Z、无 +08:00），按 UTC 解析。
 */
export const parseServerTime = (value: string | number | null | undefined): dayjs.Dayjs | null => {
  if (value == null) return null;
  const str = String(value).trim();
  if (!str) return null;
  // 如果有时区信息（Z 或 +HH:MM），dayjs 会自动处理
  if (/[Zz]$/.test(str) || /[+-]\d{2}:\d{2}$/.test(str)) {
    return dayjs(str);
  }
  // 无时区信息，按 UTC 解析
  return dayjs.utc(str);
};

/**
 * 格式化为北京时间完整日期时间：YYYY-MM-DD HH:mm:ss
 */
export const formatDateTime = (value: string | number | null | undefined): string => {
  const d = parseServerTime(value);
  if (!d || !d.isValid()) return '-';
  return d.tz(DISPLAY_TIMEZONE).format('YYYY-MM-DD HH:mm:ss');
};

/**
 * 格式化为北京时间短日期时间（省略年）：MM-DD HH:mm:ss
 */
export const formatDateTimeShort = (value: string | number | null | undefined): string => {
  const d = parseServerTime(value);
  if (!d || !d.isValid()) return '-';
  return d.tz(DISPLAY_TIMEZONE).format('MM-DD HH:mm:ss');
};

/**
 * 格式化为北京时间日期+时分（省略秒）：YYYY-MM-DD HH:mm
 */
export const formatDateMinute = (value: string | number | null | undefined): string => {
  const d = parseServerTime(value);
  if (!d || !d.isValid()) return '-';
  return d.tz(DISPLAY_TIMEZONE).format('YYYY-MM-DD HH:mm');
};

/**
 * 格式化为日期：YYYY-MM-DD
 */
export const formatDate = (value: string | number | null | undefined): string => {
  const d = parseServerTime(value);
  if (!d || !d.isValid()) return '-';
  return d.tz(DISPLAY_TIMEZONE).format('YYYY-MM-DD');
};

/**
 * 格式化时长（秒 → HH:MM:SS 或 MM:SS）
 */
export const formatDuration = (seconds: number | undefined | null): string => {
  const s = Math.floor(Number(seconds) || 0);
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};
