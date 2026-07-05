# OPC Multi-Agents System

Hệ thống xem và quản lý dữ liệu từ **MotherDuck** (DuckDB Cloud), tự động masking dữ liệu nhạy cảm, giao diện web, và workflow Agentic AI cho đánh giá cơ hội kinh doanh OPC.

---

## ✅ Chức năng đã hoàn thành

### 1. 🦆 Kết nối & lấy dữ liệu từ MotherDuck

- Kết nối tự động đến MotherDuck cloud database qua token xác thực
- Singleton connection manager — tái sử dụng connection, tự động reconnect khi mất kết nối
- **Liệt kê bảng** — Lấy danh sách tất cả bảng trong database
- **Đọc dữ liệu** — Load dữ liệu từ bảng với giới hạn số dòng (1–10.000)
- **Xem schema** — Mô tả cấu trúc bảng (tên cột, kiểu dữ liệu, nullable)
- **Truy vấn SQL** — Chạy câu lệnh SQL tùy ý

### 2. 🔒 Data Masking trước khi hiển thị

Dữ liệu nhạy cảm được **tự động phát hiện và che giấu** trước khi hiển thị trên giao diện web, theo quy luật từ bảng `masking_examples`:

| Loại dữ liệu | Tên cột mẫu | Dữ liệu gốc | Sau masking | Quy tắc |
|---|---|---|---|---|
| Mã khách hàng | `customer_id` | `CUS-005` | `CUS-***005` | Giữ prefix + 3 ký tự cuối |
| Mã tài khoản | `account_id` | `OPC_MAIN` | `OPC_****` | Giữ prefix, che phần còn lại |
| Tên công ty | `company_name` | `OPC Digital` | `OPC D*****` | Giữ từ đầu + ký tự đầu từ thứ 2 |
| Giá trị tài chính | `contract_value` | `4,200,000,000` | `4.2B band` | Gom thành khoảng (K/M/B) |
| Token/Secret | `access_token` | `eyJhbGci...` | `[SECRET]` | Che toàn bộ |
| Email | `email` | `nguyenvana@gmail.com` | `ngu***@***.com` | Che local + domain |
| Số điện thoại | `phone` | `0912345678` | `***5678` | Chỉ giữ 4 số cuối |
| Tên người | `full_name` | `Nguyễn Văn An` | `Nguyễn V*** A***` | Giữ họ, che tên |
| Địa chỉ | `address` | `123 Lê Lợi, Q1` | `12***` | Giữ 2 ký tự đầu |

> Hệ thống **tự động nhận diện** cột nhạy cảm dựa trên tên cột. Có thể bật/tắt masking bằng checkbox trên giao diện.

### 3. 🌐 Giao diện Web Data Viewer

- Dropdown chọn bảng (tự động load danh sách từ MotherDuck)
- Nút **Load Data** để tải dữ liệu lên bảng HTML
- Checkbox bật/tắt masking dữ liệu nhạy cảm
- Input giới hạn số dòng hiển thị
- Nút **Xem Schema** để xem cấu trúc bảng
- Giao diện dark theme, responsive

### 4. 🤖 Agentic AI Opportunity Workflow

- Multi-agent workflow trong `opportunity_agent.py` và thư mục `agents/`
- Knowledge graph, rule catalog, guardrails và SQL tool plan cho từng agent
- Hỗ trợ 3 agent lõi: Data & Finance, Risk & Compliance, Decision & Partner. AI/NLP reasoning là tool nội bộ của Data & Finance Agent.
- AI provider được cấu hình trong `.env`

---

## 📐 Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────┐
│  Browser (index.html)                           │
│  ┌─────────────┐ ┌───────┐ ┌────────────────┐  │
│  │ Dropdown     │ │ Limit │ │ ☑ Mask data    │  │
│  │ chọn bảng    │ │  100  │ │                │  │
│  └──────┬───────┘ └───┬───┘ └───────┬────────┘  │
│         └─────────────┼─────────────┘            │
│                 [Load Data]                      │
│                       │                          │
│  ┌────────────────────▼──────────────────────┐  │
│  │        Bảng dữ liệu (HTML Table)         │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────┘
                      │ HTTP API
┌─────────────────────▼───────────────────────────┐
│  Flask Server (main.py)                         │
│  GET /api/tables    → danh sách bảng            │
│  GET /api/table/:name → dữ liệu bảng           │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│  Data Masking (functions.py)                    │
│  Auto-detect sensitive columns → apply mask     │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│  MotherDuck Connector (connector.py)            │
│  Singleton connection, auto-reconnect           │
└─────────────────────┬───────────────────────────┘
                      │
              ☁️ MotherDuck Cloud
              (OPC Database)
