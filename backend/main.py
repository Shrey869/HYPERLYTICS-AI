import os
import shutil
import sqlite3
import json
import math
import hashlib
import uuid
import re
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from agents.supervisor import supervisor_agent
import supabase_sync

# Restore database and uploaded files from Supabase Storage at startup
supabase_sync.sync_from_cloud_on_startup()

# Auto-sync database changes to Supabase in the background whenever committed
class SyncedConnection(sqlite3.Connection):
    def commit(self):
        super().commit()
        supabase_sync.sync_to_cloud(DB_PATH)

original_connect = sqlite3.connect
def patched_connect(*args, **kwargs):
    if "factory" not in kwargs:
        kwargs["factory"] = SyncedConnection
    return original_connect(*args, **kwargs)
sqlite3.connect = patched_connect



def sanitize_json_values(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_json_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_values(x) for x in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_json_values(x) for x in obj)
    return obj


def levenshtein_ratio(s1: str, s2: str) -> float:
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()
    m, n = len(s1), len(s2)
    if m == 0 or n == 0:
        return 0.0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)
    return 1.0 - (dp[m][n] / max(m, n))


def compute_confidence_report(user_id: str, query: str, sql_executed: str, schema_cols: list, db_path: str) -> dict:
    import re
    tokens = re.findall(r'[a-zA-Z_]+', query)
    stop_words = {'select', 'from', 'where', 'group', 'order', 'limit', 'total', 'average', 'count', 'show', 'list', 'describe', 'dataset', 'table', 'file', 'and', 'or', 'not', 'in', 'is', 'for', 'the', 'of', 'by', 'forecast', 'predict'}
    intent_tokens = [t for t in tokens if len(t) > 2 and t.lower() not in stop_words]
    
    match_scores = []
    column_mappings = []
    for token in intent_tokens:
        best_sim = 0.0
        best_col = None
        for col in schema_cols:
            sim = levenshtein_ratio(token, col)
            if sim > best_sim:
                best_sim = sim
                best_col = col
        if best_col:
            match_scores.append(best_sim)
            column_mappings.append({
                "query_token": token,
                "matched_column": best_col,
                "similarity": round(best_sim, 2)
            })
            
    header_match = sum(match_scores) / len(match_scores) if match_scores else 0.85
    
    schema_coverage = 1.0
    if intent_tokens:
        mapped_count = sum(1 for score in match_scores if score > 0.5)
        schema_coverage = mapped_count / len(intent_tokens)
        
    complexity_val = 1.0
    if sql_executed:
        join_count = sql_executed.upper().count("JOIN")
        subquery_count = len(re.findall(r'\(\s*select\b', sql_executed, re.IGNORECASE))
        window_count = sql_executed.upper().count("OVER")
        
        complexity_val -= (join_count * 0.15)
        complexity_val -= (subquery_count * 0.15)
        complexity_val -= (window_count * 0.20)
        complexity_val = max(0.0, complexity_val)
        
    hist_acc = 0.70
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM chat_history WHERE user_id = ? AND role = 'ai' AND content NOT LIKE '%error%'", (user_id,))
        success_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat_history WHERE user_id = ? AND role = 'ai'", (user_id,))
        total_cnt = cur.fetchone()[0]
        con.close()
        if total_cnt > 0:
            hist_acc = success_cnt / total_cnt
    except Exception:
        pass
        
    overall_score = (header_match * 0.35) + (schema_coverage * 0.25) + (complexity_val * 0.20) + (hist_acc * 0.20)
    overall_score = round(min(max(0.0, overall_score), 1.0), 2)
    
    grade = "low"
    if overall_score >= 0.90:
        grade = "high"
    elif overall_score >= 0.70:
        grade = "good"
    elif overall_score >= 0.50:
        grade = "moderate"
        
    explanation = f"Column matching was strong ({int(header_match * 100)}%) but query complexity reduced score"
    if overall_score >= 0.90:
        explanation = "High confidence: direct schema match and simple query structure."
    elif overall_score >= 0.70:
        explanation = "Good confidence: columns matched, but moderate query complexity detected."
    elif overall_score >= 0.50:
        explanation = f"Moderate confidence: column matching score is {int(header_match * 100)}%. Review column mappings."
    else:
        explanation = "Low confidence: multiple ambiguous columns detected. Opening manual mapping configuration."
        
    return {
        "overall_score": overall_score,
        "grade": grade,
        "signals": {
            "header_match": round(header_match, 2),
            "schema_coverage": round(schema_coverage, 2),
            "complexity_penalty": round(complexity_val, 2),
            "historical_accuracy": round(hist_acc, 2)
        },
        "column_mappings": column_mappings,
        "explanation": explanation
    }


app = FastAPI(title="Hyperlytics AI Backend API", version="1.0.0")

# Setup CORS for development and production Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "hyperlytics.db")

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Create users table to store Google login profiles with role
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            picture TEXT,
            role TEXT DEFAULT 'ANALYST',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create chat_history table with user_id
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sql TEXT,
            chart TEXT,
            data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Safely migrate older databases by adding user_id and confidence_report columns if not present
    try:
        cur.execute("ALTER TABLE chat_history ADD COLUMN user_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE chat_history ADD COLUMN confidence_report TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'ANALYST'")
    except sqlite3.OperationalError:
        pass
    # Create schema_aliases table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            query_token TEXT NOT NULL,
            corrected_column TEXT NOT NULL,
            correction_count INTEGER DEFAULT 1,
            last_used DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create shared_insights table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shared_insights (
            share_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            query_text TEXT NOT NULL,
            chart_config TEXT,
            result_data TEXT,
            story_text TEXT,
            expires_at DATETIME,
            view_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create audit_log table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            user_email TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            user_agent TEXT,
            event_type TEXT NOT NULL,
            event_status TEXT NOT NULL,
            dataset_name TEXT,
            sql_executed TEXT,
            rows_returned INTEGER,
            execution_time_ms INTEGER,
            confidence_score REAL,
            error_message TEXT,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create dataset_versions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            filename TEXT NOT NULL,
            schema_definition TEXT NOT NULL,
            drift_report TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create query_cache table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT NOT NULL,
            dataset_name TEXT,
            result_data TEXT,
            chart_config TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Create query_transitions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS query_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            prev_query_template TEXT NOT NULL,
            curr_query_template TEXT NOT NULL,
            transition_count INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, prev_query_template, curr_query_template)
        )
    """)
    # Add triggers for immutable compliance audit log
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(FAIL, 'Deletion from compliance audit logs is strictly prohibited.');
        END;
    """)
    cur.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_audit_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(FAIL, 'Modifying compliance audit logs is strictly prohibited.');
        END;
    """)
    # Create dashboards table to store layout configurations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dashboards (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            dataset_name TEXT NOT NULL,
            title TEXT NOT NULL,
            widgets TEXT NOT NULL,
            theme TEXT DEFAULT 'neo-dark',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, dataset_name)
        )
    """)
    con.commit()
    con.close()

init_db()

class FingerprintRequest(BaseModel):
    dataset_name: str

class ShareRequest(BaseModel):
    user_id: str
    query_text: str
    chart_config: Optional[Any] = None
    result_data: Optional[Any] = None
    story_text: Optional[Any] = None

class ExplainRequest(BaseModel):
    query_text: str
    result_data: Any
    chart_config: Optional[Any] = None
    language: Optional[str] = "en"
    user_id: Optional[str] = None

# WebSocket Collaborative Session Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        
    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                
    async def broadcast(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()

def log_audit_event(
    user_id: str,
    user_email: str,
    ip_address: str,
    event_type: str,
    event_status: str,
    dataset_name: Optional[str] = None,
    sql_executed: Optional[str] = None,
    rows_returned: Optional[int] = None,
    execution_time_ms: Optional[int] = None,
    confidence_score: Optional[float] = None,
    error_message: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict] = None
):
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        meta_str = json.dumps(metadata) if metadata else None
        event_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO audit_log (
                event_id, user_id, user_email, ip_address, user_agent, event_type, event_status,
                dataset_name, sql_executed, rows_returned, execution_time_ms, confidence_score,
                error_message, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, user_id or "ANONYMOUS", user_email or "anonymous@hyperlytics.ai",
            ip_address, user_agent, event_type, event_status,
            dataset_name, sql_executed, rows_returned, execution_time_ms, confidence_score,
            error_message, meta_str
        ))
        con.commit()
        con.close()
    except Exception as e:
        print(f"Audit log failed: {e}")

def get_file_path(filename: str) -> str:
    safe_filename = os.path.basename(filename)
    return os.path.join(DATA_DIR, safe_filename)

def get_file_schema_columns(filepath: str) -> list:
    import duckdb
    import pandas as pd
    con = duckdb.connect(database=':memory:')
    try:
        if filepath.endswith('.csv'):
            info = con.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{filepath}')").fetchall()
        elif filepath.endswith('.parquet'):
            info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{filepath}')").fetchall()
        elif filepath.endswith('.xlsx'):
            try:
                df = pd.read_excel(filepath, engine="calamine")
            except Exception:
                df = pd.read_excel(filepath)
            con.register('excel_tbl', df)
            info = con.execute("DESCRIBE SELECT * FROM excel_tbl").fetchall()
        elif filepath.endswith('.json'):
            info = con.execute(f"DESCRIBE SELECT * FROM read_json_auto('{filepath}')").fetchall()
        else:
            return []
        return [{"column": row[0], "type": str(row[1])} for row in info]
    except Exception:
        return []
    finally:
        con.close()

