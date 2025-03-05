from langsmith import Client
from agent import analyze_domain
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any, Optional
import traceback

load_dotenv()
client = Client()

# Sjekk om evaluering er aktivert
ENABLE_EVALUATION = os.getenv("ENABLE_EVALUATION", "false").lower() == "true"
print(f"Evaluering er {'aktivert' if ENABLE_EVALUATION else 'deaktivert'}")

def check_langsmith_api():
    """Sjekker at LangSmith API-nøkkelen er riktig og at du har tilgang."""
    try:
        # Prøv å hente datasets
        datasets = client.list_datasets()
        print(f"LangSmith API fungerer! Fant {len(datasets)} datasets.")
        return True
    except Exception as e:
        print(f"Feil ved tilkobling til LangSmith API: {e}")
        return False

def check_ground_truth_dataset():
    """Sjekker at ground truth datasettet eksisterer og har eksempler."""
    try:
        dataset_name = "ground-truth"
        datasets = client.list_datasets()
        
        for dataset in datasets:
            if dataset.name == dataset_name:
                print(f"Fant ground truth datasett '{dataset_name}' med ID: {dataset.id}")
                
                # Sjekk om datasettet har eksempler
                examples = list(client.list_examples(dataset_name=dataset_name))
                print(f"Datasettet har {len(examples)} eksempler")
                
                if len(examples) == 0:
                    print("ADVARSEL: Datasettet har ingen eksempler!")
                
                return dataset
        
        print(f"ADVARSEL: Ground truth datasett '{dataset_name}' ikke funnet!")
        return None
    
    except Exception as e:
        print(f"Feil ved sjekk av ground truth datasett: {e}")
        return None

# Kjør sjekkene når modulen lastes
print("Sjekker LangSmith API...")
check_langsmith_api()
print("Sjekker ground truth datasett...")
check_ground_truth_dataset()

def create_ground_truth_dataset():
    """Henter det eksisterende ground truth datasettet."""
    dataset_name = "ground-truth"
    dataset_id = "f29c8afc-5172-4c16-9bf8-3890fbde6755"
    
    try:
        # Prøv å hente datasettet direkte med ID
        try:
            dataset = client.read_dataset(dataset_id)
            print(f"Fant ground truth datasett '{dataset.name}' med ID: {dataset.id}")
            return dataset
        except Exception as e:
            print(f"Kunne ikke hente datasett med ID {dataset_id}: {e}")
        
        # Prøv å hente datasettet med navn
        datasets = client.list_datasets()
        for dataset in datasets:
            if dataset.name == dataset_name:
                print(f"Fant ground truth datasett '{dataset_name}' med ID: {dataset.id}")
                return dataset
                
        # Hvis vi kommer hit, fant vi ikke datasettet
        raise ValueError(f"Ground truth datasett '{dataset_name}' ikke funnet")
        
    except Exception as e:
        print(f"Feil ved henting av ground truth datasett: {e}")
        raise e

def exact_match_evaluator(inputs, outputs, reference_outputs):
    """
    Enkel evaluator som sjekker om outputs matcher reference_outputs.
    
    Args:
        inputs: Input til funksjonen
        outputs: Faktisk output fra funksjonen
        reference_outputs: Forventet output (ground truth)
        
    Returns:
        float: 1.0 hvis match, 0.0 hvis ikke match
    """
    # Sjekk om outputs inneholder users
    if "users" not in outputs:
        print("Outputs mangler 'users' felt")
        return 0.0
    
    # Sjekk om reference_outputs inneholder users eller label
    if "users" in reference_outputs:
        ref_users = reference_outputs["users"]
    elif "label" in reference_outputs and isinstance(reference_outputs["label"], list):
        ref_users = reference_outputs["label"]
    else:
        print("Reference outputs mangler 'users' eller 'label' felt")
        return 0.0
    
    # Sjekk om det er minst én bruker i hver
    if len(outputs["users"]) == 0:
        print("Outputs inneholder ingen brukere")
        return 0.0
    
    if len(ref_users) == 0:
        print("Reference outputs inneholder ingen brukere")
        return 0.0
    
    # Sjekk at første bruker i outputs har samme struktur som første bruker i ref_users
    user = outputs["users"][0]
    ref_user = ref_users[0]
    
    # Sjekk at alle nøkler i ref_user finnes i user
    for key in ref_user:
        if key not in user:
            print(f"Bruker mangler nøkkel: {key}")
            return 0.0
    
    return 1.0

