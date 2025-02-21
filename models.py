from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, validator
from langchain_core.messages import BaseMessage
from datetime import datetime

#######################
# API og Input/Output modeller
#######################

class LinkedInInput(BaseModel):
    """Input for LinkedIn API"""
    linkedin_url: str = Field(..., description="LinkedIn profil URL")

class HunterInput(BaseModel):
    """Input for Hunter API"""
    domain: str = Field(..., description="Domenet å søke i")
    api_key: str = Field(..., description="Hunter.io API nøkkel")
    offset: int = Field(default=0, description="Offset for paginering")
    limit: int = Field(default=50, description="Antall resultater per side")

class HunterResponse(BaseModel):
    """Strukturert respons fra Hunter API"""
    emails: List[dict] = Field(..., description="Liste over e-poster")
    meta: dict = Field(..., description="Metadata inkludert antall sider")

#######################
# Interne modeller (for analyse)
#######################

class LinkedInRawData(BaseModel):
    """Rå data fra LinkedIn API - brukes kun for analyse"""
    about: Optional[str] = None
    city: Optional[str] = None
    connections: Optional[int] = None
    country: Optional[str] = None
    current_company: Optional[str] = None
    current_job_title: Optional[str] = None
    education: Optional[List[Dict]] = None
    experiences: Optional[List[Dict]] = None
    full_name: Optional[str] = None
    headline: Optional[str] = None
    profile_pic_url: Optional[str] = None
    languages: Optional[List[Dict]] = None

class SearchConfig(TypedDict):
    """Konfigurasjon for søk"""
    domain: str
    target_role: str
    max_results: int

class AgentState(TypedDict):
    """State for agent workflow"""
    messages: List[BaseMessage]
    config: SearchConfig
    users: List[Dict[str, Any]]

#######################
# Basis datamodeller
#######################

class BasicInfo(BaseModel):
    """Grunnleggende kontaktinformasjon og identifikasjon"""
    class Location(BaseModel):
        """Personens fysiske lokasjon"""
        city: Optional[str] = Field(None, description="By personen er lokalisert i")
        country: Optional[str] = Field(None, description="Land personen er lokalisert i")
        region: Optional[str] = Field(None, description="Region eller fylke")

    email: str = Field(..., description="Primær e-postadresse")
    first_name: Optional[str] = Field(None, description="Fornavn")
    last_name: Optional[str] = Field(None, description="Etternavn")
    full_name: Optional[str] = Field(None, description="Fullt navn fra profilen")
    headline: Optional[str] = Field(None, description="Profesjonell overskrift/tittel")
    phone_number: Optional[str] = Field(None, description="Telefonnummer")
    linkedin_url: Optional[str] = Field(None, description="Full URL til LinkedIn-profil")
    location: Location = Field(default_factory=Location)
    profile_image_url: Optional[str] = Field(None, description="URL til profilbilde")
    about: Optional[str] = Field(None, description="Om-meg tekst fra profilen")

#######################
# Analyse modeller - Karriere
#######################

class CareerProgression(BaseModel):
    """
    Analyse av karriereutvikling og profesjonell progresjon over tid.
    Fokuserer på å identifisere mønstre og strategiske karrierevalg.
    """
    pattern: str = Field(
        ...,
        description="Overordnet mønster i karriereutviklingen, f.eks. 'Systematisk "
        "progresjon fra tekniske roller til produktledelse' eller 'Konsekvent fokus "
        "på salg med økende strategisk ansvar'"
    )
    key_transitions: List[str] = Field(
        ...,
        description="Viktige karriereoverganger med begrunnelse og resultat, f.eks. "
        "'Fra utvikler til teamlead i 2019 - ledet til 40% økt produktivitet'"
    )
    previous_companies: List[str] = Field(
        ...,
        description="Kronologisk liste over tidligere arbeidsgivere, inkludert "
        "bransje og størrelse der relevant"
    )
    previous_industries: List[str] = Field(
        ...,
        description="Liste over bransjer personen har erfaring fra, med fokus på "
        "overførbar kompetanse og bransjeinnsikt"
    )
    average_tenure: float = Field(
        ..., 
        ge=0,
        description="Gjennomsnittlig ansettelsestid i år, beregnet fra hele "
        "karrierehistorikken. Indikerer stabilitet og lojalitet"
    )
    management_experience_years: Optional[int] = Field(
        None, 
        ge=0,
        description="Antall år med formelt lederansvar, spesifiser type "
        "lederrolle og omfang av ansvar"
    )