def compute_schema_diff(old_cols: list, new_cols: list) -> dict:
    old_map = {c["column"]: c["type"] for c in old_cols}
    new_map = {c["column"]: c["type"] for c in new_cols}
    
    added = [col for col in new_map if col not in old_map]
    removed = [col for col in old_map if col not in new_map]
    type_changed = []
    
    for col in old_map:
        if col in new_map and old_map[col] != new_map[col]:
            type_changed.append({
                "column": col,
                "old_type": old_map[col],
                "new_type": new_map[col]
            })
            
    return {
        "drift_detected": bool(added or removed or type_changed),
        "added": added,
        "removed": removed,
        "type_changed": type_changed
    }

def make_query_template(query: str) -> str:
    q = query.lower().strip()
    q = re.sub(r"'\d{4}-\d{2}-\d{2}'", "<date>", q)
    q = re.sub(r"'\d{2}/\d{2}/\d{4}'", "<date>", q)
    q = re.sub(r"'\w+'", "<str>", q)
    q = re.sub(r'"\w+"', "<str>", q)
    q = re.sub(r"\b\d+\b", "<num>", q)
    return q

async def precompute_and_cache_query(user_id: str, query_text: str, dataset_name: str):
    import hashlib
    try:
        # Run using supervisor_agent
        result = await supervisor_agent.run_query(query_text, dataset_name, user_id=user_id)
        if result and not result.get("error"):
            # Cache it
            q_hash = hashlib.sha256(f"{query_text}:{dataset_name}".encode('utf-8')).hexdigest()
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO query_cache (query_hash, query_text, dataset_name, result_data, chart_config)
                VALUES (?, ?, ?, ?, ?)
            """, (
                q_hash, query_text, dataset_name,
                json.dumps(result.get("data")),
                json.dumps(result.get("chart"))
            ))
            con.commit()
            con.close()
            print(f"Pre-cached query result for: {query_text}")
    except Exception as e:
        print(f"Failed to precompute and cache query: {e}")

def load_dataset_df(filepath: str, limit: int = 50000) -> Any:
    import pandas as pd
    import duckdb
    if filepath.endswith('.csv'):
        con = duckdb.connect(database=':memory:')
        df = con.execute(f"SELECT * FROM read_csv_auto('{filepath}') LIMIT {limit}").df()
        con.close()
        return df
    elif filepath.endswith('.parquet'):
        con = duckdb.connect(database=':memory:')
        df = con.execute(f"SELECT * FROM read_parquet('{filepath}') LIMIT {limit}").df()
        con.close()
        return df
    elif filepath.endswith('.xlsx'):
        try:
            df = pd.read_excel(filepath, engine="calamine").head(limit)
        except Exception:
            df = pd.read_excel(filepath).head(limit)
        return df
    elif filepath.endswith('.json'):
        con = duckdb.connect(database=':memory:')
        df = con.execute(f"SELECT * FROM read_json_auto('{filepath}') LIMIT {limit}").df()
        con.close()
        return df
    else:
        raise ValueError("Unsupported format")

def compute_data_health(df, schema_cols: list) -> dict:
    import pandas as pd
    if df is None or df.empty:
        return {"completeness": 100, "duplicate_count": 0, "outliers_count": 0, "total_rows": 0, "total_cols": len(schema_cols)}
    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return {"completeness": 100, "duplicate_count": 0, "outliers_count": 0, "total_rows": 0, "total_cols": len(schema_cols)}
    null_cells = int(df.isnull().sum().sum())
    completeness = round(((total_cells - null_cells) / total_cells) * 100, 2)
    duplicate_rows = int(df.duplicated().sum())
    outliers_count = 0
    for col in df.select_dtypes(include=['number']).columns:
        try:
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            col_outliers = ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
            outliers_count += int(col_outliers)
        except Exception:
            pass
    return {
        "completeness": completeness,
        "duplicate_count": duplicate_rows,
        "outliers_count": outliers_count,
        "total_rows": df.shape[0],
        "total_cols": df.shape[1]
    }

def classify_domain_and_suggest_queries(dataset_name: str, df_sample, schema_cols: list) -> tuple:
    import pandas as pd
    col_names_lower = [c.lower() for c in schema_cols]
    finance_keywords = {'revenue', 'sales', 'profit', 'cost', 'expense', 'income', 'budget', 'transaction', 'amount', 'delinquency', 'credit', 'loan', 'balance', 'price'}
    ecommerce_keywords = {'order', 'product', 'item', 'cart', 'shipping', 'customer', 'sku', 'quantity', 'qty', 'store'}
    hr_keywords = {'employee', 'salary', 'hire', 'department', 'performance', 'age', 'role', 'attrition', 'gender', 'tenure', 'manager'}
    marketing_keywords = {'campaign', 'click', 'impression', 'lead', 'spend', 'channel', 'cohort', 'conversion', 'ad'}
    health_keywords = {'patient', 'doctor', 'diagnosis', 'treatment', 'blood', 'heart', 'disease', 'clinical', 'trial', 'hosp'}
    ops_keywords = {'version', 'build', 'duration', 'latency', 'error', 'log', 'uptime', 'server', 'cpu', 'memory', 'disk'}
    scores = {
        "Finance": sum(1 for c in col_names_lower if any(k in c for k in finance_keywords)),
        "E-Commerce": sum(1 for c in col_names_lower if any(k in c for k in ecommerce_keywords)),
        "HR": sum(1 for c in col_names_lower if any(k in c for k in hr_keywords)),
        "Marketing": sum(1 for c in col_names_lower if any(k in c for k in marketing_keywords)),
        "Health": sum(1 for c in col_names_lower if any(k in c for k in health_keywords)),
        "Operations": sum(1 for c in col_names_lower if any(k in c for k in ops_keywords)),
    }
    best_domain = "General"
    max_score = 0
    for domain, score in scores.items():
        if score > max_score:
            max_score = score
            best_domain = domain
    if max_score == 0:
        best_domain = "General"
    num_cols = []
    cat_cols = []
    date_cols = []
    if df_sample is not None and not df_sample.empty:
        for col in schema_cols:
            if col in df_sample.columns:
                col_type = str(df_sample[col].dtype).lower()
                if 'int' in col_type or 'float' in col_type or 'num' in col_type:
                    num_cols.append(col)
                elif 'date' in col_type or 'time' in col_type or 'dt' in col_type or col.lower() in ('date', 'timestamp', 'time'):
                    date_cols.append(col)
                else:
                    cat_cols.append(col)
    if not num_cols:
        num_cols = [c for c in schema_cols if 'amt' in c.lower() or 'val' in c.lower() or 'price' in c.lower() or 'revenue' in c.lower() or 'score' in c.lower()][:2]
    if not cat_cols:
        cat_cols = [c for c in schema_cols if c not in num_cols and c not in date_cols][:2]
    suggestions = []
    if best_domain == "Finance":
        target = num_cols[0] if num_cols else (schema_cols[0] if schema_cols else "amount")
        grp = cat_cols[0] if cat_cols else (schema_cols[1] if len(schema_cols) > 1 else None)
        dt = date_cols[0] if date_cols else None
        suggestions.append(f"What is the total {target}?")
        if grp:
            suggestions.append(f"Show the average {target} by {grp}.")
        if dt:
            suggestions.append(f"Forecast the {target} for the next 30 days.")
            suggestions.append(f"What is the monthly trend of {target}?")
        suggestions.append(f"Show the top 5 records by {target}.")
        if grp:
            suggestions.append(f"Group by {grp} and find the max {target}.")
    elif best_domain == "E-Commerce":
        target = num_cols[0] if num_cols else "price"
        grp = cat_cols[0] if cat_cols else "product"
        dt = date_cols[0] if date_cols else None
        suggestions.append(f"What are the top selling {grp}?")
        suggestions.append(f"Find the total sales of each {grp}.")
        if dt:
            suggestions.append(f"Show daily order trends.")
        suggestions.append(f"What is the average order value?")
        suggestions.append(f"List records where product is most expensive.")
    elif best_domain == "HR":
        target = num_cols[0] if num_cols else "salary"
        grp = cat_cols[0] if cat_cols else "department"
        suggestions.append(f"What is the average {target} by {grp}?")
        suggestions.append(f"How many employees are in each {grp}?")
        suggestions.append(f"Find the highest paid employee details.")
        suggestions.append(f"Show headcount distribution across roles.")
    elif best_domain == "Marketing":
        target = num_cols[0] if num_cols else "clicks"
        grp = cat_cols[0] if cat_cols else "channel"
        suggestions.append(f"Which {grp} generated the most clicks?")
        suggestions.append(f"Total marketing spend by {grp}.")
        suggestions.append(f"Average conversion rate per channel.")
        suggestions.append(f"Compare ad impressions across campaigns.")
    else:
        target = num_cols[0] if num_cols else (schema_cols[0] if schema_cols else "value")
        grp = cat_cols[0] if cat_cols else (schema_cols[1] if len(schema_cols) > 1 else None)
        suggestions.append(f"Summarize the dataset columns.")
        if grp and target:
            suggestions.append(f"Compare average {target} across different {grp}.")
        suggestions.append(f"Show a sample of 10 rows from the dataset.")
        if target:
            suggestions.append(f"Show records with the maximum {target}.")
        suggestions.append("Check if there are duplicate entries in the dataset.")
    while len(suggestions) < 6:
        suggestions.append("Describe the schema and show sample data.")
    return best_domain, suggestions[:8]

def generate_og_image(share_id: str, query: str, story: dict) -> str:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (1200, 630), color='#0f172a')
    draw = ImageDraw.Draw(img)
    for y in range(630):
        r = int(11 + (30 - 11) * (y / 630))
        g = int(15 + (27 - 15) * (y / 630))
        b = int(25 + (75 - 25) * (y / 630))
        draw.line([(0, y), (1200, y)], fill=(r, g, b))
    draw.rectangle([50, 50, 1150, 580], outline='#4f46e5', width=3)
    draw.line([(50, 120), (1150, 120)], fill='#312e81', width=2)
    font_path = "C:\\Windows\\Fonts\\arial.ttf"
    if not os.path.exists(font_path):
        font_path = "C:\\Windows\\Fonts\\segoeuib.ttf"
    try:
        font_logo = ImageFont.truetype(font_path, 28)
        font_title = ImageFont.truetype(font_path, 36)
        font_body = ImageFont.truetype(font_path, 20)
        font_lbl = ImageFont.truetype(font_path, 22)
    except Exception:
        font_logo = font_title = font_body = font_lbl = ImageFont.load_default()
    draw.text((80, 75), "HYPERLYTICS AI", fill="#818cf8", font=font_logo)
    draw.text((1000, 75), "INSIGHT CARD", fill="#10b981", font=font_logo)
    query_truncated = query[:75] + "..." if len(query) > 75 else query
    draw.text((80, 160), "Query Asked:", fill="#94a3b8", font=font_lbl)
    draw.text((80, 195), f'"{query_truncated}"', fill="#f8fafc", font=font_title)
    obs = story.get("observation", "")
    ins = story.get("insight", "")
    rec = story.get("recommendation", "")
    def draw_wrapped_text(text, x, y, max_w, max_h, fill, font):
        words = text.split()
        lines = []
        curr_line = ""
        for w in words:
            test_line = curr_line + (" " if curr_line else "") + w
            try:
                w_size = draw.textlength(test_line, font=font)
            except Exception:
                w_size = len(test_line) * 10
            if w_size < max_w:
                curr_line = test_line
            else:
                lines.append(curr_line)
                curr_line = w
        if curr_line:
            lines.append(curr_line)
        curr_y = y
        for line in lines[:3]:
            draw.text((x, curr_y), line, fill=fill, font=font)
            try:
                box = font.getbbox(line)
                curr_y += box[3] - box[1] + 8
            except Exception:
                curr_y += 28
    draw.rectangle([80, 270, 600, 420], fill="#1e293b", outline="#334155", width=1)
    draw.text((95, 280), "OBSERVATION", fill="#60a5fa", font=font_lbl)
    draw_wrapped_text(obs, 95, 315, 480, 95, "#e2e8f0", font=font_body)
    draw.rectangle([80, 440, 600, 550], fill="#1e293b", outline="#334155", width=1)
    draw.text((95, 450), "INSIGHT", fill="#a78bfa", font=font_lbl)
    draw_wrapped_text(ins, 95, 485, 480, 55, "#e2e8f0", font=font_body)
    draw.rectangle([640, 270, 1120, 550], fill="#1e1b4b", outline="#4338ca", width=2)
    draw.text((660, 290), "RECOMMENDED ACTION PLAN", fill="#34d399", font=font_lbl)
    draw_wrapped_text(rec, 660, 335, 440, 195, "#f8fafc", font=font_body)
    shares_dir = os.path.join(DATA_DIR, "shares")
    os.makedirs(shares_dir, exist_ok=True)
    out_path = os.path.join(shares_dir, f"{share_id}.png")
    img.save(out_path)
    supabase_sync.sync_to_cloud(out_path)
    return out_path


init_db()

class QueryRequest(BaseModel):
    query: str
    dataset_name: Optional[str] = None
    forecast_config: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None

class AliasCorrectionRequest(BaseModel):
    user_id: str
    dataset_name: str
    query_token: str
    corrected_column: str

class ChatMessage(BaseModel):
    user_id: Optional[str] = None
    role: str
    content: str
    sql: Optional[str] = None
    chart: Optional[Any] = None
    data: Optional[Any] = None
    confidence_report: Optional[Any] = None

# Try to load .env manually if it exists in the backend directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        print(f"Error parsing .env file: {e}")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

class GoogleAuthRequest(BaseModel):
    id_token: str

@app.get("/api/auth/config")
def get_auth_config():
    """Serves authentication parameters like GOOGLE_CLIENT_ID."""
    return {"google_client_id": GOOGLE_CLIENT_ID}

@app.post("/api/auth/google")
async def verify_google_auth(payload: GoogleAuthRequest):
    """Verifies Google ID Token and upserts user details in SQLite database."""
    token = payload.id_token
    role = "ANALYST"
    
    # Check if sandbox/workspace mode (when client sends a mock token or workspace email or client ID is missing)
    if token.startswith("sandbox_") or token.startswith("workspace_auth:") or not GOOGLE_CLIENT_ID:
        if token.startswith("workspace_auth:"):
            email = token.replace("workspace_auth:", "").strip()
        elif token.startswith("sandbox_custom:"):
            email = token.replace("sandbox_custom:", "").strip()
        else:
            email = token
            
        if "@" not in email:
            email = f"{email.lower().replace(' ', '_')}@company.com"
            
        user_name = email.split("@")[0]
        domain = email.split("@")[1]
        user_id = f"workspace_{user_name.lower().replace('.', '_')}_{domain.replace('.', '_')}"
        name = user_name.replace("_", " ").replace(".", " ").title()
        picture = f"https://api.dicebear.com/7.x/initials/svg?seed={name}&radius=50&backgroundColor=4f46e5"
        
        # Override for testing profiles
        if "user_a" in token:
            name = "Sarah Connor"
            picture = "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&h=150&q=80"
            email = "sarah.connor@cyberdyne.com"
            user_id = "sandbox_user_a"
        elif "user_b" in token:
            name = "Alex Mercer"
            picture = "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=150&h=150&q=80"
            email = "alex.mercer@gentek.com"
            user_id = "sandbox_user_b"
    else:
        import httpx
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, timeout=10.0)
                if res.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid Google OAuth token signature.")
                
                info = res.json()
                user_id = info.get("sub")
                email = info.get("email")
                name = info.get("name", "Google User")
                picture = info.get("picture")
                
                if not user_id or not email:
                    raise HTTPException(status_code=400, detail="Incomplete Google user profile claims.")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=400, detail=f"OAuth verification failed: {str(e)}")
            
    # Determine user role (e.g. any email with "admin" in prefix is ADMIN)
    if "admin" in email.lower().split("@")[0]:
        role = "ADMIN"
            
    # Upsert user record in database
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO users (id, email, name, picture, role) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET email=excluded.email, name=excluded.name, picture=excluded.picture, role=excluded.role",
            (user_id, email, name, picture, role)
        )
        con.commit()
        con.close()
    except Exception as db_err:
        raise HTTPException(status_code=500, detail=f"Failed to upsert user record: {str(db_err)}")
        
    return {
        "success": True,
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "role": role
        }
    }

@app.post("/api/schema/aliases")
def save_schema_alias(payload: AliasCorrectionRequest):
    """Saves user-specific corrected column mapping to schema_aliases."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT id, correction_count FROM schema_aliases WHERE user_id = ? AND dataset_name = ? AND query_token = ?", 
                    (payload.user_id, payload.dataset_name, payload.query_token))
        row = cur.fetchone()
        if row:
            alias_id, count = row
            cur.execute("UPDATE schema_aliases SET corrected_column = ?, correction_count = ?, last_used = CURRENT_TIMESTAMP WHERE id = ?",
                        (payload.corrected_column, count + 1, alias_id))
        else:
            cur.execute("INSERT INTO schema_aliases (user_id, dataset_name, query_token, corrected_column) VALUES (?, ?, ?, ?)",
                        (payload.user_id, payload.dataset_name, payload.query_token, payload.corrected_column))
        con.commit()
        con.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
