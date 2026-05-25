import os
import json
import re
import asyncio
from typing import List, Dict, Any, Tuple
import httpx

# Direct imports of the core analytical tools to bypass stdio process bottlenecks
from mcp_servers.duckdb_server import list_datasets, get_dataset_schema, execute_query
from mcp_servers.forecast_server import generate_forecast

# Resolve absolute path to the backend folder
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.makedirs(os.path.join(BACKEND_DIR, "data"), exist_ok=True)

class SupervisorAgent:
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    def _apply_user_aliases(self, user_id: str, dataset_name: str, query: str) -> str:
        if not user_id or not dataset_name:
            return query
        try:
            import sqlite3
            db_path = os.path.join(BACKEND_DIR, "data", "hyperlytics.db")
            if os.path.exists(db_path):
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                cur.execute("SELECT query_token, corrected_column FROM schema_aliases WHERE user_id = ? AND dataset_name = ?", (user_id, dataset_name))
                rows = cur.fetchall()
                con.close()
                for token, corrected_col in rows:
                    query = re.sub(r'\b' + re.escape(token) + r'\b', corrected_col, query, flags=re.IGNORECASE)
        except Exception as e:
            print(f"Error applying user schema aliases: {e}")
        return query

    def _get_bigrams(self, word: str) -> set:
        s = word.lower().strip()
        return {s[i:i+2] for i in range(len(s)-1)}

    def _fuzzy_match(self, w1: str, w2: str) -> float:
        b1 = self._get_bigrams(w1)
        b2 = self._get_bigrams(w2)
        if not b1 or not b2:
            return 1.0 if w1.lower() == w2.lower() else 0.0
        return len(b1.intersection(b2)) / len(b1.union(b2))

    def _correct_query_columns(self, query: str, columns: List[str]) -> Tuple[str, Dict[str, str]]:
        """Maps typo words in the query to correct columns using Jaccard bigram similarity."""
        words = re.findall(r'[a-zA-Z]+', query)
        corrections = {}
        corrected_query = query
        
        for w in words:
            # Ignore short words or standard SQL command terms
            if len(w) <= 3 or w.lower() in ('select', 'from', 'where', 'group', 'order', 'limit', 'total', 'average', 'count'):
                continue
            
            best_col = None
            best_score = 0.0
            
            for col in columns:
                score = self._fuzzy_match(w, col)
                if score > best_score:
                    best_score = score
                    best_col = col
            
            # Map if similarity is above a threshold
            if best_score >= 0.45 and best_col and w.lower() != best_col.lower():
                corrections[w] = best_col
                corrected_query = re.sub(r'\b' + w + r'\b', best_col, corrected_query, flags=re.IGNORECASE)
                
        return corrected_query, corrections

    async def run_query(
        self, 
        user_query: str, 
        current_dataset: str = None,
        openai_key: str = None,
        anthropic_key: str = None,
        groq_key: str = None,
        gemini_key: str = None,
        forecast_config: Dict[str, Any] = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Main query entry point. Directly executes analytical tools in threadpools.
        Supports multi-provider API keys routed from frontend headers.
        """
        try:
            # Apply user corrections first
            user_query = self._apply_user_aliases(user_id, current_dataset, user_query)
            
            active_openai = openai_key or self.openai_key or os.getenv("OPENAI_API_KEY")
            active_anthropic = anthropic_key or self.anthropic_key or os.getenv("ANTHROPIC_API_KEY")
            active_groq = groq_key or os.getenv("GROQ_API_KEY")
            active_gemini = gemini_key or os.getenv("GEMINI_API_KEY")
            
            if active_openai or active_anthropic or active_groq or active_gemini:
                return await self._run_llm_agent(
                    user_query, 
                    current_dataset, 
                    openai_key=active_openai, 
                    anthropic_key=active_anthropic,
                    groq_key=active_groq,
                    gemini_key=active_gemini,
                    forecast_config=forecast_config
                )
            else:
                return await self._run_mock_agent(user_query, current_dataset, forecast_config=forecast_config)
                        
        except Exception as e:
            return {
                "response": f"Error running agent loop: {str(e)}",
                "sql": None,
                "data": None,
                "chart": None,
                "error": str(e)
            }

    async def _call_llm_provider(
        self,
        system_prompt: str,
        user_query: str,
        history: List[Dict[str, str]] = None,
        openai_key: str = None,
        anthropic_key: str = None,
        groq_key: str = None,
        gemini_key: str = None
    ) -> Dict[str, Any]:
        """Sends payload dynamically to OpenAI, Anthropic, Groq, or Gemini."""
        async with httpx.AsyncClient() as client:
            # 1. Groq (OpenAI Compatible)
            if groq_key:
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "llama3-70b-8192",
                    "messages": messages,
                    "response_format": {"type": "json_object"}
                }
                res = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30.0)
                res.raise_for_status()
                content_str = res.json()["choices"][0]["message"]["content"]
                return json.loads(content_str)

            # 2. Gemini Developer API
            elif gemini_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                prompt_parts = [system_prompt]
                if history:
                    for h in history:
                        prompt_parts.append(f"{h['role'].upper()}: {h['content']}")
                else:
                    prompt_parts.append(f"USER: {user_query}")
                prompt_parts.append("Return a valid JSON object matching the requested schema. Do not wrap in markdown codeblocks.")
                
                payload = {
                    "contents": [{
                        "parts": [{"text": "\n\n".join(prompt_parts)}]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                res = await client.post(url, json=payload, timeout=30.0)
                res.raise_for_status()
                content_str = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(content_str)

            # 3. Anthropic Claude
            elif anthropic_key:
                headers = {
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                messages = []
                if history:
                    for h in history:
                        messages.append({"role": h["role"], "content": h["content"]})
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": messages
                }
                res = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=30.0)
                res.raise_for_status()
                content_str = res.json()["content"][0]["text"]
                
                clean_json_match = re.search(r"\{.*\}", content_str, re.DOTALL)
                if clean_json_match:
                    content_str = clean_json_match.group(0)
                return json.loads(content_str)

            # 4. OpenAI
            else:
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "gpt-4o",
                    "messages": messages,
                    "response_format": {"type": "json_object"}
                }
                res = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30.0)
                res.raise_for_status()
                content_str = res.json()["choices"][0]["message"]["content"]
                return json.loads(content_str)

    async def _run_llm_agent(
        self, 
        user_query: str, 
        current_dataset: str,
        openai_key: str = None,
        anthropic_key: str = None,
        groq_key: str = None,
        gemini_key: str = None,
        forecast_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Runs the agent using an LLM provider by wrapping direct python calls."""
        # Pull schema if current_dataset is set, to feed as system context
        schema_context = ""
        if current_dataset:
            schema_res_str = await asyncio.to_thread(get_dataset_schema, current_dataset)
            schema_context = f"\nActive Dataset Schema:\n{schema_res_str}"
            
        system_prompt = f"""You are Hyperlytics AI, a futuristic data analytics supervisor agent.
You have access to core database functions (list_datasets, get_dataset_schema, execute_query) and forecasting functions (generate_forecast).
Active Dataset: {current_dataset or 'None'} {schema_context}

IMPORTANT GUIDELINES:
1. The user query might contain grammatical errors, typos (e.g. 'revnue', 'categry'), or be written in a foreign language (e.g., Spanish, Hindi, French, German).
2. Proactively map misspelled column references in queries to schema columns (e.g., 'revnue' maps to 'revenue').
3. If the user asks in a foreign language, generate the standard SQL using correct column names from the schema, run the tool, and then write your final natural language explanation in the *same language* the user asked in.
4. Keep the SQL query keywords clean and case-insensitive but ensure column names match exactly. Always escape columns with spaces or special characters using double quotes.
5. If the user wants a chart, return the query result and format the output.
6. If they ask for forecasts, use the generate_forecast tool.
7. Return your output in a JSON format containing:
   - "response": text explanation of the results in the user's language.
   - "sql": the SQL query you ran (if any).
   - "chart_type": best chart type for this data (e.g., 'line', 'bar', 'pie', 'forecast') or null.
   - "tool_called": name of the tool called (if any, e.g. 'execute_query', 'generate_forecast', 'list_datasets', 'get_dataset_schema') or null.
   - "tool_args": JSON object of arguments passed to the tool or null.
   - "raw_data": the raw data array returned by the tool (populated in final response).
"""
        
        # First call: Decide if we call a tool
        llm_content = await self._call_llm_provider(
            system_prompt=system_prompt,
            user_query=user_query,
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            groq_key=groq_key,
            gemini_key=gemini_key
        )
        
        tool_to_call = llm_content.get("tool_called")
        tool_args = llm_content.get("tool_args", {})
        
        if tool_to_call:
            # Invoke tools directly in threadpools
            if tool_to_call == "list_datasets":
                tool_res_str = await asyncio.to_thread(list_datasets)
            elif tool_to_call == "get_dataset_schema":
                tool_res_str = await asyncio.to_thread(get_dataset_schema, tool_args.get("dataset_name", ""))
            elif tool_to_call == "execute_query":
                tool_res_str = await asyncio.to_thread(execute_query, tool_args.get("sql_query", ""))
            elif tool_to_call == "generate_forecast":
                cfg = forecast_config or {}
                tool_res_str = await asyncio.to_thread(
                    generate_forecast,
                    dataset_name=tool_args.get("dataset_name", ""),
                    date_column=tool_args.get("date_column", ""),
                    target_column=tool_args.get("target_column", ""),
                    horizon_steps=int(tool_args.get("horizon_steps", 30)),
                    model_type=cfg.get("model_type") or tool_args.get("model_type", "auto"),
                    seasonality_mode=cfg.get("seasonality_mode") or tool_args.get("seasonality_mode", "add"),
                    clean_outliers=cfg.get("clean_outliers") if cfg.get("clean_outliers") is not None else bool(tool_args.get("clean_outliers", False)),
                    fill_method=cfg.get("fill_method") or tool_args.get("fill_method", "interpolate")
                )
            else:
                raise ValueError(f"Unknown tool: {tool_to_call}")
                
            # Second LLM call to synthesize the final explanation with data
            history = [
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": json.dumps(llm_content)},
                {"role": "user", "content": f"Tool execution result:\n{tool_res_str}\nNow output the final synthesized JSON response. Make sure to populate the 'raw_data' and 'sql' keys, and write 'response' in the user's language."}
            ]
            
            final_content = await self._call_llm_provider(
                system_prompt=system_prompt,
                user_query="",
                history=history,
                openai_key=openai_key,
                anthropic_key=anthropic_key,
                groq_key=groq_key,
                gemini_key=gemini_key
            )
            return final_content
        
        return llm_content

    async def _resolve_multi_dataset_join(self, query: str, lang: str) -> Dict[str, Any]:
        # Scan data dir for files
        data_dir = os.path.join(BACKEND_DIR, "data")
        if not os.path.exists(data_dir):
            return None
            
        available_files = [f for f in os.listdir(data_dir) if f.endswith(('.csv', '.parquet', '.xlsx', '.json'))]
        
        # Check which files are referenced in the query
        referenced_files = []
        for file in available_files:
            name_without_ext = os.path.splitext(file)[0].lower()
            if file.lower() in query.lower() or name_without_ext in query.lower():
                referenced_files.append(file)
                
        # We need at least two files to perform a JOIN
        if len(referenced_files) < 2:
            return None
            
        file1, file2 = referenced_files[0], referenced_files[1]
        
        # Get schemas
        schema1_str = await asyncio.to_thread(get_dataset_schema, file1)
        schema2_str = await asyncio.to_thread(get_dataset_schema, file2)
        
        schema1 = json.loads(schema1_str)
        schema2 = json.loads(schema2_str)
        
        if "error" in schema1 or "error" in schema2:
            return None
            
        cols1 = [c["column"] for c in schema1["columns"]]
        cols2 = [c["column"] for c in schema2["columns"]]
        
        # Look for matching keys
        join_key = None
        for c1 in cols1:
            for c2 in cols2:
                if c1.lower() == c2.lower() and c1.lower() in ('id', 'customer_id', 'cust_id', 'user_id', 'order_id', 'product_id', 'sku'):
                    join_key = c1
                    break
            if join_key:
                break
                
        # If no exact match, do a similarity match
        if not join_key:
            for c1 in cols1:
                for c2 in cols2:
                    if (c1.lower() in c2.lower() or c2.lower() in c1.lower()) and len(c1) > 2 and len(c2) > 2:
                        join_key = (c1, c2)
                        break
                if join_key:
                    break
                    
        if not join_key:
            # Fall back to first columns
            join_key = (cols1[0], cols2[0])
            
        # Construct the SQL JOIN query
        if isinstance(join_key, tuple):
            k1, k2 = join_key
            sql = f"SELECT * FROM '{file1}' JOIN '{file2}' ON '{file1}'.\"{k1}\" = '{file2}'.\"{k2}\" LIMIT 50"
        else:
            sql = f"SELECT * FROM '{file1}' JOIN '{file2}' ON '{file1}'.\"{join_key}\" = '{file2}'.\"{join_key}\" LIMIT 50"
            
        # Execute query
        res_str = await asyncio.to_thread(execute_query, sql)
        res_data = json.loads(res_str)
        
        if "error" in res_data:
            return {
                "response": f"Failed to auto-resolve JOIN: {res_data['error']}",
                "sql": sql,
                "data": None,
                "chart": None
            }
            
        # Generate inline SVG lineage data for display
        lineage_svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 120" width="100%" height="80">
            <rect width="600" height="120" rx="10" fill="#0f172a" stroke="#1e293b"/>
            <rect x="20" y="35" width="140" height="50" rx="6" fill="#1e1b4b" stroke="#4f46e5" stroke-width="2"/>
            <text x="90" y="65" fill="#e2e8f0" font-size="12" text-anchor="middle" font-family="Arial">{file1}</text>
            
            <rect x="440" y="35" width="140" height="50" rx="6" fill="#064e3b" stroke="#10b981" stroke-width="2"/>
            <text x="510" y="65" fill="#e2e8f0" font-size="12" text-anchor="middle" font-family="Arial">Joined Result</text>
            
            <rect x="220" y="35" width="160" height="50" rx="8" fill="#1e293b" stroke="#eab308" stroke-width="2"/>
            <text x="300" y="55" fill="#facc15" font-size="12" text-anchor="middle" font-weight="bold" font-family="Arial">DuckDB JOIN</text>
            <text x="300" y="72" fill="#94a3b8" font-size="9" text-anchor="middle" font-family="Arial">Key: {join_key[0] if isinstance(join_key, tuple) else join_key}</text>
            
            <path d="M 160 60 L 220 60" stroke="#6366f1" stroke-width="2"/>
            <path d="M 380 60 L 440 60" stroke="#10b981" stroke-width="2"/>
        </svg>
        """
        
        explanation = f"Auto-resolved JOIN query between '{file1}' and '{file2}' on matching column key: {join_key[0] if isinstance(join_key, tuple) else join_key}."
        if lang == "hi":
            explanation = f"मिलान वाले कॉलम की: {join_key[0] if isinstance(join_key, tuple) else join_key} के आधार पर '{file1}' और '{file2}' के बीच JOIN क्वेरी को स्वचालित रूप से हल किया गया है।"
            
        return {
            "response": explanation,
            "sql": sql,
            "data": res_data["data"],
            "chart": {
                "type": "table",
                "lineage": lineage_svg
            }
        }

    async def _run_mock_agent(
        self, 
        user_query: str, 
        current_dataset: str,
        forecast_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """A smart typo-tolerant, multi-lingual mock agent fallback executing query logic in threadpools."""
        q_lower = user_query.lower()
        lang = self._detect_language(user_query)
        
        # Check if cross-dataset JOIN is asked
        if any(w in q_lower for w in ('join', 'merge', 'combine', 'जोड़ना', 'मिलाना')):
            join_result = await self._resolve_multi_dataset_join(user_query, lang)
            if join_result:
                return join_result
        
        FORECAST_KEYWORDS = ['forecast', 'predict', 'future', 'trend', 'भविष्यवाणी', 'पूर्वानुमान', 'pronóstico', 'predecir', 'prévision', 'prédire', 'prospect', 'forecasts', 'predictions']
        SCHEMA_KEYWORDS = ['describe', 'schema', 'columns', 'structure', 'details', 'विवरण', 'संरचना', 'esquema', 'columnas', 'détails', 'structure', 'info']
        LIST_KEYWORDS = ['list', 'datasets', 'tables', 'files', 'सूची', 'lista', 'tablas', 'liste', 'fichiers']
        AGG_KEYWORDS = ['total', 'sum', 'average', 'avg', 'count', 'max', 'min', 'योग', 'औसत', 'suma', 'promedio', 'somme', 'moyenne']
        
        # 1. Handle List Datasets
        if any(w in q_lower for w in LIST_KEYWORDS) and ("dataset" in q_lower or "table" in q_lower or "file" in q_lower or "सूची" in q_lower or "lista" in q_lower or "liste" in q_lower):
            res_str = await asyncio.to_thread(list_datasets)
            data = json.loads(res_str)
            return {
                "response": self._get_lang_text(lang, "hello"),
                "sql": None,
                "data": data,
                "chart": None
            }
            
        # 2. Handle Describe / Schema
        if any(w in q_lower for w in SCHEMA_KEYWORDS) and current_dataset:
            res_str = await asyncio.to_thread(get_dataset_schema, current_dataset)
            data = json.loads(res_str)
            return {
                "response": self._get_lang_text(lang, "schema_desc", dataset=current_dataset),
                "sql": None,
                "data": data,
                "chart": None
            }
            
        # 3. Handle Forecast
        if any(w in q_lower for w in FORECAST_KEYWORDS):
            target_col = "revenue"
            date_col = "date"
            
            if current_dataset:
                schema_res_str = await asyncio.to_thread(get_dataset_schema, current_dataset)
                schema_data = json.loads(schema_res_str)
                if "error" not in schema_data:
                    cols = [c["column"] for c in schema_data["columns"]]
                    corrected_query, corrections = self._correct_query_columns(user_query, cols)
                    
                    num_cols = [c["column"] for c in schema_data["columns"] if c["type"].upper() in ('INTEGER', 'BIGINT', 'DOUBLE', 'FLOAT', 'DECIMAL')]
                    dt_cols = [c["column"] for c in schema_data["columns"] if c["type"].upper() in ('DATE', 'TIMESTAMP', 'VARCHAR')]
                    
                    matched_cols = list(corrections.values())
                    matched_num = [c for c in matched_cols if c in num_cols]
                    matched_dt = [c for c in matched_cols if c in dt_cols]
                    
                    if matched_num:
                        target_col = matched_num[0]
                    elif num_cols:
                        target_col = num_cols[0]
                        
                    if matched_dt:
                        date_col = matched_dt[0]
                    else:
                        for d in dt_cols:
                            if 'date' in d.lower() or 'time' in d.lower() or 'दिन' in d.lower() or 'fecha' in d.lower():
                                date_col = d
                                break
            
            cfg = forecast_config or {}
            res_str = await asyncio.to_thread(
                generate_forecast, 
                current_dataset or "sales.csv", 
                date_col, 
                target_col, 
                horizon_steps=30,
                frequency="auto",
                confidence_level=0.95,
                model_type=cfg.get("model_type", "auto"),
                seasonality_mode=cfg.get("seasonality_mode", "add"),
                clean_outliers=bool(cfg.get("clean_outliers", False)),
                fill_method=cfg.get("fill_method", "interpolate")
            )
            forecast_data = json.loads(res_str)
            if "error" in forecast_data:
                return {
                    "response": f"Alternate Local Engine error: {forecast_data['error']}",
                    "sql": None,
                    "data": None,
                    "chart": None
                }
            return {
                "response": self._get_lang_text(lang, "forecast_success", target_col=target_col, date_col=date_col),
                "sql": None,
                "data": forecast_data,
                "chart": {
                    "type": "forecast",
                    "target_column": target_col,
                    "date_column": date_col
                }
            }
            
        # 4. Handle Analytics / SQL query execution
        if current_dataset:
            schema_res_str = await asyncio.to_thread(get_dataset_schema, current_dataset)
            schema_data = json.loads(schema_res_str)
            
            if "error" in schema_data:
                return {
                    "response": f"Alternate Local Engine error loading schema: {schema_data['error']}",
                    "sql": None,
                    "data": None,
                    "chart": None
                }
                
            cols = [c["column"] for c in schema_data["columns"]]
            num_cols = [c["column"] for c in schema_data["columns"] if c["type"].upper() in ('INTEGER', 'BIGINT', 'DOUBLE', 'FLOAT', 'DECIMAL')]
            dt_cols = [c["column"] for c in schema_data["columns"] if c["type"].upper() in ('DATE', 'TIMESTAMP', 'VARCHAR')]
            
            # Fuzzy correct columns in the query
            corrected_query, corrections = self._correct_query_columns(user_query, cols)
            
            # Extract columns referenced in the corrected query
            referenced_cols = []
            for col in cols:
                if re.search(r'\b' + re.escape(col) + r'\b', corrected_query, re.IGNORECASE):
                    referenced_cols.append(col)
                    
            # 4a. Handle Duplicate/Identical query checks
            duplicate_words = ('duplicate', 'same', 'identical', 'repeating', 'matching', 'similar', 'दोहराना', 'समान', 'duplicado', 'mismo', 'identique', 'même', 'doppelt', 'gleich')
            is_duplicate = any(w in corrected_query.lower() for w in duplicate_words)
            
            if is_duplicate and referenced_cols:
                dup_col = referenced_cols[0]
                sql = f"SELECT * FROM '{current_dataset}' WHERE \"{dup_col}\" IN (SELECT \"{dup_col}\" FROM '{current_dataset}' GROUP BY \"{dup_col}\" HAVING COUNT(*) > 1) ORDER BY \"{dup_col}\" LIMIT 50"
                explanation = self._get_lang_text(lang, "duplicates", dataset=current_dataset, col=dup_col)
                
                res_str = await asyncio.to_thread(execute_query, sql)
                res_data = json.loads(res_str)
                if "error" not in res_data:
                    return {
                        "response": explanation + (f" (Fuzzy mapped columns: {corrections})" if corrections else ""),
                        "sql": sql,
                        "data": res_data["data"],
                        "chart": None
                    }
            
            # 4b. Handle filter logic (WHERE filters)
            where_conditions = []
            for col in cols:
                cond = self._parse_filter_condition(corrected_query, col)
                if cond:
                    where_conditions.append(cond)
                    
            where_clause = ""
            if where_conditions:
                where_clause = " WHERE " + " AND ".join(where_conditions)
                
            # 4c. Handle sorting
            order_by_clause = self._parse_sorting_condition(corrected_query, cols) or ""
            
            # 4d. Identify potential aggregates
            has_agg = any(w in q_lower for w in AGG_KEYWORDS)
            
            sql = ""
            chart_type = None
            explanation = ""
            
            if has_agg:
                # Find agg type
                agg_func = "SUM"
                agg_label = "total"
                if any(w in q_lower for w in ('average', 'avg', 'औसत', 'promedio', 'moyenne')):
                    agg_func = "AVG"
                    agg_label = "avg"
                elif any(w in q_lower for w in ('count', 'गिनती')):
                    agg_func = "COUNT"
                    agg_label = "count"
                elif any(w in q_lower for w in ('max', 'maximum', 'उच्चतम')):
                    agg_func = "MAX"
                    agg_label = "max"
                elif any(w in q_lower for w in ('min', 'minimum', 'न्यूनतम')):
                    agg_func = "MIN"
                    agg_label = "min"
                    
                # Identify column to aggregate
                ref_num_cols = [c for c in referenced_cols if c in num_cols]
                val_col = ref_num_cols[0] if ref_num_cols else (num_cols[0] if num_cols else (cols[0] if cols else "*"))
                
                # Identify grouping column
                ref_cat_cols = [c for c in referenced_cols if c != val_col]
                grp_col = ref_cat_cols[0] if ref_cat_cols else None
                
                if not grp_col and not ref_num_cols and referenced_cols:
                    grp_col = referenced_cols[0]
                    
                if not grp_col:
                    grp_col = next((c for c in cols if c != val_col and c.lower() in ('category', 'product', 'region', 'country', 'channel', 'status', 'श्रेणी', 'उत्पाद', 'categoria', 'producto')), None)
                
                if grp_col:
                    sql_agg_term = f"COUNT(*)" if agg_func == "COUNT" and val_col == "*" else f"{agg_func}(\"{val_col}\")"
                    sql = f"SELECT \"{grp_col}\", {sql_agg_term} as \"{agg_label}_{val_col}\" FROM '{current_dataset}'{where_clause} GROUP BY \"{grp_col}\""
                    if not order_by_clause:
                        sql += f" ORDER BY \"{agg_label}_{val_col}\" DESC"
                    else:
                        sql += f" {order_by_clause}"
                    sql += " LIMIT 50"
                    
                    explanation = self._get_lang_text(lang, "aggregate_group", agg=agg_func.lower(), val_col=val_col, grp_col=grp_col)
                    chart_type = "bar"
                else:
                    sql_agg_term = f"COUNT(*)" if agg_func == "COUNT" and val_col == "*" else f"{agg_func}(\"{val_col}\")"
                    sql = f"SELECT {sql_agg_term} as \"{agg_label}_{val_col}\" FROM '{current_dataset}'{where_clause}"
                    if order_by_clause:
                        sql += f" {order_by_clause}"
                    explanation = self._get_lang_text(lang, "aggregate_single", agg=agg_func.lower(), val_col=val_col)
                    chart_type = "table"
                    
            elif any(w in q_lower for w in ('trend', 'monthly', 'daily', 'over time', 'time', 'प्रवृत्ति', 'tendencia', 'tendance')):
                # Trend query
                date_col = next((c for c in referenced_cols if c in dt_cols), None)
                if not date_col:
                    date_col = dt_cols[0] if dt_cols else next((c for c in cols if 'date' in c.lower() or 'time' in c.lower() or 'दिन' in c.lower() or 'fecha' in c.lower()), cols[0])
                
                ref_num_cols = [c for c in referenced_cols if c in num_cols]
                val_col = ref_num_cols[0] if ref_num_cols else (num_cols[0] if num_cols else cols[0])
                
                sql = f"SELECT \"{date_col}\", AVG(\"{val_col}\") as \"avg_{val_col}\" FROM '{current_dataset}'{where_clause} GROUP BY \"{date_col}\" ORDER BY \"{date_col}\" ASC LIMIT 100"
                explanation = self._get_lang_text(lang, "trend", val_col=val_col, date_col=date_col)
                chart_type = "line"
                
            else:
                # Simple filtered select query
                proj_cols = ", ".join([f'"{c}"' for c in referenced_cols]) if referenced_cols else "*"
                sql = f"SELECT {proj_cols} FROM '{current_dataset}'{where_clause}"
                if order_by_clause:
                    sql += f" {order_by_clause}"
                sql += " LIMIT 50"
                
                explanation = self._get_lang_text(lang, "select", dataset=current_dataset)
                chart_type = "table"
                
            res_str = await asyncio.to_thread(execute_query, sql)
            res_data = json.loads(res_str)
            
            if "error" in res_data:
                # Fallback to general select limit 10
                sql = f"SELECT * FROM '{current_dataset}' LIMIT 10"
                res_str = await asyncio.to_thread(execute_query, sql)
                res_data = json.loads(res_str)
                explanation = self._get_lang_text(lang, "fallback", dataset=current_dataset)
                chart_type = "table"
                
            if "error" in res_data:
                return {
                    "response": f"Query execution failed: {res_data['error']}",
                    "sql": sql,
                    "data": None,
                    "chart": None
                }
                
            x_val = None
            y_val = None
            if res_data.get("data") and len(res_data["data"]) > 0:
                first_row = res_data["data"][0]
                keys = list(first_row.keys())
                if len(keys) >= 2:
                    x_val = keys[0]
                    y_val = keys[1]
                elif len(keys) == 1:
                    x_val = keys[0]
                    
            return {
                "response": explanation,
                "sql": sql,
                "data": res_data["data"],
                "chart": {
                    "type": chart_type or "table",
                    "x": x_val,
                    "y": y_val
                } if chart_type and chart_type != "table" and x_val else None
            }
            
        return {
            "response": self._get_lang_text(lang, "hello"),
            "sql": None,
            "data": None,
            "chart": None
        }

    def _detect_language(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ('योग', 'औसत', 'सूची', 'संरचना', 'भविष्यवाणी', 'समान', 'डेटासेट', 'क्या', 'है')):
            return "hi"
        if any(w in q for w in ('suma', 'promedio', 'lista', 'esquema', 'pronóstico', 'duplicado', 'mostrar', 'donde', 'ordenar')):
            return "es"
        if any(w in q for w in ('somme', 'moyenne', 'liste', 'structure', 'prévision', 'mismo', 'afficher', 'ou', 'tendance')):
            return "fr"
        if any(w in q for w in ('doppelt', 'gleich', 'liste', 'struktur', 'prognose', 'zeigen', 'wo', 'durchschnitt')):
            return "de"
        return "en"

    def _get_lang_text(self, lang: str, key: str, **kwargs) -> str:
        templates = {
            "en": {
                "hello": "Hello! Please select a dataset, and then ask me to query, describe, or forecast it.",
                "schema_desc": "Here is the schema analysis and data profile for `{dataset}`:",
                "forecast_success": "Forecast generated successfully for `{target_col}` using historical trends of `{date_col}`.",
                "duplicates": "Here are the records in '{dataset}' with duplicate/identical values for '{col}':",
                "aggregate_group": "Here is the breakdown of {agg} `{val_col}` grouped by `{grp_col}`:",
                "aggregate_single": "The calculated {agg} of `{val_col}` is:",
                "trend": "Here is the average trend of `{val_col}` over `{date_col}`:",
                "select": "Here are the filtered records from '{dataset}':",
                "fallback": "Here is a raw sample of `{dataset}`:"
            },
            "hi": {
                "hello": "नमस्ते! कृपया एक डेटासेट चुनें, और फिर मुझसे प्रश्न पूछें, विवरण मांगें या पूर्वानुमान लगाएं।",
                "schema_desc": "`{dataset}` के लिए स्कीमा विश्लेषण और डेटा प्रोफ़ाइल यहाँ है:",
                "forecast_success": "`{date_col}` के ऐतिहासिक रुझानों का उपयोग करके `{target_col}` के लिए सफलतापूर्वक पूर्वानुमान उत्पन्न किया गया।",
                "duplicates": "'{dataset}' में '{col}' के समान/दोहरे मान वाले रिकॉर्ड यहाँ हैं:",
                "aggregate_group": "`{grp_col}` द्वारा समूहीकृत `{val_col}` के {agg} का विवरण यहाँ है:",
                "aggregate_single": "`{val_col}` का परिकलित {agg} है:",
                "trend": "`{date_col}` पर `{val_col}` की औसत प्रवृत्ति यहाँ है:",
                "select": "'{dataset}' से फ़िल्टर किए गए रिकॉर्ड यहाँ हैं:",
                "fallback": "`{dataset}` का कच्चा नमूना यहाँ है:"
            },
            "es": {
                "hello": "¡Hola! Seleccione un conjunto de datos y luego pídame que lo consulte, describa o pronostique.",
                "schema_desc": "Aquí está el análisis del esquema y el perfil de datos para `{dataset}`:",
                "forecast_success": "Pronóstico generado con éxito para `{target_col}` utilizando tendencias históricas de `{date_col}`.",
                "duplicates": "Aquí están los registros en '{dataset}' con valores duplicados/idénticos para '{col}':",
                "aggregate_group": "Aquí está el desglose de {agg} `{val_col}` agrupado por `{grp_col}`:",
                "aggregate_single": "El {agg} calculado de `{val_col}` es:",
                "trend": "Aquí está la tendencia promedio de `{val_col}` sobre `{date_col}`:",
                "select": "Aquí están los registros filtrados de '{dataset}':",
                "fallback": "Aquí hay una muestra de `{dataset}`:"
            },
            "fr": {
                "hello": "Bonjour ! Veuillez sélectionner un jeu de données, puis me demander de l'interroger, de le décrire ou de le prévoir.",
                "schema_desc": "Voici l'analyse du schéma et le profil de données pour `{dataset}` :",
                "forecast_success": "Prévision générée avec succès pour `{target_col}` à l'aide des tendances historiques de `{date_col}`.",
                "duplicates": "Voici les enregistrements dans '{dataset}' avec des valeurs en double/identiques pour '{col}':",
                "aggregate_group": "Voici la ventilation de {agg} `{val_col}` regroupée par `{grp_col}`:",
                "aggregate_single": "Le {agg} calculé de `{val_col}` est :",
                "trend": "Voici la tendance moyenne de `{val_col}` sur `{date_col}`:",
                "select": "Voici les enregistrements filtrés de '{dataset}':",
                "fallback": "Voici un échantillon brut de `{dataset}`:"
            },
            "de": {
                "hello": "Hallo! Bitte wählen Sie einen Datensatz aus und bitten Sie mich dann, ihn abzufragen, zu beschreiben oder vorherzusagen.",
                "schema_desc": "Hier ist die Schemaanalyse und das Datenprofil für `{dataset}`:",
                "forecast_success": "Prognose erfolgreich erstellt für `{target_col}` unter Verwendung historischer Trends von `{date_col}`.",
                "duplicates": "Hier sind die Datensätze in '{dataset}' mit doppelten/identischen Werten für '{col}':",
                "aggregate_group": "Hier ist die Aufschlüsselung von {agg} `{val_col}` gruppiert nach `{grp_col}`:",
                "aggregate_single": "Der berechnete {agg} von `{val_col}` ist:",
                "trend": "Hier ist der durchschnittliche Trend von `{val_col}` über `{date_col}`:",
                "select": "Hier sind die gefilterten Datensätze aus '{dataset}':",
                "fallback": "Hier ist eine Rohstichprobe von `{dataset}`:"
            }
        }
        lang_dict = templates.get(lang, templates["en"])
        template = lang_dict.get(key, templates["en"].get(key, ""))
        return template.format(**kwargs)

    def _parse_filter_condition(self, query_text: str, col: str) -> str:
        pattern = r'\b' + re.escape(col) + r'\b\s*(>=|<=|>|<|!=|=|\bis\s+above\b|\bis\s+below\b|\bis\s+greater\s+than\b|\bis\s+less\s+than\b|\bgreater\s+than\b|\bless\s+than\b|\bequal\s+to\b|\bis\s+equal\s+to\b|\babove\b|\bbelow\b|\bcontains\b|\blike\b|\bis\b)\s*(\'[^\']+\'|"[^"]+"|[a-zA-Z0-9_\-\.\s\:]+)'
        match = re.search(pattern, query_text, re.IGNORECASE)
        if not match:
            return None
        
        op_text = match.group(1).lower().strip()
        val_text = match.group(2).strip()
        
        if (val_text.startswith("'") and val_text.endswith("'")) or (val_text.startswith('"') and val_text.endswith('"')):
            val_text = val_text[1:-1]
        else:
            conjunctions = [' and ', ' or ', ' order ', ' sort ', ' group ', ' limit ', ' having ', ' with ']
            for conj in conjunctions:
                if conj in f" {val_text} ":
                    parts = re.split(re.escape(conj), val_text, flags=re.IGNORECASE)
                    val_text = parts[0].strip()
                    break
                    
        sql_op = '='
        if op_text in ('>=', '<=', '>', '<', '=', '!='):
            sql_op = op_text
        elif 'greater' in op_text or 'above' in op_text:
            sql_op = '>'
        elif 'less' in op_text or 'below' in op_text:
            sql_op = '<'
        elif 'contains' in op_text or 'like' in op_text:
            sql_op = 'LIKE'
        elif 'equal' in op_text or op_text == 'is':
            sql_op = '='
            
        try:
            float(val_text)
            is_num = True
        except ValueError:
            is_num = False
            
        if is_num:
            return f'"{col}" {sql_op} {val_text}'
        else:
            if sql_op == 'LIKE':
                return f'"{col}" ILIKE \'%{val_text}%\''
            else:
                return f'"{col}" ILIKE \'{val_text}\''

    def _parse_sorting_condition(self, query_text: str, cols: List[str]) -> str:
        q_lower = query_text.lower()
        for col in cols:
            col_lower = col.lower()
            p1 = r'\b(highest|cheapest|max|maximum|best|top|descending|desc|most)\b\s+(?:of\s+)?(?:the\s+)?\b' + re.escape(col_lower) + r'\b'
            p2 = r'\b' + re.escape(col_lower) + r'\b\s+(?:is\s+)?\b(highest|cheapest|max|maximum|best|top|descending|desc|most)\b'
            
            p3 = r'\b(lowest|minimum|min|worst|cheapest|ascending|asc|least)\b\s+(?:of\s+)?(?:the\s+)?\b' + re.escape(col_lower) + r'\b'
            p4 = r'\b' + re.escape(col_lower) + r'\b\s+(?:is\s+)?\b(lowest|minimum|min|worst|cheapest|ascending|asc|least)\b'
            
            p5 = r'\b(?:sort|order)\s+by\s+\b' + re.escape(col_lower) + r'\b'
            
            if re.search(p1, q_lower) or re.search(p2, q_lower):
                return f'ORDER BY "{col}" DESC'
            elif re.search(p3, q_lower) or re.search(p4, q_lower):
                return f'ORDER BY "{col}" ASC'
            elif re.search(p5, q_lower):
                if any(w in q_lower for w in ('desc', 'descending', 'highest', 'reverse')):
                    return f'ORDER BY "{col}" DESC'
                else:
                    return f'ORDER BY "{col}" ASC'
        return None

    async def _call_llm_provider_stream(
        self,
        system_prompt: str,
        user_query: str,
        history: List[Dict[str, str]] = None,
        openai_key: str = None,
        anthropic_key: str = None,
        groq_key: str = None,
        gemini_key: str = None
    ):
        """Sends payload dynamically to OpenAI, Anthropic, Groq, or Gemini and yields text chunks."""
        async with httpx.AsyncClient() as client:
            # 1. Groq (OpenAI Compatible)
            if groq_key:
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "llama3-70b-8192",
                    "messages": messages,
                    "stream": True
                }
                async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30.0) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data["choices"][0]["delta"]
                                if "content" in delta:
                                    yield delta["content"]
                            except Exception:
                                pass

            # 2. Gemini Developer API
            elif gemini_key:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?key={gemini_key}"
                prompt_parts = [system_prompt]
                if history:
                    for h in history:
                        prompt_parts.append(f"{h['role'].upper()}: {h['content']}")
                else:
                    prompt_parts.append(f"USER: {user_query}")
                
                payload = {
                    "contents": [{
                        "parts": [{"text": "\n\n".join(prompt_parts)}]
                    }]
                }
                async with client.stream("POST", url, json=payload, timeout=30.0) as response:
                    response.raise_for_status()
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        # Standard brace matching parser to extract candidate objects from the text stream
                        while True:
                            start = buffer.find("{")
                            if start == -1:
                                break
                            brace_count = 0
                            end = -1
                            for i in range(start, len(buffer)):
                                if buffer[i] == "{":
                                    brace_count += 1
                                elif buffer[i] == "}":
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end = i
                                        break
                            if end != -1:
                                obj_str = buffer[start:end+1]
                                buffer = buffer[end+1:]
                                try:
                                    obj = json.loads(obj_str)
                                    text = obj["candidates"][0]["content"]["parts"][0]["text"]
                                    yield text
                                except Exception:
                                    pass
                            else:
                                break

            # 3. Anthropic Claude
            elif anthropic_key:
                headers = {
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                messages = []
                if history:
                    for h in history:
                        messages.append({"role": h["role"], "content": h["content"]})
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": messages,
                    "stream": True
                }
                async with client.stream("POST", "https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=30.0) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            try:
                                chunk_data = json.loads(data_str)
                                if chunk_data.get("type") == "content_block_delta":
                                    delta = chunk_data.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        yield delta.get("text", "")
                            except Exception:
                                pass

            # 4. OpenAI
            else:
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                else:
                    messages.append({"role": "user", "content": user_query})
                    
                payload = {
                    "model": "gpt-4o",
                    "messages": messages,
                    "stream": True
                }
                async with client.stream("POST", "https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30.0) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data["choices"][0]["delta"]
                                if "content" in delta:
                                    yield delta["content"]
                            except Exception:
                                pass

    async def run_query_stream(
        self,
        user_query: str,
        current_dataset: str = None,
        openai_key: str = None,
        anthropic_key: str = None,
        groq_key: str = None,
        gemini_key: str = None,
        forecast_config: Dict[str, Any] = None,
        user_id: str = None
    ):
        """
        Runs query and yields event dictionaries:
        - {"type": "token", "content": "..."}
        - {"type": "sql", "content": "..."}
        - {"type": "data", "content": [...]}
        - {"type": "chart", "content": {...}}
        """
        try:
            # Apply user corrections first
            user_query = self._apply_user_aliases(user_id, current_dataset, user_query)
            
            active_openai = openai_key or self.openai_key or os.getenv("OPENAI_API_KEY")
            active_anthropic = anthropic_key or self.anthropic_key or os.getenv("ANTHROPIC_API_KEY")
            active_groq = groq_key or os.getenv("GROQ_API_KEY")
            active_gemini = gemini_key or os.getenv("GEMINI_API_KEY")
            
            if active_openai or active_anthropic or active_groq or active_gemini:
                # LLM Mode
                # First call: get tool classification (Normal non-stream JSON call)
                schema_context = ""
                if current_dataset:
                    schema_res_str = await asyncio.to_thread(get_dataset_schema, current_dataset)
                    schema_context = f"\nActive Dataset Schema:\n{schema_res_str}"
                    
                system_prompt = f"""You are Hyperlytics AI, a futuristic data analytics supervisor agent.
You have access to core database functions (list_datasets, get_dataset_schema, execute_query) and forecasting functions (generate_forecast).
Active Dataset: {current_dataset or 'None'} {schema_context}

IMPORTANT GUIDELINES:
1. Identify if a tool needs to be called.
2. Return your output in a JSON format containing:
   - "tool_called": name of the tool called (e.g. 'execute_query', 'generate_forecast', 'list_datasets', 'get_dataset_schema') or null.
   - "tool_args": JSON object of arguments passed to the tool or null.
   - "sql": the SQL query you ran/intend to run (if any).
   - "chart_type": best chart type for this data (e.g., 'line', 'bar', 'pie', 'forecast') or null.
"""
                try:
                    llm_content = await self._call_llm_provider(
                        system_prompt=system_prompt,
                        user_query=user_query,
                        openai_key=active_openai,
                        anthropic_key=active_anthropic,
                        groq_key=active_groq,
                        gemini_key=active_gemini
                    )
                except Exception as e:
                    yield {"type": "token", "content": f"LLM Connection error: {str(e)}"}
                    return
                
                tool_to_call = llm_content.get("tool_called")
                tool_args = llm_content.get("tool_args", {})
                sql_query_ran = llm_content.get("sql")
                chart_type = llm_content.get("chart_type")
                
                tool_res_str = ""
                raw_data = None
                
                if tool_to_call:
                    # Run the tool
                    try:
                        if tool_to_call == "list_datasets":
                            tool_res_str = await asyncio.to_thread(list_datasets)
                        elif tool_to_call == "get_dataset_schema":
                            tool_res_str = await asyncio.to_thread(get_dataset_schema, tool_args.get("dataset_name", ""))
                        elif tool_to_call == "execute_query":
                            tool_res_str = await asyncio.to_thread(execute_query, tool_args.get("sql_query", ""))
                        elif tool_to_call == "generate_forecast":
                            cfg = forecast_config or {}
                            tool_res_str = await asyncio.to_thread(
                                generate_forecast,
                                dataset_name=tool_args.get("dataset_name", ""),
                                date_column=tool_args.get("date_column", ""),
                                target_column=tool_args.get("target_column", ""),
                                horizon_steps=int(tool_args.get("horizon_steps", 30)),
                                model_type=cfg.get("model_type") or tool_args.get("model_type", "auto"),
                                seasonality_mode=cfg.get("seasonality_mode") or tool_args.get("seasonality_mode", "add"),
                                clean_outliers=cfg.get("clean_outliers") if cfg.get("clean_outliers") is not None else bool(tool_args.get("clean_outliers", False)),
                                fill_method=cfg.get("fill_method") or tool_args.get("fill_method", "interpolate")
                            )
                        
                        # Parse raw data
                        if tool_res_str:
                            parsed_res = json.loads(tool_res_str)
                            if isinstance(parsed_res, dict) and "data" in parsed_res:
                                raw_data = parsed_res["data"]
                            elif isinstance(parsed_res, list):
                                raw_data = parsed_res
                            else:
                                raw_data = parsed_res
                    except Exception as tool_err:
                        tool_res_str = f"Error executing tool: {str(tool_err)}"
                
                # Now stream the final explanation (Second LLM Call)
                history = [
                    {"role": "user", "content": user_query},
                    {"role": "assistant", "content": json.dumps(llm_content)},
                    {"role": "user", "content": f"Tool execution result:\n{tool_res_str}\nNow write the final natural language explanation in the user's language. Describe findings from the data. Do NOT output any JSON blocks. Just stream the plain text."}
                ]
                
                explanation_prompt = f"Explain the dataset analytics findings clearly to the user. Do not return JSON. Write in the user's language."
                
                # Call streaming provider
                async for token in self._call_llm_provider_stream(
                    system_prompt=explanation_prompt,
                    user_query="",
                    history=history,
                    openai_key=active_openai,
                    anthropic_key=active_anthropic,
                    groq_key=active_groq,
                    gemini_key=active_gemini
                ):
                    yield {"type": "token", "content": token}
                
                # Construct final structural events
                if sql_query_ran:
                    yield {"type": "sql", "content": sql_query_ran}
                
                if raw_data is not None:
                    yield {"type": "data", "content": raw_data}
                    
                    # Guess chart config
                    if chart_type and chart_type != "table":
                        x_col = ""
                        y_col = ""
                        if isinstance(raw_data, list) and len(raw_data) > 0:
                            first_row = raw_data[0]
                            if isinstance(first_row, dict):
                                keys = list(first_row.keys())
                                x_col = keys[0] if len(keys) > 0 else ""
                                y_col = keys[1] if len(keys) > 1 else (keys[0] if len(keys) > 0 else "")
                        yield {
                            "type": "chart", 
                            "content": {
                                "type": chart_type,
                                "x": x_col,
                                "y": y_col
                            }
                        }
            else:
                # Alternate Mock Local Engine
                # Get the result from mock agent (which is instant)
                mock_result = await self._run_mock_agent(user_query, current_dataset, forecast_config)
                
                explanation = mock_result.get("response", "")
                sql = mock_result.get("sql")
                data = mock_result.get("data")
                chart = mock_result.get("chart")
                
                # Stream the explanation text slowly (word by word)
                words = explanation.split(" ")
                for i, word in enumerate(words):
                    space = " " if i < len(words) - 1 else ""
                    yield {"type": "token", "content": word + space}
                    # Sleep slightly to simulate token-by-token streaming
                    await asyncio.sleep(0.015)
                
                # Yield other data parts
                if sql:
                    yield {"type": "sql", "content": sql}
                if data is not None:
                    yield {"type": "data", "content": data}
                if chart:
                    yield {"type": "chart", "content": chart}
                    
        except Exception as e:
            yield {"type": "token", "content": f"\nError in streaming pipeline: {str(e)}"}

supervisor_agent = SupervisorAgent()