class CareerInfo(BaseModel):
    """Detaljert analyse av karriere og posisjon"""
    current_role: str = Field(
        ...,
        description="Nåværende stillingstittel med presisering av nivå og "
        "ansvarsområde, f.eks. 'Senior Product Manager med ansvar for B2B-porteføljen'"
    )
    current_company: str = Field(
        ...,
        description="Nåværende arbeidsgiver med relevant kontekst om "
        "selskapets størrelse, bransje og posisjon i markedet"
    )
    company_industry: str = Field(
        ...,
        description="Detaljert beskrivelse av bransjen selskapet opererer i, "
        "inkludert relevante markedssegmenter og teknologiområder"
    )
    years_in_role: int = Field(
        ..., 
        ge=0,
        description="Antall år i nåværende stilling, indikerer dybdekunnskap "
        "og stabilitet i rollen"
    )
    years_in_company: int = Field(
        ..., 
        ge=0,
        description="Antall år i nåværende selskap, viser lojalitet og "
        "evne til langsiktig verdiskaping"
    )
    total_experience_years: int = Field(
        ..., 
        ge=0,
        description="Total relevant arbeidserfaring i år, inkluderer bare "
        "profesjonell erfaring etter fullført utdanning"
    )
    seniority_level: str = Field(
        ...,
        description="Vurdering av erfaringsnivå basert på roller, ansvar og "
        "innflytelse. Vurder både formell posisjon og reell påvirkningskraft"
    )
    career_progression: CareerProgression
    responsibilities: List[str] = Field(
        ...,
        description="Liste over konkrete hovedansvarsområder i nåværende rolle, "
        "med fokus på målbare resultater og strategisk betydning"
    )

    @validator('seniority_level')
    def validate_seniority(cls, v):
        valid_levels = ['Junior', 'Mid-level', 'Senior', 'Lead', 'Executive']
        if v not in valid_levels:
            raise ValueError(f'Ugyldig erfaringsnivå. Må være en av: {valid_levels}')
        return v

#######################
# Analyse modeller - Kompetanse
#######################

class ExpertiseInfo(BaseModel):
    """
    Omfattende analyse av personens faglige kompetanse og spesialisering.
    Fokuserer på å identifisere både dybde- og breddekompetanse, samt praktisk erfaring.
    """
    class Language(BaseModel):
        """Språkferdighet med nivå"""
        name: str = Field(..., description="Språkets navn")
        proficiency: str = Field(..., description="Ferdighetsnivå")

        @validator('proficiency')
        def validate_proficiency(cls, v):
            valid_levels = ['Morsmål', 'Flytende', 'Profesjonelt', 'Begrenset']
            if v not in valid_levels:
                raise ValueError(f'Ugyldig språknivå. Må være en av: {valid_levels}')
            return v

    primary_skills: List[str] = Field(
        ...,
        description="Kjernekompetanser med dokumentert erfaring og mestring. "
        "Ranger etter ekspertisenivå og relevans for målrollen"
    )
    industry_knowledge: List[str] = Field(
        ...,
        description="Spesifikk bransjekunnskap og domenekompetanse, inkludert "
        "kjennskap til regelverk, standarder og beste praksis"
    )
    tools_and_technologies: List[str] = Field(
        ...,
        description="Konkrete verktøy, systemer og teknologier personen "
        "behersker. Spesifiser erfaringsnivå og bruksområder"
    )
    languages: List[Language] = Field(
        ...,
        description="Språkferdigheter med nivåangivelse og kontekst for bruk. "
        "Vurder både skriftlig og muntlig kommunikasjonsevne"
    )
    certifications: List[str] = Field(
        ...,
        description="Formelle sertifiseringer og akkrediteringer med årstall "
        "og utstedende organisasjon. Vurder relevans og aktualitet"
    )
    key_achievements: List[str] = Field(
        ...,
        description="Dokumenterte prestasjoner og resultater som demonstrerer "
        "ekspertise. Fokuser på målbare effekter og innovasjon"
    )
    specializations: List[str] = Field(
        ...,
        description="Spesialområder hvor personen har dyp kompetanse og "
        "anerkjennelse. Dokumenter med konkrete prosjekter eller bidrag"
    )

#######################
# Analyse modeller - Utdanning
#######################

