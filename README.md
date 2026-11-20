# 课程辅导效果检验 · Tutor Effect

知行职教教研组用真实的两组成绩评估晚间小组辅导效果，贯通成绩复核、辅导方案、后台统计检验、结论签核和结果导出。

## 业务场景
知行职教有城东、城西、滨江、高新 4 个教学点。原流程由教学点导出成绩表，分析员复制进工作簿计算，再将截图发给负责人。三类痛点是：排除缺考时容易丢失口径、方案与结果脱节、签核结论没有当时的样本证据。上游是教学点期末成绩；本应用替代手工核对与计算；下游由教研负责人决定是否扩大辅导试点。

五个业务模块：**成绩样本**支持筛选、录入和修订；**辅导分组**登记研究范围和排除规则；**资格批次**按入学分门槛登记各期门槛与入学分，锁定后形成资格名册，实际参辅另行登记；**检验工作台**提交后台任务并查看失败原因与历史结果，主视图是按门槛断点估计实际参辅局部效果，附保留原两组 Welch 比较；**教研结论**起草解释、负责人签核并下载包括原始样本快照的 JSON 报告。业务数据均在 PostgreSQL 中持久化，统计由 Python worker 计算。

### 为什么按门槛而不是直接比两组
直接比较参辅组与未参辅组会把“本来基础更好”混入效果。资格批次把入学分门槛登记为外生规则：入学分越过门槛才获得辅导资格，但资格不等于实际参辅。以门槛为断点、实际参辅为处理变量做模糊断点（fuzzy RD），估计断点处合规者的局部平均效应（LATE），而不是全体平均效应。

### 资格批次流程
1. 草稿：登记批次名称、期次、门槛、方向（≥ / ≤）、每侧最少人数与不同入学分、最低参辅率跳变，再逐条登记候选人及其入学分。
2. 锁定：两阶段提交，先把批次置为 `locking`，写入资格名册与校验码后再置为 `locked`。中途崩溃时批次停在 `locking`，可“恢复原批”回到草稿；重试锁定沿用同一批次，`(batch_id, student_id)` 唯一约束保证不会重复建名册。已锁定批次再次锁定直接复用原名册。
3. 实际参辅：锁定后逐人登记，与资格名册分开存储；每次变更都会让既有断点报告失效。
4. 勘误：锁定后门槛、方向、某人的入学分或参辅状态只能通过勘误修改。勘误递增批次修订号、刷新名册校验码，并使该批全部报告立即失效（含已签核报告）。重算会基于当前修订生成新报告，旧报告保留失效标记与原因。

### 断点估计口径
- 断点：入学分门槛；处理变量：实际参辅；结局：结课成绩。
- 编译器：局部线性 2SLS（三角核），断点两侧各自截距与斜率，资格指示作工具变量。报告实际参辅 LATE、95% 区间、参辅率跳变及区间、结课成绩跳变（简约式）、第一阶段 F 或完全合规提示。
- 带宽：默认 `auto_min_side_n`，只使用入学分分布与名册人数——从门槛对称向外扩展，直到两侧各达到最少人数与不同分数要求；**选择带宽时完全不看结课成绩**，报告中记录该依据（`uses_outcome: false`）。也可手动固定带宽，规则相同。
- 识别假设（随报告与导出保存）：入学分不可精确操纵；断点处其他因素对结课成绩无跳跃；参辅对入学分单调；排除性约束（资格仅通过参辅影响成绩）；效应仅适用于带宽内合规者。
- 拒绝因果结论：入学分过于离散（任一侧不同取值少于 3 个或门槛质量点超过 20%）、参辅率跳变低于批次设定下限、第一阶段 F < 10、带宽内样本不足、资格标记与门槛规则不一致。拒绝时仍保留简约式与参辅率证据，但不能签核为有效因果结论。
- 并发安全：勘误与发布都先锁定批次行（PostgreSQL `FOR UPDATE`，SQLite 测试下另有进程内锁）。发布前校验报告修订号等于批次当前修订号，勘误后所有报告立即标为失效，因此并发不会漏标；已失效报告的重算生成新报告并用 `recomputed_from_id` 关联。

