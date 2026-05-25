import os
import re
import json
import duckdb
import pandas as pd
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("Hyperlytics DuckDB Engine")

# Data directory
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)

def get_file_path(filename: str) -> str:
    """Resolve full path of a file in the data directory."""
    # Prevent directory traversal attacks
    safe_filename = os.path.basename(filename)
    return os.path.join(DATA_DIR, safe_filename)

@mcp.tool()
def list_datasets() -> str:
    """
    Lists all available datasets uploaded to the system, including file sizes and extensions.
    Use this to see what tables/datasets are available to query.
    """
    if not os.path.exists(DATA_DIR):
        return json.dumps([])
    
    datasets = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(('.csv', '.parquet', '.xlsx', '.json')):
            path = os.path.join(DATA_DIR, file)
            datasets.append({
                "name": file,
                "size_bytes": os.path.getsize(path),
                "format": file.split('.')[-1].upper(),
                "path": path
            })
    return json.dumps(datasets, indent=2)

@mcp.tool()
def get_dataset_schema(dataset_name: str) -> str:
    """
    Profiles a dataset to return its column names, data types, null percentage, 
    cardinality, and a 3-row data sample.
    """
    filepath = get_file_path(dataset_name)
    if not os.path.exists(filepath):
        return json.dumps({"error": f"Dataset '{dataset_name}' not found."})

    try:
        con = duckdb.connect(database=':memory:')
        
        # Determine reading query based on file type
        if filepath.endswith('.csv'):
            read_query = f"SELECT * FROM read_csv_auto('{filepath}')"
        elif filepath.endswith('.parquet'):
            read_query = f"SELECT * FROM read_parquet('{filepath}')"
        elif filepath.endswith('.xlsx'):
            # Fall back to pandas for excel sheets using calamine if possible
            try:
                df = pd.read_excel(filepath, engine="calamine")
            except Exception:
                df = pd.read_excel(filepath)
            con.register('excel_tbl', df)
            read_query = "SELECT * FROM excel_tbl"
        elif filepath.endswith('.json'):
            read_query = f"SELECT * FROM read_json_auto('{filepath}')"
        else:
            return json.dumps({"error": "Unsupported file format."})

        # Get schema columns and types
        info = con.execute(f"DESCRIBE {read_query}").fetchall()
        schema = []
        for col_name, col_type, null_val, key, default_val, extra in info:
            # Escape double quotes in column names for standard SQL identifier quoting
            escaped_col = col_name.replace('"', '""')
            null_count = con.execute(f"SELECT COUNT(*) - COUNT(\"{escaped_col}\") FROM ({read_query})").fetchone()[0]
            total_count = con.execute(f"SELECT COUNT(*) FROM ({read_query})").fetchone()[0]
            cardinality = con.execute(f"SELECT COUNT(DISTINCT \"{escaped_col}\") FROM ({read_query})").fetchone()[0]
            
            schema.append({
                "column": col_name,
                "type": col_type,
                "null_percentage": round((null_count / total_count) * 100, 2) if total_count > 0 else 0,
                "cardinality": cardinality
            })
            
        # Get 3-row sample
        sample_df = con.execute(f"SELECT * FROM ({read_query}) LIMIT 3").df()
        # Clean Pandas NaN/inf to None to ensure standard JSON compliance
        sample_df = sample_df.where(pd.notnull(sample_df), None)
        sample_data = sample_df.to_dict(orient='records')
        
        con.close()
        
        return json.dumps({
            "dataset": dataset_name,
            "row_count": total_count,
            "columns": schema,
            "sample_data": sample_data
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": f"Failed to profile dataset: {str(e)}"})

@mcp.tool()
def execute_query(sql_query: str) -> str:
    """
    Executes a read-only DuckDB SQL query.
    Note: You must refer to tables using their filenames as table names, e.g., 'sales.csv' or 'users.parquet'.
    Example: SELECT product, SUM(revenue) FROM 'sales.csv' GROUP BY product ORDER BY 2 DESC LIMIT 5;
    """
    # Basic security check to prevent destructive queries
    cleaned_query = sql_query.strip().lower()
    forbidden_keywords = ['drop', 'delete', 'insert', 'update', 'alter', 'truncate', 'grant', 'revoke', 'create table']
    for keyword in forbidden_keywords:
        # Check for matching word boundary to prevent matching substrings like "droplet"
        if re.search(r'\b' + keyword + r'\b', cleaned_query):
            return json.dumps({"error": f"Security Exception: Query contains forbidden state-modifying keyword: '{keyword}'"})
            
    # Resolve all referenced file tables in the query to their full path in the data folder
    # Matches strings inside quotes: 'filename.ext' or "filename.ext"
    matches = re.findall(r"['\"]([^\'\"]+?\.(?:csv|parquet|xlsx|json))['\"]", sql_query, re.IGNORECASE)
    modified_query = sql_query
    
    for match in matches:
        if match.lower().endswith(('.csv', '.parquet', '.json')):
            full_path = get_file_path(match).replace("\\", "/")
            modified_query = modified_query.replace(f"'{match}'", f"'{full_path}'").replace(f'"{match}"', f"'{full_path}'")
        elif match.lower().endswith('.xlsx'):
            # Replace single quotes with double quotes so DuckDB treats it as registered table identifier
            modified_query = modified_query.replace(f"'{match}'", f'"{match}"')

    try:
        con = duckdb.connect(database=':memory:')
        # Check if there are any excel tables that need register
        for match in matches:
            if match.lower().endswith('.xlsx'):
                full_path = get_file_path(match)
                if os.path.exists(full_path):
                    try:
                        df = pd.read_excel(full_path, engine="calamine")
                    except Exception:
                        df = pd.read_excel(full_path)
                    con.register(match, df)

        # Run query
        df = con.execute(modified_query).df()
        con.close()
        
        # Limit rows returned in context to 100 to prevent context window overflow, 
        # but let the agent know there might be more.
        total_rows = len(df)
        df_truncated = df.head(100)
        df_truncated = df_truncated.where(pd.notnull(df_truncated), None)
        
        return json.dumps({
            "query_executed": sql_query,
            "total_rows_in_result": total_rows,
            "rows_returned": len(df_truncated),
            "data": df_truncated.to_dict(orient='records')
        }, indent=2, default=str)
        
    except Exception as e:
        return json.dumps({"error": f"Failed to execute query: {str(e)}"})

if __name__ == "__main__":
    # Expose command-line run for stdio
    mcp.run()