class EducationInfo(BaseModel):
    """Oversikt over utdanning og akademiske prestasjoner"""
    class Institution(BaseModel):
        """Utdanningsinstitusjon med grad"""
        name: str = Field(..., description="Navn på institusjon")
        degree: str = Field(..., description="Gradsbetegnelse")
        field: str = Field(..., description="Fagområde/studieretning")
        year: int = Field(..., description="Avslutningsår")

        @validator('year')
        def validate_year(cls, v):
            if v < 1950 or v > datetime.now().year:
                raise ValueError(f'Ugyldig år: {v}')
            return v

    highest_degree: str = Field(...)
    field_of_study: str = Field(...)
    institutions: List[Institution] = Field(...)
    continuing_education: List[str] = Field(...)
    graduation_year: Optional[int] = Field(None)
    academic_achievements: List[str] = Field(...)

#######################
# Analyse modeller - Nettverk
#######################

class NetworkInfo(BaseModel):
    """
    Analyse av personens profesjonelle nettverk og innflytelse.
    Vurderer både kvantitative og kvalitative aspekter ved nettverket.
    """
    connection_count: int = Field(
        ..., 
        ge=0,
        description="Totalt antall LinkedIn-forbindelser. Vurder opp mot "
        "bransjestandarder og personens karrierelengde"
    )
    follower_count: int = Field(
        ..., 
        ge=0,
        description="Antall følgere på LinkedIn, indikerer rekkevidde og "
        "innflytelse i profesjonelle nettverk"
    )
    engagement_level: str = Field(
        ...,
        description="Kvalitativ vurdering av aktivitetsnivå og engasjement i "
        "nettverket. Vurder hyppighet og kvalitet på interaksjoner"
    )
    geographical_reach: List[str] = Field(
        ...,
        description="Geografiske områder hvor personen har sterkt nettverk. "
        "Spesifiser regioner og markeder med aktive forbindelser"
    )
    industry_presence: str = Field(
        ...,
        description="Beskrivelse av personens posisjon og synlighet i relevant "
        "bransje. Vurder deltakelse i fagnettverk og arrangementer"
    )
    influence_score: float = Field(
        ..., 
        ge=0, 
        le=1,
        description="Kvantitativ score for innflytelse basert på nettverksstørrelse, "
        "engasjement og bransjeposisjon. Begrunn scoren med konkrete eksempler"
    )
    networking_style: str = Field(
        ...,
        description="Analyse av hvordan personen bygger og vedlikeholder "
        "profesjonelle relasjoner. Beskriv typiske mønstre i nettverksbygging"
    )

    @validator('engagement_level')
    def validate_engagement(cls, v):
        valid_levels = ['Høy', 'Moderat', 'Lav', 'Inaktiv']
        if v not in valid_levels:
            raise ValueError(f'Ugyldig engasjementsnivå. Må være en av: {valid_levels}')
        return v

#######################
# Analyse modeller - Personlighet
#######################

class CommunicationStyle(BaseModel):
    """
    Analyse av personens kommunikasjonsmønstre og uttrykksmåte i profesjonell kontekst.
    Basert på skriftlig kommunikasjon i profil, innlegg og prosjektbeskrivelser.
    """
    primary_style: str = Field(
        ...,
        description="Dominerende kommunikasjonsstil, f.eks. 'Teknisk presis med "
        "fokus på målbare resultater' eller 'Narrativ med vekt på brukeropplevelser'"
    )
    writing_tone: str = Field(
        ...,
        description="Analyse av språklig tone, formalitetsnivå og bruk av fagterminologi. "
        "Vurder konsistens på tvers av ulike kontekster"
    )
    key_phrases: List[str] = Field(
        ...,
        description="Karakteristiske formuleringer og vendinger som går igjen i "
        "personens profesjonelle kommunikasjon. Direkte sitater fra profilen"
    )
    storytelling_ability: str = Field(
        ...,
        description="Vurdering av evnen til å strukturere og formidle profesjonelle "
        "narrativer. Fokuser på hvordan personen presenterer prosjekter og resultater"
    )
    persuasion_approach: str = Field(
        ...,
        description="Analyse av argumentasjonsteknikker og overbevisningsstrategier. "
        "Hvordan bygger personen troverdighet og presenterer løsninger?"
    )