```

## 🗂️ Cấu trúc project

```
OPC-multi-agents-system/
├── .env                    # API keys (MotherDuck token + OpenAI key)
├── connector.py            # MotherDuck connection manager (singleton)
├── functions.py            # Data masking + CRUD tool functions
├── main.py                 # Flask web server + API endpoints
├── templates/
│   └── index.html          # Giao diện web data viewer
├── requirement.txt         # Python dependencies
└── README.md               # Tài liệu này
```

---

## 🚀 Hướng dẫn cài đặt

### Yêu cầu hệ thống

- **Python** 3.10 trở lên
- **pip** (Python package manager)
- Tài khoản **MotherDuck** — https://motherduck.com
- *(Tùy chọn)* **OpenAI API key** — chỉ cần nếu dùng AI Agent

### Bước 1: Clone repository

```bash
git clone https://github.com/your-username/OPC-multi-agents-system.git
cd OPC-multi-agents-system
```

### Bước 2: Cài đặt dependencies

```bash
pip install -r requirement.txt
```

| Package | Mục đích |
|---------|----------|
| `duckdb` | DuckDB database engine |
| `python-dotenv` | Load biến môi trường từ `.env` |
| `pandas` | Xử lý dữ liệu DataFrame |
| `openpyxl` | Đọc/ghi file Excel |
| `sqlalchemy` | SQL toolkit |
| `langchain` | LLM integration framework |
| `langchain-openai` | OpenAI GPT integration |
| `flask` | Web server |

### Bước 3: Cấu hình API keys

Tạo hoặc chỉnh sửa file `.env` ở thư mục gốc project:

```env
# [BẮT BUỘC] MotherDuck token
# Lấy tại: https://app.motherduck.com/settings/tokens
MOTHERDUCK_TOKEN=your_motherduck_token_here

# [TÙY CHỌN] OpenAI API key (chỉ cần nếu dùng AI Agent)
# Lấy tại: https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key_here

# Tên database trên MotherDuck
MOTHERDUCK_DATABASE=OPC Database
```

### Bước 4: Chạy ứng dụng

```bash
python main.py
```

Server sẽ khởi động và hiện:

```
✅ Connected to MotherDuck database: OPC Database
 * Running on http://127.0.0.1:5000
```

Mở trình duyệt → truy cập **http://127.0.0.1:5000**

---

## 💬 Hướng dẫn sử dụng

### Xem dữ liệu bảng

1. Mở **http://127.0.0.1:5000** trên trình duyệt
2. **Chọn bảng** từ dropdown (danh sách tự động load từ MotherDuck)
3. Điều chỉnh **số dòng** muốn hiển thị (mặc định 100)
4. Bật/tắt **checkbox "Mask dữ liệu nhạy cảm"** tùy nhu cầu
5. Nhấn **📥 Load Data**
6. *(Tùy chọn)* Nhấn **📐 Xem Schema** để xem cấu trúc bảng

### Các bảng có trong OPC Database

| Bảng | Mô tả |
|------|--------|
| `ai_use_disclosure` | Khai báo sử dụng AI |
| `cashflow` | Dòng tiền |
| `contracts` | Hợp đồng |
| `customers` | Khách hàng |
| `data_class` | Phân loại dữ liệu |
| `design_log` | Log thiết kế |
| `invoices` | Hóa đơn |
| `masking_examples` | Ví dụ masking dữ liệu |
| `opc_profile` | Hồ sơ OPC |
| `orders` | Đơn hàng |
| `products` | Sản phẩm |
| `risk_rules` | Quy tắc rủi ro |

---

## ⚙️ Cấu hình nâng cao

### Thêm quy tắc masking mới

Mở file `functions.py`, thêm pattern vào `SENSITIVE_PATTERNS` và hàm mask tương ứng vào `MASK_FUNCTIONS`:

```python
# Thêm pattern nhận diện cột
SENSITIVE_PATTERNS = {
    ...
    "my_type": r"(?i)(my_column_name|other_column)",
}

# Thêm hàm mask
def _mask_my_type(value: str) -> str:
    return value[:3] + "***"

MASK_FUNCTIONS = {
    ...
    "my_type": _mask_my_type,
}
```

## 📝 License

MIT License
