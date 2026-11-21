"""Innovation filter: relevance gate, verdict thresholds, rule fixes, labeled examples."""
from django.test import TestCase, override_settings
from analysis.core import decide, finalize
from analysis.evaluation import evaluate
from analysis.examples import EXAMPLES
from analysis.rules import AUTHOR, analyze


def run(text, title=""):
    return finalize(analyze(text, title), text)


def crit(d, key):
    return next(c for c in d["criteria"] if c["key"] == key)


SOLUTION = ("Zespół opracował czujnik, który umożliwia wykrywanie wycieków wody w budynkach. "
            "Problemem zarządców jest brak szybkiej informacji o awariach w piwnicach. ")


class RuleFixTests(TestCase):
    def test_lab_test_is_prototype_not_pilot(self):
        d = run(SOLUTION + "Urządzenie przetestowano w laboratorium uczelni na stanowisku badawczym.")
        self.assertEqual(d["stage"], "prototype")
        self.assertEqual(crit(d, "dowody")["score"], 1)

    def test_field_test_is_pilot(self):
        d = run(SOLUTION + "Urządzenie przetestowano w warunkach rzeczywistych w trzech budynkach spółdzielni.")
        self.assertEqual(d["stage"], "pilot")
        self.assertEqual(crit(d, "dowody")["score"], 2)

    def test_w_celu_is_not_a_problem(self):
        d = run("Spotkanie zorganizowano w celu omówienia planu zajęć na kolejny semestr studiów.")
        self.assertIsNone(crit(d, "problem")["score"])

    def test_score_does_not_grow_with_sentence_count(self):
        one = "Nowy system poprawi obsługę klientów w urzędzie miasta. "
        d1, d5 = run(one), run(one * 5)
        self.assertEqual(crit(d1, "wyniki")["score"], crit(d5, "wyniki")["score"])

    def test_author_titles_any_case(self):
        text = "Autorami są Dr inż. Anna Nowak-Kowalska oraz PROF. Jan Wiśniewski i dr hab. inż. Ewa Lis."
        self.assertEqual([m.group(0) for m in AUTHOR.finditer(text)],
                         ["Dr inż. Anna Nowak-Kowalska", "PROF. Jan Wiśniewski", "dr hab. inż. Ewa Lis"])


class GateTests(TestCase):
    def test_event_notice_rejected_with_reason(self):
        d = run("Zapraszamy na dzień otwarty uczelni. Na kandydatów czekają spotkania i informacje o rekrutacji.")
        self.assertEqual(d["verdict"]["id"], "odrzucone")
        self.assertIn("Nie wygląda na opis innowacji", d["verdict"]["reason"])

    def test_solution_with_evidence_reaches_main_list(self):
        d = run(next(e for e in EXAMPLES if e["id"] == "czujnik-sepsy")["text"])
        self.assertEqual(d["verdict"]["id"], "glowna")
        self.assertTrue(d["relevance"]["evidence"])

    def test_unverified_relevance_quote_needs_review(self):
        raw = {"relevance": {"is_solution": True, "evidence": ["Tego zdania nie ma w artykule wcale."]}}
        d = finalize(raw, "Krótki tekst bez cytowanego zdania o niczym konkretnym.")
        self.assertEqual(d["verdict"]["id"], "weryfikacja")

    def test_thresholds(self):
        yes = {"is_solution": True, "reason": "", "evidence": ["x"]}
        self.assertEqual(decide(yes, 80, 80)["id"], "glowna")
        self.assertEqual(decide(yes, 80, 40)["id"], "weryfikacja")  # too little evidence
        self.assertEqual(decide(yes, 40, 80)["id"], "weryfikacja")
        self.assertEqual(decide(yes, 10, 80)["id"], "odrzucone")
        self.assertEqual(decide(yes, None, 0)["id"], "weryfikacja")

    @override_settings(ANALYSIS={"BACKEND": "rules", "WEIGHTS": {"problem": 1, "dowody": 2, "wyniki": 2,
                                 "przenosnosc": 1, "gotowosc": 1}, "THRESHOLDS": {"main": 90}})
    def test_thresholds_configurable(self):
        yes = {"is_solution": True, "reason": "", "evidence": ["x"]}
        self.assertEqual(decide(yes, 80, 80)["id"], "weryfikacja")


class LabeledExamplesTests(TestCase):
    def test_examples_size_and_balance(self):
        self.assertTrue(12 <= len(EXAMPLES) <= 40)  # incl. non-technological school/JST cases
        self.assertTrue(any(e["label"] for e in EXAMPLES) and not all(e["label"] for e in EXAMPLES))

    def test_no_interesting_example_rejected_and_precision_holds(self):
        r = evaluate()
        self.assertEqual(r["lenient"]["fn"], 0, r["errors"])
        self.assertGreaterEqual(r["lenient"]["precision"], 0.9)
