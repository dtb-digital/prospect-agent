# Prospect Agent

En agent for å analysere og prioritere potensielle kandidater basert på LinkedIn-profiler.

## Installasjon

1. Klon repositoriet:
   ```
   git clone https://github.com/din-organisasjon/prospect-agent.git
   cd prospect-agent
   ```

2. Installer avhengigheter:
   ```
   pip install -r requirements.txt
   ```

3. Opprett en `.env`-fil med nødvendige API-nøkler:
   ```
   OPENAI_API_KEY=din_openai_api_nøkkel
   LANGCHAIN_API_KEY=din_langchain_api_nøkkel
   LANGCHAIN_PROJECT=prospect-agent
   LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
   LINKEDIN_API_KEY=din_linkedin_api_nøkkel
   HUNTER_API_KEY=din_hunter_api_nøkkel
   ```

## Bruk

### Kjøre agenten 

```
python agent.py
```

### API-grensesnitt

Start API-serveren:
```
python api.py
```

Eksempel på API-kall:
```
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com", "target_role": "CTO", "max_results": 5}'
```

## Prompt-håndtering

Dette prosjektet bruker LangSmith Prompt Hub for å håndtere prompter.

### Kommandoer for prompt-håndtering

- **List alle prompter**:
  ```
  python prompt_hub.py list
  ```

- **Hent en prompt**:
  ```
  python prompt_hub.py get <prompt_name>
  ```

- **Oppdater en prompt fra fil**:
  ```
  python prompt_hub.py update <prompt_name> <fil>
  ```

- **Opprett en ny prompt fra fil**:
  ```
  python prompt_hub.py create <prompt_name> <fil>
  ```

- **Synkroniser system-prompter til LangSmith**:
  ```
  python prompt_hub.py sync-to-langsmith
  ```

- **Synkroniser prompter fra LangSmith til lokale filer**:
  ```
  python prompt_hub.py sync-from-langsmith
  ```

### Prompt-versjoner

Prosjektet støtter flere versjoner av prompter for A/B-testing:

- **Hovedversjoner**:
  - `prospect-agent-analysis-prompt` - Hovedversjon av analyseprompten
  - `prospect-agent-priority-prompt` - Hovedversjon av prioriteringsprompten

- **Testversjoner**:
  - `prospect-agent-analysis-prompt-v1` - Versjon 1 (teknisk fokus)
  - `prospect-agent-priority-prompt-v1` - Versjon 1 (teknisk fokus)
  - `prospect-agent-analysis-prompt-v2` - Versjon 2 (ledelsesfokus)
  - `prospect-agent-priority-prompt-v2` - Versjon 2 (ledelsesfokus)

## Evaluering

### Kjøre evaluering

```
python evaluate.py
```

### Sammenligne promptversjoner

```
python evaluate.py compare
```

### Automatisert sammenligning

```
./compare_prompts.sh
```

## Docker

Bygg Docker-image:
```
docker build -t prospect-agent .
```

Kjør Docker-container:
```
docker run -p 8000:8000 --env-file .env prospect-agent
```

## Beste praksis

1. **Prompt-håndtering**:
   - Rediger prompter i LangSmith UI for enkel redigering og versjonskontroll
   - Synkroniser prompter til lokale filer for backup
   - Bruk `evaluate.py compare` for å sammenligne ulike promptversjoner

2. **Evaluering**:
   - Kjør regelmessige evalueringer for å måle ytelsen
   - Bruk LangSmith UI for å analysere resultatene
   - Forbedre promptene basert på evalueringsresultatene

3. **Utvikling**:
   - Følg GitFlow for branching-strategi
   - Skriv tester for ny funksjonalitet
   - Dokumenter endringer i koden

## Feilsøking

- **API-feil**: Sjekk at API-nøklene er riktige i `.env`-filen
- **LangSmith-feil**: Sjekk at LangSmith API-et er tilgjengelig
- **Prompt-feil**: Synkroniser prompter fra LangSmith til lokale filer

## Lisens

Dette prosjektet er lisensiert under MIT-lisensen.
