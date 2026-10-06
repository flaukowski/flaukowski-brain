"""pub_guard on synthetic text only: no held-out item appears in this file.

    python -m pytest test_pub_guard.py -q
"""
import pub_guard as g


def fp_from(held, public):
    pub_tok = {w for t in public for w in g.words(t)}
    pub_gram = {x for t in public for x in g.grams(g.words(t))}
    tok, gram = {}, {}
    for w in g.words(held):
        if g.distinctive(w) and w not in pub_tok:
            tok.setdefault(g.h(w), ["held:1"])
    for x in g.grams(g.words(held)):
        if x not in pub_gram:
            gram.setdefault(g.h(x), ["held:1"])
    return {"token": tok, "ngram": gram}


HELD = "The kiln at Brackwater fires above 1,350 degrees when the glaze is cobalt."
PUBLIC = ["The kiln fires when the glaze is ready, as the record says."]
FP = fp_from(HELD, PUBLIC)


def sev(text):
    return sorted({(s, k) for s, k, _, _ in g.check_text(text, FP)})


def test_number_blocks():
    assert ("BLOCK", "token") in sev("the reading was 1,350 that day")


def test_number_inside_hyphenated_token_blocks():
    assert ("BLOCK", "token") in sev("a 1,350-degree firing")


def test_phrase_blocks():
    hits = g.check_text("we heard the kiln at brackwater broke", FP)
    assert [k for s, k, _, _ in hits if s == "BLOCK"] == ["ngram"]   # 'the kiln at brackwater'; no number


def test_lone_rare_word_only_warns():
    assert sev("Brackwater was mentioned") == [("WARN", "token")]


def test_public_phrasing_passes():
    assert sev("The kiln fires when the glaze is ready.") == []


def test_dotted_token_splits():
    assert "systemx" in g.words("systemx.exec(5)")
