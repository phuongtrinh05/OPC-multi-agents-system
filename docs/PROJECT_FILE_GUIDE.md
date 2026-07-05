# OPC Multi-Agent System - File Guide

Tai lieu nay tong hop vai tro cua cac file chinh trong project `OPC-multi-agents-system`.
Muc dich la giup giai thich code khi demo, review voi ban giam khao, hoac onboarding thanh vien khac trong team.

> Luu y: file `.env` co chua token/API key, khong dua vao slide, repo public, hoac bai nop.

## 1. Tong Quan He Thong

He thong demo mot workflow danh gia co hoi kinh doanh cua OPC theo kien truc multi-agent:

1. Lay du lieu tu MotherDuck bang SQL thong qua DuckDB.
2. Backend Flask dieu phoi workflow tung buoc.
3. Cac agent xu ly data, finance, AI/NLP reasoning, risk, decision va partner matching.
4. Frontend hien thi tung man hinh agent, handoff payload va Human-in-the-loop gate.
5. Founder la nguoi chot cuoi; agent chi dua ra khuyen nghi.

Workflow chinh:

```text
MotherDuck SQL Data
    -> Flask API
    -> Orchestrator
    -> Data Intake & Screening Agent
    -> Founder Shortlist HITL
    -> Finance + AI/NLP Tool inside Data & Finance Agent
    -> Founder AI Review HITL
    -> Risk & Compliance Agent
    -> Founder Risk Review HITL
    -> Decision & Partner Agent
    -> Founder Final Approval
    -> Post-decision Automation / External Release Gate
```

## 2. File Chay Chinh

### `main.py`

Day la Flask web server cua project.

Vai tro chinh:

- Serve giao dien tai `/`.
- Cung cap API doc bang du lieu.
- Cung cap API workflow tung buoc co Human-in-the-loop.

API quan trong:

```text
GET  /
GET  /api/tables
GET  /api/opportunities
GET  /api/opportunity/<contract_id>/decision
POST /api/workflow/start
POST /api/workflow/<workflow_id>/ai-reasoning
POST /api/workflow/<workflow_id>/risk
POST /api/workflow/<workflow_id>/decision
```

Y nghia cac workflow endpoint:

- `/api/workflow/start`: chi chay intake/screening, chua chay finance sau.
- `/api/workflow/<id>/ai-reasoning`: sau khi Founder approve shortlist moi chay finance va AI/NLP.
- `/api/workflow/<id>/risk`: sau khi Founder approve AI reasoning moi chay Risk Agent.
- `/api/workflow/<id>/decision`: sau khi Founder approve risk moi chay Decision & Partner Agent.

## 3. Lop Ket Noi Data

### `connector.py`

Day la file ket noi MotherDuck va chay SQL.

He thong ket noi MotherDuck bang DuckDB:

```python
duckdb.connect("md:")
```

Sau do chon database:

```sql
USE "OPC Database"
```

Ham doc bang chinh:

```python
read_table(table_name, limit)
```

Ben trong ham nay co chay SQL:

```sql
SELECT *
FROM "main"."<table_name>"
LIMIT <limit>
```

Ket qua SQL duoc tra ve thanh pandas DataFrame de agent xu ly.

### `normalize_motherduck.py`

Dung de upload/normalize Excel Team Pack len MotherDuck.

Vai tro:

- Doc cac sheet trong Excel.
- Tao bang tren MotherDuck.
- Chuan hoa ten bang/cot neu can.
- Phuc vu buoc chuan bi data truoc khi demo.

## 4. Orchestrator

### `opportunity_agent.py`

Day la file dieu phoi cac agent.

Vai tro:

- Load cac bang can dung tu MotherDuck.
- Chon danh sach hop dong de demo/test.
- Goi tung agent theo dung thu tu business workflow.
- Gom output thanh JSON tra ve frontend.

Ham quan trong:

```python
list_opportunities()
evaluate_opportunity()
run_data_finance_step()
run_ai_reasoning_step()
run_risk_step()
run_decision_step()
```

Ham load data:

