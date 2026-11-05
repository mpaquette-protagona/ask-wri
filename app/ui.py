"""HTML builders for the AskWRI chat page. Pure functions (no Streamlit, no AWS) so they are easy to check.
Every piece of text that comes from the model or from a document is escaped before it goes into HTML.
Interface text comes from i18n.Tr, so the same builders serve every interface language.
"""
import html
import re

BAR_COLORS = ["var(--bar-1)", "var(--bar-2)", "var(--bar-3)"]  # defined in style.css, so dark mode can change them
OTHER_COLOR = "var(--bar-other)"


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def prepare_body(body, valid_numbers):
    """Make the answer safe to show with st.markdown(unsafe_allow_html=True).
    Escapes "<" so model text cannot inject HTML, escapes "$" so prices are not read as math,
    and turns each [n] that matches a retrieved source into a citation chip."""
    body = body.replace("<", "&lt;").replace("$", "\\$")

    def chip(match):
        number = int(match.group(1))
        return f'<span class="cite">{number}</span>' if number in valid_numbers else match.group(0)

    return re.sub(r"\[(\d+)\]", chip, body)


def pages_text(source, tr):
    start, end, total = source.get("page_start"), source.get("page_end"), source.get("pages_total")
    label = tr("page_one", a=start) if start == end else tr("page_range", a=start, b=end)
    return tr("of_total", label=label, total=total) if total else label


def years_text(years):
    if not years:
        return "\u2013"
    return years[0] if len(years) == 1 else f"{years[0]}\u2013{years[-1][-2:]}"


def percent(score):
    """Relevancy as a whole percent. The score is a cosine similarity from the vector search (1 - distance)."""
    return max(0, min(100, round(float(score) * 100)))


def question_html(question, mode_label=None):
    tag = f'<div class="q-mode">{esc(mode_label)}</div>' if mode_label else ""
    return f'{tag}<div class="q-bubble">{esc(question)}</div>'


def found_html(stats, badge, tr):
    """The "What the search found" card. First view shows documents only: four number tiles and a
    documents-by-type bar. Passages are one click away, in the document list."""
    languages = stats.get("languages") or []
    # full names in the page language ("Spanish", "Español"...); a code we have no name for is shown as it is
    names = [tr.label("language", code) if tr.label("language", code) != code else code.upper() for code in languages]
    language_text = ", ".join(names) if names else "\u2013"
    tiles = [(stats["documents_retrieved"], tr("tile_retrieved")),
             (stats["documents_cited"], tr("tile_cited")),
             (years_text(stats["years"]), tr("tile_year")),
             (language_text, tr("tile_languages"))]
    # a long value (language names) gets a smaller size so it stays inside its tile
    tiles_html = "".join(f'<div class="tile"><div class="tile-n{" tile-n-text" if len(str(n)) > 6 else ""}">{esc(n)}</div>'
                         f'<div class="tile-l">{esc(label)}</div></div>' for n, label in tiles)
    types = stats.get("by_subtype") or []
    shown, rest = types[:3], sum(count for _, count in types[3:])
    parts = [(tr.label("subtype", name), count, BAR_COLORS[i]) for i, (name, count) in enumerate(shown)]
    if rest:
        parts.append((tr("other"), rest, OTHER_COLOR))
    bar = "".join(f'<span style="flex:{count};background:{color}" title="{esc(name)}"></span>'
                  for name, count, color in parts)
    legend = "".join(f'<span class="lg"><i style="background:{color}"></i>{esc(name)} {count}</span>'
                     for name, count, color in parts)
    type_block = (f'<div class="found-sub">{esc(tr("by_type"))}</div><div class="bar">{bar}</div>'
                  f'<div class="legend">{legend}</div>') if parts else ""
    return (f'<div class="found-head"><span class="found-title">{esc(tr("found_title"))}</span>'
            f'<span class="badge">{esc(badge)}</span></div>'
            f'<div class="tiles">{tiles_html}</div>{type_block}')


def relevancy_html(score, tr):
    pct = percent(score)
    return (f'<div class="rel"><div class="rel-bar"><span style="width:{pct}%"></span></div>'
            f'<span class="rel-text">{esc(tr("relevancy", pct=pct))}</span></div>')


def document_meta(document, tr):
    """One line under a document title: type, year, language."""
    return " \u00b7 ".join(x for x in [tr.label("subtype", document.get("subtype") or "Other"),
                                      document.get("year"), tr.label("language", document.get("language"))] if x)


def source_html(source, tr):
    """The right-hand panel: status line, title, details, the passage with the quote highlighted."""
    language = tr.label("language", source.get("language")) if source.get("language") else ""
    translated = source.get("language") not in (None, "", "en")
    if source.get("verified"):
        status = tr("status_verified_translated" if translated else "status_verified", n=source["n"])
        css = "status-ok"
    else:
        status, css = tr("status_not_found", n=source["n"]), "status-warn"

    meta = " \u00b7 ".join(x for x in [tr.label("subtype", source.get("subtype") or "Other"), source.get("year"),
                                      language, pages_text(source, tr)] if x)
    passage = source["passage"]
    text, span = passage["text"], passage.get("highlight")
    if span:
        body = esc(text[:span[0]]) + "<mark>" + esc(text[span[0]:span[1]]) + "</mark>" + esc(text[span[1]:])
    else:
        body = esc(text)
    lead = "\u2026" if passage.get("cut_start") else ""
    tail = "\u2026" if passage.get("cut_end") else ""
    note = ""
    if translated:
        note = f'<div class="note">{esc(tr("note_translated", language=language))}</div>'
    elif source.get("verified") is False:
        note = f'<div class="note">{esc(tr("note_unverified"))}</div>'
    relevancy = relevancy_html(source["relevancy"], tr) if source.get("relevancy") is not None else ""
    return (f'<div class="src-status {css}">{esc(status)}</div>'
            f'<div class="src-title">{esc(source["title"])}</div>'
            f'<div class="src-meta">{esc(meta)}</div>{relevancy}'
            f'<div class="src-section">{esc(source["section_title"])}</div>'
            f'<div class="passage">{lead}{body}{tail}</div>{note}')
