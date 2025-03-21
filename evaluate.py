from langsmith import Client
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any, Optional, List
import traceback
from langchain_core.runnables import RunnableConfig
from langsmith.schemas import Example, Run

load_dotenv()

# Initialiser LangSmith-klienten
try:
    # Sjekk at miljøvariabelen er satt
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        print("ADVARSEL: LANGCHAIN_API_KEY er ikke satt i .env-filen.")
    
    # Bruk LANGSMITH_ENDPOINT hvis det er satt, ellers bruk standard EU-endepunkt
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    print(f"Bruker LangSmith-endepunkt: {endpoint}")
    
    # Initialiser klienten
    client = Client(
        api_key=api_key,
        api_url=endpoint
    )
    print("LangSmith-klient initialisert.")
except Exception as e:
    print(f"Feil ved initialisering av LangSmith-klient: {e}")
    client = None

# Sjekk om evaluering er aktivert
ENABLE_EVALUATION = os.getenv("ENABLE_EVALUATION", "false").lower() == "true"
print(f"Evaluering er {'aktivert' if ENABLE_EVALUATION else 'deaktivert'}")

# Navn på ground-truth datasettet
GROUND_TRUTH_DATASET = os.getenv("GROUND_TRUTH_DATASET", "ground-truth")

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

def evaluate_result(domain: str, target_role: str, results: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluerer resultatene fra agenten."""
    
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        return results
    
    try:
        print("Evaluerer resultater...")
        
        # Opprett en Run-lignende struktur for å bruke evaluatorene
        mock_run = type('Run', (), {
            'outputs': results,
            'inputs': {
                'domain': domain,
                'target_role': target_role
            }
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
        
        # Sjekk at API-nøkkelen er gyldig
        if not check_langsmith_api():
            print("Kan ikke evaluere: LangSmith API-nøkkelen er ikke gyldig.")
            return None
        
        # Sjekk at datasettet eksisterer og har eksempler
        dataset = check_ground_truth_dataset()
        if not dataset:
            print("Kan ikke evaluere: Ground-truth datasett ikke funnet eller har ingen eksempler.")
            print("Du må opprette datasettet og legge til eksempler manuelt i LangSmith.")
            return None
        
        # Importer analyze_domain her for å unngå sirkularitet
        from agent import analyze_domain
        
        # Definer en wrapper-funksjon for analyze_domain
        def predict(inputs: Dict[str, Any]) -> Dict[str, Any]:
            """Wrapper-funksjon for analyze_domain."""
            # Sjekk om input har config-objekt
            if "config" in inputs and isinstance(inputs["config"], dict):
                config = inputs["config"]
                domain = config.get("domain")
                target_role = config.get("target_role")
            else:
                # Prøv å hente direkte fra inputs
                domain = inputs.get("domain")
                target_role = inputs.get("target_role")
            
            # Valider inputs
            if not domain or not isinstance(domain, str):
                print(f"Ugyldig domain: {domain}")
                return {"error": "Domain må være en gyldig streng"}
            
            if not target_role or not isinstance(target_role, str):
                print(f"Ugyldig target_role: {target_role}")
                return {"error": "Target role må være en gyldig streng"}
            
            print(f"Kjører analyze_domain med domain={domain}, target_role={target_role}")
            result = analyze_domain(domain, target_role)
            print(f"Resultat: {len(result.get('users', []))} brukere funnet")
            return result
        
        # Lag et unikt eksperimentnavn med tidsstempel
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        experiment_prefix = f"prospect-agent-eval-{timestamp}"
        
        # Kjør evalueringen
        print(f"Evaluerer agenten mot ground-truth datasett...")
        print(f"Eksperiment: {experiment_prefix}")
        
        # Skriv ut alle evaluatorer som brukes
        evaluators = [
            relevans_evaluator,
            kvalitet_evaluator,
            fullstendighet_evaluator,
            prioritering_evaluator
        ]
        print(f"Bruker {len(evaluators)} evaluatorer:")
        for evaluator in evaluators:
            print(f"  - {evaluator.__name__}")
        
        # Kjør evalueringen
        results = client.evaluate(
            predict,
            data=GROUND_TRUTH_DATASET,
            evaluators=evaluators,
            experiment_prefix=experiment_prefix,
            metadata={"timestamp": timestamp, "tags": ["prospect-agent", "evaluation"]}
        )
        
        print(f"Evaluering fullført!")
        print(f"Eksperiment: {experiment_prefix}")
        print(f"Se resultatene i LangSmith: https://eu.smith.langchain.com/projects")
        
        return results
    
    except Exception as e:
        print(f"Kunne ikke evaluere mot ground-truth datasett: {e}")
        traceback.print_exc()
        return None

def check_langsmith_api():
    """Sjekker at LangSmith API-nøkkelen er riktig og at du har tilgang."""
    try:
        # Sjekk at miljøvariabelen er satt
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if not api_key:
            print("ADVARSEL: LANGCHAIN_API_KEY er ikke satt i .env-filen.")
            return False
        
        # Skriv ut de første og siste tegnene i API-nøkkelen for debugging
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
        print(f"Bruker LANGCHAIN_API_KEY: {masked_key}")
        
        # Sjekk at andre nødvendige miljøvariabler er satt
        project = os.getenv("LANGCHAIN_PROJECT")
        if not project:
            print("ADVARSEL: LANGCHAIN_PROJECT er ikke satt i .env-filen.")
        else:
            print(f"Bruker LANGCHAIN_PROJECT: {project}")
        
        # Sjekk at endepunktet er riktig
        endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
        print(f"Bruker LANGSMITH_ENDPOINT: {endpoint}")
        
        # Prøv å hente datasets
        # Konverter generator til liste for å kunne bruke len()
        datasets = list(client.list_datasets())
        print(f"LangSmith API fungerer! Fant {len(datasets)} datasets.")
        
        # Skriv ut navnene på datasettene
        if datasets:
            print("Tilgjengelige datasett:")
            for dataset in datasets:
                print(f"  - {dataset.name} (ID: {dataset.id})")
        
        return True
    except Exception as e:
        print(f"Feil ved tilkobling til LangSmith API: {e}")
        traceback.print_exc()
        return False

def check_ground_truth_dataset():
    """Sjekker at ground-truth datasettet eksisterer og har eksempler."""
    try:
        print(f"Sjekker ground-truth datasett: {GROUND_TRUTH_DATASET}")
        
        # Sjekk om datasettet eksisterer
        try:
            dataset = client.read_dataset(dataset_name=GROUND_TRUTH_DATASET)
            print(f"Fant ground-truth datasett: {dataset.name} (ID: {dataset.id})")
        except Exception as e:
            print(f"Ground-truth datasett '{GROUND_TRUTH_DATASET}' ikke funnet: {e}")
            print("Du må opprette datasettet manuelt i LangSmith før du kan kjøre evalueringen.")
            return None
        
        # Sjekk om datasettet har eksempler
        # Konverter generator til liste for å kunne bruke len()
        examples = list(client.list_examples(dataset_name=GROUND_TRUTH_DATASET))
        print(f"Datasettet har {len(examples)} eksempler")
        
        if len(examples) == 0:
            print("ADVARSEL: Datasettet har ingen eksempler!")
            print("Du må legge til minst ett eksempel i datasettet før du kan kjøre evalueringen.")
            return None
        
        return dataset
    
    except Exception as e:
        print(f"Feil ved sjekk av ground-truth datasett: {e}")
        traceback.print_exc()
        return None

# Kjør sjekken når modulen lastes
print("Sjekker LangSmith API...")
if not check_langsmith_api():
    print("ADVARSEL: LangSmith API-nøkkelen er ikke gyldig eller du har ikke tilgang.")
    print("Sett LANGCHAIN_API_KEY i .env-filen.")

print("Sjekker ground-truth datasett...")
check_ground_truth_dataset()

if __name__ == "__main__":
    # Kjør evaluering mot ground-truth datasettet
    evaluate_against_ground_truth() 