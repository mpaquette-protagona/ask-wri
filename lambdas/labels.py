"""The only tags, regions, topics and languages Claude is allowed to assign to a document.
The sections Lambda and the agent use these lists. KEEP lambdas/labels.py AND agent/labels.py IDENTICAL.
"""

TAGS = [
    "adaptation", "adaptation finance", "agriculture", "aquaculture",
    "artificial intelligence (AI)", "biking", "biodiversity", "biofuels", "Business",
    "carbon capture and storage (CCS)", "carbon pricing", "carbon removal", "circular economy",
    "Cities", "Climate", "climate change", "climate finance", "climate impacts",
    "climate investment funds", "climate policy", "climate science", "commodities", "congestion",
    "conservation", "COP16", "COP17", "COP18", "COP20", "COP21", "COP22", "COP23", "COP24",
    "COP25", "COP26", "COP27", "COP28", "COP29", "COP30", "COP31", "coral reefs", "coronavirus",
    "corporate sustainability", "data", "data centers", "data visualization", "deforestation",
    "development", "drought", "Economics", "electric grid", "electric mobility", "Energy",
    "energy efficiency", "environmental democracy", "environmental justice",
    "Equity & Governance", "extractive industries", "extreme heat", "extreme weather", "Finance",
    "fires", "fisheries", "floods", "Food", "food security", "forest monitoring",
    "forest products", "Forests", "fossil fuels", "freedom of information", "Freshwater", "G20",
    "GHG emissions", "GHG Protocol", "green bonds", "Green Climate Fund",
    "greenhouse gas accounting", "greenhouse gases", "Green Jobs & Skills", "health", "housing",
    "human rights", "hurricanes", "hypoxia", "Igniting Innovation", "illegal logging",
    "industry", "infrastructure", "international climate policy", "Iran War", "land rights",
    "landscapes", "land use", "Latin America", "long-term strategies",
    "low carbon development", "mapping", "multilateral development banks",
    "natural infrastructure", "natural resources", "nature-based solutions", "NDC", "NDC-TIA",
    "net-zero emissions", "Ocean", "offsets", "Paris Agreement", "paris rulebook",
    "Paying for Paris", "podcasts", "pollution", "poverty", "power plants", "protected areas",
    "public participation", "public transit", "regulation", "renewable energy", "restoration",
    "rivers", "road safety", "sanitation", "school bus", "science based targets",
    "sea level rise", "Solutions in Focus", "stories to watch", "sustainable development goals",
    "Top Outcome: 2023", "Top Outcome: 2024", "Top Outcome: 2025",
    "Towards a More Equal City", "transportation", "U.S. Climate Policy-Schools",
    "U.S. Climate Policy-Tax Incentives", "U.S. policy", "UNFCCC", "United Nations",
    "Unlocking Climate Action", "Urban Transformations", "Voices in Supply Chains", "waste",
    "wastewater", "water pollution", "water quality", "water risk", "wetlands",
    "WRI Ross Center Prize for Cities",
]

REGIONS = ["Africa", "Asia", "Europe", "Latin America", "North America", "Oceania"]

TOPICS = ["Business", "Cities", "Climate", "Economics", "Energy", "Equity & Governance",
          "Finance", "Food", "Forests", "Freshwater", "Ocean"]

# The language a document is written in (its main language). The code is stored; the name is shown.
LANGUAGES = {"en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese",
             "zh": "Chinese", "hi": "Hindi", "other": "Other"}