def health_check():
    """Simple API status health check."""
    return {"status": "healthy", "service": "Hyperlytics Backend"}

@app.get("/api/datasets")
def list_datasets():
    """Lists all datasets currently stored in the workspace data folder."""
    if not os.path.exists(DATA_DIR):
        return []
    
    datasets = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(('.csv', '.parquet', '.xlsx', '.json')):
            path = os.path.join(DATA_DIR, file)
            datasets.append({
                "name": file,
                "size_bytes": os.path.getsize(path),
                "format": file.split('.')[-1].upper()
            })
    return datasets

@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Uploads a file dataset to the server with auto-versioning and schema drift profiling."""
    allowed_extensions = ('.csv', '.parquet', '.xlsx', '.json')
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Must be one of: {', '.join(allowed_extensions)}"
        )
        
    file_path = os.path.join(DATA_DIR, file.filename)
    drift_report = None
    next_ver = 1
    
    try:
        # Check if dataset already exists to do schema drift detection and versioning
        if os.path.exists(file_path):
            # 1. Fetch old schema columns
            old_cols = get_file_schema_columns(file_path)
            
            # 2. Get next version number
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("SELECT COALESCE(MAX(version), 0) FROM dataset_versions WHERE dataset_name = ?", (file.filename,))
            max_ver = cur.fetchone()[0]
            con.close()
            next_ver = max_ver + 1
            
            # 3. Create version copy of current dataset file (e.g. sales_v1.csv)
            base, ext = os.path.splitext(file.filename)
            versioned_filename = f"{base}_v{next_ver-1}{ext}"
            versioned_filepath = os.path.join(DATA_DIR, versioned_filename)
            shutil.copy(file_path, versioned_filepath)
            
            # 4. Save new file to active path
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            # 5. Fetch new schema columns
            new_cols = get_file_schema_columns(file_path)
            
            # 6. Compute drift
            drift_report = compute_schema_diff(old_cols, new_cols)
            
            # 7. Write previous version metadata to dataset_versions
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("""
                INSERT INTO dataset_versions (dataset_name, version, filename, schema_definition, drift_report)
                VALUES (?, ?, ?, ?, ?)
            """, (
                file.filename, next_ver - 1, versioned_filename,
                json.dumps(old_cols), json.dumps(drift_report)
            ))
            con.commit()
            con.close()
        else:
            # First upload
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
                
            cols = get_file_schema_columns(file_path)
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("""
                INSERT INTO dataset_versions (dataset_name, version, filename, schema_definition, drift_report)
                VALUES (?, ?, ?, ?, ?)
            """, (
                file.filename, 1, file.filename,
                json.dumps(cols), json.dumps({"drift_detected": False, "added": [], "removed": [], "type_changed": []})
            ))
            con.commit()
            con.close()
            
        # Sync uploaded dataset files to Supabase Storage
        supabase_sync.sync_to_cloud(file_path)
        if next_ver > 1:
            supabase_sync.sync_to_cloud(versioned_filepath)

        # Log compliance audit event
        log_audit_event(
            user_id="ANALYST_SSO",
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="DATASET_UPLOAD",
            event_status="SUCCESS",
            dataset_name=file.filename,
            metadata={"version": next_ver, "drift_detected": bool(drift_report and drift_report.get("drift_detected"))}
        )
        
        return {
            "success": True,
            "filename": file.filename,
            "size_bytes": os.path.getsize(file_path),
            "version": next_ver,
            "drift_report": drift_report,
            "message": "Dataset uploaded successfully."
        }
    except Exception as e:
        log_audit_event(
            user_id="ANALYST_SSO",
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="DATASET_UPLOAD",
            event_status="FAILED",
            dataset_name=file.filename,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

@app.delete("/api/datasets/{filename}")
def delete_dataset(filename: str):
    """Deletes a dataset from the workspace data folder."""
    # Safety check against path traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(DATA_DIR, safe_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dataset not found.")
        
    try:
        os.remove(file_path)
        log_audit_event(
            user_id="ANALYST_SSO",
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="DATASET_DELETE",
            event_status="SUCCESS",
            dataset_name=safe_filename
        )
        return {"success": True, "message": f"Dataset '{safe_filename}' deleted."}
    except Exception as e:
        log_audit_event(
            user_id="ANALYST_SSO",
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="DATASET_DELETE",
            event_status="FAILED",
            dataset_name=safe_filename,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@app.post("/api/query")
async def query_endpoint(
    payload: QueryRequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_groq_key: Optional[str] = Header(None, alias="X-Groq-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Runs natural language analytics query with caching, pre-caching, and auditing."""
    if not payload.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    user_id = payload.user_id or "anonymous"
    dataset_name = payload.dataset_name or ""
    
    # 1. Check Query Cache
    q_hash = hashlib.sha256(f"{payload.query}:{dataset_name}".encode('utf-8')).hexdigest()
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT result_data, chart_config FROM query_cache WHERE query_hash = ?", (q_hash,))
        cache_row = cur.fetchone()
        con.close()
        
        if cache_row:
            cached_data = json.loads(cache_row[0])
            cached_chart = json.loads(cache_row[1]) if cache_row[1] else None
            
            # Log cached audit
            log_audit_event(
                user_id=user_id,
                user_email="analyst@company.com",
                ip_address="127.0.0.1",
                event_type="QUERY_EXECUTION",
                event_status="SUCCESS",
                dataset_name=dataset_name,
                sql_executed="/* CACHE HIT */",
                rows_returned=len(cached_data) if isinstance(cached_data, list) else 0,
                execution_time_ms=1, # Sub-10ms performance
                confidence_score=1.0,
                metadata={"cache_hit": True}
            )
            
            return {
                "response": "Here is the cached query result (sub-10ms pre-cache hit).",
                "sql": "/* CACHE HIT */",
                "data": cached_data,
                "chart": cached_chart,
                "confidence_report": {
                    "overall_score": 1.0,
                    "grade": "high",
                    "explanation": "Result served directly from predicted query pre-cache."
                }
            }
    except Exception as e:
        print(f"Cache check error: {e}")
        
    # 2. Run supervisor agent query
    import time
    start_time = time.time()
    
    try:
        result = await supervisor_agent.run_query(
            payload.query, 
            payload.dataset_name,
            openai_key=x_openai_key,
            anthropic_key=x_anthropic_key,
            groq_key=x_groq_key,
            gemini_key=x_gemini_key,
            forecast_config=payload.forecast_config,
            user_id=payload.user_id
        )
        
        exec_time = int((time.time() - start_time) * 1000)
        
        # Calculate Confidence Report
        schema_cols = []
        if payload.dataset_name:
            try:
                from mcp_servers.duckdb_server import get_dataset_schema as gds
                schema_res_str = gds(payload.dataset_name)
                schema_data = json.loads(schema_res_str)
                schema_cols = [c["column"] for c in schema_data.get("columns", [])]
            except Exception:
                pass
                
        confidence = compute_confidence_report(
            user_id,
            payload.query,
            result.get("sql") or "",
            schema_cols,
            DB_PATH
        )
        result["confidence_report"] = confidence
        
        # Write to Cache
        try:
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO query_cache (query_hash, query_text, dataset_name, result_data, chart_config)
                VALUES (?, ?, ?, ?, ?)
            """, (q_hash, payload.query, dataset_name, json.dumps(result.get("data")), json.dumps(result.get("chart"))))
            con.commit()
            con.close()
        except Exception as e:
            print(f"Save cache error: {e}")
            
        # Log Audit event
        log_audit_event(
            user_id=user_id,
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="QUERY_EXECUTION",
            event_status="SUCCESS",
            dataset_name=dataset_name,
            sql_executed=result.get("sql"),
            rows_returned=len(result.get("data")) if result.get("data") else 0,
            execution_time_ms=exec_time,
            confidence_score=confidence.get("overall_score"),
            metadata={"cache_hit": False}
        )
        
        # 3. Predict & Pre-cache Next Query (Markov Sequence Model)
        curr_template = make_query_template(payload.query)
        try:
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            # Fetch last template
            cur.execute("SELECT content FROM chat_history WHERE user_id = ? AND role = 'user' ORDER BY id DESC LIMIT 1 OFFSET 1", (user_id,))
            last_row = cur.fetchone()
            if last_row:
                prev_template = make_query_template(last_row[0])
                cur.execute("""
                    INSERT INTO query_transitions (user_id, prev_query_template, curr_query_template, transition_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(user_id, prev_query_template, curr_query_template) DO UPDATE SET transition_count = transition_count + 1
                """, (user_id, prev_template, curr_template))
                con.commit()
            
            # Find next predicted template
            cur.execute("""
                SELECT curr_query_template FROM query_transitions 
                WHERE user_id = ? AND prev_query_template = ? 
                ORDER BY transition_count DESC LIMIT 1
            """, (user_id, curr_template))
            pred_row = cur.fetchone()
            con.close()
            
            if pred_row:
                predicted_template = pred_row[0]
                # Find the last exact query matching the predicted template to precompute
                con = sqlite3.connect(DB_PATH)
                cur = con.cursor()
                cur.execute("""
                    SELECT content FROM chat_history 
                    WHERE user_id = ? AND role = 'user' AND content LIKE ? 
                    ORDER BY id DESC LIMIT 1
                """, (user_id, "%" + predicted_template.replace("<num>", "").replace("<str>", "").replace("<date>", "") + "%"))
                exact_row = cur.fetchone()
                con.close()
                
                if exact_row:
                    exact_pred_query = exact_row[0]
                    # Fire background prediction compute!
                    asyncio.create_task(precompute_and_cache_query(user_id, exact_pred_query, dataset_name))
        except Exception as pred_err:
            print(f"Markov prediction error: {pred_err}")
            
        return sanitize_json_values(result)
        
    except Exception as e:
        exec_time = int((time.time() - start_time) * 1000)
        log_audit_event(
            user_id=user_id,
            user_email="analyst@company.com",
            ip_address="127.0.0.1",
            event_type="QUERY_EXECUTION",
            event_status="FAILED",
            dataset_name=dataset_name,
            execution_time_ms=exec_time,
            error_message=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query/stream")
async def query_stream_endpoint(
    payload: QueryRequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_groq_key: Optional[str] = Header(None, alias="X-Groq-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Runs natural language query and streams response token-by-token with auditing."""
    if not payload.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    user_id = payload.user_id or "anonymous"
    dataset_name = payload.dataset_name or ""
    
    async def event_generator():
        import time
        start_time = time.time()
        sql_executed = ""
        rows_count = 0
        error_msg = None
        
        try:
            async for event in supervisor_agent.run_query_stream(
                payload.query, 
                payload.dataset_name,
                openai_key=x_openai_key,
                anthropic_key=x_anthropic_key,
                groq_key=x_groq_key,
                gemini_key=x_gemini_key,
                forecast_config=payload.forecast_config,
                user_id=payload.user_id
            ):
                sanitized_event = sanitize_json_values(event)
                if sanitized_event.get("type") == "sql":
                    sql_executed = sanitized_event.get("content") or ""
                elif sanitized_event.get("type") == "data":
                    rows_count = len(sanitized_event.get("content") or [])
                yield f"data: {json.dumps(sanitized_event)}\n\n"
                
            # Yield confidence report
            schema_cols = []
            if payload.dataset_name:
                try:
                    from mcp_servers.duckdb_server import get_dataset_schema as gds
                    schema_res_str = gds(payload.dataset_name)
                    schema_data = json.loads(schema_res_str)
                    schema_cols = [c["column"] for c in schema_data.get("columns", [])]
                except Exception:
                    pass
            confidence = compute_confidence_report(
                user_id,
                payload.query,
                sql_executed,
                schema_cols,
                DB_PATH
            )
            yield f"data: {json.dumps({'type': 'confidence_report', 'content': confidence})}\n\n"
            
            exec_time = int((time.time() - start_time) * 1000)
            # Log success audit
            log_audit_event(
                user_id=user_id,
                user_email="analyst@company.com",
                ip_address="127.0.0.1",
                event_type="QUERY_STREAM",
                event_status="SUCCESS",
                dataset_name=dataset_name,
                sql_executed=sql_executed,
                rows_returned=rows_count,
                execution_time_ms=exec_time,
                confidence_score=confidence.get("overall_score")
            )
        except Exception as e:
            error_msg = str(e)
            err_event = {"type": "token", "content": f"\nServer error: {str(e)}"}
            yield f"data: {json.dumps(err_event)}\n\n"
            
            exec_time = int((time.time() - start_time) * 1000)
            log_audit_event(
                user_id=user_id,
                user_email="analyst@company.com",
                ip_address="127.0.0.1",
                event_type="QUERY_STREAM",
                event_status="FAILED",
                dataset_name=dataset_name,
                execution_time_ms=exec_time,
                error_message=error_msg
            )
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/chat")
def get_chat_history(user_id: Optional[str] = None):
    """Loads user-specific chat history from sqlite database."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        if user_id:
            cur.execute("SELECT role, content, sql, chart, data, confidence_report FROM chat_history WHERE user_id = ? ORDER BY id ASC", (user_id,))
        else:
            cur.execute("SELECT role, content, sql, chart, data, confidence_report FROM chat_history WHERE user_id IS NULL ORDER BY id ASC")
        rows = cur.fetchall()
        con.close()
        
        messages = []
        for r in rows:
            role, content, sql, chart_str, data_str, confidence_str = r
            chart = None
            data = None
            confidence_report = None
            if chart_str:
                try:
                    chart = json.loads(chart_str)
                except Exception:
                    chart = None
            if data_str:
                try:
                    data = json.loads(data_str)
                except Exception:
                    data = None
            if confidence_str:
                try:
                    confidence_report = json.loads(confidence_str)
                except Exception:
                    confidence_report = None
            messages.append({
                "role": role,
                "content": content,
                "sql": sql,
                "chart": chart,
                "data": data,
                "confidence_report": confidence_report
            })
        return sanitize_json_values(messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/chat")
def save_chat_message(message: ChatMessage):
    """Saves a new user-isolated chat message to the sqlite database."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        # Sanitize message payload to remove any float NaN/Inf values
        sanitized_msg = sanitize_json_values(message.dict())
        
        chart_str = json.dumps(sanitized_msg.get("chart")) if sanitized_msg.get("chart") is not None else None
        data_str = json.dumps(sanitized_msg.get("data")) if sanitized_msg.get("data") is not None else None
        confidence_str = json.dumps(sanitized_msg.get("confidence_report")) if sanitized_msg.get("confidence_report") is not None else None
        
        cur.execute(
            "INSERT INTO chat_history (user_id, role, content, sql, chart, data, confidence_report) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sanitized_msg.get("user_id"), sanitized_msg.get("role"), sanitized_msg.get("content"), sanitized_msg.get("sql"), chart_str, data_str, confidence_str)
        )
        con.commit()
        con.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.delete("/api/chat")
def clear_chat_history(user_id: Optional[str] = None):
    """Truncates user-specific records from the chat_history table."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        if user_id:
            cur.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        else:
            cur.execute("DELETE FROM chat_history WHERE user_id IS NULL")
        con.commit()
        con.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/datasets/fingerprint")
def get_dataset_fingerprint(payload: FingerprintRequest):
    """Profiles a dataset's semantic domain, suggestions, completeness, outliers, and duplicates."""
    filepath = get_file_path(payload.dataset_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Dataset not found.")
        
    try:
        # Load up to 50000 rows for analysis to be sub-100ms performant
        df = load_dataset_df(filepath, limit=50000)
        
        # Get schema columns
        schema_cols = get_file_schema_columns(filepath)
        col_names = [c["column"] for c in schema_cols]
        
        # Compute health profile
        health = compute_data_health(df, col_names)
        
        # Classify Domain & suggested query chips
        domain, suggestions = classify_domain_and_suggest_queries(payload.dataset_name, df, col_names)
        
        return {
            "success": True,
            "dataset_name": payload.dataset_name,
            "domain": domain,
            "suggestions": suggestions,
            "health": health
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to profile dataset fingerprint: {str(e)}")

@app.post("/api/query/explain")
async def explain_query_endpoint(
    payload: ExplainRequest,
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_groq_key: Optional[str] = Header(None, alias="X-Groq-Key"),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Generates structured narrative data story in observation, insight, and recommendation format."""
    query = payload.query_text
    data = payload.result_data
    lang = payload.language or "en"
    
    # Try to check if we can run via LLM
    active_key = x_openai_key or x_anthropic_key or x_groq_key or x_gemini_key or os.getenv("OPENAI_API_KEY")
    if active_key:
        try:
            # Construct explanation prompt
            system_prompt = """You are the Hyperlytics AI Data Story Narrator.
Analyze the user's natural language query and the corresponding tabular query results.
Generate a structured 3-part data story:
1. Observation: A concise summary of the primary facts shown in the data.
2. Insight: Explain the significance of these facts, identifying key drivers, anomalies, or business patterns.
3. Recommendation: Suggest 1-2 actionable, realistic steps that could be taken based on this finding.

Format your response as a strict JSON object with three keys: "observation", "insight", and "recommendation".
Write in the user's language (either English or Hindi). Avoid any markdown codeblocks or wrapper text in your output."""
            
            user_prompt = f"Query: {query}\n\nResult Data Sample:\n{json.dumps(data[:15])}"
            
            narrative = await supervisor_agent._call_llm_provider(
                system_prompt=system_prompt,
                user_query=user_prompt,
                openai_key=x_openai_key,
                anthropic_key=x_anthropic_key,
                groq_key=x_groq_key,
                gemini_key=x_gemini_key
            )
            if isinstance(narrative, dict) and "observation" in narrative:
                return {"story": narrative}
        except Exception as e:
            print(f"LLM Narrator failed, falling back to rule engine: {e}")
            
    # Mock / Rule-based Fallback (High Quality)
    obs, ins, rec = "", "", ""
    is_hindi = lang == "hi"
    
    # Check if there is data
    if isinstance(data, list) and len(data) > 0:
        first_row = data[0]
        keys = list(first_row.keys())
        
        # Look for numeric fields
        num_keys = [k for k in keys if isinstance(first_row[k], (int, float))]
        cat_keys = [k for k in keys if k not in num_keys]
        
        if num_keys and cat_keys:
            # Aggregate group data
            cat = cat_keys[0]
            val = num_keys[0]
            
            # Sort data to find max and min
            try:
                sorted_data = sorted(data, key=lambda x: float(x[val]) if x[val] is not None else 0.0, reverse=True)
                highest = sorted_data[0]
                lowest = sorted_data[-1]
                
                h_name = highest[cat]
                h_val = highest[val]
                l_name = lowest[cat]
                l_val = lowest[val]
                
                if is_hindi:
                    obs = f"डेटा विश्लेषण से पता चलता है कि '{h_name}' {val} के लिए उच्चतम रिकॉर्ड ({h_val}) दिखाता है, जबकि '{l_name}' न्यूनतम रिकॉर्ड ({l_val}) दर्ज करता है।"
                    ins = f"यह विसंगति दर्शाती है कि '{h_name}' और '{l_name}' के बीच प्रदर्शन या मात्रा में महत्वपूर्ण अंतर है, जो परिचालन असमानताओं को इंगित करता है।"
                    rec = f"हम अनुशंसा करते हैं कि '{h_name}' में अपनाई गई रणनीतियों का अध्ययन करें और उन्हें सुधार के लिए '{l_name}' में लागू करें।"
                else:
                    obs = f"Data analysis shows that '{h_name}' accounts for the highest {val} ({h_val}), whereas '{l_name}' records the lowest {val} ({l_val})."
                    ins = f"This variance suggests a performance or volume discrepancy between '{h_name}' and '{l_name}', pointing to resource allocation or regional demand factors."
                    rec = f"Examine successful drivers in '{h_name}' and deploy targeted optimization strategies to uplift performance in '{l_name}'."
            except Exception:
                if is_hindi:
                    obs = f"डेटा सेट की समीक्षा से पता चलता है कि {cat} श्रेणियों में {val} के स्तर भिन्न हैं।"
                    ins = f"विभिन्न श्रेणियों के स्तरों में भिन्नता बाजार की बदलती प्राथमिकताओं को दर्शाती है।"
                    rec = f"डेटा रुझानों के आधार पर विभिन्न उत्पाद श्रेणियों की इन्वेंट्री स्तरों की समीक्षा करें।"
                else:
                    obs = f"A review of the dataset indicates varying levels of {val} across different {cat} categories."
                    ins = f"The dispersion in {val} levels points to market preferences or operational fluctuations."
                    rec = f"Review resource utilization and adjust budgets based on active demand patterns."
        elif num_keys:
            # Single numeric metric
            val = num_keys[0]
            vals = [float(row[val]) for row in data if row[val] is not None]
            avg = sum(vals) / len(vals) if vals else 0.0
            
            if is_hindi:
                obs = f"डेटा सेट विश्लेषण {val} के लिए औसतन {round(avg, 2)} प्रदर्शित करता है।"
                ins = f"यह मूल्य स्थापित बेंचमार्क के भीतर है, लेकिन यह बाजार के रुझानों के प्रति संवेदनशील हो सकता है।"
                rec = f"रुझानों की पुष्टि के लिए ऐतिहासिक समय-श्रृंखला डेटा के साथ इस औसत की तुलना करें।"
            else:
                obs = f"Data metrics show an average {val} value of {round(avg, 2)} across the observed rows."
                ins = f"This metric aligns with baseline thresholds but remains sensitive to macroeconomic shifts."
                rec = f"Compare this metric against historical quarterly benchmarks to validate overall growth trajectory."
        else:
            # Plain select query
            if is_hindi:
                obs = f"डेटाबेस से फ़िल्टर किया गया परिणाम {len(data)} विशिष्ट रिकॉर्ड प्रदर्शित करता है।"
                ins = f"इन पंक्तियों का वितरण डेटाबेस वर्गीकरण नियमों के अनुसार सुसंगत है।"
                rec = f"डेटा सटीकता बनाए रखने के लिए समय-समय पर इन फ़िल्टर्ड श्रेणियों की जांच करें।"
            else:
                obs = f"The filtered query output represents a subset of {len(data)} rows matching the selection criteria."
                ins = f"The distribution of records is consistent with database indexing rules."
                rec = f"Perform periodic validation to verify data cleanliness and formatting standards."
    else:
        if is_hindi:
            obs = "क्वेरी द्वारा कोई रिकॉर्ड नहीं मिला। डेटासेट खाली है या फ़िल्टर सीमा बहुत सख्त है।"
            ins = "यह रिक्त परिणाम दिखाता है कि मिलान करने वाली कोई प्रविष्टि वर्तमान डेटाबेस में नहीं है।"
            rec = "कृपया फ़िल्टर सीमा को कम करें या इनपुट मापदंडों की दोबारा जांच करें।"
        else:
            obs = "No query records returned. The current selection filters out all database rows."
            ins = "This empty state indicates that no active records match your specific parameters."
            rec = "Loosen the filter parameters or verify that the spelling matches the schema fields."
            
    return {
        "story": {
            "observation": obs,
            "insight": ins,
            "recommendation": rec
        }
    }

@app.post("/api/query/share")
def create_share_link(payload: ShareRequest):
    """Stores query data and story insights in shared_insights table and renders card PNG."""
    import uuid
    share_id = str(uuid.uuid4())[:12] # Clean 12-char ID
    
    # Format story values
    story = payload.story_text or {"observation": "Data analysis run.", "insight": "", "recommendation": ""}
    if isinstance(story, str):
        story = {"observation": story, "insight": "", "recommendation": ""}
        
    chart_config_str = json.dumps(payload.chart_config) if payload.chart_config else None
    result_data_str = json.dumps(payload.result_data) if payload.result_data else None
    story_text_str = json.dumps(story)
    
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("""
            INSERT INTO shared_insights (share_id, user_id, query_text, chart_config, result_data, story_text)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (share_id, payload.user_id, payload.query_text, chart_config_str, result_data_str, story_text_str))
        con.commit()
        con.close()
        
        # Pre-render Open Graph Image card using Pillow
        generate_og_image(share_id, payload.query_text, story)
        
        return {
            "success": True,
            "share_id": share_id,
            "image_url": f"/api/query/share/{share_id}/image",
            "pdf_url": f"/api/query/share/{share_id}/pdf",
            "share_url": f"/share/{share_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save shared insight: {str(e)}")

@app.get("/api/query/share/{share_id}")
def get_shared_insight(share_id: str):
    """Retrieves shared data insight and increments views counter."""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT query_text, chart_config, result_data, story_text, view_count, created_at FROM shared_insights WHERE share_id = ?", (share_id,))
        row = cur.fetchone()
        if not row:
            con.close()
            raise HTTPException(status_code=404, detail="Shared insight not found.")
            
        # Increment views
        cur.execute("UPDATE shared_insights SET view_count = view_count + 1 WHERE share_id = ?", (share_id,))
        con.commit()
        con.close()
        
        query_text, chart_config_str, result_data_str, story_text_str, view_count, created_at = row
        
        return {
            "share_id": share_id,
            "query_text": query_text,
            "chart_config": json.loads(chart_config_str) if chart_config_str else None,
            "result_data": json.loads(result_data_str) if result_data_str else None,
            "story": json.loads(story_text_str) if story_text_str else {},
            "views": view_count + 1,
            "created_at": created_at
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/query/share/{share_id}/image")
def get_shared_image(share_id: str):
    """Serves pre-rendered Open Graph card PNG image."""
    img_path = os.path.join(DATA_DIR, "shares", f"{share_id}.png")
    if not os.path.exists(img_path):
        # Fallback card render
        try:
            generate_og_image(share_id, "Data Insights Report", {"observation": "Executive Summary Data", "insight": "", "recommendation": ""})
        except Exception:
            raise HTTPException(status_code=404, detail="Open Graph image card not found.")
            
    return FileResponse(img_path, media_type="image/png")

@app.get("/api/query/share/{share_id}/pdf")
def export_story_pdf(share_id: str):
    """Exports structured data story narrative as a custom branded ReportLab PDF report."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT query_text, result_data, story_text, created_at FROM shared_insights WHERE share_id = ?", (share_id,))
    row = cur.fetchone()
    con.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Shared story not found.")
        
    query_text, result_data_str, story_text_str, created_at = row
    
    # Parse story
    try:
        story = json.loads(story_text_str)
    except Exception:
        story = {"observation": story_text_str, "insight": "", "recommendation": ""}
        
    try:
        result_data = json.loads(result_data_str) if result_data_str else []
    except Exception:
        result_data = []
        
    # Generate PDF
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    pdf_path = os.path.join(DATA_DIR, f"report_{share_id}.pdf")
    
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    
    # Custom branded styling
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=15
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#4f46e5'),
        spaceAfter=25
    )
    h2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=15,
        textColor=colors.HexColor('#1e1b4b'),
        spaceBefore=15,
        spaceAfter=10
    )
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['BodyText'],
        fontSize=10.5,
        textColor=colors.HexColor('#334155'),
        leading=15,
        spaceAfter=15
    )
    
    story_elements = []
    
    # Title & Metadata Header
    story_elements.append(Paragraph("HYPERLYTICS AI - Data Story Report", title_style))
    story_elements.append(Paragraph(f"Created: {created_at} | Shared Insights Instance: {share_id}", subtitle_style))
    story_elements.append(Spacer(1, 10))
    
    # Query asked
    story_elements.append(Paragraph("Analytical Inquiry Asked", h2_style))
    story_elements.append(Paragraph(f'"{query_text}"', body_style))
    story_elements.append(Spacer(1, 10))
    
    # Narrative
    story_elements.append(Paragraph("Executive Summary & Data Story", h2_style))
    story_elements.append(Paragraph(f"<b>Observation:</b> {story.get('observation', 'N/A')}", body_style))
    story_elements.append(Paragraph(f"<b>Insight:</b> {story.get('insight', 'N/A')}", body_style))
    story_elements.append(Paragraph(f"<b>Recommended Action:</b> {story.get('recommendation', 'N/A')}", body_style))
    story_elements.append(Spacer(1, 10))
    
    # Data Table
    if result_data and isinstance(result_data, list):
        story_elements.append(Paragraph("Analyzed Query Output Sample (Top Rows)", h2_style))
        keys = list(result_data[0].keys())
        table_content = [keys]
        
        for row_dict in result_data[:12]:
            row_vals = [str(row_dict.get(k, "")) for k in keys]
            table_content.append(row_vals)
            
        col_width = (doc.width) / len(keys)
        col_widths = [col_width] * len(keys)
        
        t = Table(table_content, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 6),
            ('TOPPADDING', (0,0), (-1,0), 6),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('BOTTOMPADDING', (0,1), (-1,-1), 4),
            ('TOPPADDING', (0,1), (-1,-1), 4),
        ]))
        story_elements.append(t)
        
    doc.build(story_elements)
    
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"hyperlytics_report_{share_id}.pdf"
    )

