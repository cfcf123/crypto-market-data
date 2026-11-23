# 用户固定执行规则（长期有效）

本文件记录用户明确要求，适用于所有新旧 ChatGPT 对话窗口。执行任务前必须遵守，不得因换窗口、上下文变化或定时工作流配置而遗忘。

## 一、数据采集触发规则
1. 禁止每 10 分钟自动采集。
2. 禁止任何 cron 定时采集、定时 watchdog、过期自动刷新或后台自动派发采集。
3. 只有用户明确发出“执行一次任务”“严格执行一次任务”等执行指令时，才启动本次采集。
4. 每次用户指令都必须创建或更新仓库根目录的 manual-trigger.txt，并 push 到 main，以此启动一次全新的 GitHub Actions 采集。
5. 每次触发标记必须唯一，包含本次执行标识和 UTC 时间，避免误认其他运行。
6. 不允许用无关文档提交代替本次任务触发；不允许复用上一次运行的 Artifact，即使上一次数据仍在 10 分钟以内。
7. 用户没有要求执行任务时，不得自行触发采集。

## 二、每次执行的强制核验
1. 等待本次 push 对应的 GitHub Actions 完成。
2. 必须核对本次运行的 head SHA 与触发提交一致。
3. 必须确认单元测试、数据采集、数据校验、分析生成和 Artifact 上传步骤状态。
4. 必须下载本次 run 对应的 Artifact，并核对 run_id、run_number、SHA、生成时间及文件完整性。
5. 不再单独执行下载后数据年龄/新鲜度门槛核验；每次任务均通过新的 manual-trigger.txt push 启动采集，并且只使用该次运行对应的 Artifact。仍须确认 Artifact 与本次 run 的 SHA、run_id、run_number 对应。
6. 若采集、Artifact 下载、文件完整性或关键字段解析失败，明确报告 DATA_UNAVAILABLE；不得拿旧运行的 Artifact 冒充本次结果，不得编造实时价格和交易点位。

## 三、交易报告要求
1. BTCUSDT 与 ETHUSDT 都必须分析。
2. 报告开头优先给出交易点位和多空/观望权重。
3. 每个币种必须覆盖四种策略：左侧回调做多、左侧反弹做空、右侧突破做多、右侧跌破做空。
4. 每个策略应给出入场/触发价、止损、TP1、TP2、触发条件及盈亏比；条件不成立时也必须列出，并说明原因。
5. 多头、空头、观望权重合计 100%，权重代表证据倾向，不代表胜率。
6. Binance Spot 价格可用时作为参考价；K线同一币种不得混用交易所来源。关键数据源基差超过 0.5% 时必须醒目警告并暂停相关实际执行建议。
7. 必须遵循仓库中的 TASK_REPORT_OUTPUT_RULES.md 及其他既有策略规则，不得擅自删减。

## 四、邮件规则
只有在用户要求发送邮件或对应定时任务明确要求发送时才发送。邮件收件人固定为 cao2026feng@outlook.com。邮件正文与聊天报告必须是同一份完整报告；未完成本次数据核验，不得发送完整交易报告邮件。

## 五、修改规则
未经用户明确同意，不得恢复定时采集、自动 watchdog 或后台刷新。任何修改均不得降低以上数据核验和交易报告要求。

## 六、当前唯一允许的采集触发模式
用户明确指令 -> 更新 manual-trigger.txt -> push main -> 等待本次 Actions -> 下载并核验本次 Artifact -> 生成 BTC/ETH 报告。

**核心原则：按用户指令采集；不按时间自动采集。**


## Same-time cross-exchange basis validation (mandatory)
- Never compare Binance Spot live price with a previous candle close to determine exchange basis. Candle close age is not a live quote timestamp.
- Collector must timestamp every secondary live ticker independently (cross_exchange[].observed_at) and timestamp the Binance Spot reference (spot_price.observed_at).
- Compare only valid positive live prices whose timestamps differ by no more than 30 seconds .
- Calculate basis as abs(secondary_live_price - Binance_spot_price) / Binance_spot_price * 100. A verified same-time difference above 0.5% sets execution_allowed=false and execution_status=paused_basis_mismatch.
- If no secondary live quote passes timestamp-alignment checks, set execution_allowed=false and execution_status=paused_basis_unverified. Missing data must never be interpreted as zero basis.
- Do not scale ATR, EMA, swing highs/lows, or other candle structure by the ratio between a live spot price and a stale candle close. Keep candle-derived levels in the source candle series native price scale.
- Preserve conditional levels for observation, but clearly pause live execution when basis is mismatched or unverified. Automated tests must cover stale-close false positives, aligned live prices below/above threshold, and missing/misaligned timestamps.


