/**
 * One locally selected joke per system calendar day.
 */
(() => {
  const STORAGE_KEY = "haizaiqidong.daily-joke.v1";
  const JOKE_LIBRARY = Object.freeze([
    [
      "尖塔四位围在篝火旁讲笑话",
      "",
      "战士站起来讲了一个关于烧牌的笑话，大家都笑了",
      "猎人站起来讲了一个关于运转的笑话，大家都笑了",
      "观者站起来讲了一个关于数值的笑话，大家都笑了",
      "鸡煲站起来，大家都笑了",
    ].join("\n"),
    [
      "A：看，这是我们的一座模拟舞台，台上有歌手机器人，吉他机器人，鼓手机器人，贝斯机器人，台下还有机器人负责鼓掌，运行效果很不错",
      "",
      "B：可是台上都演奏完成有一会了，台下怎么还不鼓掌呢？",
      "",
      "A：哦，鼓掌机器人还在启动",
    ].join("\n"),
    [
      "猎人、战士和观者走到火堆，发现了躺在地上的鸡煲，",
      "",
      "猎人说：“我觉得睡觉是很正常的，战损高休息是稳妥的选择。”",
      "战士说：“我也觉得如此，有时候敲位并没有那么紧张。”",
      "观者俯下身子看了看：“你们在说什么乱七八糟的，它好像死了。”",
    ].join("\n"),
    [
      "终于查到成绩了，696 分，我看完后泪如雨下，",
      "",
      "想起这高中三年，想起为我拼搏的父母，我赶紧拨通清华的电话",
      "",
      "但是他们说杀戮尖塔的分不算，还问我这点分我玩的故障机器人？",
    ].join("\n"),
    [
      "心脏让觉醒者阻击鸡煲，觉醒者最后回来说 “不好了”，心脏以为他输了，",
      "",
      "觉醒者说：鸡煲是阻击成功了，但旁边有两个 999 力量的咔咔往这边来了",
    ].join("\n"),
    [
      "谁是尖塔最强的角色？",
      "",
      "战士：鸡煲。",
      "猎人：看情况，但大概是鸡煲吧。",
      "观者：大概是鸡煲吧？如果考虑到第一层的抓牌，情况可能会不同？",
      "鸡煲：大红地精。",
    ].join("\n"),
    [
      "大鲸鱼说终局心脏会给你塞状态牌污染你的牌库导致核心组件沉底，而且它每回合会锁血，你伤害不够就打不过",
      "",
      "战士：什么是状态牌？",
      "猎人：什么是沉底？",
      "观者：什么是伤害不够？",
      "鸡煲：什么是心脏？",
    ].join("\n"),
    [
      "鸡煲和骨妹爬塔，发现了一个不错的遗物，都想要，于是鸡煲说，要不石头剪刀布吧，谁赢谁就拿走。",
      "",
      "骨妹：“什么是石头剪刀布？”",
      "鸡煲：“简单来说就是出手，谁更厉害就赢。”",
      "骨妹点了点头，侧过脑袋说 “奥斯提，揍他。”",
    ].join("\n"),
    [
      "老者弥留前，给三个儿子八十八块钱，说谁能用这些钱买的东西把房子装满，谁就能继承遗产。",
      "",
      "大儿子买了一堆稻草，却只填了房子的一小半，",
      "二儿子买了一只蜡烛，烛光照亮了几乎每个角落。大家都以为二儿子要继承遗产了，",
      "三儿子摇摇头，购买了杀戮尖塔直播了一把机器人，果然笑声充满了整个房间",
    ].join("\n"),
    [
      "铁甲战士：“我的逻辑很简单，只要我血够多，你就得死。”",
      "猎手：“我的逻辑很缜密，只要你毒够深，你就得死。”",
      "观者：“我的逻辑很完美，只要我算得准，你就得死。”",
      "机器人：“我的逻辑很复杂，只要我把这三个球激发顺序排对…… 哎呀，死早了。”",
    ].join("\n"),
  ]);

  let memoryRecord = null;

  function localDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function isValidRecord(record) {
    return !!record &&
      typeof record.date === "string" &&
      Number.isInteger(record.index) &&
      record.index >= 0 &&
      record.index < JOKE_LIBRARY.length;
  }

  function readRecord() {
    try {
      const record = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
      if (isValidRecord(record)) return record;
    } catch (_error) {
      // WebView storage can be unavailable in restricted environments.
    }
    return isValidRecord(memoryRecord) ? memoryRecord : null;
  }

  function writeRecord(record) {
    memoryRecord = record;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
    } catch (_error) {
      // The in-memory copy still keeps the joke stable for this session.
    }
  }

  function chooseIndex(previousIndex) {
    const count = JOKE_LIBRARY.length;
    if (count <= 1) return 0;
    if (!Number.isInteger(previousIndex) || previousIndex < 0 || previousIndex >= count) {
      return Math.floor(Math.random() * count);
    }

    // Choose among all entries except yesterday's so a date change is visible.
    const candidate = Math.floor(Math.random() * (count - 1));
    return candidate >= previousIndex ? candidate + 1 : candidate;
  }

  function getToday(date = new Date()) {
    const today = localDateKey(date);
    const previous = readRecord();
    if (previous && previous.date === today) {
      return JOKE_LIBRARY[previous.index];
    }

    const record = {
      date: today,
      index: chooseIndex(previous && previous.index),
    };
    writeRecord(record);
    return JOKE_LIBRARY[record.index];
  }

  window.DailyJoke = Object.freeze({ getToday });
})();
