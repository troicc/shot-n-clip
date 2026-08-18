# Editorial V2 — V1 旧图审计（2026-08-17）

审计对象：`work/z-WfDn_0AWE/outputs/`（Bill Gurley TED《How to Build a Career
You Love》，pack 前身 = selection.json 单组 6 句），以及
`publish_xhs.md` / `publish_wechat.md`。V1 成图与文案已备份到 /tmp 供
comparison_before_after.jpg 使用。

## 1. 原文可信度 — 中风险

- V1 的 `source_text` 均可回溯到字幕（validate 有硬校验），这点成立。
- 但 `display_en` 存在一处**越权清理**：q04 原文是
  "When you're learning about something you don't like, it saps your energy,
  … When you learn about something you're fascinated by, you get energy…"
  两句，V1 首版 display_en 直接改写成
  "Learning what you don't like saps your energy. Learning what fascinates
  you gives it back."——**"gives it back" 是改写，不是清理**（原文没有
  "gives … back" 结构）。这正是 V2 §八 要求 token-diff 审计要拦下的类别。
- q01–q03、q05、q06 的 display_en 属于允许范围（标点/破折号统一）。

## 2. 中文自然度 — 明显翻译腔（V2 §一.4 点名）

- q05「着迷的人，会留下很大的脚印。」——"leave big footprints" 直译，
  中文里「留下很大的脚印」不是自然表达，读者第一反应可能是字面脚印。
- q03「着迷自带机制：你会「自动地」去钻研。」——「自带机制」是
  mechanism 的机翻腔；「自动地」加「地」生硬，且嵌套引号排版突兀。
- q02「该追的是着迷，不是热情——热情不会带来行动。」——「该追的是」
  尚可，但整句是英文语序镜像（"You should follow X, not Y"）。
- q06「这个世界最需要的，也许是更多的一句话伯乐。」——「一句话伯乐」
  是自造词，原文 Uncle Richard 是具体人物指代，翻译丢失了「人」的具象。

## 3. 命名实体 — 有幻觉风险的改写

- q06 把 **Uncle Richard**（具体人物、演讲中的核心角色）意译成
  「一句话伯乐」——属于 V2 §七 明确禁止的「人名/昵称自由意译」。
  原人物在字幕中反复出现（s24 处 "Uncle Richard can tell something's
  not right" 等多处），本可锁定为「Richard 叔叔」。
- q01 演讲者 Bill Gurley 在图内未标注（speaker 字段有但未渲染），
  文案里也只是顺带提到，来源归属弱。

## 4. 语气与逻辑 — 有强化倾向

- q01 原文 "Obsessive and continuous learning is not an input — it's an
  output. It's not the cause, it's the effect." 本身是并列双句；V1 中文
  「持续而痴迷的学习不是原因，是结果。」删掉了第二层（cause/effect 与
  input/output 是同义强调），可接受；但「痴迷」比 obsessive 略情绪化。
- q06 "Maybe all the world really needs…" 的 **maybe**（保留意见）在
  「这个世界最需要的，也许是…」中保留了，合格。
- 整组没有出现绝对化断言，但「该追的是着迷，不是热情」比原句
  "you should follow your fascination"（建议语气）略强。

## 5. 重复句式 — AI 模板腔初现

- 6 句中文里有 3 句使用「A，是 B」/「A，不是 B」判断句式
  （q01 不是…是…、q02 是…不是…、q05 会…）。
- q01+q02 连续两句都是「不是/不是」结构，节奏雷同（V2 lint 规则 3、9）。

## 6. 英文断行 — 基本合格但有隐患

- 实测图上未发现单词中间断行（V1 换行器按字符累积，英文恰好都在空格
  处回车），但算法是「逐字符试宽」，**没有任何单词边界约束**——遇到
  长单词贴边时可能拆词。这是靠运气而非靠规则。
- q01 英文 95 字符 2 行，最后一行 "It's not the cause, it's the effect."
  偏短但可读；未实现 widow guard。

## 7. 每张图主题连贯性 — 成立但单薄

- 6 句确实围绕「着迷 vs 热情」形成 Hook→Problem→Insight→Evidence→
  Method→Close 推进（V1 已按此选句）。
- 但演讲里至少还有 3 个独立可发布主题被浪费：
  a) Danny Meyer 90% 降薪转行做餐饮的完整故事弧；
  b) AI 时代静态技能贬值 vs 着迷者的 jetpack（Mark Cuban 二分法）；
  c) 「安全工作不再安全」+ 简历军备竞赛的制度批判线。
- 一视频只出一张 → V2 §十 的多 pack 缺失。

## 8. 发布文案泛化 — 是

- `publish_xhs.md` 标题候选 2/3/5 是纯模板句（「从这期访谈里，我记住
  了这6句话」「用 XX 的框架，重新审视…」），换成任何视频都成立——
  违反 V2 §十二.2「必须指出该 pack 的具体矛盾、机制或启发」。
- 导语只复述了角度承诺句，没有给出该演讲独有的信息（如 Danny 降薪
  90% 这类具体事实）。
- `publish_wechat.md` 结构完整，但「每句上下文」直接复用了
  selection_reason（内部编辑理由如 "Hook：全场核心论点"），不是给读者
  看的上下文——暴露了内部字段当文案用的问题。

## 9. 其他工程性发现

- `bin/qcard validate/build` 相对路径解析 bug（交付报告已声明）。
- 字幕为 **auto 生成**（asr），专名 Danny/Eleven Madison/Gramercy Tavern
  等靠字幕本身无法 100% 确认，V2 需进入 entity glossary + 人工复核队列。
- V1 渲染器 zh/en 字号窗口是全局常量，未按条带高度实测计算（恰好
  合格，但不满足 V2 §十四.5 的「先算行数再定字号」）。

## 10. 旧产物路径（供对比）

- 旧图：`work/z-WfDn_0AWE/outputs/{01_zh,02_en,03_bilingual}.png`
- 旧选句：`work/z-WfDn_0AWE/selection.json`
- 旧文案：`work/z-WfDn_0AWE/outputs/publish_{xhs,wechat}.md`
- 备份：`/tmp/v1_{01_zh,02_en,03_bilingual}.png`、`/tmp/v1_{xhs,wechat}.md`
- V2 产物目标：`work/z-WfDn_0AWE/packs/<pack-id>/`（不覆盖旧 outputs/）
