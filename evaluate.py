from langsmith import Client
from langsmith.evaluation import RunEvaluator
from agent import analyze_domain
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import time

load_dotenv()

# Initialiser LangSmith klienten
client = Client()

# 1. Lag et enkelt evalueringsdatasett
def create_test_dataset():
    # Sjekk om datasettet allerede eksisterer
    dataset_name = "prospect-agent-test"
    try:
        # Hent alle datasett
        datasets = client.list_datasets()
        # Finn datasettet med riktig navn
        for dataset in datasets:
            if dataset.name == dataset_name:
                print(f"Datasett '{dataset_name}' eksisterer allerede med ID: {dataset.id}")
                return dataset
                
        # Hvis vi kommer hit, fant vi ikke datasettet
        raise ValueError(f"Datasett '{dataset_name}' ikke funnet")
    except Exception as e:
        print(f"Kunne ikke finne eksisterende datasett: {e}")
        
        # Opprett nytt datasett
        try:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description="Test datasett for prospect-agent"
            )
            print(f"Opprettet nytt datasett '{dataset_name}' med ID: {dataset.id}")
            
            # Legg til noen testeksempler
            examples = [
                {
                    "inputs": {
                        "domain": "example.com",
                        "target_role": "CTO",
                        "max_results": 3
                    },
                    "outputs": {}  # Tomme outputs for nå
                },
                {
                    "inputs": {
                        "domain": "langchain.com",
                        "target_role": "Developer",
                        "max_results": 3
                    },
                    "outputs": {}
                }
            ]
            
            for example in examples:
                client.create_example(
                    inputs=example["inputs"],
                    outputs=example["outputs"],
                    dataset_id=dataset.id
                )
            
            print(f"La til {len(examples)} eksempler i datasettet")
            return dataset
        except Exception as e:
            print(f"Kunne ikke opprette nytt datasett: {e}")
            # Siste utvei - prøv å hente datasettet direkte med navn
            try:
                datasets = client.list_datasets()
                for dataset in datasets:
                    if dataset.name == dataset_name:
                        print(f"Fant eksisterende datasett '{dataset_name}' med ID: {dataset.id}")
                        return dataset
            except:
                pass
            
            raise e

# 2. Definer en enkel evaluator
class ProfileQualityEvaluator(RunEvaluator):
    def evaluate_run(self, run, example):
        # Hent resultatet fra kjøringen
        if not run.outputs:
            return {"error": "Ingen output fra kjøringen"}
        
        # Hent brukere fra output
        outputs = json.loads(run.outputs)
        users = outputs.get("users", [])
        analyzed_users = [u for u in users if "analyzed" in u.get("sources", [])]
        
        # Evaluer antall brukere
        count_score = min(1.0, len(analyzed_users) / 3)  # Forventer minst 3
        
        # Evaluer kvalitet (enkel versjon)
        quality_scores = []
        for user in analyzed_users:
            score = 0.0
            # Sjekk om viktige felter er fylt ut
            if user.get("about"):
                score += 0.3
            if user.get("career"):
                score += 0.3
            if user.get("expertise"):
                score += 0.4
            quality_scores.append(score)
        
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        return {
            "count_score": count_score,
            "quality_score": avg_quality,
            "overall_score": (count_score + avg_quality) / 2
        }

# Wrapper for analyze_domain som tar et dictionary av argumenter
def analyze_domain_wrapper(inputs):
    """Wrapper for analyze_domain som håndterer dictionary-input fra LangSmith."""
    return analyze_domain(
        domain=inputs.get("domain"),
        target_role=inputs.get("target_role"),
        max_results=inputs.get("max_results", 5)
    )

