// 封装前端日志工具（模拟分级，方便生产环境控制输出）
export const logger = {
  debug: (message) => {
    // 开发环境才输出debug日志
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[DEBUG] ${new Date().toLocaleString()} - ${message}`);
    }
  },
  info: (message) => {
    console.info(`[INFO] ${new Date().toLocaleString()} - ${message}`);
  },
  warn: (message) => {
    console.warn(`[WARN] ${new Date().toLocaleString()} - ${message}`);
  },
  error: (message, error) => {
    console.error(`[ERROR] ${new Date().toLocaleString()} - ${message}`, error || '');
  }
};