```python
def _load_tables():
    conn = get_connector()
    return {name: conn.read_table(name, 10_000) for name in TABLE_NAMES}
```

Nghia la orchestrator goi `connector.py`, sau do `connector.py` chay SQL len MotherDuck.

## 5. Thu Muc `agents`

Thu muc nay chua tung agent rieng de tach nhiem vu ro rang.

### `agents/data_finance_agent.py`

Agent nay xu ly intake, screening va finance.

Hien da tach thanh 2 phase de dung luong business:

#### `run_intake_screening`

Chay buoc 1-2:

- Loc hop dong can danh gia.
- Tao Opportunity Profile.
- Join customer, contract, orders, products, invoices, alerts.
- Kiem tra data readiness.
- Danh gia customer payment risk.
- Danh gia margin, payment terms, service segment fit.
- Danh gia feasibility.
- Tao gateway flags.

Phase nay chua tinh finance sau. Sau phase nay can Founder shortlist confirmation.

#### `run_finance_after_shortlist`

Chay buoc 3, chi sau khi Founder approve shortlist:

- Tinh `total_open_ar`.
- Tinh `total_estimated_cost`.
- Doi chieu `09_CASHFLOW`.
- Xac dinh `cashflow_gap_flag`.
- Quet tin hieu bank-service trong `payment_terms` va `delivery_note`.
- Xac dinh `funding_need`.

### `agents/ai_reasoning_tool.py`

Day la AI/NLP tool nam ben trong Data & Finance Agent, khong phai agent rieng.

Vai tro:

- Goi AI provider duoc cau hinh trong `.env`.
- Doc du lieu phi cau truc va tin hieu finance.
- Tra ve structured JSON cho downstream agents.

Provider dang ho tro:

```text
openai
gemini
groq
```

Output AI co cac truong:

```text
province_count
bank_service_required_flag
operational_complexity
cashflow_reasoning
risk_narrative
logic_summary
evidence_used
assumptions_or_gaps
recommended_focus
confidence
```

Quan trong: UI khong hien chain-of-thought noi bo cua model. UI chi hien reasoning summary, evidence, assumptions va JSON output co the audit.

### `agents/risk_compliance_agent.py`

Agent nay nhan flag tu cac buoc truoc va doi chieu bang `13_RISK_RULES`.

Vi du:

- `cashflow_gap_flag = TRUE` -> kich hoat RR-002.
- `low_margin_flag = TRUE` -> kich hoat RR-003.
- `confidence_score < 0.65` -> kich hoat RR-006.

Output:

```text
risk_level
applicable_risk_flags[]
```

Logic tong hop risk:

- Co RR-002 -> High.
- Chi co RR-003 -> Medium.
- Khong co rule nao -> Low.

### `agents/decision_partner_agent.py`

Agent nay xu ly decision va partner matching.

Vai tro:

- Map `funding_need` + `payment_terms` sang financing type.
- Match voi `10_CREDIT_PROFILE`.
- Match san pham ngan hang tu `11_BANK_PRODUCTS`.
- Tao recommendation.
- Tao Decision Card cho Founder.

Financing type co the la:

```text
None
Working Capital
Performance Bond
LC / Trade Finance
```

Recommendation co the la:

```text
Accept
Conditional Accept
Reject
```

Luu y nghiep vu: recommendation cua agent chi la khuyen nghi. Founder van la nguoi chot Accept/Reject cuoi cung.

### `agents/shared.py`

File helper dung chung cho cac agent.

Chua cac ham:

- Chuan hoa text/float/date.
- Lay mot row theo key.
- Convert DataFrame sang records JSON.
- Lay risk rule.
- Match customer segment voi target segment.

## 6. Frontend

### `templates/index.html`

Day la giao dien web chinh.

Vai tro:

- Hien dropdown chon hop dong.
- Goi API Flask bang `fetch`.
- Hien workflow tung man hinh.
- Hien agent action, input, output, reasoning summary va handoff payload.
- Hien Human-in-the-loop gate o tung buoc.
- Hien Founder Final Gate va External Release Gate.

