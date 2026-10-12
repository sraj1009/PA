// mood 枚举的中文叫法只有一个来源：雷达、树洞、聊天都读这里，
// 免得同一个 joy 在两个页面上一个显示"开心"一个显示"愉悦"。
const ORDER = ['joy', 'calm', 'anxious', 'angry', 'low'];

const LABELS = {
  joy: '开心',
  calm: '平静',
  anxious: '焦虑',
  angry: '生气',
  low: '低落',
};

function label(m) {
  return LABELS[m] || '未标注';
}

module.exports = { ORDER, LABELS, label };