# 3. Kjør evalueringen
def run_evaluation():
    """Kjører evaluering av agenten på et datasett."""
    # Opprett eller hent datasett
    dataset = create_test_dataset()
    
    # Lag et unikt prosjektnavn med tidsstempel
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_name = f"prospect-agent-evaluation-{timestamp}"
    
    print(f"Starter evaluering med prosjekt: {project_name}")
    
    # Legg til en lengre forsinkelse før evalueringen
    print("Venter 3 sekunder for å unngå tidsstempelproblemer...")
    time.sleep(3)
    
    try:
        # Hent eksempler fra datasettet
        examples = list(client.list_examples(dataset_name=dataset.name))
        print(f"Fant {len(examples)} eksempler i datasettet")
        
        # Bruk manuell evaluering i stedet for run_on_dataset
        print("Bruker manuell evaluering for å unngå tidsstempelproblemer...")
        results = {}
        for i, example in enumerate(examples):
            print(f"Evaluerer eksempel {i+1}/{len(examples)}")
            try:
                # Kjør agenten manuelt
                inputs = example.inputs
                output = analyze_domain_wrapper(inputs)
                
                # Lagre resultatet
                results[example.id] = {
                    "input": inputs,
                    "output": output,
                    "feedback": []
                }
                
                # Legg til en forsinkelse for å unngå rate limiting
                time.sleep(1)
            except Exception as ex:
                print(f"Feil ved evaluering av eksempel {i+1}: {ex}")
        
        print(f"Manuell evaluering fullført! Resultater: {results}")
        return {"results": results, "project_name": project_name}
    except Exception as e:
        print(f"Feil under evaluering: {e}")
        
        # Prøv å kjøre uten evaluator hvis det var problemet
        if "evaluators" in str(e):
            print("Prøver uten evaluator...")
            results = client.run_on_dataset(
                dataset_name="prospect-agent-test",
                llm_or_chain_factory=analyze_domain_wrapper,
                project_name=project_name,
                verbose=True
            )
            print(f"Kjøring fullført! Resultater: {results}")
            return results
        elif "session end time is before run start time" in str(e):
            print("Tidsstempelfeil oppdaget. Prøver med manuell evaluering...")
            # Kjør manuell evaluering i stedet
            results = {}
            for i, example in enumerate(examples):
                print(f"Evaluerer eksempel {i+1}/{len(examples)}")
                try:
                    # Kjør agenten manuelt
                    inputs = example.inputs
                    output = analyze_domain_wrapper(inputs)
                    
                    # Lagre resultatet
                    results[example.id] = {
                        "input": inputs,
                        "output": output,
                        "feedback": []
                    }
                    
                    # Legg til en forsinkelse for å unngå rate limiting
                    time.sleep(1)
                except Exception as ex:
                    print(f"Feil ved evaluering av eksempel {i+1}: {ex}")
            
            print(f"Manuell evaluering fullført! Resultater: {results}")
            return {"results": results, "project_name": project_name}
        raise e

