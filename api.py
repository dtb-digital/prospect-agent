from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from agent import app as workflow_app, get_config, analyze_domain
from models import SearchConfig, User, State
from langsmith import Client
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(
    title="Prospect Agent API",
    description="API for å finne og analysere relevante kontakter",
    version="1.0.0"
)
client = Client()

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
        result = workflow_app.invoke({
            "messages": [],
            "users": [],
            "config": SearchConfig(
                domain=request.domain,
                target_role=request.target_role,
                max_results=request.max_results
            )
        }, config=get_config())
        
        # Logg forespørselen for evaluering
        # Denne funksjonen kan beholdes hvis du vil fortsette å logge API-forespørsler,
        # men fjern kallet til trigger_evaluation_if_needed()
        
        # Sjekk at users-nøkkelen eksisterer
        if "users" not in result:
            print(f"Advarsel: 'users' ikke funnet i resultatet for domene {request.domain}")
            return SearchResponse(profiles=[])
        
        # Filtrer analyserte brukere
        analyzed_users = [
            User(**user) for user in result["users"] 
            if "sources" in user and "analyzed" in user["sources"]
        ]
        
        return SearchResponse(profiles=analyzed_users)
    except Exception as e:
        print(f"Feil i search_prospects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Velkommen til Prospect Agent API"}

def log_request_for_evaluation(request, result):
    """Logger en API-forespørsel til et evalueringsdatasett."""
    try:
        # Opprett eller hent evalueringsdatasett
        dataset_name = "prospect-agent-api-requests"
        
        # Sjekk om datasettet eksisterer
        datasets = client.list_datasets()
        dataset_exists = any(d.name == dataset_name for d in datasets)
        
        if not dataset_exists:
            client.create_dataset(
                dataset_name=dataset_name,
                description="API-forespørsler for evaluering av prospect-agent"
            )
        
        # Logg forespørselen
        client.create_example(
            inputs={
                "domain": request.domain,
                "target_role": request.target_role,
                "max_results": request.max_results
            },
            outputs=result,
            dataset_name=dataset_name
        )
        
        print(f"Logget API-forespørsel for domene {request.domain} til evalueringsdatasett")
        
        # Fjernet kallet til trigger_evaluation_if_needed()
    except Exception as e:
        print(f"Kunne ikke logge API-forespørsel for evaluering: {e}")

# Fjernet funksjonen trigger_evaluation_if_needed() 