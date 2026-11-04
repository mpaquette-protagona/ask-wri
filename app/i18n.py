"""Interface text in five languages. The page asks for text by key, and for filter values by kind.
Filter values are shown translated but always sent to the agent in English (their stored form).
Document titles, section names and passages are document content and are never translated here.
"""

UI_LANGUAGES = {"en": "English", "es": "Español", "fr": "Français", "pt": "Português", "zh": "中文", "hi": "हिन्दी"}
# The language name the agent is told to write the answer in
ANSWER_LANGUAGE = {"en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese", "zh": "Simplified Chinese", "hi": "Hindi"}

TEXT = {
    "en": {
        "nav_ask": "Ask a question", "nav_briefing": "Research briefing", "nav_gaps": "Find gaps",
        "mode_briefing": "Research briefing", "mode_gaps": "Find gaps",
        "hint_ask": "Ask about WRI research", "hint_briefing": "Name a topic, e.g. electric school buses",
        "hint_gaps": "Name a topic, e.g. energy efficiency",
        "example_ask": "What does WRI say about food loss and waste in Kenya?",
        "example_briefing": "Electric school buses", "example_gaps": "Energy efficiency", "recent": "Recent", "language_label": "Language",
        "hero_title": "Ask WRI's research a question",
        "hero_sub": "Every answer cites the document, the pages and the passage it comes from. "
                    "Searching {count} publications from {first} to {last}.",
        "searching": "Searching and reading WRI documents. This can take up to a minute.",
        "error_title": "Something went wrong",
        "error_body": "The agent did not answer ({error}). Please try again.",
        "answered_in": "Answered in {seconds} s", "turn_into_briefing": "Turn into briefing",
        "found_title": "What the search found",
        "badge_none": "No sources cited", "badge_single": "Single source", "badge_many": "{n} documents",
        "tile_retrieved": "Documents retrieved", "tile_cited": "Documents cited",
        "tile_year": "Publication year", "tile_languages": "Document languages",
        "by_type": "Documents by type", "other": "Other",
        "note_single": "Every finding comes from one {kind}, so nothing here is cross-checked against other WRI publications.",
        "note_many": "Findings draw on {n} WRI documents.",
        "note_none": "No retrieved document supports an answer to this question.",
        "view_all": "View all {n} documents", "dialog_title": "All retrieved documents",
        "dialog_caption": "Sorted by relevancy: how similar your question is to the document's best-matching "
                          "passage, as scored by the vector search (100 % would be an identical match).",
        "relevancy": "Relevancy {pct} %", "cited": "Cited", "not_cited": "Not cited",
        "passages_in_doc": "Passages from this document",
        "sources_heading": "Sources, most relevant first",
        "status_verified": "SOURCE {n} · VERIFIED IN DOCUMENT TEXT",
        "status_verified_translated": "SOURCE {n} · VERIFIED IN TRANSLATED TEXT",
        "status_not_found": "SOURCE {n} · QUOTE NOT FOUND IN TEXT", "status_not_cited": "SOURCE {n} · RETRIEVED, NOT CITED",
        "note_translated": "The original document is in {language}. This passage is the English translation made "
                           "when the document was added to the library.",
        "note_unverified": "The quote the answer relies on could not be matched to this passage. "
                           "Treat the claim as unconfirmed and check the document.",
        "open_document": "Open the document",
        "page_one": "page {a}", "page_range": "pages {a}–{b}", "of_total": "{label} of {total}",
    },
    "es": {
        "nav_ask": "Hacer una pregunta", "nav_briefing": "Informe de investigación", "nav_gaps": "Detectar vacíos",
        "mode_briefing": "Informe de investigación", "mode_gaps": "Detectar vacíos",
        "hint_ask": "Pregunta sobre la investigación de WRI",
        "hint_briefing": "Indica un tema, por ejemplo autobuses escolares eléctricos",
        "hint_gaps": "Indica un tema, por ejemplo eficiencia energética",
        "example_ask": "¿Qué dice WRI sobre la pérdida y el desperdicio de alimentos en Kenia?",
        "example_briefing": "Autobuses escolares eléctricos", "example_gaps": "Eficiencia energética", "recent": "Recientes", "language_label": "Idioma",
        "hero_title": "Hazle una pregunta a la investigación de WRI",
        "hero_sub": "Cada respuesta cita el documento, las páginas y el pasaje de donde proviene. "
                    "Se buscan {count} publicaciones de {first} a {last}.",
        "searching": "Buscando y leyendo documentos de WRI. Puede tardar hasta un minuto.",
        "error_title": "Algo salió mal",
        "error_body": "El agente no respondió ({error}). Inténtalo de nuevo.",
        "answered_in": "Respondido en {seconds} s", "turn_into_briefing": "Convertir en informe",
        "found_title": "Lo que encontró la búsqueda",
        "badge_none": "Sin fuentes citadas", "badge_single": "Una sola fuente", "badge_many": "{n} documentos",
        "tile_retrieved": "Documentos recuperados", "tile_cited": "Documentos citados",
        "tile_year": "Año de publicación", "tile_languages": "Idiomas de los documentos",
        "by_type": "Documentos por tipo", "other": "Otro",
        "note_single": "Todos los hallazgos provienen de un solo documento ({kind}), por lo que nada aquí se contrasta con otras publicaciones de WRI.",
        "note_many": "Los hallazgos se basan en {n} documentos de WRI.",
        "note_none": "Ningún documento recuperado respalda una respuesta a esta pregunta.",
        "view_all": "Ver los {n} documentos", "dialog_title": "Todos los documentos recuperados",
        "dialog_caption": "Ordenados por relevancia: cuánto se parece tu pregunta al pasaje del documento que mejor "
                          "coincide, según la búsqueda vectorial (100 % sería una coincidencia idéntica).",
        "relevancy": "Relevancia {pct} %", "cited": "Citado", "not_cited": "No citado",
        "passages_in_doc": "Pasajes de este documento",
        "sources_heading": "Fuentes, de mayor a menor relevancia",
        "status_verified": "FUENTE {n} · VERIFICADA EN EL TEXTO DEL DOCUMENTO",
        "status_verified_translated": "FUENTE {n} · VERIFICADA EN EL TEXTO TRADUCIDO",
        "status_not_found": "FUENTE {n} · CITA NO ENCONTRADA EN EL TEXTO", "status_not_cited": "FUENTE {n} · RECUPERADA, NO CITADA",
        "note_translated": "El documento original está en {language}. Este pasaje es la traducción al inglés "
                           "hecha al añadir el documento a la biblioteca.",
        "note_unverified": "No se pudo asociar la cita en la que se basa la respuesta con este pasaje. "
                           "Considera la afirmación como no confirmada y revisa el documento.",
        "open_document": "Abrir el documento",
        "page_one": "página {a}", "page_range": "páginas {a}–{b}", "of_total": "{label} de {total}",
    },
    "fr": {
        "nav_ask": "Poser une question", "nav_briefing": "Note de recherche", "nav_gaps": "Repérer les lacunes",
        "mode_briefing": "Note de recherche", "mode_gaps": "Repérer les lacunes",
        "hint_ask": "Posez une question sur les recherches du WRI",
        "hint_briefing": "Indiquez un sujet, par exemple les bus scolaires électriques",
        "hint_gaps": "Indiquez un sujet, par exemple l'efficacité énergétique",
        "example_ask": "Que dit le WRI sur les pertes et le gaspillage alimentaires au Kenya ?",
        "example_briefing": "Bus scolaires électriques", "example_gaps": "Efficacité énergétique", "recent": "Récents", "language_label": "Langue",
        "hero_title": "Posez une question aux recherches du WRI",
        "hero_sub": "Chaque réponse cite le document, les pages et le passage d'où elle provient. "
                    "Recherche dans {count} publications de {first} à {last}.",
        "searching": "Recherche et lecture des documents du WRI. Cela peut prendre jusqu'à une minute.",
        "error_title": "Une erreur s'est produite",
        "error_body": "L'agent n'a pas répondu ({error}). Veuillez réessayer.",
        "answered_in": "Réponse en {seconds} s", "turn_into_briefing": "Transformer en note",
        "found_title": "Ce que la recherche a trouvé",
        "badge_none": "Aucune source citée", "badge_single": "Source unique", "badge_many": "{n} documents",
        "tile_retrieved": "Documents trouvés", "tile_cited": "Documents cités",
        "tile_year": "Année de publication", "tile_languages": "Langues des documents",
        "by_type": "Documents par type", "other": "Autre",
        "note_single": "Toutes les conclusions viennent d'un seul document ({kind}) : rien n'est donc recoupé avec d'autres publications du WRI.",
        "note_many": "Les conclusions s'appuient sur {n} documents du WRI.",
        "note_none": "Aucun document trouvé ne permet de répondre à cette question.",
        "view_all": "Voir les {n} documents", "dialog_title": "Tous les documents trouvés",
        "dialog_caption": "Classés par pertinence : à quel point votre question ressemble au passage le plus proche "
                          "du document, selon la recherche vectorielle (100 % correspondrait à une identité parfaite).",
        "relevancy": "Pertinence {pct} %", "cited": "Cité", "not_cited": "Non cité",
        "passages_in_doc": "Passages de ce document",
        "sources_heading": "Sources, de la plus pertinente à la moins pertinente",
        "status_verified": "SOURCE {n} · VÉRIFIÉE DANS LE TEXTE DU DOCUMENT",
        "status_verified_translated": "SOURCE {n} · VÉRIFIÉE DANS LE TEXTE TRADUIT",
        "status_not_found": "SOURCE {n} · CITATION INTROUVABLE DANS LE TEXTE", "status_not_cited": "SOURCE {n} · TROUVÉE, NON CITÉE",
        "note_translated": "Le document original est en {language}. Ce passage est la traduction anglaise faite "
                           "lors de l'ajout du document à la bibliothèque.",
        "note_unverified": "La citation sur laquelle repose la réponse n'a pas pu être rapprochée de ce passage. "
                           "Considérez l'affirmation comme non confirmée et vérifiez le document.",
        "open_document": "Ouvrir le document",
        "page_one": "page {a}", "page_range": "pages {a}–{b}", "of_total": "{label} sur {total}",
    },
    "pt": {
        "nav_ask": "Fazer uma pergunta", "nav_briefing": "Resumo de pesquisa", "nav_gaps": "Encontrar lacunas",
        "mode_briefing": "Resumo de pesquisa", "mode_gaps": "Encontrar lacunas",
        "hint_ask": "Pergunte sobre as pesquisas do WRI",
        "hint_briefing": "Indique um tema, por exemplo ônibus escolares elétricos",
        "hint_gaps": "Indique um tema, por exemplo eficiência energética",
        "example_ask": "O que o WRI diz sobre perda e desperdício de alimentos no Quênia?",
        "example_briefing": "Ônibus escolares elétricos", "example_gaps": "Eficiência energética", "recent": "Recentes", "language_label": "Idioma",
        "hero_title": "Faça uma pergunta às pesquisas do WRI",
        "hero_sub": "Cada resposta cita o documento, as páginas e o trecho de onde vem. "
                    "Pesquisando {count} publicações de {first} a {last}.",
        "searching": "Pesquisando e lendo documentos do WRI. Pode levar até um minuto.",
        "error_title": "Algo deu errado",
        "error_body": "O agente não respondeu ({error}). Tente novamente.",
        "answered_in": "Respondido em {seconds} s", "turn_into_briefing": "Transformar em resumo",
        "found_title": "O que a busca encontrou",
        "badge_none": "Nenhuma fonte citada", "badge_single": "Fonte única", "badge_many": "{n} documentos",
        "tile_retrieved": "Documentos recuperados", "tile_cited": "Documentos citados",
        "tile_year": "Ano de publicação", "tile_languages": "Idiomas dos documentos",
        "by_type": "Documentos por tipo", "other": "Outro",
        "note_single": "Todas as conclusões vêm de um único documento ({kind}), então nada aqui é confrontado com outras publicações do WRI.",
        "note_many": "As conclusões se baseiam em {n} documentos do WRI.",
        "note_none": "Nenhum documento recuperado sustenta uma resposta para esta pergunta.",
        "view_all": "Ver os {n} documentos", "dialog_title": "Todos os documentos recuperados",
        "dialog_caption": "Ordenados por relevância: o quanto sua pergunta se parece com o trecho do documento que mais "
                          "combina, segundo a busca vetorial (100 % seria uma correspondência idêntica).",
        "relevancy": "Relevância {pct} %", "cited": "Citado", "not_cited": "Não citado",
        "passages_in_doc": "Trechos deste documento",
        "sources_heading": "Fontes, da mais relevante para a menos relevante",
        "status_verified": "FONTE {n} · VERIFICADA NO TEXTO DO DOCUMENTO",
        "status_verified_translated": "FONTE {n} · VERIFICADA NO TEXTO TRADUZIDO",
        "status_not_found": "FONTE {n} · CITAÇÃO NÃO ENCONTRADA NO TEXTO", "status_not_cited": "FONTE {n} · RECUPERADA, NÃO CITADA",
        "note_translated": "O documento original está em {language}. Este trecho é a tradução para o inglês "
                           "feita quando o documento foi adicionado à biblioteca.",
        "note_unverified": "A citação em que a resposta se baseia não pôde ser associada a este trecho. "
                           "Trate a afirmação como não confirmada e confira o documento.",
        "open_document": "Abrir o documento",
        "page_one": "página {a}", "page_range": "páginas {a}–{b}", "of_total": "{label} de {total}",
    },
    "zh": {
        "nav_ask": "提问", "nav_briefing": "研究简报", "nav_gaps": "查找研究空白",
        "mode_briefing": "研究简报", "mode_gaps": "查找研究空白",
        "hint_ask": "询问 WRI 的研究",
        "hint_briefing": "输入主题，例如电动校车", "hint_gaps": "输入主题，例如能效",
        "example_ask": "WRI 如何看待肯尼亚的粮食损失和浪费？",
        "example_briefing": "电动校车", "example_gaps": "能效", "recent": "最近", "language_label": "语言",
        "hero_title": "向 WRI 的研究提问",
        "hero_sub": "每个回答都会标明所依据的文件、页码和段落。当前检索 {first} 年至 {last} 年的 {count} 份出版物。",
        "searching": "正在检索并阅读 WRI 文件，最多可能需要一分钟。",
        "error_title": "出错了",
        "error_body": "智能体没有返回回答（{error}）。请重试。",
        "answered_in": "用时 {seconds} 秒", "turn_into_briefing": "生成简报",
        "found_title": "检索结果概览",
        "badge_none": "未引用任何来源", "badge_single": "单一来源", "badge_many": "{n} 份文件",
        "tile_retrieved": "检索到的文件", "tile_cited": "被引用的文件",
        "tile_year": "出版年份", "tile_languages": "文件语言",
        "by_type": "按类型统计的文件", "other": "其他",
        "note_single": "所有结论都来自同一份文件（{kind}），因此没有与 WRI 的其他出版物交叉核对。",
        "note_many": "结论基于 {n} 份 WRI 文件。",
        "note_none": "检索到的文件无法回答这个问题。",
        "view_all": "查看全部 {n} 份文件", "dialog_title": "检索到的全部文件",
        "dialog_caption": "按相关度排序：即您的问题与文件中最匹配段落的相似程度，由向量检索打分（100 % 表示完全一致）。",
        "relevancy": "相关度 {pct} %", "cited": "已引用", "not_cited": "未引用",
        "passages_in_doc": "此文件中的段落",
        "sources_heading": "来源（按相关度由高到低）",
        "status_verified": "来源 {n} · 已在文件原文中核实",
        "status_verified_translated": "来源 {n} · 已在翻译文本中核实",
        "status_not_found": "来源 {n} · 在文本中未找到该引文", "status_not_cited": "来源 {n} · 已检索，未引用",
        "note_translated": "原文件为{language}。此段落是文件加入资料库时生成的英文译文。",
        "note_unverified": "回答所依据的引文无法与此段落匹配。请将该说法视为未经证实，并查阅原文件。",
        "open_document": "打开文件",
        "page_one": "第 {a} 页", "page_range": "第 {a}–{b} 页", "of_total": "{label}，共 {total} 页",
    },
    "hi": {
        "nav_ask": "प्रश्न पूछें", "nav_briefing": "शोध सारांश", "nav_gaps": "शोध अंतराल खोजें",
        "mode_briefing": "शोध सारांश", "mode_gaps": "शोध अंतराल खोजें",
        "hint_ask": "WRI के शोध के बारे में पूछें",
        "hint_briefing": "कोई विषय बताएँ, जैसे इलेक्ट्रिक स्कूल बस", "hint_gaps": "कोई विषय बताएँ, जैसे ऊर्जा दक्षता",
        "example_ask": "केन्या में खाद्य हानि और बर्बादी के बारे में WRI क्या कहता है?",
        "example_briefing": "इलेक्ट्रिक स्कूल बस", "example_gaps": "ऊर्जा दक्षता",
        "recent": "हाल के", "language_label": "भाषा",
        "hero_title": "WRI के शोध से कोई प्रश्न पूछें",
        "hero_sub": "हर उत्तर में दस्तावेज़, पृष्ठ और वह अंश बताया जाता है जिससे वह लिया गया है। "
                    "{first} से {last} तक के {count} प्रकाशनों में खोज की जा रही है।",
        "searching": "WRI के दस्तावेज़ खोजे और पढ़े जा रहे हैं। इसमें एक मिनट तक लग सकता है।",
        "error_title": "कुछ गड़बड़ हो गई",
        "error_body": "एजेंट ने उत्तर नहीं दिया ({error})। कृपया फिर से प्रयास करें।",
        "answered_in": "{seconds} सेकंड में उत्तर मिला", "turn_into_briefing": "सारांश में बदलें",
        "found_title": "खोज में क्या मिला",
        "badge_none": "कोई स्रोत उद्धृत नहीं", "badge_single": "एकल स्रोत", "badge_many": "{n} दस्तावेज़",
        "tile_retrieved": "प्राप्त दस्तावेज़", "tile_cited": "उद्धृत दस्तावेज़",
        "tile_year": "प्रकाशन वर्ष", "tile_languages": "दस्तावेज़ों की भाषाएँ",
        "by_type": "प्रकार के अनुसार दस्तावेज़", "other": "अन्य",
        "note_single": "सभी निष्कर्ष एक ही दस्तावेज़ ({kind}) से आते हैं, इसलिए यहाँ किसी बात की WRI के अन्य प्रकाशनों से जाँच नहीं की गई है।",
        "note_many": "निष्कर्ष WRI के {n} दस्तावेज़ों पर आधारित हैं।",
        "note_none": "प्राप्त किसी भी दस्तावेज़ से इस प्रश्न का उत्तर नहीं मिलता।",
        "view_all": "सभी {n} दस्तावेज़ देखें", "dialog_title": "प्राप्त सभी दस्तावेज़",
        "dialog_caption": "प्रासंगिकता के अनुसार क्रमबद्ध: आपका प्रश्न दस्तावेज़ के सबसे मेल खाते अंश से कितना मिलता है, "
                          "वेक्टर खोज के स्कोर के अनुसार (100 % का अर्थ है पूर्ण मेल)।",
        "relevancy": "प्रासंगिकता {pct} %", "cited": "उद्धृत", "not_cited": "उद्धृत नहीं",
        "passages_in_doc": "इस दस्तावेज़ के अंश",
        "sources_heading": "स्रोत, सबसे प्रासंगिक पहले",
        "status_verified": "स्रोत {n} · दस्तावेज़ के पाठ में सत्यापित",
        "status_verified_translated": "स्रोत {n} · अनूदित पाठ में सत्यापित",
        "status_not_found": "स्रोत {n} · उद्धरण पाठ में नहीं मिला", "status_not_cited": "स्रोत {n} · प्राप्त, उद्धृत नहीं",
        "note_translated": "मूल दस्तावेज़ {language} में है। यह अंश उस अंग्रेज़ी अनुवाद का है जो दस्तावेज़ को लाइब्रेरी में जोड़ते समय बनाया गया था।",
        "note_unverified": "उत्तर जिस उद्धरण पर आधारित है, वह इस अंश से मेल नहीं खा सका। इस दावे को अपुष्ट मानें और दस्तावेज़ देखें।",
        "open_document": "दस्तावेज़ खोलें",
        "page_one": "पृष्ठ {a}", "page_range": "पृष्ठ {a}–{b}", "of_total": "{label} / {total}",
    },
}