def run_prompt_comparison():
    """
    Kjører en sammenligning av original prompt med en alternativ versjon.
    """
    # Opprett eller hent datasett
    dataset = create_test_dataset()
    
    # Lag et unikt prosjektnavn med tidsstempel
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_name = f"prospect-agent-prompt-comparison-{timestamp}"
    
    print(f"Starter prompt-sammenligning med prosjekt: {project_name}")
    
    # Sammenlign original med alternativ versjon
    versions = ["original", "alternativ"]
    
    # Sjekk om promptversjonene eksisterer
    from prompt_hub import get_prompt_from_hub
    from system_prompts import get_analysis_prompt, get_priority_prompt
    
    print("Sjekker tilgjengelige promptversjoner...")
    
    # Sjekk om alternativ versjon eksisterer
    analysis_prompt_name = "prospect-agent-analysis-prompt-alternativ"
    priority_prompt_name = "prospect-agent-priority-prompt-alternativ"
    
    # Sjekk eksistens ved å prøve å hente promptene
    print(f"Sjekker om {analysis_prompt_name} eksisterer...")
    analysis_content = get_prompt_from_hub(analysis_prompt_name, None)
    analysis_exists = analysis_content is not None
    
    print(f"Sjekker om {priority_prompt_name} eksisterer...")
    priority_content = get_prompt_from_hub(priority_prompt_name, None)
    priority_exists = priority_content is not None
    
    if not analysis_exists:
        print(f"Advarsel: {analysis_prompt_name} finnes ikke i LangSmith")
    if not priority_exists:
        print(f"Advarsel: {priority_prompt_name} finnes ikke i LangSmith")
    
    if not analysis_exists or not priority_exists:
        print("Oppretter alternativ versjon basert på filen 'prompts/analysis_prompt_v1.txt'...")
        
        try:
            # Les alternativ prompt fra fil
            with open("prompts/analysis_prompt_v1.txt", "r") as f:
                alt_analysis_prompt = f.read()
                
            # Bruk original priority prompt for alternativ versjon
            alt_priority_prompt = get_priority_prompt()
            
            # Oppdater eller opprett promptene
            from prompt_hub import update_prompt_in_hub
            
            if not analysis_exists:
                update_prompt_in_hub(analysis_prompt_name, alt_analysis_prompt)
                print(f"Opprettet {analysis_prompt_name} fra fil")
            
            if not priority_exists:
                update_prompt_in_hub(priority_prompt_name, alt_priority_prompt)
                print(f"Opprettet {priority_prompt_name} basert på original")
                
        except FileNotFoundError:
            print("Filen 'prompts/analysis_prompt_v1.txt' ble ikke funnet.")
            print("Oppretter alternativ versjon basert på original med små endringer...")
            
            # Lag en enkel modifisert versjon av originalen
            original_analysis = get_analysis_prompt()
            alt_analysis_prompt = original_analysis + "\n\nVær ekstra grundig i analysen og fokuser på teknisk kompetanse."
            
            # Bruk original priority prompt for alternativ versjon
            alt_priority_prompt = get_priority_prompt()
            
            # Oppdater eller opprett promptene
            from prompt_hub import update_prompt_in_hub
            
            if not analysis_exists:
                update_prompt_in_hub(analysis_prompt_name, alt_analysis_prompt)
                print(f"Opprettet {analysis_prompt_name} med modifisert original")
            
            if not priority_exists:
                update_prompt_in_hub(priority_prompt_name, alt_priority_prompt)
                print(f"Opprettet {priority_prompt_name} basert på original")
    
    results = {}
    version_metrics = {}
    
    # Kjør hver versjon separat
    for version in versions:
        # Bruk "default" for original i agent_wrapper
        agent_version = "default" if version == "original" else "alternativ"
        version_project = f"{project_name}-{version}"
        print(f"Evaluerer versjon: {version} med prosjekt: {version_project}")
        
        # Legg til en forsinkelse for å unngå tidsstempelproblemer
        print(f"Venter 3 sekunder før evaluering av versjon {version}...")
        time.sleep(3)
        
        # Opprett agent med denne promptversjonen
        agent_wrapper = create_agent_with_prompt(agent_version)
        
        # Kjør evalueringen
        try:
            version_results = client.run_on_dataset(
                dataset_name="prospect-agent-test",
                llm_or_chain_factory=agent_wrapper,
                project_name=version_project,
                verbose=True
            )
            
            results[version] = version_results
            
            # Beregn metrikker for denne versjonen
            metrics = calculate_version_metrics(version_results)
            version_metrics[version] = metrics
            
            print(f"Evaluering av versjon {version} fullført!")
            
        except Exception as e:
            print(f"Feil under evaluering av versjon {version}: {e}")
    
    # Sammenlign resultatene
    print("\n=== Promptsammenligning ===")
    print(f"Sammenlignet {len(versions)} promptversjoner: {', '.join(versions)}")
    print("\nMetrikker per versjon:")
    
    for version, metrics in version_metrics.items():
        print(f"\n{version.upper()}:")
        for metric_name, metric_value in metrics.items():
            print(f"  {metric_name}: {metric_value}")
    
    # Finn beste versjon basert på gjennomsnittlig responstid
    if version_metrics:
        best_version = min(version_metrics.items(), key=lambda x: x[1].get('avg_execution_time', float('inf')))[0]
        print(f"\nBeste versjon basert på responstid: {best_version.upper()}")
        
        # Finn beste versjon basert på andre metrikker hvis de finnes
        if any('quality_score' in metrics for metrics in version_metrics.values()):
            best_quality = max(version_metrics.items(), key=lambda x: x[1].get('avg_quality_score', 0))[0]
            print(f"Beste versjon basert på kvalitet: {best_quality.upper()}")
    
    print("\nSe detaljerte resultater i LangSmith UI:")
    print(f"https://eu.smith.langchain.com/o/{os.getenv('LANGCHAIN_PROJECT')}/projects")
    
    return {
        "results": results,
        "metrics": version_metrics,
        "project_name": project_name
    }

# Hjelpefunksjon for å beregne metrikker for en versjon
def calculate_version_metrics(version_results):
    """Beregner metrikker for en promptversjon basert på evalueringsresultatene."""
    if not version_results or 'results' not in version_results:
        return {}
    
    results = version_results['results']
    
    # Beregn gjennomsnittlig kjøretid
    execution_times = [r.get('execution_time', 0) for r in results.values()]
    avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
    
    # Beregn gjennomsnittlig kvalitetsscore hvis tilgjengelig
    quality_scores = []
    for result in results.values():
        feedback = result.get('feedback', [])
        for f in feedback:
            if isinstance(f, dict) and 'quality_score' in f:
                quality_scores.append(f['quality_score'])
    
    metrics = {
        'avg_execution_time': round(avg_execution_time, 3),
        'num_examples': len(results)
    }
    
    if quality_scores:
        metrics['avg_quality_score'] = round(sum(quality_scores) / len(quality_scores), 3)
    
    return metrics

