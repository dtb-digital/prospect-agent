from langsmith import Client
from agent import analyze_domain
import os
from dotenv import load_dotenv
from datetime import datetime
from openevals.llm import create_llm_as_judge

load_dotenv()
client = Client()

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
    
    # Sjekk om antall brukere matcher
    if len(outputs["users"]) != len(ref_users):
        print(f"Antall brukere matcher ikke: {len(outputs['users'])} vs {len(ref_users)}")
        return 0.0
    
    # Sjekk om hver bruker matcher
    for i, ref_user in enumerate(ref_users):
        if i >= len(outputs["users"]):
            print(f"Mangler bruker {i} i outputs")
            return 0.0
        
        user = outputs["users"][i]
        
        # Sjekk navn og tittel
        if user.get("name") != ref_user.get("name") or user.get("title") != ref_user.get("title"):
            print(f"Bruker {i} matcher ikke: {user.get('name')} vs {ref_user.get('name')}")
            return 0.0
    
    return 1.0

# Definer en tilpasset prompt for LLM-as-a-judge
DOMAIN_ANALYSIS_PROMPT = """
Du er en ekspert på å evaluere domeneanalyser. Din oppgave er å vurdere kvaliteten på en domeneanalyse basert på følgende kriterier:

<Kriterier>
  En god domeneanalyse:
  - Identifiserer relevante personer basert på domenet og målrollen
  - Gir nøyaktig informasjon om personene (navn, tittel, etc.)
  - Inkluderer relevant informasjon om personenes bakgrunn og ekspertise
  - Er relevant for målrollen som er spesifisert
</Kriterier>

<Input>
Domain: {inputs[domain]}
Target role: {inputs[target_role]}
</Input>

<Output>
{outputs}
</Output>

<Reference Output>
{reference_outputs}
</Reference Output>

Vurder hvor godt outputen matcher reference outputen på en skala fra 0 til 10, der 10 er perfekt match og 0 er ingen match.

Gi en begrunnelse for din vurdering, og avslutt med en numerisk score på formatet "Score: X/10".
"""

def evaluate_against_ground_truth():
    """Evaluerer agenten mot ground truth datasettet."""
    # Hent ground truth datasett
    dataset = create_ground_truth_dataset()
    
    # Lag et unikt prosjektnavn med tidsstempel
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_name = f"prospect-agent-ground-truth-eval-{timestamp}"
    
    # Opprett LLM-as-a-judge evaluator fra openevals
    llm_judge = create_llm_as_judge(
        prompt=DOMAIN_ANALYSIS_PROMPT,
        feedback_key="domain_analysis_quality",
        model="openai:gpt-4",
        continuous=True  # Bruk kontinuerlig score (0-1) i stedet for binær (True/False)
    )
    
    # Kjør evalueringen
    print(f"Evaluerer agenten mot ground truth datasett...")
    results = client.evaluate(
        analyze_domain,
        data=dataset.name,
        evaluators=[exact_match_evaluator, llm_judge],
        experiment_prefix=project_name,
        description="Evaluering mot ground truth med openevals LLM-as-a-judge",
        max_concurrency=2
    )
    
    print(f"Evaluering fullført!")
    print(f"Se resultatene i LangSmith: https://eu.smith.langchain.com/o/{os.getenv('LANGCHAIN_PROJECT')}/projects")
    
    return results

if __name__ == "__main__":
    evaluate_against_ground_truth() 