Cac man hinh workflow:

```text
1-2 Intake & Screening
3 Finance + AI/NLP
4 Risk Rules
5-10 Decision + HITL
```

Luu y khi chay:

```text
Dung:  http://127.0.0.1:5000
Sai:   file:///D:/MIS_TALENT/OPC-multi-agents-system/templates/index.html
```

Neu mo truc tiep file HTML bang `file:///`, browser se khong goi duoc API Flask va co the bao `Failed to fetch`.

## 7. Data

### `data/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx`

Day la file Excel Team Pack nguon.

Du lieu trong file nay duoc dua len MotherDuck thanh cac bang:

```text
02_OPC_PROFILE
03_CUSTOMERS
04_CONTRACTS
05_PRODUCTS
06_ORDERS
07_INVOICES
08_BANK_TXN
09_CASHFLOW
10_CREDIT_PROFILE
11_BANK_PRODUCTS
13_RISK_RULES
14_ALERTS
```

### `data/MISTalent2026_OPC_AgenticAI_TeamPack_v2.xlsx`

Ban data cu hon, giu lai de doi chieu.

## 8. Runtime

### `runtime/analysis`

Chua tai lieu phan tich pipeline.

File dang chu y:

```text
OPC_Opportunity_Pipeline_BanChot_v2.md
Vong Chung Khao (10).md
```

Dung de doi chieu luong business voi code.

### `runtime/logs`

Thu muc log tam thoi. Cac JSON snapshot cu da duoc xoa de tranh nham voi mock data.
Khi demo, trang web lay ket qua truc tiep tu Flask API va MotherDuck, khong doc lai JSON trong thu muc nay.

## 9. Cac File Khac

### `functions.py`

Chua cac tool/helper cu:

- Doc bang.
- Chay SELECT SQL.
- Mask data nhay cam.
- Insert/update record.

Mot so logic trong file nay phuc vu data viewer va cac tool ban dau.

### `README.md`

Huong dan chung ve project, setup, chay server va cau hinh.

### `requirement.txt`

Danh sach thu vien Python can cai.

### `.env`

Chua bien moi truong:

```text
MOTHERDUCK_TOKEN
MOTHERDUCK_DATABASE
AI_PROVIDER
OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY
```

Khong public file nay.

## 10. Giai Thich Ngan Khi Demo

Co the thuyet trinh nhu sau:

> He thong lay data tu MotherDuck bang SQL thong qua DuckDB. Backend Flask goi orchestrator de dieu phoi 3 agent loi. Data & Finance Agent dau tien tao Opportunity Profile, screening, finance summary va goi AI/NLP tool noi bo de doc payment terms, delivery notes, mo ta hop dong va cac tin hieu finance de tao structured reasoning JSON. Risk Agent dung cac flag do de kich hoat risk rules. Decision Agent match credit profile, bank product va tao Decision Card. Founder la nguoi chot cuoi, agent chi khuyen nghi. Neu Founder approve thi he thong moi chay post-decision automation va external release gate neu co gui du lieu ra doi tac.

## 11. Bang Tom Tat Nhanh

| File/Folder | Vai tro |
| --- | --- |
| `main.py` | Flask API va web server |
| `connector.py` | Ket noi MotherDuck, chay SQL, tra DataFrame |
| `opportunity_agent.py` | Orchestrator dieu phoi cac agent |
| `agents/data_finance_agent.py` | Intake, screening, finance |
| `agents/ai_reasoning_tool.py` | Tool AI/NLP cua Data & Finance Agent, tao structured reasoning |
| `agents/risk_compliance_agent.py` | Doi chieu risk rules |
| `agents/decision_partner_agent.py` | Financing, partner matching, Decision Card |
| `agents/shared.py` | Helper dung chung |
| `templates/index.html` | Frontend workflow/HITL |
| `data/` | Excel Team Pack nguon |
| `runtime/analysis/` | Tai lieu phan tich business pipeline |
| `runtime/logs/` | Log tam thoi, khong phai source data cua demo |
| `docs/` | Tai lieu giai thich/thiet ke |