# Legg til en compare-funksjon for å sammenligne promptversjoner
def compare_prompts():
    """Sammenligner ulike versjoner av prompter."""
    from prompt_hub import get_prompt_from_hub
    from system_prompts import get_analysis_prompt, get_priority_prompt
    
    # Hent ulike versjoner av promptene
    analysis_prompt_v1 = get_prompt_from_hub("prospect-agent-analysis-prompt-v1", get_analysis_prompt())
    analysis_prompt_v2 = get_prompt_from_hub("prospect-agent-analysis-prompt-v2", get_analysis_prompt())
    priority_prompt_v1 = get_prompt_from_hub("prospect-agent-priority-prompt-v1", get_priority_prompt())
    priority_prompt_v2 = get_prompt_from_hub("prospect-agent-priority-prompt-v2", get_priority_prompt())
    
    # Kjør evalueringer med ulike promptkombinasjoner
    # ...
    
    # Lagre resultatene i LangSmith
    # ...

# Definer funksjonen for å opprette en agent med en spesifikk promptversjon
def create_agent_with_prompt(prompt_version):
    def agent_wrapper(inputs):
        # Lagre originale prompter
        from agent import analysis_prompt, priority_prompt
        from prompt_hub import get_prompt_from_hub
        from system_prompts import get_analysis_prompt, get_priority_prompt
        
        original_analysis = analysis_prompt
        original_priority = priority_prompt
        
        try:
            # Hent spesifikke promptversjoner
            if prompt_version != "default":
                # Hent prompter fra hub
                analysis_prompt_name = f"prospect-agent-analysis-prompt-{prompt_version}"
                priority_prompt_name = f"prospect-agent-priority-prompt-{prompt_version}"
                
                print(f"Henter prompter for versjon {prompt_version}...")
                analysis_prompt_content = get_prompt_from_hub(
                    analysis_prompt_name, 
                    fallback_content=get_analysis_prompt()
                )
                priority_prompt_content = get_prompt_from_hub(
                    priority_prompt_name, 
                    fallback_content=get_priority_prompt()
                )
                
                # Oppdater globale prompter midlertidig
                import agent
                agent.analysis_prompt = analysis_prompt_content
                agent.priority_prompt = priority_prompt_content
                
                # Oppdater chains
                from langchain_core.prompts import ChatPromptTemplate
                agent.analysis_chain = (
                    ChatPromptTemplate.from_messages([
                        ("system", analysis_prompt_content),
                        ("human", agent.ANALYSIS_PROMPT)
                    ])
                    | agent.llm.with_structured_output(agent.User, method="json_mode")
                )
                
                agent.priority_chain = (
                    ChatPromptTemplate.from_messages([
                        ("system", priority_prompt_content),
                        ("human", agent.PRIORITY_PROMPT)
                    ])
                    | agent.llm.with_structured_output(agent.PriorityAnalysis, method="json_mode")
                )
            
            # Kjør agenten
            from agent import analyze_domain
            return analyze_domain(
                domain=inputs.get("domain"),
                target_role=inputs.get("target_role"),
                max_results=inputs.get("max_results", 5)
            )
        finally:
            # Gjenopprett originale prompter
            if prompt_version != "default":
                import agent
                agent.analysis_prompt = original_analysis
                agent.priority_prompt = original_priority
                
                # Gjenopprett chains
                from langchain_core.prompts import ChatPromptTemplate
                agent.analysis_chain = (
                    ChatPromptTemplate.from_messages([
                        ("system", original_analysis),
                        ("human", agent.ANALYSIS_PROMPT)
                    ])
                    | agent.llm.with_structured_output(agent.User, method="json_mode")
                )
                
                agent.priority_chain = (
                    ChatPromptTemplate.from_messages([
                        ("system", original_priority),
                        ("human", agent.PRIORITY_PROMPT)
                    ])
                    | agent.llm.with_structured_output(agent.PriorityAnalysis, method="json_mode")
                )
    
    return agent_wrapper

# Oppdater kommandolinje-grensesnittet
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        run_prompt_comparison()
    else:
        run_evaluation() 