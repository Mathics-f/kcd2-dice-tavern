# 🎲 骰子酒馆 dice-tavern

《天国：拯救 2》酒馆里那副骰子，用**普通骰子**还原的小游戏。
浏览器里自己玩，也可以接进自己的 QQ 机器人，让 AI 坐对面陪你打。

纯 Python 标准库，没有第三方依赖；页面也就一个 HTML + 一个 CSS + 一个 JS。

> 👉 **第一次来？** 看 [TUTORIAL.md](TUTORIAL.md)：从零跑起来 → 接进自己的 QQ 机器人 → 挂到公网，一步步写好了。

![规则](https://img.shields.io/badge/rules-Farkle%2FKCD2-amber) ![python](https://img.shields.io/badge/python-3.9%2B-blue)

## 目录

```
dice-tavern/
├── rules.py        计分 / 牌桌规则（唯一真相）
├── ai.py           期望值算法 + 本地台词
├── brain.py        让模型本人拍板（可选，失败自动退回 ai.py）
├── persona.py      让模型说一句 / 人设（可选）
├── identity.py     认人：是主人还是陌生人
├── qqtext.py       QQ 文本层：认指令、排版面
├── qq_bridge.py    给 QQ 机器人用的薄客户端（自动把服务拉起来）
├── server.py       本地服务 + 页面 + HTTP 接口
├── web/            index.html / style.css / app.js
├── tests/          单测
├── TUTORIAL.md     面向新人的上手教程
├── config_local.py 本地私人配置（模板见下，已 gitignore）
└── 启动牌馆.bat     Windows 双击启动
```

## 怎么玩

```
python server.py
```

浏览器自动打开 <http://127.0.0.1:8790>，点右上角「开一局」。

- 点桌上骰子挑要留的 → 「留所选」；也可以直接点上方推荐好的组合
- 留完继续「掷骰」，够了就「收分」落袋
- 空格 / 回车 = 掷骰（或留所选）
- 右上角还能选「她的手气」（心软/正常/心狠）和「她的脑子」（期望值算法 / DeepSeek 本人）

## 规则（KCD2 那套）

先到 4000 分赢（右上角可改 2000 / 4000 / 6000）。

| 组合 | 分 |
| --- | --- |
| 单颗 1 / 单颗 5 | 100 / 50 |
| 1-2-3-4-5 | 500 |
| 2-3-4-5-6 | 750 |
| 1-2-3-4-5-6（一条龙） | 1500 |
| 三同 1 / 2 / 3 / 4 / 5 / 6 | 1000 / 200 / 300 / 400 / 500 / 600 |
| 四同、五同、六同 | 三同基础上 ×2 / ×4 / ×8 |

一回合：

1. 掷出手上所有的骰子
2. **至少留一颗计分骰**，剩下的重掷（留不出任何计分骰 = 爆骰，本回合分清零）
3. 觉得够了就收分，换人
4. 六颗全留下 = 洗手重掷：本回合的分留着，六颗骰子全回来

爆骰不会一闪而过：不点数的骰子会红着脸抖一下停在桌上，看清楚"就是这几颗白瞎了"，
过一会儿才收场换人，配一声闷「咚」和 1.25 秒的慢速抖。

没有特殊骰、没有徽章、没有恶魔之首 —— 就一副干净的普通骰子。

## 接进自己的 QQ 机器人

`qq_bridge.try_handle(text, is_group, gid, uid, nick)` 是唯一需要调的入口：

```python
# 在你机器人的消息入口（拿到 text/gid/uid/nick 之后），先问牌馆一句：
import qq_bridge
reply = qq_bridge.try_handle(text, is_group, gid, uid, nick)
if reply:                  # 是骰子指令，牌馆已经处理完，直接回给群
    send_text(reply)
    continue               # 别再把这条丢给大模型
```

- 不是骰子指令 → 返回 `None`，你的机器人照常聊天
- 牌馆没开也没关系：`qq_bridge` 会用 `pythonw` 静默拉起 `server.py`（`DICE_TAVERN_URL` 可改地址）
- 返回文本按行拆成最多 3 条消息比较合适（微信/QQ 的常规限制）

群里直接说：

```
骰子开局          # 开一桌，你先掷
骰子 掷           # 掷骰子
骰子 留 1 5       # 留下点数为 1 和 5 的骰子（照着桌面上的点数报）
骰子 全留         # 一把把能留的都留下
骰子 收           # 收分落袋
骰子 状态         # 看牌面
骰子 规则         # 玩法说明
骰子 加入         # 别人也能坐下（最多 5 个人 + 她）
骰子 退出         # 撤桌
```

## 配置（都不进仓库）

复制 `config_local.py.example` 为 `config_local.py`，按需填写；或者用环境变量：

| 变量 | 作用 |
| --- | --- |
| `DICE_OWNER_QQ` | 这些 QQ 号发指令时，她认成「主人」（逗号分隔） |
| `DICE_OWNER_IPS` | 这些公网 IP 访问页面时认成主人（支持 `1.2.3.*`） |
| `DICE_BEHIND_PROXY=1` | 服务在 nginx 等反代后面时打开，免得把反代的 127.0.0.1 误认成主人 |
| `DICE_SECRETS` | `secrets.json` 路径（默认：项目目录下 `secrets.json`） |
| `DEEPSEEK_API_KEY` | DeepSeek 密钥（优先级高于 secrets.json） |
| `DICE_BRAIN=model` | 让 QQ 那边也用模型拍板（默认本地算法，省 token） |
| `DICE_BRAIN_VERBOSE=1` | 打印每次模型调用和 token 数 |
| `DICE_BRAIN_TIMEOUT` | 模型调用超时秒数（默认 12） |
| `DICE_TAVERN_URL` | 页面对外的服务地址（默认 `http://127.0.0.1:8790`） |

`secrets.json` 只需要一个字段：

```json
{"deepseek_api_key": "sk-你的密钥"}
```

## 她是谁（可选）

默认她就是一副本地台词 + 期望值算法，不需要任何密钥。
想让她「本人」下场：填上 DeepSeek 密钥，右上角「她的脑子」选「DeepSeek 本人」。
每次决策把比分/桌面/所有合法留法写成一屏短提示问模型，实测一整局到 4000 分约 **25 次调用、1 万 token**；
任何一步失败（没密钥/断网/超时/返回不合法/挑了不存在的留法）都自动退回本地算法，游戏不会卡住。

她还会认人（`identity.py`）：主人来了会撒娇嘴硬，陌生人来了客气收着。

## HTTP 接口

服务默认 `127.0.0.1:8790`，纯标准库：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/ping` | 活着没 |
| GET | `/api/whoami` | 当前访客被认成谁 |
| GET | `/api/table?id=` | 取牌桌快照 |
| GET | `/api/qq/tables` | 群里正在打的桌子 |
| POST | `/api/new` | `{name,target,style,brain}` 开一张自己的桌 |
| POST | `/api/action` | `{id,seat,op,indices}`，op = roll/keep/bank/settle |
| POST | `/api/bot_turn` | 让她把这一回合走完，返回每一步 |
| POST | `/api/qq/command` | `{chat,uid,nick,text}` → `{reply}` |
| POST | `/api/qq/push` | 走 NapCat 往群里发一句 |
| POST | `/api/say` | 让她针对当前牌面说一句 |

## 测试

```
python -m unittest discover -s tests -v
```

## 隐私

这个仓库不含任何密钥、QQ 号、IP 或服务器信息：

- `secrets.json`、`config_local.py`、`ev_cache.json`、`__pycache__/` 都在 `.gitignore` 里
- 认人用的主人 QQ/IP 只从配置读，没有硬编码
- 想公开部署：`server.py --host 0.0.0.0 --port 8790` 或挂在 nginx 后面（记得 `DICE_BEHIND_PROXY=1` 并透传 `X-Forwarded-For`）
