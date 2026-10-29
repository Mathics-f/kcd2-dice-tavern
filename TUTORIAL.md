# 上手教程：从零到"群友来一局"

这是给第一次看到这个仓库的人写的。看完你会知道：怎么把它跑起来、怎么玩、怎么接进自己的 QQ 机器人、怎么挂到公网上，以及哪儿可以改。

---

## 0. 先看看这是什么

一句话：**《天国：拯救 2》酒馆里那副骰子，用普通骰子做的网页版，旁边坐着一个会嘴硬的 AI 陪练。**

不需要数据库、不需要前端构建、不需要第三方 Python 包，一个 `python server.py` 就全起来了。

```
你掷 6 颗 → 挑要留的计分骰 → 剩下的重掷 → 觉得够了就收分 → 换她
先到 4000 分的人赢。留不出任何计分骰 = 爆骰，这一手的分清零。
```

规则细节见 [README](README.md#规则kcd2-那套)，这里不重复。

---

## 1. 五分钟跑起来

### 环境

- Python 3.9+（Windows 装的时候记得勾 "Add python.exe to PATH"）
- 一张能跑的网卡就行，不需要 npm / node / docker

### 跑

```bash
git clone 本仓库
cd dice-tavern
python server.py
```

浏览器会自动打开 <http://127.0.0.1:8790>，点右上角「开一局」。

Windows 用户也可以直接双击 `启动牌馆.bat`。

想换端口：

```bash
python server.py --port 8791
```

### 玩

1. **掷骰**：六颗骰子飞出来
2. **留**：点桌上你想留的骰子（会变亮），点「留所选」；懒得选就点上面推荐的组合（「1+5 = 150」「三个4 = 400」这种）
3. **继续掷**：桌上只剩没留的骰子被重掷
4. **收分**：够了就点「收分」落袋，换对面
5. 空格 / 回车 = 掷骰（或留所选），键盘也能玩

她会根据自己的分数、差多少、还剩几颗骰子考虑要不要再来一手。想要她更莽/更怂，右上角「她的手气」调。

---

## 2. 让它认出你（可选，但体验差很多）

默认情况下，浏览器访问的人都会被当成"陌生人"，她对你客客气气，不撒娇不叫爸爸。
想让她把你当主人：

复制 `config_local.py.example` 为 `config_local.py`，填上：

```python
OWNER_QQ = "你自己的QQ号"      # 群里发骰子时认你
OWNER_IPS = "你的公网IP"       # 从外面访问页面时认你（本机/局域网会自动认）
```

这个文件已经写进 `.gitignore`，不会被提交。不想建文件也可以：

```bash
# Windows PowerShell
$env:DICE_OWNER_QQ = "123456789"; python server.py

# Linux / macOS
DICE_OWNER_QQ=123456789 python server.py
```

效果：她开口前会先知道对面是谁——主人来了会撒娇、耍赖、输了嘟囔；陌生人来了客气收着。
页面右上角有枚小徽章写着「对面：爸爸 · 她认出你了」或「对面：陌生的酒客」，一眼能看出来。

---

## 3. 接进自己的 QQ 机器人

`qq_bridge.py` 是给机器人用的**薄客户端**，它只做三件事：把消息丢给牌馆、拿回一段文字、牌馆没开就自己把服务拉起来。

### 3.1 你的机器人得先能收消息

任何能跑 OneBot v11 的框架都行：NapCat、LLOneBot、Lagrange、go-cqhttp 等。
以 NapCat 为例（也是最常用的）：

1. 装 NapCat，登录你的 QQ 小号
2. 打开 WebUI（默认 `http://127.0.0.1:6099/webui`），配置：
   - **HTTP 服务**：随便开一个端口（比如 3000）
   - **反向 WebSocket**：`ws://127.0.0.1:3001`
3. 你的机器人脚本连 `ws://127.0.0.1:3001`，收到 `post_type == "message"` 的事件

### 3.2 在消息入口插三行

```python
import qq_bridge

async def on_message(event):
    text = event["raw_message"]
    gid  = event.get("group_id")
    uid  = event["user_id"]
    nick = event["sender"].get("card") or event["sender"].get("nickname")

    reply = await asyncio.to_thread(
        qq_bridge.try_handle, text, gid is not None, gid, uid, nick
    )
    if reply:
        await send_group_msg(gid, reply)   # 或按行拆成最多 3 条
        return                             # 骰子指令到此为止，别再丢给大模型
    ... # 不是骰子指令，照常聊天
```

就这么点。不是骰子指令时 `try_handle` 返回 `None`，你的机器人毫无感知。

### 3.3 群里怎么玩

```
骰子开局          开一桌，你先掷
骰子 掷           掷
骰子 留 1 5       留下点数为 1 和 5 的骰子
骰子 全留         能留的都留下
骰子 收           收分
骰子 状态         看牌面
骰子 加入         别人也能坐下（最多 5 人 + 她）
骰子 退出         撤桌
```

> 💡 回复是按行拆的，`qq_bridge` 已经把每条控制在 3 行以内 —— 大多数 QQ 框架单条消息太长了会难看。

### 3.4 牌馆没开？

不用管。第一次有人发「骰子开局」时，`qq_bridge` 会用 `pythonw` 在后台把 `server.py` 拉起来（约 1~2 秒），之后一直复用。
想让机器人连别的机器上的牌馆：设 `DICE_TAVERN_URL=http://那台机器:8790`。

---

## 4. 让她"本人"下场（可选，要花点小钱）

默认她其实是个**期望值算法**：把 6 颗骰子所有可能性枚举一遍，算出"留哪几颗接着掷平均还能拿多少分"，零 token、零延迟。

但如果你给了 DeepSeek 的 API Key，右上角「她的脑子」可以切成 **DeepSeek 本人**：
把比分、桌面骰子、所有合法留法写成一屏提示，问模型"你挑哪手、收不收"，顺带让她回一句嘴硬台词。

### 配置

项目根目录建一个 `secrets.json`（已在 `.gitignore`）：

```json
{"deepseek_api_key": "sk-你的Key"}
```

或者直接环境变量 `DEEPSEEK_API_KEY`。Key 在 <https://platform.deepseek.com> 申请。

### 成本

实测一整局打到 4000 分：

- 约 **25 次调用**、**1 万 token**、两三毛钱人民币
- 每次决策 1 秒左右，页面会显示「她在盘算……」

QQ 那边默认**还是本地算法**（省 token）；想让她在群里也真动脑：

```bash
# Windows
$env:DICE_BRAIN = "model"; python server.py
# Linux
DICE_BRAIN=model python server.py
```

### 不会翻车

没 Key、断网、超时、回的不是合法 JSON、挑了不存在的留法 —— 任何一步出错都自动退回本地算法，游戏不会卡、她也不会犯规。
调试想看她每次想了什么都行：`DICE_BRAIN_VERBOSE=1`。

---

## 5. 挂到公网上给朋友玩

### 5.1 直接开

```bash
python server.py --host 0.0.0.0 --port 8790
```

有公网 IP / 内网穿透的话，朋友就能用 `http://你的地址:8790` 来玩。

### 5.2 正经一点：nginx + systemd

`server.py` 默认只监听 `127.0.0.1`，建议用反代挂出去。

nginx 片段：

```nginx
server {
    listen 443 ssl;
    server_name dice.example.com;

    location / {
        proxy_pass http://127.0.0.1:8790;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

systemd 服务（`/etc/systemd/system/dice-tavern.service`）：

```ini
[Unit]
Description=Dice Tavern
After=network.target

[Service]
WorkingDirectory=/home/you/dice-tavern
ExecStart=/usr/bin/python3 server.py --quiet --no-browser
Restart=always
Environment=DICE_BEHIND_PROXY=1

[Install]
WantedBy=multi-user.target
```

两个容易踩的坑：

1. **`DICE_BEHIND_PROXY=1` 必须开**，否则 nginx 转发的 `127.0.0.1` 会被当成"主人"，所有访客都会看到她撒娇。
2. 想让自己的公网 IP 也被认成主人，填 `DICE_OWNER_IPS`（支持 `1.2.3.*`）。

不想折腾 systemd 的，仓库里的 `start.sh` 会循环拉起服务，`nohup bash start.sh &` 也能用。

---

## 6. 想改点自己的东西？

| 想改 | 去哪儿 |
| --- | --- |
| 她叫什么、什么脾气、说话像谁 | `persona.py` 里的 `PERSONA` / `TONE` |
| 收分门槛（多少分就收） | `ai.py` 的 `STYLE` 字典 |
| 默认目标分、玩家名字 | 页面右上角能选；代码里改 `rules.DEFAULT_TARGET`、`server._make_table` |
| 计分规则 | `rules.py` 顶部的 `SINGLE / TRIPLE / STRAIGHTS` 三张表 |
| 爆骰的抖动/音效 | `web/style.css` 的 `shakeBust`、`web/app.js` 的 `thud()` |
| 页面配色 | `web/style.css` 顶部那几个 `:root` 变量 |
| 加个骰子点数图案、换字体 | `web/app.js` 的 `PIPS` / 字体引用 |

改之前强烈建议先看一遍 `rules.py`——它是计分的唯一真相，`ai.py` 和页面都只消费它的结果。

---

## 7. 测试

```bash
python -m unittest discover -s tests -v
```

17 条用例：三同/四同/顺子/非法组合、留骰合法性、洗手重掷、爆骰时骰子停在桌上、认人（QQ 号/本机/公网/反代）、期望值表。改完规则跑一下，心里有底。

---

## 8. 隐私与安全

- 仓库里**没有任何**密钥、QQ 号、IP、服务器地址；认人的 id 全从 `config_local.py` / 环境变量读
- `secrets.json`、`config_local.py`、`ev_cache.json`、`__pycache__/` 都在 `.gitignore`
- 你的 API Key 只在你自己的进程里，服务端不会转发给别人
- 公网部署时记得设 `DICE_OWNER_IPS`，不然所有访客都会被当成陌生人（这也挺好的，安全）

---

## 9. 常见问题

**Q：她怎么不说话了 / 一直都是那几句固定的话？**
A：正常。没配 DeepSeek Key 时她用本地台词池，就是那几句。想看模型版就按第 4 节配 Key，然后右上角切「DeepSeek 本人」。

**Q：群里的「骰子 xxx」没反应？**
A：三个地方查：① 机器人进程是不是重启过（钩子代码生效需要重启）；② `DICE_TAVERN_URL` 指对了没；③ 日志里有没有 `骰子酒馆接口已挂上`。

**Q：页面能玩，QQ 里却说她"没认出你"？**
A：`DICE_OWNER_QQ` / `config_local.py` 里的号跟你现在登的 QQ 号对不上。改完重启 `server.py`。

**Q：手机上能玩吗？**
A：能，页面是响应式的，只是骰子小一点、点选没那么舒服。

**Q：能加特殊骰（徽章、恶魔之首、幸运骰）吗？**
A：故意没加。这个仓库就还原"那副普通骰子"，想要花哨的可以自己加，`rules.py` 的 `_score` 表改起来不难。

**Q：许可证？**
A：MIT，随便用，注明来源就行。

---

## 10. 想贡献？

欢迎 PR / issue。几个方向：

- 更多台词风格（和 `ai.py` 的 `STYLE` 对齐）
- 移动端交互优化
- 接入其它聊天平台（Telegram、Discord）——走 `/api/qq/command` 那个接口就行，把 `qqtext.py` 换个外壳
- 多语言（i18n）

提 PR 前跑一下 `python -m unittest discover -s tests -v`，谢谢。
