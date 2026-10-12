// 周边好店示例目录：店名、坐标、评分、营业时间为演示数据，非真实商户信息。
// 距离不写死，由页面按定位（或校内基准点）用 haversine 现算，坐标即唯一事实来源。
const ORIGIN = { name: '校园中心广场', lat: 30.5152, lng: 114.4308 };

const cats = [
  { id: 'meal', label: '吃饭' },
  { id: 'coffee', label: '咖啡饮品' },
  { id: 'study', label: '自习' },
  { id: 'life', label: '生活服务' },
  { id: 'fun', label: '休闲' },
];

const shops = [
  {
    id: 's01', name: '老门面馆', cats: ['meal'], lat: 30.5121, lng: 114.4336,
    rating: 4.5, price: 1, open: [7, 21],
    desc: '后街口上的牛肉面，汤底现熬', tips: ['加辣提前说', '午高峰 12:00 后要等位'], tags: ['面食', '性价比'],
  },
  {
    id: 's02', name: '一人食小碗菜', cats: ['meal'], lat: 30.5118, lng: 114.4329,
    rating: 4.2, price: 2, open: [10, 21],
    desc: '小份现炒，一个人也能吃两三个菜', tips: ['可以点半份', '米饭免费加'], tags: ['家常菜', '一人食'],
  },
  {
    id: 's03', name: '南门烧烤', cats: ['meal', 'fun'], lat: 30.5102, lng: 114.4295,
    rating: 4.3, price: 2, open: [18, 2],
    desc: '晚上十点以后最热闹，翻台快', tips: ['招牌是烤茄子', '周末要拿号'], tags: ['夜宵', '聚会'],
  },
  {
    id: 's04', name: '食堂三楼自选餐', cats: ['meal'], lat: 30.5136, lng: 114.4312,
    rating: 4.0, price: 0, open: [6, 20],
    desc: '校内窗口里性价比最高的一层', tips: ['出锅最快的是小炒档', '刷卡比现金便宜'], tags: ['食堂', '性价比'],
  },
  {
    id: 's05', name: '轻食沙拉吧', cats: ['meal'], lat: 30.5168, lng: 114.4281,
    rating: 4.1, price: 3, open: [10, 21],
    desc: ' gym 旁边，可以自选热量', tips: ['鸡胸要提前订', '酱汁另放更脆'], tags: ['健身餐', '素食'],
  },
  {
    id: 's06', name: '咖啡馆（校内）', cats: ['coffee', 'study'], lat: 30.5141, lng: 114.4302,
    rating: 4.6, price: 2, open: [8, 22],
    desc: '有插座的位置在东侧靠墙', tips: ['下午两点后最吵', '美式可以续杯'], tags: ['咖啡', '办公'],
  },
  {
    id: 's07', name: '茶饮实验室', cats: ['coffee'], lat: 30.5129, lng: 114.4341,
    rating: 4.4, price: 1, open: [9, 23],
    desc: '后街奶茶里糖度选择最细的一家', tips: ['三分糖比五分好喝', '新品周三上架'], tags: ['奶茶', '甜品'],
  },
  {
    id: 's08', name: '手冲小馆', cats: ['coffee'], lat: 30.5175, lng: 114.4330,
    rating: 4.8, price: 3, open: [9, 20],
    desc: '老板会讲豆子产地，适合慢慢坐', tips: ['单一产区按当日豆单', '不能外带杯子'], tags: ['精品咖啡', '安静'],
  },
  {
    id: 's09', name: '通宵自习空间', cats: ['study'], lat: 30.5159, lng: 114.4321,
    rating: 4.2, price: 2, open: [0, 24],
    desc: '按小时计费的付费自习室，有独立隔间', tips: ['靠窗位要提前预约', '静音仓在里间'], tags: ['自习', '通宵'],
  },
  {
    id: 's10', name: '图书馆咖啡角', cats: ['study', 'coffee'], lat: 30.5148, lng: 114.4291,
    rating: 4.3, price: 1, open: [8, 22],
    desc: '馆内二楼，买完直接上楼自习', tips: ['靠窗位七点后满', '不允许大声交谈'], tags: ['自习', '咖啡'],
  },
  {
    id: 's11', name: '共享打印中心', cats: ['life', 'study'], lat: 30.5144, lng: 114.4325,
    rating: 4.0, price: 0, open: [8, 23],
    desc: '论文打印装订一站式', tips: ['双面比单面便宜', '装订要等 20 分钟'], tags: ['打印', '论文'],
  },
  {
    id: 's12', name: '北门便利店', cats: ['life'], lat: 30.5126, lng: 114.4283,
    rating: 4.1, price: 0, open: [0, 24],
    desc: '唯一 24 小时亮着灯的店', tips: ['关东煮十点后打折', '可代收快递'], tags: ['便利店', '夜宵'],
  },
  {
    id: 's13', name: '驿站快递点', cats: ['life'], lat: 30.5115, lng: 114.4276,
    rating: 3.9, price: 0, open: [9, 20],
    desc: '寄件比校外网点便宜两元', tips: ['傍晚取件人最多', '大件要提前电话'], tags: ['快递', '寄件'],
  },
  {
    id: 's14', name: '剪发工作室', cats: ['life'], lat: 30.5109, lng: 114.4318,
    rating: 4.4, price: 2, open: [10, 21],
    desc: '学生价，Tony 不推销办卡', tips: ['周五晚上要预约', '可以带参考图'], tags: ['理发', '学生价'],
  },
  {
    id: 's15', name: '宿舍楼下洗衣房', cats: ['life'], lat: 30.5172, lng: 114.4268,
    rating: 4.0, price: 1, open: [6, 23],
    desc: '滚筒 6 台，扫码启动', tips: ['周日下午最空', '烘干机要另计费'], tags: ['洗衣', '生活'],
  },
  {
    id: 's16', name: '篮球场旁器材店', cats: ['life', 'fun'], lat: 30.5191, lng: 114.4334,
    rating: 4.2, price: 2, open: [9, 21],
    desc: '球、护具、鞋垫都能补', tips: ['可现场穿线', '学生证九折'], tags: ['运动', '器材'],
  },
  {
    id: 's17', name: '桌游吧', cats: ['fun'], lat: 30.5105, lng: 114.4344,
    rating: 4.5, price: 2, open: [13, 2],
    desc: '两百多款本子，主持人会带局', tips: ['工作日下午便宜', '可以自带游戏'], tags: ['桌游', '社交'],
  },
  {
    id: 's18', name: '校园影院', cats: ['fun'], lat: 30.5183, lng: 114.4259,
    rating: 4.3, price: 1, open: [14, 23],
    desc: '小厅排片偏艺术片', tips: ['周二学生半价', '爆米花可续'], tags: ['电影', '约会'],
  },
  {
    id: 's19', name: '花艺工作室', cats: ['fun', 'life'], lat: 30.5162, lng: 114.4348,
    rating: 4.7, price: 3, open: [10, 20],
    desc: '生日花束当天可取', tips: ['提前一天订更便宜', '单支也卖'], tags: ['花艺', '礼物'],
  },
  {
    id: 's20', name: '修理铺', cats: ['life'], lat: 30.5131, lng: 114.4271,
    rating: 4.1, price: 0, open: [8, 19],
    desc: '修自行车、换锁、配钥匙', tips: ['补胎十分钟', '周日只到中午'], tags: ['维修', '自行车'],
  },
];

module.exports = { ORIGIN, cats, shops };