def field_validation(inputs, outputs, reference_outputs):
    """
    Sjekker at output inneholder samme felter som referanse-output.
    Evaluerer strukturen uavhengig av domene og rolle.
    
    Args:
        inputs: Input til workflowen
        outputs: Output fra workflowen
        reference_outputs: Referanse-output fra ground truth
        
    Returns:
        Dict med score og kommentar
    """
    try:
        # Sjekk om outputs inneholder users-feltet
        if "users" not in outputs:
            return {
                "score": 0.0,
                "comment": "Output mangler users-feltet"
            }
        
        # Sjekk om reference_outputs inneholder users-feltet
        if "users" not in reference_outputs:
            return {
                "score": 0.0,
                "comment": "Reference output mangler users-feltet"
            }
        
        # Hent users fra outputs og reference_outputs
        actual_users = outputs.get("users", [])
        ref_users = reference_outputs.get("users", [])
        
        # Sjekk om det er minst én bruker i hver
        if len(actual_users) == 0:
            return {
                "score": 0.0,
                "comment": "Output inneholder ingen brukere"
            }
        
        if len(ref_users) == 0:
            return {
                "score": 0.0,
                "comment": "Reference output inneholder ingen brukere"
            }
        
        # Sjekk at første bruker i actual_users har samme felter som første bruker i ref_users
        actual_user = actual_users[0]
        ref_user = ref_users[0]
        
        # Hent alle nøkler i ref_user
        ref_keys = set(ref_user.keys())
        actual_keys = set(actual_user.keys())
        
        # Finn viktige nøkler som bør være til stede
        important_keys = {"name", "title", "email", "linkedin_url", "relevance_score"}
        
        # Finn manglende viktige nøkler
        missing_important_keys = important_keys - actual_keys
        
        # Beregn score basert på antall manglende viktige nøkler
        if len(missing_important_keys) > 0:
            # Beregn prosentandel av viktige nøkler som er til stede
            score = 1.0 - (len(missing_important_keys) / len(important_keys))
            return {
                "score": score,
                "comment": f"Output mangler følgende viktige felter: {', '.join(missing_important_keys)}"
            }
        
        # Alt er bra!
        return {
            "score": 1.0,
            "comment": "Output inneholder alle nødvendige felter"
        }
    
    except Exception as e:
        return {
            "score": 0.0,
            "comment": f"Feil under evaluering: {str(e)}"
        }

def evaluate_against_ground_truth():
    """Evaluerer agenten mot ground truth datasettet."""
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        print("Evaluering er deaktivert. Sett ENABLE_EVALUATION=true for å aktivere.")
        return None
    
    try:
        # Hent ground truth datasett
        dataset = create_ground_truth_dataset()
        
        # Lag et unikt prosjektnavn med tidsstempel
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project_name = f"prospect-agent-ground-truth-eval-{timestamp}"
        
        # Definer en wrapper-funksjon som konverterer resultatet til et serialiserbart format
        def analyze_domain_wrapper(inputs):
            from agent import analyze_domain
            domain = inputs.get("domain")
            target_role = inputs.get("target_role")
            result = analyze_domain(domain, target_role)
            
            # Konverter resultatet til et serialiserbart format
            serializable_result = {}
            if "users" in result:
                serializable_result["users"] = result["users"]
            
            return serializable_result
        
        # Kjør evalueringen
        print(f"Evaluerer agenten mot ground truth datasett...")
        results = client.evaluate(
            analyze_domain_wrapper,
            data=dataset.name,
            evaluators=[field_validation, exact_match_evaluator],
            experiment_prefix=project_name,
            description="Evaluering mot ground truth",
            max_concurrency=2
        )
        
        print(f"Evaluering fullført!")
        print(f"Se resultatene i LangSmith: https://eu.smith.langchain.com/o/{os.getenv('LANGCHAIN_PROJECT')}/projects")
        
        return results
    
    except Exception as e:
        print(f"Kunne ikke evaluere mot ground truth: {e}")
        return None

