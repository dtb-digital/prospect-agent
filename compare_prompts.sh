#!/bin/bash

# Lag promptmappen hvis den ikke finnes
mkdir -p prompts

# Synkroniser system-prompter til LangSmith
echo "Synkroniserer system-prompter til LangSmith..."
python prompt_hub.py sync-to-langsmith

# Kjør sammenligningen
echo "Kjører sammenligning av promptversjoner..."
python evaluate.py compare

echo "Ferdig! Sjekk LangSmith UI for resultater." 