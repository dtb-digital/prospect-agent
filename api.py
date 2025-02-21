from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from agent import app as workflow_app, get_config
from models import SearchConfig, User

class SearchRequest(BaseModel):
    domain: str
    target_role: str
    max_results: int = 5

class SearchResponse(BaseModel):
    messages: List[Dict[str, Any]]
    users: List[Dict[str, Any]]

app = FastAPI(
    title="Prospect Agent API",
    description="API for å finne og analysere relevante kontakter",
    version="1.0.0"
)

@app.post("/search", response_model=SearchResponse)
async def search_prospects(request: SearchRequest):
    try:
        result = workflow_app.invoke({
            "messages": [],
            "users": [],
            "config": SearchConfig(
                domain=request.domain,
                target_role=request.target_role,
                max_results=request.max_results
            )
        }, config=get_config())
        
        return {
            "messages": [msg.dict() for msg in result["messages"]],
            "users": result["users"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Velkommen til Prospect Agent API"} 