# Filter values: stored English value -> text per language (missing values are shown as stored)
VALUES = {
    "subtype": {
        "es": {"Case Study": "Estudio de caso", "Conference Proceedings": "Actas de conferencia", "Expert Note": "Nota de expertos",
               "Fact Sheet": "Ficha informativa", "Guidebook": "Guía", "Issue Brief": "Resumen de políticas",
               "Practice Note": "Nota de práctica", "Report": "Informe", "Technical Note": "Nota técnica",
               "Working Paper": "Documento de trabajo", "Other": "Otro"},
        "fr": {"Case Study": "Étude de cas", "Conference Proceedings": "Actes de conférence", "Expert Note": "Note d'expert",
               "Fact Sheet": "Fiche d'information", "Guidebook": "Guide", "Issue Brief": "Note de synthèse",
               "Practice Note": "Note de pratique", "Report": "Rapport", "Technical Note": "Note technique",
               "Working Paper": "Document de travail", "Other": "Autre"},
        "pt": {"Case Study": "Estudo de caso", "Conference Proceedings": "Anais de conferência", "Expert Note": "Nota de especialista",
               "Fact Sheet": "Ficha informativa", "Guidebook": "Guia", "Issue Brief": "Resumo de políticas",
               "Practice Note": "Nota de prática", "Report": "Relatório", "Technical Note": "Nota técnica",
               "Working Paper": "Documento de trabalho", "Other": "Outro"},
        "hi": {"Case Study": "केस स्टडी", "Conference Proceedings": "सम्मेलन की कार्यवाही", "Expert Note": "विशेषज्ञ टिप्पणी",
               "Fact Sheet": "तथ्य-पत्र", "Guidebook": "मार्गदर्शिका", "Issue Brief": "मुद्दा सारांश",
               "Practice Note": "व्यवहार नोट", "Report": "रिपोर्ट", "Technical Note": "तकनीकी नोट",
               "Working Paper": "कार्य-पत्र", "Other": "अन्य"},
        "zh": {"Case Study": "案例研究", "Conference Proceedings": "会议论文集", "Expert Note": "专家说明",
               "Fact Sheet": "情况说明", "Guidebook": "指南", "Issue Brief": "政策简报", "Practice Note": "实践说明",
               "Report": "报告", "Technical Note": "技术说明", "Working Paper": "工作论文", "Other": "其他"},
    },
    # Document languages (codes), named in each interface language
    "language": {
        "en": {"en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese", "zh": "Chinese", "hi": "Hindi"},
        "es": {"en": "Inglés", "es": "Español", "fr": "Francés", "pt": "Portugués", "zh": "Chino", "hi": "Hindi"},
        "fr": {"en": "Anglais", "es": "Espagnol", "fr": "Français", "pt": "Portugais", "zh": "Chinois", "hi": "Hindi"},
        "pt": {"en": "Inglês", "es": "Espanhol", "fr": "Francês", "pt": "Português", "zh": "Chinês", "hi": "Hindi"},
        "hi": {"en": "अंग्रेज़ी", "es": "स्पेनिश", "fr": "फ़्रेंच", "pt": "पुर्तगाली", "zh": "चीनी", "hi": "हिन्दी"},
        "zh": {"en": "英语", "es": "西班牙语", "fr": "法语", "pt": "葡萄牙语", "zh": "中文", "hi": "印地语"},
    },
}


class Tr:
    """Translator for one interface language."""

    def __init__(self, lang):
        self.lang = lang if lang in TEXT else "en"

    def __call__(self, key, **values):
        text = TEXT[self.lang].get(key) or TEXT["en"][key]
        return text.format(**values) if values else text

    def label(self, kind, value):
        """Show a stored filter value in this language."""
        return VALUES.get(kind, {}).get(self.lang, {}).get(value, value)

    @property
    def answer_language(self):
        return ANSWER_LANGUAGE[self.lang]
