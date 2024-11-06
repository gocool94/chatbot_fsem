from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import snowflake.connector
import requests
import json

app = FastAPI()

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://192.168.0.112:3000"],  # Allow only the frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Rest of your code...
# Snowflake connection parameters
HOST = "fnb15390.snowflakecomputing.com"
DATABASE = "LLM_PM_CORTEX"
SCHEMA = "CIVIL_MACHINES"
SS = "manual_extract_ss"

# Connect to Snowflake
def get_snowflake_connection():
    return snowflake.connector.connect(
        user="TWINKLE",
        password="Twinkle@2000",
        account="fnb15390",
        host=HOST,
        port=443,
        warehouse="XS_WH",
        role="ACCOUNTADMIN"
    )

# Request and Response models for FastAPI
class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    answer: str
    references: list

# Endpoint to process user query
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(query_request: QueryRequest):
    conn = get_snowflake_connection()

    # Call Snowflake or external API
    try:
        prompt = query_request.question
        response = send_message(prompt, conn)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# Snowflake Cortex API call
def send_message(prompt: str, conn):
    request_body = {
        "query": prompt,
        "columns": ["chunk", "file_url", "relative_path"],
        "filter": {"@and": [{"@eq": {"language": "English"}}]},
        "limit": 10,
    }
    headers = {
        "Authorization": f'Snowflake Token="{conn.rest.token}"',
        "Content-Type": "application/json",
    }
    resp = requests.post(
        url=f"https://{HOST}/api/v2/databases/{DATABASE}/schemas/{SCHEMA}/cortex-search-services/{SS}:query",
        json=request_body,
        headers=headers,
    )
    request_id = resp.headers.get("X-Snowflake-Request-Id")

    if resp.status_code < 400:
        content = resp.json().get("results", [])
        context = json.dumps(content).replace("'", "")
        user_prompt = f"""
            <context>
            {context}
            </context>
            <question>
            {prompt}
            </question>
        """
        generated_response = conn.cursor().execute(
            f'''SELECT snowflake.cortex.complete('jamba-instruct', '{user_prompt}')'''
        ).fetchall()
        answer = generated_response[0][0]
        references = [{"relative_path": ref["relative_path"]} for ref in content]
        return QueryResponse(answer=answer, references=references)
    else:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"API Request failed with status {resp.status_code}"
        )