## 启动
```sh
cp .env.example .env
docker compose up -d --build
# 可选：手动幂等 seed
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18202 。API http://localhost:19202/docs 。数据库端口 17702。停止并清空演示数据：`docker compose down -v --remove-orphans`。Compose 顶层 name 保证中文父目录也能运行。

|角色|账号|密码|权限|
|---|---|---|---|
|教研负责人 admin|admin@demo.local|Demo123!|全部编辑、统计、结论签核发布、审计|
|教研分析员 analyst|analyst@demo.local|Demo123!|成绩/方案编辑、检验、未签核结论起草；不能签核或改已签核结论|
|教学点观察员 viewer|viewer@demo.local|Demo123!|只读台账、方案、报告及导出；不能发起计算|

JWT 有效期 8 小时；角色由服务器读取数据库，不信任客户端显示。密码使用随机盐 PBKDF2-SHA256 180000 次，登录不保存明文密码。

## 一天的工作剧本
1. 08:50 观察员打开 `ZX-2026-001` 学员记录，核对缺考标记。
2. 09:00 分析员查看学员台账，按城东教学点筛选。
3. 09:10 录入 `ZX-2026-161`，学员161，城东，小组辅导组，82.5 分。
4. 09:20 将缺考学员标记为缺考并清空成绩，避免把零分当缺失。
5. 09:30 新建 `2026秋季 · 城东晚间辅导` 方案，选城东并排除缺考（保留的观察性比较）。
6. 09:40 登记资格批次：门槛 60、入学分逐条录入，锁定资格名册并核对校验码。
7. 09:50 登记实际参辅；断点检验提交后台任务，页面显示排队、完成、证据不足或失败。
8. 10:00 查看看板：断点两侧样本、越线参辅/未越线却参辅人数、参辅率跳变、LATE 与 95% 区间、带宽依据与识别假设。
9. 10:05 发现一条入学分录入错误，登记勘误；该批所有报告立即失效，重算后新报告恢复可发布。
10. 10:10 负责人签核结论；分析员不能修改已签核报告，证据不足的结果不能签核为因果结论。
11. 10:20 观察员下载 `rd-report-<id>.json` 或 `tutor-effect-report-<id>.json`，复核样本快照与校验码。

## 算法与口径
输入是方案教学点内两组 0–100 分成绩。空成绩永远排除；开启排除缺考时再排除 absent=true 的成绩。显示总选中数和排除数。有效样本每组至少 2 条；两组方差都为零时任务失败且保留可读原因。

以干预组减对照组定义 Δ。Welch t = Δ / sqrt(s1²/n1+s0²/n0)，自由度使用 Welch-Satterthwaite 公式；双侧 p 值和 95% 区间通过 SciPy t 分布计算。Cohen d 使用两组自由度加权 pooled 标准差，描述效应大小，与 Welch 方差假设相互独立。显著性 α 固定为 0.05。观察性分组不能直接做因果断言。

seed 使用 Random(20261115)：160 名学员，4 教学点、各 80 人两组、7 条缺考记录；初始方案为 `2026秋季 · 晚间小组辅导`，初始报告为便于演示的真实计算结果。另生成 120 人的 `2026秋季 · 入学分60资格批次`（同时含越线未参辅与门槛下侧参辅样本）并已锁定，用于断点演示；`RD-2026-*` 学员为演示用，不计入原有 160 人台账故事。seed 以 email/code/title 自然键查重，已存在对象不更新，重跑不覆盖用户修改。报告保存计算样本快照与校验码；后续成绩修订不会改旧报告。

## 技术与结构
|层|技术|
|---|---|
|前端|原生 HTML/CSS/ES Modules、Nginx 1.27，无构建依赖|
|后端|Python 3.11、FastAPI 0.115.6、SQLAlchemy 2.0.36|
|统计|SciPy 1.14.1|
|数据与队列|PostgreSQL 16、Redis 7，独立 Python worker|
|认证|PyJWT 2.10.1、PBKDF2|

`frontend/src/api` 负责请求，`stores` 管业务状态，`pages` 分五页，`components/common` 复用结果、表格、状态和通知，`hooks` 封装表单/轮询，`utils` 做转义/下载。`backend/src/models` 定义表，`schemas` 验证，`services` 处理业务与算法（`eligibility.py` 批次/名册/勘误，`rd.py` 断点估计，`rd_reports.py` 结果生命周期），`routes` 提供接口，`controllers` 序列化，`middlewares` 处理审计和全局错误。`backend/migrations/001_initial.sql` 与 `002_eligibility_rd.sql` 记录结构；启动使用 metadata.create_all，后续字段迁移需人工管理。

共享枚举位置：角色 ROLES、分组 GROUPS、报告状态 REPORT_STATUSES、断点报告状态 RD_REPORT_STATUSES、批次状态 ELIGIBILITY_BATCH_STATUSES、资格方向 ELIGIBILITY_DIRECTIONS 在 `backend/src/constants/enums.py`；前端对应 `frontend/src/constants/enums.js` 的 ROLES、GROUPS、STATUS、RD_STATUS、BATCH_STATUS、SIDE。API 输入的 group、direction、bandwidth_rule 枚举同时在 `backend/src/schemas/business.py` 校验。

## Docker 与环境变量
恰好五服务：frontend/backend/worker/db/redis，各有健康检查。backend 和 worker 依赖健康 DB/Redis，frontend 依赖 backend；worker 依赖 backend 初始化完成。数据库、Redis AOF、报告产物预留共享卷分别命名。worker 真正从 Redis 唤醒并处理数据库待执行任务，每 2 秒更新心跳。Redis 任务通知丢失仍会扫描数据库待执行任务。计算结果权威存于数据库，shared reports 卷供未来文件归档；当前 JSON 按快照直接导出。

`.env.example` 列出 COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、POSTGRES_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET（默认 10.253.103.0/24）。所有变量均可覆盖；默认是本地演示配置，外部部署前需更换密码和 JWT_SECRET。`.env` 已忽略。每次最多允许 10 个待执行任务，HTTP 429 提示等待。

## 本地开发
后端在 Python3.11 虚拟环境运行 `pip install -r backend/requirements.txt`，设置 DATABASE_URL、REDIS_URL、JWT_SECRET，进入 backend 后运行 `uvicorn src.main:app --reload` 和另一个终端 `python -m src.worker`。前端无打包步骤，可直接由 Nginx 提供静态文件并代理 /api/。

测试（SQLite + 伪队列，无需 PostgreSQL/Redis）：`cd backend && python -m pytest tests -q`。覆盖锁定幂等与中断恢复、勘误失效与重算、勘误/发布并发、弱跳变与离散分数拒绝、带宽与结课成绩无关、前端读取字段契约。

## 已知范围
不含 CSV 批量导入、随机分组器或多重比较校正；成绩与入学分可逐条录入/修订。教学点为自由文本，前端方案选项来自现有成绩。初始报告为同步真实计算的演示快照，新提交报告全部走异步 worker。外网字体不可用时使用本地 serif 回退。进程中断在 running 状态的任务需管理员在数据库重置为 queued；当前小型版本未提供任务取消/自动回收。资格批次锁定中断可“恢复原批”，但 running 报告不会自动回收。审计列表只给管理员，最多最近 100 条。断点是单一门槛；多门槛、协变量调整与带宽敏感性曲线尚未包含。

License: MIT（见 LICENSE）。真实验收证据在批次根 `test-artifacts/gb-3103/`，源码目录不含截图或测试报告。