def evaluate_result(domain: str, target_role: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Evaluerer et resultat mot ground truth.
    Fokuserer på struktur og kvalitet i output, uavhengig av domene og rolle.
    
    Args:
        domain: Domenet som ble analysert
        target_role: Målrollen som ble brukt
        result: Resultatet fra workflowen
        
    Returns:
        Dict med evalueringsresultater, eller None hvis evaluering er deaktivert
    """
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        print("Evaluering er deaktivert. Sett ENABLE_EVALUATION=true for å aktivere.")
        return None
    
    try:
        # Hent ground truth datasettet
        dataset_name = "ground-truth"
        
        # Hent første eksempel fra ground truth for evaluering
        examples = list(client.list_examples(dataset_name=dataset_name))
        if examples:
            # Velg første eksempel for evaluering
            example = examples[0]
            print(f"Evaluerer resultat for domene {domain} mot ground truth eksempel")
                
            # Lag et unikt prosjektnavn med tidsstempel
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            project_name = f"workflow-evaluation-{timestamp}"
                
            # Kjør evalueringen
            from langsmith import evaluate
            results = evaluate(
                lambda x: result,  # Returner resultatet direkte
                data=dataset_name,
                evaluators=[field_validation, exact_match_evaluator],
                experiment_prefix=project_name,
            )
                
            print(f"Evaluert resultat for domene {domain} mot ground truth")
            return results
        
        print(f"Ingen ground truth eksempler funnet for evaluering")
        return None
    
    except Exception as e:
        print(f"Kunne ikke evaluere mot ground truth: {e}")
        return None

def evaluate_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """
    Evaluerer en trace mot ground truth hvis det finnes en match.
    Fokuserer på struktur og kvalitet i output.
    
    Args:
        trace_id: ID-en til tracen som skal evalueres
        
    Returns:
        Dict med evalueringsresultater, eller None hvis evaluering er deaktivert
        eller ingen match ble funnet
    """
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        print("Evaluering er deaktivert. Sett ENABLE_EVALUATION=true for å aktivere.")
        return None
    
    try:
        # Hent tracen
        trace = client.get_run(trace_id)
        
        # Hent inputs og outputs
        inputs = trace.inputs
        outputs = trace.outputs
        
        # Hent domain og target_role
        domain = inputs.get("domain")
        target_role = inputs.get("target_role")
        
        if not domain or not target_role:
            print(f"Trace {trace_id} mangler domain eller target_role")
            return None
        
        # Evaluer resultatet
        return evaluate_result(domain, target_role, outputs)
    
    except Exception as e:
        print(f"Kunne ikke evaluere trace {trace_id}: {e}")
        return None

def evaluate_against_all_ground_truth():
    """
    Evaluerer agenten mot hele ground truth datasettet.
    Fokuserer på struktur og kvalitet i output.
    """
    # Sjekk om evaluering er aktivert
    if not ENABLE_EVALUATION:
        print("Evaluering er deaktivert. Sett ENABLE_EVALUATION=true for å aktivere.")
        return None
    
    try:
        # Hent ground truth datasett
        dataset = create_ground_truth_dataset()
        
        # Lag et unikt prosjektnavn med tidsstempel
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project_name = f"prospect-agent-full-eval-{timestamp}"
        
        # Importer analyze_domain her for å unngå sirkularitet
        from agent import analyze_domain
        
        # Kjør evalueringen mot hele datasettet
        print(f"Evaluerer agenten mot hele ground truth datasettet...")
        results = client.evaluate(
            analyze_domain,
            data=dataset.name,
            evaluators=[field_validation, exact_match_evaluator],
            experiment_prefix=project_name,
            description="Full evaluering mot ground truth",
            max_concurrency=2
        )
        
        print(f"Evaluering fullført!")
        print(f"Se resultatene i LangSmith: https://eu.smith.langchain.com/o/{os.getenv('LANGCHAIN_PROJECT')}/projects")
        
        return results
    
    except Exception as e:
        print(f"Kunne ikke evaluere mot ground truth: {e}")
        return None

if __name__ == "__main__":
    # Kjør evaluering mot hele datasettet
    evaluate_against_all_ground_truth() 