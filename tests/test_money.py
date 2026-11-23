"""Money tests with answers worked out by hand. Made-up inputs only: this file is in the public repository.
The one check against Ben's real standing decision runs only where the private records are present (the engine job)
and compares two private files, so no private figure is written here.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "ops", "engine"))
sys.path.insert(0, os.path.join(HERE, "..", "ops"))

import actions as A  # noqa: E402
import allocation as AL  # noqa: E402
import consistency as C  # noqa: E402
import events as EV  # noqa: E402
import qlab as Q  # noqa: E402
import test_numbers as TN  # noqa: E402


def ctx(**kw):
    return TN.Actions.ctx(TN.Actions(), **kw)


class Fees(unittest.TestCase):
    def test_percent_applies_above_the_minimum(self):
        self.assertEqual(A.fee(1000.0, 0.0025, 1.12), 2.50)

    def test_minimum_applies_on_a_small_order(self):
        self.assertEqual(A.fee(100.0, 0.0025, 1.12), 1.12)

    def test_the_crossover_is_exact(self):
        self.assertEqual(A.fee(448.0, 0.0025, 1.12), 1.12)

    def test_no_order_no_fee(self):
        self.assertEqual(A.fee(0.0, 0.0025, 1.12), 0.0)

    def test_a_zero_percent_plan_charges_its_flat_fee(self):
        self.assertEqual(A.fee(5000.0, 0.0, 0.02), 0.02)

    def test_quant_lab_fee_rate_on_a_small_order(self):
        self.assertAlmostEqual(Q.fee_rate(100.0), 0.01)

    @unittest.expectedFailure
    def test_every_module_uses_one_fee_schedule(self):
        # OPEN, Ben's decision: live cards use his real plan (about 2 cents), other modules 0.25% with $1 or $1.12.
        import decide, files, lab, plans
        mins = {decide.FEE_MIN, files.FEE_MIN, lab.FEE_MIN, plans.FEE_MIN, Q.FEE_MIN, AL.FEE_MIN}
        self.assertEqual(len(mins), 1, mins)


class OrderSizes(unittest.TestCase):
    def test_whole_shares_when_the_money_buys_one(self):
        self.assertEqual(A.shares_for(1000.0, 300.0), 3.0)

    def test_a_fraction_rounds_down(self):
        self.assertEqual(A.shares_for(50.0, 300.0), 0.1666)

    def test_never_spends_more_than_given(self):
        for usd, px in ((257.99, 302.7), (999.99, 3.33), (100.0, 99.99), (1.0, 4321.0)):
            self.assertLessEqual(A.shares_for(usd, px) * px, usd + 1e-9)

    def test_no_price_buys_nothing(self):
        self.assertEqual(A.shares_for(100.0, 0), 0.0)

    def test_buy_card_prices_are_ordered(self):
        acts, _ = A.today(ctx())
        a = acts[0]
        limit = a["buy"]["limit"] if a["type"] == "SWAP" else a["limit"]
        self.assertLess(a["stop"], limit)
        self.assertLess(limit, a["take_profit"])

    def test_sale_proceeds_and_tax(self):
        n = A.sell_numbers("OLD", ctx())
        self.assertEqual(n["gross"], 200.0)
        self.assertEqual(n["proceeds"], round(200.0 - n["fees"], 2))
        self.assertAlmostEqual(n["gain"], 200.0 - n["fees"] - 120.0, places=2)
        self.assertAlmostEqual(n["tax"], 0.15 * n["gain"], places=2)


class TargetSplit(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "answers"))
        os.makedirs(os.path.join(self.root, "state", "allocation"))
        self.old = AL.ROOT
        AL.ROOT = self.root

    def tearDown(self):
        AL.ROOT = self.old
        shutil.rmtree(self.root)

    def answer(self, name, **kw):
        with open(os.path.join(self.root, "answers", "alloc-%s.json" % name), "w", encoding="utf-8") as f:
            json.dump(dict({"kind": "allocation", "id": name, "at": "2026-11-24T10:00:00Z"}, **kw), f)

    def test_a_split_of_100_is_saved(self):
        self.answer("a", stocks=40, bonds=10, etfs=50, band=5)
        tg, _ = AL.read_target()
        self.assertEqual((tg["stocks"], tg["bonds"], tg["etfs"]), (40, 10, 50))

    def test_a_split_that_does_not_add_up_is_refused(self):
        self.answer("a", stocks=60, bonds=30, etfs=20)
        self.assertIsNone(AL.read_target()[0])

    def test_a_negative_part_is_refused(self):
        self.answer("a", stocks=-10, bonds=60, etfs=50)
        self.assertIsNone(AL.read_target()[0])

    def test_the_band_is_kept_between_1_and_20(self):
        self.answer("a", stocks=40, bonds=10, etfs=50, band=99)
        self.assertEqual(AL.read_target()[0]["band"], 20)

    def act(self, stocks, etfs, cash=0.0):
        inv = stocks + etfs
        return {"invested": inv, "cash": cash, "usd": {"stocks": stocks, "bonds": 0.0, "etfs": etfs},
                "pct": {"stocks": round(100.0 * stocks / inv, 1), "bonds": 0.0, "etfs": round(100.0 * etfs / inv, 1)},
                "positions": [{"ticker": "KEEP", "part": "stocks", "value": stocks, "cost": stocks}, {"ticker": "SPY", "part": "etfs", "value": etfs, "cost": etfs}]}

    def test_drift_inside_the_band_is_not_flagged(self):
        p = AL.plan({"stocks": 50, "bonds": 0, "etfs": 50, "band": 5}, self.act(540.0, 460.0), {})
        self.assertEqual(p["outside_band"], [])

    def test_drift_outside_the_band_is_flagged(self):
        p = AL.plan({"stocks": 50, "bonds": 0, "etfs": 50, "band": 5}, self.act(560.0, 440.0), {})
        self.assertEqual(sorted(p["outside_band"]), ["etfs", "stocks"])

    def test_new_money_never_exceeds_the_cash(self):
        p = AL.plan({"stocks": 20, "bonds": 40, "etfs": 40, "band": 5}, self.act(800.0, 200.0, cash=300.0), {"KEEP": {}})
        self.assertLessEqual(sum(s["usd"] for s in p["steps"] if s["type"] == "BUY"), 300.0)

    def test_a_kept_holding_is_never_in_a_sale_step(self):
        p = AL.plan({"stocks": 10, "bonds": 40, "etfs": 50, "band": 5, "allow_sales": True}, self.act(800.0, 200.0), {"KEEP": {}})
        self.assertNotIn("KEEP", [s.get("ticker") for s in p["steps"] if s["type"] == "SELL"])

    def test_outcomes_known_answer(self):
        a = {"mu": {"stocks": 0.10, "bonds": 0.0, "etfs": 0.0}, "cov": [[0.04, 0, 0], [0, 0, 0], [0, 0, 0]]}
        o = AL.outcomes({"stocks": 100, "bonds": 0, "etfs": 0}, a, 1)
        self.assertAlmostEqual(o["typical"], 0.0833, places=4)          # exp(0.10 - 0.04/2) - 1
        self.assertAlmostEqual(o["bad_1_in_10"], -0.1615, places=3)     # exp(0.08 - 1.2816 x 0.2) - 1
        self.assertAlmostEqual(o["chance_of_loss"], 0.345, places=2)    # N(-0.08 / 0.2)


class CaseCounts(unittest.TestCase):
    def run_tool(self, n):
        old = Q.TOOLS.get("backtest")
        Q.TOOLS["backtest"] = lambda inp: {"cases": n, "case_word": "cases"}
        try:
            return Q.run_one({"id": "qlab-1", "tool": "backtest", "inputs": {}})["cases_note"]
        finally:
            Q.TOOLS["backtest"] = old

    def test_19_cases_are_too_few(self):
        self.assertEqual(self.run_tool(19), "too few cases to rely on")

    def test_20_cases_are_enough(self):
        self.assertEqual(self.run_tool(20), "20 cases")

    def test_event_study_marks_19_as_few(self):
        self.assertTrue(EV.summary([0.01] * 19)["few"])
        self.assertFalse(EV.summary([0.01] * 20)["few"])

    def test_monte_carlo_percentiles_known_answer(self):
        o = Q.pcts([x / 100.0 for x in range(-50, 51)])
        self.assertEqual((o["typical"], o["bad_1_in_10"], o["good_1_in_10"]), (0.0, -0.4, 0.4))
        self.assertAlmostEqual(o["chance_of_loss"], 50 / 101.0, places=3)


class OneDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "state"))
        self.old = C.ROOT

    def tearDown(self):
        C.ROOT = self.old
        shutil.rmtree(self.root)

    def write(self, name, obj):
        with open(os.path.join(self.root, "state", name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def book(self, cards=None, actions=None, **dec):
        acts = actions if actions is not None else [{"type": "BUY", "ticker": "ABC", "key": "SCORE:ABC", "line": "BUY 1 ABC at limit $10.00."}]
        text = "\n".join(a["line"] for a in acts) or "DO NOTHING TODAY"
        self.write("actions.json", {"as_of": "2026-11-24T10:00:00Z", "actions": acts, "final": {"headline": "DO THIS 1 THING" if acts else "DO NOTHING TODAY", "text": text, "lines": [x["line"] for x in acts],
                                                                                         "action_tickers": [x["ticker"] for x in acts], "action_keys": [x["key"] for x in acts]}})
        self.write("decisions.json", dict({"cards": cards or [], "keeps": {"KEEP": {}}}, **dec))

    def test_a_matching_card_passes(self):
        self.book([{"id": "1", "status": "open", "kind": "idea", "key": "SCORE:ABC", "ticker": "ABC", "title": "ABC: idea"}])
        self.assertEqual(C.check(self.root), [])

    def test_an_offered_card_outside_the_answer_fails(self):
        self.book([{"id": "2", "status": "open", "kind": "idea", "key": "SCORE:XYZ", "ticker": "XYZ", "title": "XYZ: idea"}])
        self.assertTrue(any("outside today's answer" in x for x in C.check(self.root)))

    def test_a_greyed_card_titled_buy_fails(self):
        self.book([{"id": "3", "status": "open", "kind": "buy", "key": "BUY:PFE", "greyed": True, "title": "Buy $255.76 of PFE"}])
        self.assertTrue(any("not in today's answer" in x for x in C.check(self.root)))

    def test_a_morning_question_outside_the_answer_fails(self):
        self.book(morning={"questions": [{"id": "9", "kind": "decision", "text": "Buy XYZ?"}]})
        self.assertTrue(any("morning check" in x for x in C.check(self.root)))


class ConvictionGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "state"))
        self.old = C.ROOT

    def tearDown(self):
        C.ROOT = self.old
        shutil.rmtree(self.root)

    def write(self, name, obj):
        with open(os.path.join(self.root, "state", name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def violations(self, acts=None, results=None):
        self.write("decisions.json", {"cards": [], "keeps": {"UBER": {}}})
        self.write("actions.json", {"actions": acts or [], "final": {"text": "DO NOTHING TODAY"}})
        if results:
            self.write("results.json", results)
        return C.check_conviction(self.root)

    def test_a_sell_action_on_the_kept_holding_fails(self):
        self.assertTrue(self.violations([{"type": "SELL", "ticker": "UBER", "line": "SELL UBER"}]))

    def test_a_swap_out_of_the_kept_holding_fails(self):
        self.assertTrue(self.violations([{"type": "SWAP", "sell": {"ticker": "UBER"}, "line": "SWAP"}]))

    def test_trim_wording_fails(self):
        self.assertTrue(self.violations([{"type": "HOLD", "ticker": "X", "line": "Consider trimming UBER."}]))

    def test_its_result_in_the_system_record_fails(self):
        self.assertTrue(self.violations(results={"system": {"positions": [{"ticker": "UBER"}]}}))

    def test_take_profit_never_sells_a_kept_holding(self):
        c = ctx(plans={"KEEP": {"take_profit": 60.0}})
        acts, _ = A.today(c)
        self.assertNotIn("KEEP", [a.get("ticker") for a in acts if a["type"] == "SELL"])
        self.assertNotIn("KEEP", [(a.get("sell") or {}).get("ticker") for a in acts])

    def test_asking_to_sell_it_answers_hold(self):
        self.assertEqual(A.should_sell("keep", ctx())[0]["type"], "HOLD")

    def test_real_target_and_review_date_match_the_standing_decision(self):
        root = os.environ.get("MC_ROOT", ".")
        doc, dec = os.path.join(root, "CLAUDE.md"), os.path.join(root, "state", "decisions.json")
        if not (os.path.exists(doc) and os.path.exists(dec)):
            self.skipTest("private records not present")
        text = open(doc, encoding="utf-8").read()
        m = re.search(r"Target \$([\d.]+), review date (\d+ \w+ \d{4})", text)
        k = (json.load(open(dec, encoding="utf-8")).get("keeps") or {}).get("UBER") or {}
        self.assertEqual(float(k.get("target")), float(m.group(1)))
        d = m.group(2).split()
        months = {"Oct": "10"}
        self.assertEqual(str(k.get("by") or k.get("review")), "%s-%s-%02d" % (d[2], months[d[1]], int(d[0])))


class ValueIsSharesTimesPrice(unittest.TestCase):
    # 23 Nov 2026: a share logged at $108 while its quote was $87.64 kept its cost as its value, so the total was $111 too high
    def snap(self):
        return {"cash": 0.0, "nav": 1000.0, "positions": [{"ticker": "NEW", "qty": 10.0, "last_price": 80.0, "market_value": 1000.0}]}

    def test_refresh_saves_a_wrong_value_when_the_price_is_unchanged(self):
        import prices
        s = self.snap()
        changed = prices.refresh(s, fetch=lambda t: {"current_price": 80.0, "last_trade_time": "2026-11-23T21:00:00"})
        self.assertEqual(changed, ["NEW"])
        self.assertEqual(s["positions"][0]["market_value"], 800.0)
        self.assertEqual(s["nav"], 800.0)

    def test_refresh_reports_nothing_when_all_is_right(self):
        import prices
        s = self.snap()
        s["positions"][0]["market_value"] = 800.0
        self.assertEqual(prices.refresh(s, fetch=lambda t: {"current_price": 80.0}), [])


class NightlyRemark(unittest.TestCase):
    def test_remark_uses_shares_times_close_not_the_old_value(self):
        import keeper
        s = {"cash": 0.0, "positions": [{"ticker": "NEW", "qty": 10.0, "last_price": 80.0, "market_value": 1000.0, "price_as_of": "2026-11-20T21:00:00Z"}]}
        keeper.remark(s, {"NEW": ("2026-11-23", 90.0)}, "2026-11-23T22:00:00Z")
        self.assertEqual(s["positions"][0]["market_value"], 900.0)

    def test_remark_saves_a_wrong_value_when_the_close_is_unchanged(self):
        import keeper
        s = {"cash": 0.0, "nav": 1000.0, "positions": [{"ticker": "NEW", "qty": 10.0, "last_price": 80.0, "market_value": 1000.0, "price_as_of": "2026-11-23T21:00:00Z"}]}
        self.assertEqual(keeper.remark(s, {"NEW": ("2026-11-23", 80.0)}, "2026-11-23T22:00:00Z"), ["NEW"])
        self.assertEqual(s["nav"], 800.0)

    def test_remark_without_a_share_count_still_scales(self):
        import keeper
        s = {"cash": 0.0, "positions": [{"ticker": "OLD", "qty": None, "last_price": 50.0, "market_value": 500.0, "price_as_of": "2026-11-20T21:00:00Z"}]}
        keeper.remark(s, {"OLD": ("2026-11-23", 55.0)}, "2026-11-23T22:00:00Z")
        self.assertEqual(s["positions"][0]["market_value"], 550.0)


class PhoneMessages(unittest.TestCase):
    def test_the_clock_starts_message_pickup(self):
        # GitHub skipped the five-minute schedule for hours on 23 Nov 2026, so phone messages waited
        text = open(os.path.join(HERE, "..", ".github", "workflows", "clock.yml"), encoding="utf-8").read()
        self.assertIn("gh workflow run listen.yml", text)


class PublicRepo(unittest.TestCase):
    def test_no_record_folder_is_tracked(self):
        try:
            out = subprocess.check_output(["git", "ls-files"], cwd=os.path.join(HERE, ".."), text=True)
        except Exception:
            self.skipTest("git not available")
        bad = [f for f in out.splitlines() if re.match(r"(state|treasury|answers|research|inbox|outbox|digests|brief)/", f)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