class WorkStyle(BaseModel):
    """
    Analyse av personens tilnærming til arbeid og problemløsning.
    Utledet fra konkrete eksempler i prosjektbeskrivelser og oppnådde resultater.
    """
    problem_solving: str = Field(
        ...,
        description="Karakteristisk tilnærming til utfordringer, f.eks. 'Systematisk "
        "med vekt på datainnsamling og hypotesetesting' eller 'Innovativ med fokus "
        "på brukerinvolvering'"
    )
    decision_making: str = Field(
        ...,
        description="Analyse av personens tilnærming til å ta beslutninger og vurdere "
        "alternativer. Vurder konsistens på tvers av ulike situasjoner"
    )
    collaboration_preference: str = Field(
        ...,
        description="Analyse av personens preferanse for samarbeid og "
        "kollektivt arbeid. Vurder konsistens på tvers av ulike prosjekter og team"
    )
    innovation_tendency: str = Field(
        ...,
        description="Analyse av personens evne til å utvikle nye ideer og "
        "løsninger. Vurder konsistens på tvers av ulike prosjekter og situasjoner"
    )
    stress_handling: str = Field(
        ...,
        description="Analyse av personens evne til å håndtere stress og "
        "presjon. Vurder konsistens på tvers av ulike situasjoner"
    )
    leadership_style: str = Field(
        ...,
        description="Analyse av personens evne til å lede og inspirere team og "
        "andre. Vurder konsistens på tvers av ulike situasjoner"
    )

class PersonalityTraits(BaseModel):
    """
    Analyse av personens dominerende personlighetstrekk i profesjonell kontekst.
    Basert på konsistente mønstre i kommunikasjon, beslutninger og handlinger.
    """
    dominant_traits: List[str] = Field(
        ...,
        description="Hovedtrekk ved personligheten, dokumentert med konkrete eksempler. "
        "F.eks. ['Strategisk beslutningstaker - demonstrert gjennom systematisk "
        "oppbygging av nye forretningsområder', 'Innovativ problemløser - vist ved...']"
    )
    work_preferences: List[str] = Field(
        ...,
        description="Tydelige preferanser for arbeidsmåter og -miljø, utledet fra "
        "karrierevalg og prosjektbeskrivelser. Fokuser på konsistente mønstre"
    )
    adaptability: str = Field(
        ...,
        description="Konkret vurdering av tilpasningsevne, dokumentert gjennom "
        "håndtering av endringer og nye utfordringer. Gi spesifikke eksempler"
    )
    growth_mindset: str = Field(
        ...,
        description="Analyse av læringsvilje og -evne, basert på karriereutvikling "
        "og kompetansebygging. Hvordan søker personen aktivt nye utfordringer?"
    )
    professional_values: List[str] = Field(
        ...,
        description="Verdier som konsistent kommer til uttrykk gjennom karrierevalg "
        "og profesjonelle prioriteringer. Dokumenter med konkrete eksempler"
    )

class Motivations(BaseModel):
    """
    Dyptgående analyse av drivkrefter og motivasjonsfaktorer.
    Fokuserer på mønstre i karrierevalg og profesjonell utvikling.
    """
    career_drivers: List[str] = Field(
        ...,
        description="Identifiserte hovedmotivasjoner bak karrierevalg, med konkrete "
        "eksempler fra karrierehistorikken. Hva driver personens beslutninger?"
    )
    value_priorities: List[str] = Field(
        ...,
        description="Rangerte profesjonelle verdier basert på konsistente valg og "
        "prioriteringer. Hvilke verdier styrer karrierevalg og prosjektfokus?"
    )
    achievement_patterns: str = Field(
        ...,
        description="Analyse av hva personen definerer som suksess, basert på "
        "fremhevede resultater og prestasjoner. Hvilke typer mål prioriteres?"
    )
    growth_aspirations: str = Field(
        ...,
        description="Tydelige mønstre i karriereutvikling som indikerer fremtidige "
        "ambisjoner og utviklingsretning. Hvor ser personen seg selv på vei?"
    )
    recognition_preferences: str = Field(
        ...,
        description="Hvordan personen foretrekker å bli anerkjent, utledet fra "
        "karrierevalg og prestasjonsbeskrivelser. Hvilken type anerkjennelse søkes?"
    )

class SocialDynamics(BaseModel):
    """
    Analyse av sosiale og profesjonelle samhandlingsmønstre.
    Basert på beskrivelser av samarbeid, ledelse og relasjonsbygging.
    """
    team_role: str = Field(
        ...,
        description="Naturlig rolle i team, dokumentert gjennom konkrete prosjekt- og "
        "samarbeidserfaringer. F.eks. 'Strategisk brobygger mellom tekniske og "
        "kommersielle team' eller 'Faglig mentor med fokus på kunnskapsdeling'"
    )
    influence_style: str = Field(
        ...,
        description="Karakteristisk måte å påvirke og lede på, demonstrert gjennom "
        "beskrevne resultater og prestasjoner. Hvordan oppnår personen gjennomslag?"
    )
    conflict_handling: str = Field(
        ...,
        description="Tilnærming til utfordrende situasjoner og uenighet, basert på "
        "beskrevne erfaringer. Gi eksempler på konflikthåndtering og resultater"
    )
    relationship_building: str = Field(
        ...,
        description="Metode for å bygge og vedlikeholde profesjonelle relasjoner, "
        "utledet fra nettverksbygging og samarbeidshistorikk"
    )
    cultural_fit: str = Field(
        ...,
        description="Vurdering av kulturell tilpasning og verdisamsvar, basert på "
        "tidligere erfaringer og uttrykte preferanser. Hvilke miljøer trives personen i?"
    )