## 左侧预埋策略规则（永久固定，EMA20不得一票否决）
1. BTCUSDT、ETHUSDT必须独立评估左侧回调做多与左侧反弹做空；不得仅因EMA20相对现价的位置不符合旧条件而判定不可用。
2. EMA20/EMA50仅为辅助评分因素，不是硬性门槛；均线一致加分，不一致减分，但不得单独否决。
3. 左侧做空独立检查现价上方有效前高/摆动高点/结构压力；左侧做多独立检查现价下方有效前低/摆动低点/结构支撑。结构缺失、与现价重叠或距离超过8 ATR，方可因结构证据不足判定不可用。
4. 可用候选必须提供入场区间、止损、TP1、TP2、风险收益比、结构依据、质量评分/等级和收盘K线确认条件。评分低于60仅观察，不建议挂单；预埋价不等于成交。
5. 评分综合大周期趋势、结构位置/距离及EMA20/EMA50辅助方向。成交量拒绝、供需区、成交密集区、VWAP、斐波那契、威科夫等仅在数据实际可用时纳入，不得假称已计算。
6. 止损置于结构失效位置之外；止盈在有利方向，TP1/TP2顺序正确，盈亏比有效。
7. 不得取消本次 Push 与本次 Artifact 的对应关系、Binance参考价、同币种K线来源一致、基差超过0.5%暂停执行、用户手动Push触发及四类策略完整输出等既有保护。


## 威科夫结构确认模块（WYCKOFF-SEQUENCE-V2，永久固定）
1. BTCUSDT、ETHUSDT及各可用周期独立分析；只使用同一交易所、已收盘OHLCV，不混合成交量或K线来源。
2. 多头结构按Spring候选（可选）→ SOS候选 → SOS后回踩测试 → LPS确认；空头结构按UTAD候选（可选）→ SOW候选 → SOW后反抽测试 → LPSY确认。Spring/UTAD不是必需条件。
3. SOS筛选条件：收盘有效突破此前结构区间阻力、上涨K线收盘位置靠近高点（至少70%）、成交量不低于此前均量1.15倍、K线波幅不低于此前平均波幅1.20倍。SOW按相反方向对称判定（收盘跌破支撑、收盘位置不高于30%、量能至少1.15倍、波幅至少1.20倍）。阈值是保守筛选参数，不是市场定律。
4. SOS/SOW只能先标记候选/等待测试。SOS后LPS确认需在突破位附近回踩、收盘守住原突破位、测试阶段成交量均值低于突破K线的80%、平均波幅低于突破K线的85%，并出现方向性拒绝及后续跟进。SOW后LPSY按镜像规则判定。
5. 若回踩/反抽收盘重新进入原区间，标记突破失败；若测试量能或波幅未收缩，标记测试弱/未确认；数据不足时标记等待，不得补造事件。
6. 报告展示结构区间、Spring/UTAD候选、SOS/SOW状态、LPS/LPSY状态、突破/测试位置、量能/波幅相对值、失效条件及对应周期。状态区分“未发现、候选、等待确认、已确认、失败、数据不足”。
7. 多周期证据冲突时明确披露（例如周线SOW、4小时SOS），不得只选择有利方向的周期。威科夫证据仅作有限权重辅助，不得覆盖多周期趋势、价格结构或风险约束。
8. 单点OI、资金费率或单根放量阳线不得用来断言空头回补/挤空。缺少连续OI变化、强平数据和主动买卖成交流（taker flow）时，必须写“无法区分真实需求与空头回补”。
9. SOS/LPS与SOW/LPSY是结构证据，不是自动交易指令；实际点位仍由四类策略引擎独立计算。EMA20/EMA50只参与辅助评分，不能单独否决左侧策略。


## 消息面与事件风险采集（NEWS-COLLECTION-V1，永久固定）
1. 每次用户触发的新采集必须收集最近7天新闻；新闻失败不得阻断价格/K线采集，但必须披露来源成功/失败数、文章数及可信度限制。
2. 覆盖BTC/ETH与加密监管、现货ETF资金流、美国经济与美联储/FOMC、特朗普/白宫/国会政策、地缘政治/制裁/战争、英伟达/黄仁勋/AI芯片/半导体、Binance/CZ/CoinGlass及交易所风险。
3. 来源包括Google News主题RSS，以及美联储、SEC、白宫官方RSS。重要公司/监管/央行公告优先引用官方原文；重大事件尽可能用Reuters/AP/Bloomberg/FT交叉核验。保留标题、发布方、发布时间、抓取时间、原文链接、分类及来源状态。
4. 重大事件（央行决议、战争/制裁、重大监管、交易所破产/黑客、ETF批准/资金异常、头部公司CEO变动、Nvidia/AI产业链重大事件）必须单独列出；黄仁勋/Nvidia高层变化为重点关键词。
5. 区分“已核实事实、市场可能的传导机制、尚未证实的推断/假设”；不得把相关性写成因果关系，不得仅凭标题判断方向。
6. 分别说明BTC和ETH的影响路径：美元/美债利率/流动性、全球风险偏好、科技股与纳指相关性、监管/ETF资金、加密行业自身风险；区分直接影响与间接情绪影响。
7. 报告提供正面/负面/中性事件、重要性、影响期限（即时/1-3天/1-4周）、BTC影响、ETH影响、确认数据及是否构成暂停交易条件。
8. 经济日历、ETF每日净流、CoinGlass清算和官方社交媒体动态若结构化来源未成功获取，标记未获取/不可用，不得用RSS标题冒充实时数据。
9. 新闻优先级关键词只作初筛，最终方向由分析确定；新闻不直接改变点位，不自动生成交易指令。消息面与技术面冲突时明确披露并下调信号可信度。
10. RSS覆盖不完整，逐源报告成功/失败并保留链接与抓取时间。


