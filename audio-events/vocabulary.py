"""Per-trigger decoder grammars and explicit spellings for spoken aliases."""

from events import words


def normalize(text):
    return " ".join(words(text))


def validate_vocabulary_settings(value):
    if not isinstance(value, dict):
        raise ValueError("Vocabulary must be an object")
    if type(value.get("enabled", False)) is not bool:
        raise ValueError("Vocabulary enabled must be true or false")
    for key in ("words", "sentences"):
        entries = value.get(key, [])
        if not isinstance(entries, list) or any(not isinstance(item, str) or not normalize(item) or "[unk]" in words(item) for item in entries):
            raise ValueError(f"Vocabulary {key} must be a list of nonempty terms")
        normalized = [normalize(item) for item in entries]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"Duplicate vocabulary {key}")
    aliases = value.get("aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("Aliases must map spoken phrases to written spellings")
    seen = set()
    for spoken, written in aliases.items():
        if any(not isinstance(term, str) or not normalize(term) or "[unk]" in words(term) for term in (spoken, written)):
            raise ValueError("Aliases need nonempty spoken and written forms")
        key = normalize(spoken)
        if key in seen:
            raise ValueError("Duplicate spoken alias")
        seen.add(key)
    if value.get("enabled") and not grammar_phrases(value):
        raise ValueError("Add vocabulary words, sentences, or aliases before enabling it")


def grammar_phrases(value):
    """Expand written names into known spoken words before creating the FST."""
    aliases = value.get("aliases", {})
    expansions = {}
    for spoken, written in aliases.items():
        expansions.setdefault(tuple(words(written)), words(spoken))
    keys = sorted(expansions, key=len, reverse=True)

    def expand(term):
        tokens = words(term)
        output = []
        index = 0
        while index < len(tokens):
            match = next((key for key in keys if tuple(tokens[index:index + len(key)]) == key), None)
            if match:
                output.extend(expansions[match])
                index += len(match)
            else:
                output.append(tokens[index])
                index += 1
        return " ".join(output)

    return sorted({expand(term) for term in value.get("words", []) + value.get("sentences", [])}
                  | {normalize(term) for term in aliases})


def apply_aliases(text, value):
    """Whole-word, longest-first replacement; output is never reprocessed."""
    aliases = {tuple(words(spoken)): written for spoken, written in value.get("aliases", {}).items()}
    if not aliases:
        return " ".join(token for token in text.split() if token != "[unk]")
    tokens = words(text)
    keys = sorted(aliases, key=len, reverse=True)
    output = []
    index = 0
    while index < len(tokens):
        match = next((key for key in keys if tuple(tokens[index:index + len(key)]) == key), None)
        if match:
            output.append(aliases[match])
            index += len(match)
        else:
            if tokens[index] != "[unk]":
                output.append(tokens[index])
            index += 1
    return " ".join(output)
