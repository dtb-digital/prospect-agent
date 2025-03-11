from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from agent import app as workflow_app, get_config
from models import User
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(
    title="Prospect Agent API",
    description="API for å finne og analysere relevante kontakter",
    version="1.0.0"
)

class SearchRequest(BaseModel):
    domain: str
    target_role: str
    max_results: int = 5

class SearchResponse(BaseModel):
    """API respons med kun analyserte profiler"""
    profiles: List[User]

@app.post("/search", response_model=SearchResponse)
async def search_prospects(request: SearchRequest):
    try:
        print(f"=== Søker etter prospekter for domene: {request.domain} ===")
        print(f"Målrolle: {request.target_role}")
        print(f"Maks resultater: {request.max_results}")
        
        # Opprett config-objekt
        config = {
            "domain": request.domain,
            "target_role": request.target_role,
            "max_users": request.max_results  # Sjekk at nøkkelen er riktig
        }
        
        # Opprett initial state
        initial_state = {
            "messages": [],
            "users": [],
            "config": config
        }
        
        print(f"Initial state: {initial_state}")
        
        # Kjør workflow
        result = workflow_app.invoke(initial_state, config=get_config())
        
        print(f"Workflow fullført. Resultat inneholder følgende nøkler: {list(result.keys())}")
        
        # Sjekk at users-nøkkelen eksisterer
        if "users" not in result:
            print(f"FEIL: 'users' ikke funnet i resultatet for domene {request.domain}")
            print(f"Resultat: {result}")
            return SearchResponse(profiles=[])
        
        print(f"Antall brukere i resultatet: {len(result['users'])}")
        
        # Filtrer analyserte brukere
        analyzed_users = [
            User(**user) for user in result["users"] 
            if "sources" in user and "analyzed" in user["sources"]
        ]
        
        print(f"Antall analyserte brukere: {len(analyzed_users)}")
        
        return SearchResponse(profiles=analyzed_users)
    except Exception as e:
        print(f"FEIL i search_prospects: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Velkommen til Prospect Agent API"} 