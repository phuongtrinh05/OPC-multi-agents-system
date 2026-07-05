# OPC Multi-Agents System

Demo Agentic AI cho bài MIS Talent 2026. Hệ thống hỗ trợ OPC đánh giá cơ hội kinh doanh/hợp đồng, đọc dữ liệu từ MotherDuck, phân tích nhu cầu tài chính, rà soát rủi ro và gợi ý phương án ngân hàng trước khi Founder/CEO ra quyết định cuối cùng.

## Tính năng chính

- Web app Flask để xem dữ liệu, chọn opportunity và chạy workflow.
- Data viewer có masking dữ liệu nhạy cảm khi hiển thị.
- Workflow 3 agent: Data & Finance, Risk & Compliance, Decision & Partner.
- AI/NLP reasoning là tool nội bộ của Data & Finance Agent, cấu hình qua Groq.
- Knowledge/rule context cục bộ trong `agents/knowledge/`.
- Neo4j Aura Knowledge Graph là tùy chọn, app vẫn chạy được nếu chưa cấu hình.

## Kiến trúc workflow

1. Data & Finance Agent nhận `contract_id`, gom dữ liệu hợp đồng, khách hàng, đơn hàng, hóa đơn, cashflow và credit profile.
2. AI reasoning tool đọc thêm ngữ cảnh text như mô tả hợp đồng, điều khoản thanh toán và delivery note.
3. Risk & Compliance Agent áp rule, guardrail và tín hiệu giao dịch để tạo risk score, alerts và recommended actions.
4. Decision & Partner Agent map nhu cầu tài chính sang sản phẩm ngân hàng, tính confidence score và tạo Decision Card.
5. Founder/CEO xem dashboard và quyết định approve, reject hoặc request more info.

## Cấu trúc thư mục

```text
OPC-multi-agents-system/
├── main.py                         # Flask app và API endpoints
├── connector.py                    # Kết nối MotherDuck/DuckDB
├── opportunity_agent.py            # Orchestrator workflow chính
├── functions.py                    # Data masking và helper functions
├── normalize_motherduck.py         # Script chuẩn hóa/nạp dữ liệu khi cần
├── requirement.txt                 # Python dependencies
├── .env.example                    # Mẫu cấu hình, không chứa secret thật
├── agents/
│   ├── data_finance_agent.py
│   ├── ai_reasoning_tool.py
│   ├── risk_compliance_agent.py
│   ├── decision_partner_agent.py
│   ├── ai_provider.py
│   ├── knowledge_base.py
│   ├── knowledge_graph.py
│   ├── neo4j_client.py
│   ├── shared.py
│   └── knowledge/
│       ├── agent_guardrails.json
│       └── rule_catalog.json
├── web/
│   ├── templates/
│   │   ├── index.html
│   │   └── components/
│   └── static/
│       ├── app.css
│       ├── app.js
│       └── assets/opc-logo.png
└── docs/
    ├── AGENT_BLUEPRINT.md
    ├── PROJECT_FILE_GUIDE.md
    └── README.md
```

## Cài đặt

Yêu cầu:

- Python 3.10 trở lên.
- MotherDuck token và database đã có dữ liệu demo.
- Groq API key nếu muốn chạy phần AI reasoning thật.

Tạo môi trường và cài thư viện:

```powershell
cd D:\MIS_TALENT\OPC-multi-agents-system
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirement.txt
```

Nếu PowerShell chặn activate script, chạy trong terminal hiện tại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## Cấu hình `.env`

Tạo file `.env` từ mẫu:

```powershell
Copy-Item .env.example .env
```

Điền tối thiểu:

```env
MOTHERDUCK_TOKEN=your_motherduck_token_here
MOTHERDUCK_DATABASE=OPC Database

AI_PROVIDER=groq
RISK_AI_PROVIDER=groq
DECISION_AI_PROVIDER=groq

GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com
GROQ_SSL_VERIFY=false
```

Neo4j là tùy chọn:

```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=your_neo4j_username_or_instance_id
NEO4J_PASSWORD=your_neo4j_password_here
NEO4J_DATABASE=your_database_or_instance_id
NEO4J_QUERY_LIMIT=8
NEO4J_TIMEOUT_SECONDS=8
NEO4J_SSL_VERIFY=true
```

Không commit file `.env` thật vì có token/API key.

## Chạy ứng dụng

```powershell
python main.py
```

Mở trình duyệt tại:

```text
http://127.0.0.1:5000
```

Không mở trực tiếp `web/templates/index.html` bằng `file:///...` vì frontend cần gọi API từ Flask server.

## Cách demo

1. Mở `http://127.0.0.1:5000`.
2. Chọn một opportunity/hợp đồng ở khu vực Opportunity.
3. Xem dữ liệu đầu vào: Contract, Customer, Order, Financial Snapshot.
4. Nhấn Start Workflow.
5. Duyệt từng bước agent theo các human gate trên UI.
6. Xem Decision Dashboard: recommendation, reasons, conditions, confidence, risk và sản phẩm ngân hàng đề xuất.

## API endpoints

```text
GET  /api/tables
GET  /api/table/<table_name>?limit=100&mask=true
GET  /api/opportunities
GET  /api/opportunity/<contract_id>/decision
POST /api/workflow/start
POST /api/workflow/<workflow_id>/ai-reasoning
POST /api/workflow/<workflow_id>/risk
POST /api/workflow/<workflow_id>/decision
```

## Kiểm tra nhanh

Kiểm tra syntax:

```powershell
python -m py_compile main.py connector.py opportunity_agent.py agents\data_finance_agent.py agents\risk_compliance_agent.py agents\decision_partner_agent.py
```

Kiểm tra server sau khi chạy:

```powershell
Invoke-WebRequest http://127.0.0.1:5000/api/tables
```

## Lỗi thường gặp

Không load được dữ liệu:

- Kiểm tra Flask server đã chạy chưa.
- Kiểm tra URL là `http://127.0.0.1:5000`.
- Kiểm tra `MOTHERDUCK_TOKEN` và `MOTHERDUCK_DATABASE` trong `.env`.
- Kiểm tra token MotherDuck còn hiệu lực.

AI reasoning không chạy:

- Kiểm tra `GROQ_API_KEY`.
- Kiểm tra `GROQ_BASE_URL=https://api.groq.com`.
- Kiểm tra quota/rate limit của API key.
- Nếu không có key, một số phần có thể chạy theo fallback hoặc trả lỗi provider.

Neo4j không query được:

- Kiểm tra `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
- Nếu chưa cấu hình Neo4j, workflow vẫn dùng được knowledge context cục bộ.

## Lệnh chạy tóm tắt

```powershell
cd D:\MIS_TALENT\OPC-multi-agents-system
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirement.txt
Copy-Item .env.example .env
python main.py
```