class PersonalityInfo(BaseModel):
    """
    Helhetlig analyse av personens profesjonelle personlighet.
    Kombinerer alle aspekter av personlighetsanalysen for å gi et komplett bilde.
    
    Analysen skal:
    1. Baseres på konkrete eksempler og observerbare mønstre
    2. Fokusere på profesjonell kontekst og arbeidsrelevant atferd
    3. Vise konsistens på tvers av ulike situasjoner og over tid
    4. Dokumentere kilder og grunnlag for vurderinger
    """
    communication: CommunicationStyle
    work_style: WorkStyle
    personality_traits: PersonalityTraits
    motivations: Motivations
    social_dynamics: SocialDynamics

#######################
# Analyse modeller - Meta
#######################

class MetaInfo(BaseModel):
    """
    Metadata og kvalitetsinformasjon om analysen.
    Brukes for å vurdere pålitelighet og relevans av analyserte data.
    """
    sources: List[str] = Field(
        ...,
        description="Liste over alle datakilder brukt i analysen, f.eks. "
        "['LinkedIn profil', 'Prosjektbeskrivelser', 'Artikler og innlegg']"
    )
    confidence_score: Optional[str] = Field(
        None,
        description="Samlet vurdering av datakvalitet og analysesikkerhet. "
        "Vurder mengde, konsistens og kvalitet på tilgjengelig data"
    )
    priority_score: Optional[float] = Field(
        None, 
        description="Prioriteringsscore (0-1) basert på match mot målrollen "
        "og potensial for videre utvikling",
        ge=0,
        le=1
    )
    priority_reason: Optional[str] = Field(
        None,
        description="Detaljert begrunnelse for prioriteringsscore, med konkrete "
        "eksempler på hvorfor personen er relevant for målrollen"
    )
    role_relevance: Optional[float] = Field(
        None,
        description="Kvantitativ vurdering (0-1) av match mot spesifikke krav "
        "og ønsker for målrollen",
        ge=0,
        le=1
    )
    last_updated: datetime = Field(
        ...,
        description="Tidspunkt for siste oppdatering av analysen"
    )
    data_completeness: float = Field(
        ...,
        description="Prosentvis kompletthet av tilgjengelig data (0-1). "
        "Vurder hvilke aspekter av analysen som mangler eller er ufullstendige",
        ge=0,
        le=1
    )

    @validator('confidence_score')
    def validate_confidence(cls, v):
        if v is not None:
            valid_scores = ['Høy', 'Medium', 'Lav']
            if v not in valid_scores:
                raise ValueError(f'Ugyldig confidence score. Må være en av: {valid_scores}')
        return v

class PriorityUser(BaseModel):
    """Prioritert bruker med score og begrunnelse"""
    email: str = Field(..., description="Brukerens email")
    score: float = Field(..., description="Prioriteringsscore (0-1)", ge=0, le=1)
    reason: str = Field(..., description="Begrunnelse for score")

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Ugyldig email format')
        return v.lower()  # Standardiser til lowercase

class PriorityAnalysis(BaseModel):
    """Resultat av prioriteringsanalyse"""
    users: List[PriorityUser] = Field(..., description="Liste over prioriterte brukere")
    
    @validator('users')
    def validate_users(cls, v):
        if not v:
            raise ValueError('Prioriteringsanalyse må inneholde minst én bruker')
        return v

#######################
# User modellen
#######################

class User(BaseModel):
    """
    Representerer en bruker med all analysert informasjon.
    Bygges opp gradvis gjennom analyseprosessen.
    """
    # Basis info (fra Hunter)
    email: str
    linkedin_url: Optional[str] = None
    
    # Analyse-resultater (nå direkte i User-modellen)
    basic_info: Optional[BasicInfo] = None
    career: Optional[CareerInfo] = None
    expertise: Optional[ExpertiseInfo] = None
    education: Optional[EducationInfo] = None
    network: Optional[NetworkInfo] = None
    personality: Optional[PersonalityInfo] = None
    meta: Optional[MetaInfo] = None
    
    # Tracking
    sources: List[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.now)