@app.get("/api/admin/audit")
def get_audit_trail(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    """Exposes immutable audit logs for compliance checks, restricted to ADMIN users."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication credentials required.")
        
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT role FROM users WHERE id = ?", (x_user_id,))
    row = cur.fetchone()
    con.close()
    
    if not row or row[0] != "ADMIN":
        raise HTTPException(status_code=403, detail="Forbidden. Admin access required.")
        
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT event_id, user_email, ip_address, event_type, event_status, dataset_name, sql_executed, execution_time_ms, confidence_score, created_at FROM audit_log ORDER BY id DESC LIMIT 100")
    rows = cur.fetchall()
    con.close()
    
    logs = []
    for r in rows:
        logs.append({
            "event_id": r[0],
            "user_email": r[1],
            "ip_address": r[2],
            "event_type": r[3],
            "event_status": r[4],
            "dataset_name": r[5],
            "sql_executed": r[6],
            "execution_time_ms": r[7],
            "confidence_score": r[8],
            "created_at": r[9]
        })
    return logs

# ── Feature 3 & 6 Dashboard API Endpoints ─────────────────────────────────────

class DashboardSaveRequest(BaseModel):
    dataset_name: str
    title: str
    widgets: List[Dict[str, Any]]
    theme: Optional[str] = "neo-dark"

def generate_default_dashboard_widgets(filepath: str) -> List[Dict[str, Any]]:
    import pandas as pd
    import duckdb
    
    schema_cols = get_file_schema_columns(filepath)
    col_names = [c["column"] for c in schema_cols]
    if not col_names:
        return []
        
    num_cols = []
    cat_cols = []
    date_cols = []
    
    # Store ID/junk columns separately
    fallback_num_cols = []
    fallback_cat_cols = []
    
    def is_junk_column(col_name: str) -> bool:
        c_low = col_name.lower()
        junk_terms = ['id', 'code', 'key', 'index', 'lat', 'long', 'latitude', 'longitude', 'zip', 'postal', 'phone', 'address']
        for term in junk_terms:
            if term == c_low:
                return True
            if c_low.endswith('_' + term) or c_low.endswith(' ' + term) or c_low.startswith(term + '_') or c_low.startswith(term + ' '):
                return True
        return False
        
    try:
        df_sample = load_dataset_df(filepath, limit=100)
    except Exception:
        df_sample = None
        
    if df_sample is not None and not df_sample.empty:
        for col_info in schema_cols:
            col = col_info["column"]
            if col in df_sample.columns:
                col_type = str(df_sample[col].dtype).lower()
                is_num = 'int' in col_type or 'float' in col_type or 'num' in col_type
                is_dt = 'date' in col_type or 'time' in col_type or 'dt' in col_type or col.lower() in ('date', 'timestamp', 'time')
                
                if is_dt:
                    date_cols.append(col)
                elif is_num:
                    if is_junk_column(col):
                        fallback_num_cols.append(col)
                    else:
                        num_cols.append(col)
                else:
                    if is_junk_column(col):
                        fallback_cat_cols.append(col)
                    else:
                        cat_cols.append(col)
                        
    # Fallback to column lists if empty
    if not num_cols:
        num_cols = fallback_num_cols if fallback_num_cols else [c for c in col_names if c not in date_cols][:2]
    if not cat_cols:
        cat_cols = fallback_cat_cols if fallback_cat_cols else [c for c in col_names if c not in num_cols and c not in date_cols][:2]
        
    # Helper to check if a numeric column is actually an ID/Code
    def is_id_or_code(col_name: str) -> bool:
        c_low = col_name.lower()
        return c_low == 'id' or c_low.endswith('_id') or c_low.endswith(' id') or c_low == 'code' or c_low.endswith('_code') or c_low.endswith(' code')
        
    widgets = []
    
    # 1. Total Rows KPI Card (x: 0, y: 0, w: 3, h: 2)
    widgets.append({
        "id": "kpi-rows",
        "type": "KPI_CARD",
        "title": "Total Rows",
        "x": 0, "y": 0, "w": 3, "h": 2,
        "data_binding": {
            "x_col": col_names[0] if col_names else "id",
            "y_col": None,
            "aggregation": "COUNT"
        }
    })
    
    # 2. Metric KPI Card (x: 3, y: 0, w: 3, h: 2)
    if num_cols:
        primary_metric = num_cols[0]
        if is_id_or_code(primary_metric):
            # If it's an ID, show "Total {Metric}s" with COUNT_DISTINCT
            widgets.append({
                "id": "kpi-metric-1",
                "type": "KPI_CARD",
                "title": f"Total {primary_metric}s",
                "x": 3, "y": 0, "w": 3, "h": 2,
                "data_binding": {
                    "x_col": primary_metric,
                    "y_col": primary_metric,
                    "aggregation": "COUNT_DISTINCT"
                }
            })
        else:
            # If it's a real metric, show "Total {Metric}" with SUM
            widgets.append({
                "id": "kpi-metric-1",
                "type": "KPI_CARD",
                "title": f"Total {primary_metric}",
                "x": 3, "y": 0, "w": 3, "h": 2,
                "data_binding": {
                    "x_col": primary_metric,
                    "y_col": primary_metric,
                    "aggregation": "SUM"
                }
            })
    else:
        # Fallback to column count
        widgets.append({
            "id": "kpi-cols",
            "type": "KPI_CARD",
            "title": "Feature Columns",
            "x": 3, "y": 0, "w": 3, "h": 2,
            "data_binding": {
                "x_col": col_names[0],
                "y_col": None,
                "aggregation": "COUNT_COLUMNS"
            }
        })
        
    # 3. Average/Unique KPI Card (x: 6, y: 0, w: 3, h: 2)
    if len(num_cols) > 1:
        sec_metric = num_cols[1]
        if is_id_or_code(sec_metric):
            widgets.append({
                "id": "kpi-metric-2",
                "type": "KPI_CARD",
                "title": f"Total {sec_metric}s",
                "x": 6, "y": 0, "w": 3, "h": 2,
                "data_binding": {
                    "x_col": sec_metric,
                    "y_col": sec_metric,
                    "aggregation": "COUNT_DISTINCT"
                }
            })
        else:
            widgets.append({
                "id": "kpi-metric-2",
                "type": "KPI_CARD",
                "title": f"Average {sec_metric}",
                "x": 6, "y": 0, "w": 3, "h": 2,
                "data_binding": {
                    "x_col": sec_metric,
                    "y_col": sec_metric,
                    "aggregation": "AVG"
                }
            })
    elif num_cols and not is_id_or_code(num_cols[0]):
        widgets.append({
            "id": "kpi-metric-1-avg",
            "type": "KPI_CARD",
            "title": f"Average {num_cols[0]}",
            "x": 6, "y": 0, "w": 3, "h": 2,
            "data_binding": {
                "x_col": num_cols[0],
                "y_col": num_cols[0],
                "aggregation": "AVG"
            }
        })
    else:
        widgets.append({
            "id": "kpi-cat-count",
            "type": "KPI_CARD",
            "title": f"Unique {cat_cols[0]}" if cat_cols else "Unique Categories",
            "x": 6, "y": 0, "w": 3, "h": 2,
            "data_binding": {
                "x_col": cat_cols[0] if cat_cols else col_names[0],
                "y_col": cat_cols[0] if cat_cols else col_names[0],
                "aggregation": "COUNT_DISTINCT"
            }
        })
        
    # 4. Data Completeness KPI Card (x: 9, y: 0, w: 3, h: 2)
    widgets.append({
        "id": "kpi-health",
        "type": "KPI_CARD",
        "title": "Data Completeness",
        "x": 9, "y": 0, "w": 3, "h": 2,
        "data_binding": {
            "x_col": col_names[0] if col_names else "id",
            "y_col": None,
            "aggregation": "COMPLETENESS"
        }
    })
    
    # 5. Row 2 Left (y: 2, w: 8, h: 4) - Trend or primary breakdown
    if date_cols and num_cols and not is_id_or_code(num_cols[0]):
        widgets.append({
            "id": "chart-trend",
            "type": "AREA_CHART",
            "title": f"{num_cols[0]} Trend Over Time",
            "x": 0, "y": 2, "w": 8, "h": 4,
            "data_binding": {
                "x_col": date_cols[0],
                "y_col": num_cols[0],
                "aggregation": "SUM"
            }
        })
    elif cat_cols and num_cols:
        y_metric = num_cols[0]
        agg = "COUNT" if is_id_or_code(y_metric) else "SUM"
        title_suffix = "Count" if agg == "COUNT" else f"Total {y_metric}"
        widgets.append({
            "id": "chart-bar",
            "type": "BAR_CHART",
            "title": f"{title_suffix} by {cat_cols[0]}",
            "x": 0, "y": 2, "w": 8, "h": 4,
            "data_binding": {
                "x_col": cat_cols[0],
                "y_col": y_metric,
                "aggregation": agg
            }
        })
    else:
        widgets.append({
            "id": "chart-bar-fallback",
            "type": "BAR_CHART",
            "title": "Row Count Breakdown",
            "x": 0, "y": 2, "w": 8, "h": 4,
            "data_binding": {
                "x_col": cat_cols[0] if cat_cols else col_names[0],
                "y_col": col_names[0],
                "aggregation": "COUNT"
            }
        })
        
    # 6. Row 2 Right (y: 2, w: 4, h: 4) - Distribution breakdown
    if cat_cols and num_cols:
        y_metric = num_cols[0]
        agg = "COUNT" if is_id_or_code(y_metric) else "SUM"
        title_suffix = "Distribution" if agg == "COUNT" else f"{y_metric} Distribution"
        widgets.append({
            "id": "chart-cat-breakdown",
            "type": "BAR_CHART",
            "title": f"{title_suffix}",
            "x": 8, "y": 2, "w": 4, "h": 4,
            "data_binding": {
                "x_col": cat_cols[0],
                "y_col": y_metric,
                "aggregation": agg
            }
        })
    else:
        widgets.append({
            "id": "chart-pie-fallback",
            "type": "PIE_CHART",
            "title": "Category Distribution",
            "x": 8, "y": 2, "w": 4, "h": 4,
            "data_binding": {
                "x_col": cat_cols[0] if cat_cols else col_names[0],
                "y_col": col_names[0],
                "aggregation": "COUNT"
            }
        })
        
    # 7. Row 3 Left (y: 6, w: 4, h: 4) - Pie Chart share breakdown
    if len(cat_cols) > 1 and num_cols:
        y_metric = num_cols[0]
        agg = "COUNT" if is_id_or_code(y_metric) else "SUM"
        title_suffix = "Share" if agg == "COUNT" else f"{y_metric} Share"
        widgets.append({
            "id": "chart-pie",
            "type": "PIE_CHART",
            "title": f"{title_suffix} by {cat_cols[1]}",
            "x": 0, "y": 6, "w": 4, "h": 4,
            "data_binding": {
                "x_col": cat_cols[1],
                "y_col": y_metric,
                "aggregation": agg
            }
        })
    elif len(cat_cols) > 0 and num_cols:
        y_metric = num_cols[0]
        agg = "COUNT" if is_id_or_code(y_metric) else "SUM"
        title_suffix = "Share" if agg == "COUNT" else f"{y_metric} Share"
        widgets.append({
            "id": "chart-pie",
            "type": "PIE_CHART",
            "title": f"{title_suffix} by {cat_cols[0]}",
            "x": 0, "y": 6, "w": 4, "h": 4,
            "data_binding": {
                "x_col": cat_cols[0],
                "y_col": y_metric,
                "aggregation": agg
            }
        })
    else:
        widgets.append({
            "id": "chart-pie-fallback-2",
            "type": "PIE_CHART",
            "title": "Data Breakdown",
            "x": 0, "y": 6, "w": 4, "h": 4,
            "data_binding": {
                "x_col": col_names[0],
                "y_col": col_names[0],
                "aggregation": "COUNT"
            }
        })
        
    # 8. Row 3 Right (y: 6, w: 8, h: 4) - Data Table preview
    widgets.append({
        "id": "chart-table",
        "type": "TABLE",
        "title": "Raw Data Preview Summary",
        "x": 4, "y": 6, "w": 8, "h": 4,
        "data_binding": {
            "x_col": cat_cols[0] if cat_cols else col_names[0],
            "y_col": num_cols[0] if num_cols else col_names[0],
            "aggregation": "COUNT" if (not num_cols or is_id_or_code(num_cols[0])) else "AVG"
        }
    })
    
    return widgets

def get_dashboard_filter_options(filepath: str) -> Dict[str, List[Any]]:
    import duckdb
    schema_cols = get_file_schema_columns(filepath)
    cat_cols = []
    
    try:
        df_sample = load_dataset_df(filepath, limit=100)
    except Exception:
        df_sample = None
        
    if df_sample is not None and not df_sample.empty:
        for col_info in schema_cols:
            col = col_info["column"]
            if col in df_sample.columns:
                col_type = str(df_sample[col].dtype).lower()
                is_numeric = 'int' in col_type or 'float' in col_type or 'num' in col_type
                is_date = 'date' in col_type or 'time' in col_type or 'dt' in col_type or col.lower() in ('date', 'timestamp', 'time')
                is_id = '_id' in col.lower() or col.lower() == 'id'
                if not is_numeric and not is_date and not is_id:
                    cat_cols.append(col)
                    
    cat_cols = cat_cols[:3]
    
    con = duckdb.connect(database=':memory:')
    filter_options = {}
    try:
        if filepath.endswith('.csv'):
            read_func = f"read_csv_auto('{filepath}')"
        elif filepath.endswith('.parquet'):
            read_func = f"read_parquet('{filepath}')"
        elif filepath.endswith('.xlsx'):
            import pandas as pd
            try:
                df = pd.read_excel(filepath, engine="calamine")
            except Exception:
                df = pd.read_excel(filepath)
            con.register('excel_tbl', df)
            read_func = "excel_tbl"
        elif filepath.endswith('.json'):
            read_func = f"read_json_auto('{filepath}')"
        else:
            return {}
            
        for col in cat_cols:
            res = con.execute(f"SELECT DISTINCT \"{col}\" FROM {read_func} WHERE \"{col}\" IS NOT NULL LIMIT 15").fetchall()
            filter_options[col] = [row[0] for row in res]
            
        return filter_options
    except Exception as e:
        print("Failed to load filter options:", e)
        return {}
    finally:
        con.close()

# NOTE: /save and /query-widget MUST come BEFORE /{dataset_name} to avoid route swallowing
@app.post("/api/dashboard/save")
def save_dashboard_layout(
    payload: DashboardSaveRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """Persists customized grid layout configurations and widget positions."""
    user_id = x_user_id or "ANONYMOUS"
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("SELECT id FROM dashboards WHERE user_id = ? AND dataset_name = ?", (user_id, payload.dataset_name))
        row = cur.fetchone()
        dash_id = row[0] if row else str(uuid.uuid4())
        cur.execute("""
            INSERT OR REPLACE INTO dashboards (id, user_id, dataset_name, title, widgets, theme, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now','utc'))
        """, (dash_id, user_id, payload.dataset_name, payload.title, json.dumps(payload.widgets), payload.theme))
        con.commit()
        return {"success": True, "id": dash_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        con.close()

@app.get("/api/dashboard/query-widget")
def query_dashboard_widget(
    dataset_name: str,
    x_col: str,
    y_col: Optional[str] = None,
    aggregation: Optional[str] = None,
    filters: Optional[str] = None,
    is_kpi: bool = False,
    limit: int = 15
):
    """Executes sandboxed analytical aggregate queries in DuckDB for a dashboard widget card."""
    filepath = get_file_path(dataset_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    where_clauses = []
    if filters:
        try:
            filter_dict = json.loads(filters)
            for col, val_list in filter_dict.items():
                if val_list and isinstance(val_list, list):
                    escaped_vals = []
                    for v in val_list:
                        v_str = str(v).replace("'", "''")
                        escaped_vals.append(f"'{v_str}'")
                    where_clauses.append(f"\"{col}\" IN ({', '.join(escaped_vals)})")
        except Exception as e:
            print("Failed to parse filter JSON:", e)
            
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    import duckdb
    con = duckdb.connect(database=':memory:')
    try:
        if aggregation == "COUNT_COLUMNS":
            schema_cols = get_file_schema_columns(filepath)
            return [{"x": "Columns", "y": len(schema_cols)}]
            
        elif aggregation == "COMPLETENESS":
            df = load_dataset_df(filepath, limit=10000)
            if df is None or df.empty:
                return [{"x": "Completeness", "y": 100}]
            total_cells = df.shape[0] * df.shape[1]
            null_cells = int(df.isnull().sum().sum())
            pct = round(((total_cells - null_cells) / total_cells) * 100, 2)
            return [{"x": "Completeness", "y": pct}]
            
        if filepath.endswith('.csv'):
            read_func = f"read_csv_auto('{filepath}')"
        elif filepath.endswith('.parquet'):
            read_func = f"read_parquet('{filepath}')"
        elif filepath.endswith('.xlsx'):
            import pandas as pd
            try:
                df = pd.read_excel(filepath, engine="calamine")
            except Exception:
                df = pd.read_excel(filepath)
            con.register('excel_tbl', df)
            read_func = "excel_tbl"
        elif filepath.endswith('.json'):
            read_func = f"read_json_auto('{filepath}')"
        else:
            raise HTTPException(status_code=400, detail="Unsupported format")
            
        if is_kpi:
            if aggregation == "COUNT":
                query_sql = f"SELECT COUNT(*) AS y FROM {read_func} {where_sql}"
            elif aggregation == "COUNT_DISTINCT":
                query_sql = f"SELECT COUNT(DISTINCT \"{x_col}\") AS y FROM {read_func} {where_sql}"
            elif aggregation in ("SUM", "AVG", "MIN", "MAX"):
                query_sql = f"SELECT {aggregation}(\"{x_col}\") AS y FROM {read_func} {where_sql}"
            else:
                query_sql = f"SELECT COUNT(*) AS y FROM {read_func} {where_sql}"
                
            res = con.execute(query_sql).fetchone()
            val = res[0] if res else 0
            return [{"x": "Total", "y": sanitize_json_values(val)}]
            
        # Non-KPI charts
        if not y_col or y_col == "None" or aggregation == "COUNT" or not aggregation:
            query_sql = f"SELECT \"{x_col}\" AS x, COUNT(*) AS y FROM {read_func} {where_sql} GROUP BY \"{x_col}\" ORDER BY y DESC LIMIT {limit}"
        else:
            if aggregation == "COUNT_DISTINCT":
                query_sql = f"SELECT \"{x_col}\" AS x, COUNT(DISTINCT \"{y_col}\") AS y FROM {read_func} {where_sql} GROUP BY \"{x_col}\" ORDER BY y DESC LIMIT {limit}"
            else:
                query_sql = f"SELECT \"{x_col}\" AS x, {aggregation}(\"{y_col}\") AS y FROM {read_func} {where_sql} GROUP BY \"{x_col}\" ORDER BY y DESC LIMIT {limit}"
                
        res = con.execute(query_sql).fetchall()
        data = [{"x": row[0], "y": sanitize_json_values(row[1])} for row in res]
        return data
    except Exception as e:
        print(f"Widget DB error: {e}")
        return []
    finally:
        con.close()

@app.get("/api/dashboard/{dataset_name}")
def get_or_generate_dashboard(
    dataset_name: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """Fetches user dashboard structure for a dataset, or automatically generates a default structure."""
    user_id = x_user_id or "ANONYMOUS"
    filepath = get_file_path(dataset_name)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, title, widgets, theme FROM dashboards WHERE user_id = ? AND dataset_name = ?", (user_id, dataset_name))
    row = cur.fetchone()
    con.close()
    
    if row:
        dash_id, title, widgets_str, theme = row
        widgets = json.loads(widgets_str)
    else:
        widgets = generate_default_dashboard_widgets(filepath)
        dash_id = str(uuid.uuid4())
        title = f"Hyperlytics {dataset_name.split('.')[0]} Dashboard"
        theme = "neo-dark"
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        try:
            cur.execute("""
                INSERT OR REPLACE INTO dashboards (id, user_id, dataset_name, title, widgets, theme)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (dash_id, user_id, dataset_name, title, json.dumps(widgets), theme))
            con.commit()
        except Exception as e:
            print("Failed to auto-save default dashboard:", e)
        con.close()
        
    filter_options = get_dashboard_filter_options(filepath)
    return {
        "id": dash_id,
        "dataset_name": dataset_name,
        "title": title,
        "widgets": widgets,
        "theme": theme,
        "filter_options": filter_options
    }

@app.websocket("/ws/collaborate/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Manages real-time cursor actions, presence coordinates, and lock updates."""
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Broadcast actions like cursor moves, selections, laser clicks, lock acquire
            await manager.broadcast(session_id, data)
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)

if __name__ == "__main__":
    import uvicorn
    # In production, this runs behind gunicorn/nginx
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