## 安全做空备选进场规则（SAFE-SHORT-ENTRY-V1，永久固定）
1. 若左侧反弹做空评分不足、结构不支持或风险收益不合格，报告不得只写“不推荐做空”；必须继续独立评估右侧确认型空单，分别给出“压力位确认做空”和“有效跌破后反抽做空”两类候选方案。
2. 压力位确认做空：先标出压力区与观察价；只有价格到达压力区后出现可验证的转弱证据（如关键周期收盘受阻/重新跌回压力区下方、冲高回落、量价转弱或结构性低点被破坏）才可列为确认进场。不得把触及压力位本身视为触发。
3. 跌破后反抽做空：先要求关键支撑被指定周期的闭合K线有效跌破；再等待反抽原支撑/突破位附近，确认收盘无法重新站回且出现卖压/拒绝信号后才考虑进场。未完成反抽确认不得追空。
4. 两类方案均必须给出具体入场区间、触发周期与收盘条件、止损价及结构失效理由、TP1、TP2、预估R倍数/盈亏比、取消条件；点位须基于本次新鲜数据计算，不得沿用旧报告价位或为凑数编造。
5. 明确区分“预埋观察价/提醒价”与“确认进场价”。观察价仅用于提醒，不代表可直接挂单；若需等待收盘确认，应明确写“条件单/提醒，不提前成交”。
6. 若左侧评分低于60分，仍只列观察价并注明“仅观察、不建议挂单”。右侧方案也须经过风险收益和结构有效性评估；不满足时明确写“无安全空单”，给出等待条件，不强行提供可执行单。
7. 优先考虑“跌破后反抽失败”这一确认路径，但不得机械固定；若压力位拒绝信号更清晰、止损更合理，可将其列为首选。若行情单边下跌且无反抽，不追空，等待下一结构。
8. BTC与ETH分别评估，不能因两者相关性而复制同一入场价/触发条件。消息面与技术面冲突、数据基差异常或采集失败时降低信号等级，必要时暂停给出可执行点位。
9. 报告在左侧策略不推荐时，仍需展示首选安全空单方案、次选方案（若存在）、触发/失效条件及“当前是否已触发”；任何方案均非自动交易指令，不代用户下单。


## 四类策略独立机会权重（STRATEGY-OPPORTUNITY-WEIGHTS-V1，永久固定）
1. BTCUSDT、ETHUSDT分别为四种策略计算独立机会权重：左侧回调做多（left_pullback_long）、右侧突破做多（right_breakout_long）、左侧反弹做空（left_rebound_short）、右侧跌破做空（right_breakdown_short）。
2. 另设“暂无合格机会/观望”（no_trade）权重。以上五项在每个币种内合计必须严格为100.0%（显示精度修正后）。
3. 四类策略机会权重与原有“多头/空头/观望”方向权重是两个不同维度：原有方向权重保留且合计100%；策略权重用于比较四种进场路径的相对优先级，不得相互替代。
4. 每项策略同时输出0–100的strategy_score和strategy_weight_pct；报告总览展示五项百分比，并在每个策略详细栏目重复标注对应权重，避免只在总览出现。
5. 权重由本次分析的多周期证据、左侧结构质量、数据覆盖率和周期冲突度计算。左侧结构不可用时，该左侧策略权重必须为0；不得为凑齐四类而伪造可用性或价格。
6. 右侧突破/跌破权重表示方向与策略质量的相对倾向，不表示触发已发生。必须独立标明触发状态；仍须等待指定闭合K线确认，未触发不得追单。
7. no_trade权重须随数据覆盖不足、周期冲突、策略质量偏低而上升。若所有策略质量均弱，应由no_trade占据主要权重；不得为了压低观望权重而人为抬高某一方向。
8. 策略权重不是胜率、盈利概率、仓位比例或资金分配建议；不得直接按权重下单或按比例配置资金。策略质量分、权重、信号等级和实际触发状态必须分栏呈现。
9. 报告与邮件均须包含BTC、ETH的四类策略权重和no_trade权重，并检查五项合计100.0%；字段缺失、非数值或合计错误时，明确标记策略权重生成/读取失败，不得自行编造补齐。
