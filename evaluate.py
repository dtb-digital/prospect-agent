from langsmith import Client
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any, Optional, List
import traceback
from langchain_core.runnables import RunnableConfig
from langsmith.schemas import Example, Run

load_dotenv()
client = Client()

# Sjekk om evaluering er aktivert
ENABLE_EVALUATION = os.getenv("ENABLE_EVALUATION", "false").lower() == "true"
print(f"Evaluering er {'aktivert' if ENABLE_EVALUATION else 'deaktivert'}")

# Navn på ground-truth datasettet
GROUND_TRUTH_DATASET = os.getenv("GROUND_TRUTH_DATASET", "prospect-agent-ground-truth")

def get_evaluation_config() -> RunnableConfig:
    """Konfigurerer evaluering av agenten."""
    
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        return {}
    
    print("Setter opp evalueringskonfigurasjon...")
    
    # Bruk en enkel konfigurasjon for tracing
    return RunnableConfig(
        callbacks=[],
        tags=["prospect-agent-eval"],
        metadata={"evaluation_enabled": True}
    )

# Definer evalueringsfunksjoner
def relevans_evaluator(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluerer relevansen av de identifiserte kontaktene."""
    prediction = run.outputs
    users = prediction.get("users", [])
    
    # Sjekk om brukerne er relevante for målrollen
    target_role = run.inputs.get("target_role", "")
    
    # Enkel heuristikk: Sjekk om brukerne har en relevance_score over 0.7
    relevant_users = [u for u in users if u.get("relevance_score", 0) > 0.7]
    score = len(relevant_users) / len(users) if users else 0
    
    return {
        "key": "relevans", 
        "score": score,
        "comment": f"Fant {len(relevant_users)} av {len(users)} relevante kontakter for {target_role}"
    }

def kvalitet_evaluator(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluerer kvaliteten på analysen av hver kontakt."""
    prediction = run.outputs
    users = prediction.get("users", [])
    
    # Enkel heuristikk: Sjekk om brukerne har en fyldig analyse
    quality_score = 0
    for user in users:
        # Sjekk om brukeren har en analyse
        if "analysis" in user and len(user.get("analysis", "")) > 100:
            quality_score += 1
    
    score = quality_score / len(users) if users else 0
    
    return {
        "key": "kvalitet", 
        "score": score,
        "comment": f"Fant {quality_score} av {len(users)} kontakter med fyldig analyse"
    }

def fullstendighet_evaluator(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluerer om alle viktige aspekter ved kontaktene er analysert."""
    prediction = run.outputs
    users = prediction.get("users", [])
    
    # Viktige felter som bør være til stede
    important_fields = ["name", "title", "email", "linkedin_url", "relevance_score", "analysis"]
    
    # Sjekk om brukerne har alle viktige felter
    completeness_score = 0
    for user in users:
        # Sjekk om brukeren har alle viktige felter
        if all(field in user for field in important_fields):
            completeness_score += 1
    
    score = completeness_score / len(users) if users else 0
    
    return {
        "key": "fullstendighet", 
        "score": score,
        "comment": f"Fant {completeness_score} av {len(users)} kontakter med alle viktige felter"
    }

def prioritering_evaluator(run: Run, example: Example) -> Dict[str, Any]:
    """Evaluerer om prioriteringen av kontaktene er fornuftig."""
    prediction = run.outputs
    users = prediction.get("users", [])
    
    # Sjekk om brukerne er sortert etter relevance_score
    if not users:
        return {
            "key": "prioritering", 
            "score": 0,
            "comment": "Ingen kontakter funnet"
        }
    
    # Sjekk om brukerne har relevance_score
    if not all("relevance_score" in user for user in users):
        return {
            "key": "prioritering", 
            "score": 0,
            "comment": "Ikke alle kontakter har relevance_score"
        }
    
    # Sjekk om brukerne er sortert etter relevance_score (høyest først)
    scores = [user.get("relevance_score", 0) for user in users]
    is_sorted = all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
    
    return {
        "key": "prioritering", 
        "score": 1.0 if is_sorted else 0.0,
        "comment": "Kontaktene er sortert etter relevans" if is_sorted else "Kontaktene er ikke sortert etter relevans"
    }

def evaluate_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluerer resultatene fra agenten."""
    
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        return results
    
    try:
        print("Evaluerer resultater...")
        
        # Opprett en Run-lignende struktur for å bruke evaluatorene
        mock_run = type('Run', (), {
            'outputs': results,
            'inputs': results.get('config', {})
        })
        
        # Evaluer resultatene med hver evaluator
        evaluation_results = {}
        evaluation_results["relevans"] = relevans_evaluator(mock_run, None)
        evaluation_results["kvalitet"] = kvalitet_evaluator(mock_run, None)
        evaluation_results["fullstendighet"] = fullstendighet_evaluator(mock_run, None)
        evaluation_results["prioritering"] = prioritering_evaluator(mock_run, None)
        
        # Legg til evalueringsresultatene i resultatene
        results["evaluation"] = evaluation_results
        
        print("Evaluering fullført")
        
        return results
    
    except Exception as e:
        print(f"Feil ved evaluering av resultater: {e}")
        traceback.print_exc()
        return results

def evaluate_against_ground_truth():
    """
    Evaluerer agenten mot ground-truth datasettet.
    """
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        print("Evaluering er deaktivert. Sett ENABLE_EVALUATION=true for å aktivere.")
        return None
    
    try:
        print(f"Evaluerer agenten mot ground-truth datasett: {GROUND_TRUTH_DATASET}")
        
        # Importer analyze_domain her for å unngå sirkularitet
        from agent import analyze_domain
        
        # Definer en wrapper-funksjon for analyze_domain
        def predict(inputs: Dict[str, Any]) -> Dict[str, Any]:
            """Wrapper-funksjon for analyze_domain."""
            domain = inputs.get("domain")
            target_role = inputs.get("target_role")
            return analyze_domain(domain, target_role)
        
        # Lag et unikt eksperimentnavn med tidsstempel
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        experiment_prefix = f"prospect-agent-eval-{timestamp}"
        
        # Kjør evalueringen
        print(f"Evaluerer agenten mot ground-truth datasett...")
        results = client.evaluate(
            predict,
            data=GROUND_TRUTH_DATASET,
            evaluators=[
                relevans_evaluator,
                kvalitet_evaluator,
                fullstendighet_evaluator,
                prioritering_evaluator
            ],
            experiment_prefix=experiment_prefix,
            metadata={"timestamp": timestamp},
            tags=["prospect-agent", "evaluation"]
        )
        
        print(f"Evaluering fullført!")
        print(f"Se resultatene i LangSmith: https://smith.langchain.com/projects")
        
        return results
    
    except Exception as e:
        print(f"Kunne ikke evaluere mot ground-truth datasett: {e}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # Kjør evaluering mot ground-truth datasettet
    evaluate_against_ground_truth() 