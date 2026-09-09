import argparse
import json
import re
from pathlib import Path

import spacy

SUBJECT_DEPENDENCIES = {
    "nsubj",
    "nsubjpass",
    "csubj",
}

OBJECT_DEPENDENCIES = {
    "dobj",
    "obj",
    "attr",
    "oprd",
    "dative",
}


def read_text_file(file_path: str) -> str:
    """Read UTF-8 text from a file."""

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Text file not found: {file_path}")

    return path.read_text(encoding="utf-8")


def load_nlp_model():
    """Load the installed English spaCy model."""

    try:
        return spacy.load("en_core_web_sm")

    except OSError as error:
        raise RuntimeError(
            "The spaCy English model is not installed. Run:\n"
            "python -m spacy download en_core_web_sm"
        ) from error


def extract_entities(document) -> list[dict]:
    """
    Extract named entities and noun phrases.

    Named entities include recognized people, organizations,
    dates, locations, quantities, etc.

    Noun phrases are stored as general concepts.
    """

    entities = []
    seen = set()

    # Named entities detected by spaCy NER
    for entity in document.ents:
        key = (
            entity.text.strip().casefold(),
            entity.label_,
        )

        if key not in seen:
            seen.add(key)

            entities.append(
                {
                    "text": entity.text.strip(),
                    "label": entity.label_,
                    "source": "named_entity_recognizer",
                }
            )

    # Noun phrases that may represent technical concepts
    for noun_chunk in document.noun_chunks:
        text = noun_chunk.text.strip()

        # Ignore very short or pronoun-only phrases
        if len(text) < 2:
            continue

        if noun_chunk.root.pos_ == "PRON":
            continue

        key = (
            text.casefold(),
            "CONCEPT",
        )

        if key not in seen:
            seen.add(key)

            entities.append(
                {
                    "text": text,
                    "label": "CONCEPT",
                    "source": "noun_phrase_extractor",
                }
            )

    return entities


def build_phrase_index(document) -> dict[int, str]:
    """
    Map token positions to the complete entity or noun phrase
    containing each token.
    """

    phrase_index = {}

    # Named entities receive priority.
    for entity in document.ents:
        for token_index in range(entity.start, entity.end):
            phrase_index[token_index] = entity.text.strip()

    # Fill remaining positions with noun phrases.
    for noun_chunk in document.noun_chunks:
        for token_index in range(noun_chunk.start, noun_chunk.end):
            phrase_index.setdefault(
                token_index,
                noun_chunk.text.strip(),
            )

    return phrase_index


def phrase_for_token(token, phrase_index: dict[int, str]) -> str:
    """Return the full phrase containing a token."""

    return phrase_index.get(token.i, token.text).strip()


def token_with_conjuncts(token) -> list:
    """
    Return a token and coordinated tokens.

    Example:
        salicylic acid and acetate
    """

    return [token, *list(token.conjuncts)]


def normalise_predicate(predicate: str) -> str:
    """
    Convert a relationship name into a machine-friendly form.

    Example:
        hydrolyze to -> hydrolyze_to
    """

    predicate = predicate.lower().strip()
    predicate = re.sub(r"[^a-z0-9]+", "_", predicate)

    return predicate.strip("_")


def find_objects(verb) -> list[tuple[str, object]]:
    """
    Find direct objects, prepositional objects, and objects
    connected through an infinitive verb.

    Returns:
        List of (predicate, object-token) pairs.
    """

    results = []

    # Direct objects
    for child in verb.children:
        if child.dep_ in OBJECT_DEPENDENCIES:
            for object_token in token_with_conjuncts(child):
                results.append(
                    (
                        verb.lemma_,
                        object_token,
                    )
                )

    # Prepositional relationships:
    # hydrolyzes to salicylic acid
    # detected after 15 minutes
    # acts as a base
    for child in verb.children:
        if child.dep_ == "prep":
            for preposition_object in child.children:
                if preposition_object.dep_ in {"pobj", "obj"}:
                    predicate = (
                        f"{verb.lemma_}_{child.lemma_}"
                    )

                    for object_token in token_with_conjuncts(
                        preposition_object
                    ):
                        results.append(
                            (
                                predicate,
                                object_token,
                            )
                        )

    # Infinitive relationships:
    # chromatography was used to monitor the reaction
    for child in verb.children:
        if child.dep_ == "xcomp" and child.pos_ == "VERB":
            for xcomp_child in child.children:
                if xcomp_child.dep_ in OBJECT_DEPENDENCIES:
                    predicate = (
                        f"{verb.lemma_}_to_{child.lemma_}"
                    )

                    for object_token in token_with_conjuncts(
                        xcomp_child
                    ):
                        results.append(
                            (
                                predicate,
                                object_token,
                            )
                        )

    return results


def extract_relationships(document) -> list[dict]:
    """
    Extract basic subject-predicate-object relationships using
    the grammatical dependency structure.
    """

    relationships = []
    seen = set()

    phrase_index = build_phrase_index(document)

    for sentence in document.sents:
        for verb in sentence:
            if verb.pos_ != "VERB":
                continue

            subjects = []

            for child in verb.children:
                if child.dep_ in SUBJECT_DEPENDENCIES:
                    subjects.extend(
                        token_with_conjuncts(child)
                    )

            if not subjects:
                continue

            objects = find_objects(verb)

            for subject_token in subjects:
                subject = phrase_for_token(
                    subject_token,
                    phrase_index,
                )

                for predicate_text, object_token in objects:
                    object_text = phrase_for_token(
                        object_token,
                        phrase_index,
                    )

                    predicate = normalise_predicate(
                        predicate_text
                    )

                    if not subject or not predicate or not object_text:
                        continue

                    if subject.casefold() == object_text.casefold():
                        continue

                    key = (
                        subject.casefold(),
                        predicate,
                        object_text.casefold(),
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    relationships.append(
                        {
                            "subject": subject,
                            "predicate": predicate,
                            "object": object_text,
                            "sentence": sentence.text.strip(),
                        }
                    )

    return relationships


def save_json(data, output_path: Path) -> None:
    """Save data as formatted JSON."""

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract entities and relationships "
            "from a plain-text document."
        )
    )

    parser.add_argument(
        "text_path",
        nargs="?",
        default="test01.txt",
        help="Input text file",
    )

    arguments = parser.parse_args()

    input_path = Path(arguments.text_path)

    text = read_text_file(str(input_path))
    nlp = load_nlp_model()

    print("Processing text...")

    document = nlp(text)

    entities = extract_entities(document)
    relationships = extract_relationships(document)

    entity_output = input_path.with_name(
        f"{input_path.stem}_entities.json"
    )

    relationship_output = input_path.with_name(
        f"{input_path.stem}_relationships.json"
    )

    save_json(entities, entity_output)
    save_json(relationships, relationship_output)

    print()
    print(f"Entities extracted: {len(entities)}")
    print(f"Saved to: {entity_output}")

    print()
    print(f"Relationships extracted: {len(relationships)}")
    print(f"Saved to: {relationship_output}")

    print("\nFirst extracted relationships:\n")

    for relationship in relationships[:20]:
        print(
            f"{relationship['subject']} "
            f"--{relationship['predicate']}--> "
            f"{relationship['object']}"
        )


if __name__ == "__main__":
    main()