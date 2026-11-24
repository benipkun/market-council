"""Money tests with answers worked out by hand. Made-up inputs only: this file is in the public repository.
The one check against Ben's real standing decision runs only where the private records are present (the engine job)
and compares two private files, so no private figure is written here.
"""
import datetime
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
        self.assertAlmostEqual(Q.fee_rate(100.0), 0.0002)

    def test_every_live_module_uses_one_fee_schedule(self):
        # Ben, 24 Nov 2026: 10 free trades, then 2 cents. The lab's back-tests keep 0.25% as a deliberate stress test.
        import decide, fees, files
        self.assertEqual({decide.FEE_MIN, files.FEE_MIN, Q.FEE_MIN, AL.FEE_MIN}, {fees.AFTER_FREE})
        self.assertEqual({decide.FEE_PCT, files.FEE_RATE, Q.FEE, AL.FEE_PCT}, {0.0})

    def test_the_first_ten_trades_of_a_month_are_free(self):
        import fees
        self.assertEqual(fees.fee_now(9), 0.0)
        self.assertEqual(fees.fee_now(10), 0.02)

    def test_trades_are_counted_by_month(self):
        import fees
        e = [{"action": "buy", "status": "applied", "at": "2026-11-30T10:00:00Z"}, {"action": "sell", "status": "applied", "at": "2026-12-01T10:00:00Z"},
             {"action": "deposit", "status": "applied", "at": "2026-12-01T11:00:00Z"}, {"action": "cash", "status": "applied", "at": "2026-12-01T11:00:00Z"},
             {"action": "buy", "status": "rejected", "at": "2026-12-02T10:00:00Z"}, {"action": "buy", "status": "applied", "undone_by": "x", "at": "2026-12-02T10:00:00Z"}]
        self.assertEqual(fees.trades_in_month(e, "2026-12-15"), 1)
        self.assertEqual(fees.trades_in_month(e, "2026-11-15"), 1)


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
        same_target = float(k.get("target")) == float(m.group(1))
        self.assertTrue(same_target, "the target differs from the standing decision")
        day = datetime.datetime.strptime(m.group(2), "%d %b %Y").strftime("%Y-%m-%d")
        self.assertTrue(str(k.get("by") or k.get("review")) == day, "the review date differs from the standing decision")


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


class DoNothingReason(unittest.TestCase):
    # 23 Nov 2026: with $0 cash the answer said no idea makes money, next to ideas with a positive expected result
    def cands(self):
        why = "REJECTED TODAY: no cash: free cash is $0.00, under the $100 minimum order"
        return [{"t": "AAA", "edge": 0.02, "held_back": [why], "fc": {}}, {"t": "BBB", "edge": 0.05, "held_back": [why], "fc": {}},
                {"t": "CCC", "edge": None, "held_back": ["no forecast yet"], "fc": {}}]

    def test_no_cash_is_named_as_the_reason(self):
        r = A.why_nothing(self.cands(), {"stale": [], "free_cash": 0.0, "monthly_huf": 120000.0})
        self.assertTrue(r.startswith("No free cash"), r)
        self.assertNotIn("No idea is expected to make money", r)

    def test_the_waiting_ideas_are_ranked_best_first(self):
        r = A.why_nothing(self.cands(), {"stale": [], "free_cash": 0.0})
        self.assertLess(r.index("BBB +5.0%"), r.index("AAA +2.0%"))
        self.assertNotIn("CCC", r)

    def test_ideas_that_truly_lose_keep_the_old_reason(self):
        r = A.why_nothing([{"t": "DDD", "edge": -0.01, "held_back": ["price check failed"], "fc": {}, "index_edge": 0.08}], {"stale": [], "free_cash": 500.0})
        self.assertTrue(r.startswith("No idea is expected to make money"), r)


class PhoneDelivery(unittest.TestCase):
    # GitHub keeps one waiting job per group and cancels the older one, so a message added by a cancelled job was never sent
    def test_a_message_from_a_cancelled_job_is_still_sent(self):
        import outbox_send as O
        self.assertEqual(O.pending(["a.json", "b.json", "c.json"], {"a.json"}), ["b.json", "c.json"])

    def test_a_sent_message_is_never_sent_twice(self):
        import outbox_send as O
        self.assertEqual(O.pending(["a.json"], {"a.json"}), [])

    def test_first_run_does_not_resend_the_whole_history(self):
        import outbox_send as O
        self.assertEqual(O.pending(["a.json", "b.json"], None), [])

    def test_only_delivered_messages_are_marked_sent(self):
        import outbox_send as O
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "outbox", "queue"))
            for n in ("a", "b"):
                open(os.path.join(d, "outbox", "queue", n + ".json"), "w").write("{}")
            open(os.path.join(d, "outbox", "sent.txt"), "w").write("# sent\n")
            failed = O.run(d, lambda name, msg: 200 if name == "a.json" else 500)
            self.assertEqual(failed, ["b.json"])
            self.assertEqual(open(os.path.join(d, "outbox", "sent.txt")).read().split(), ["#", "sent", "a.json"])
        finally:
            shutil.rmtree(d)


class DeliveryBadInput(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "outbox", "queue"))

    def tearDown(self):
        shutil.rmtree(self.d)

    def put(self, name, text):
        with open(os.path.join(self.d, "outbox", "queue", name), "w", encoding="utf-8") as f:
            f.write(text)

    def sent(self):
        return open(os.path.join(self.d, "outbox", "sent.txt"), encoding="utf-8").read().split()

    def test_a_bad_file_does_not_block_the_next_message(self):
        import outbox_send as O
        self.put("a.json", "[1, 2]")
        self.put("b.json", "not json")
        self.put("c.json", "{}")
        open(os.path.join(self.d, "outbox", "sent.txt"), "w").write("# sent\n")
        got = []
        self.assertEqual(O.run(self.d, lambda n, m: got.append(n) or 200), [])
        self.assertEqual(got, ["c.json"])

    def test_a_bad_file_is_not_retried_for_ever(self):
        import outbox_send as O
        self.put("a.json", "[1, 2]")
        open(os.path.join(self.d, "outbox", "sent.txt"), "w").write("# sent\n")
        O.run(self.d, lambda n, m: 200)
        self.assertIn("bad:a.json", self.sent())
        self.assertEqual(O.pending(["a.json"], O.read_sent(os.path.join(self.d, "outbox", "sent.txt"))), [])

    def test_an_error_while_sending_keeps_the_message_for_next_time(self):
        import outbox_send as O
        self.put("a.json", "{}")
        self.put("b.json", "{}")
        open(os.path.join(self.d, "outbox", "sent.txt"), "w").write("# sent\n")

        def send(n, m):
            if n == "a.json":
                raise ValueError("boom")
            return 200
        self.assertEqual(O.run(self.d, send), ["a.json"])
        self.assertIn("b.json", self.sent())

    def test_an_emptied_list_does_not_flood_the_phone(self):
        import outbox_send as O
        self.put("a.json", "{}")
        open(os.path.join(self.d, "outbox", "sent.txt"), "w").write("")
        got = []
        O.run(self.d, lambda n, m: got.append(n) or 200)
        self.assertEqual(got, [])
        self.assertIn("a.json", self.sent())


class RollbackChoice(unittest.TestCase):
    # newest first; the signature stands for the content of the app and engine at that release
    SIG = {"r4": "D", "r3": "C", "r2": "B", "r1": "A"}

    def pick(self, head, bad=()):
        import release_pick as R
        return R.pick(["r4", "r3", "r2", "r1"], head, self.SIG.get, set(bad))

    def test_goes_to_the_release_before_the_live_one(self):
        self.assertEqual(self.pick("D"), ("r3", "r4"))

    def test_an_untested_live_version_goes_to_the_newest_release(self):
        self.assertEqual(self.pick("X"), ("r4", None))

    def test_a_second_press_goes_one_further_back(self):
        self.assertEqual(self.pick("C", bad=["r4"]), ("r2", "r3"))

    def test_a_release_rolled_back_from_is_never_chosen_again(self):
        self.assertEqual(self.pick("X", bad=["r4"]), ("r3", None))

    def test_nothing_to_go_back_to(self):
        import release_pick as R
        self.assertEqual(R.pick(["r1"], "A", {"r1": "A"}.get, set()), (None, "r1"))

    def test_workflows_survive_a_release_without_the_money_tests(self):
        for f, path in (("tests.yml", "tests/test_money.py"), ("engine.yml", "_code/tests/test_money.py")):
            text = open(os.path.join(HERE, "..", ".github", "workflows", f), encoding="utf-8").read()
            self.assertIn("[ ! -f %s ] ||" % path, text)


class UnknownChecks(unittest.TestCase):
    # Ben, 24 Nov 2026: missing data must not count against a share. The pass mark follows the checks we can actually read.
    def test_pass_marks_by_known_checks(self):
        import strategy as S
        self.assertEqual([S.pass_mark_for(k) for k in (7, 6, 5)], [5, 5, 4])

    def test_too_few_known_checks_never_qualify(self):
        import strategy as S
        self.assertIsNone(S.pass_mark_for(4))

    def rising(self):
        return [100.0 * (1.001 ** i) for i in range(300)]

    def test_no_insider_trades_is_unknown_not_a_fail(self):
        import strategy as S
        r = S.score_checks(20.0, 150.0, 0.2, self.rising(), 0.05, {"open_market_buys_90d": 0, "open_market_sales_90d": 0}, None, None)
        c = [x for x in r["checks"] if x["id"] == "insiders"][0]
        self.assertIsNone(c["pass"])

    def test_insider_selling_is_still_a_fail(self):
        import strategy as S
        r = S.score_checks(20.0, 150.0, 0.2, self.rising(), 0.05, {"open_market_buys_90d": 0, "open_market_sales_90d": 2, "sale_value_90d": 5000.0}, None, None)
        self.assertIs([x for x in r["checks"] if x["id"] == "insiders"][0]["pass"], False)

    def test_a_share_with_four_of_five_known_qualifies(self):
        import strategy as S
        kh = [{"recent_activity": "Add 5%"}, {"recent_activity": ""}]
        r = S.score_checks(None, None, 0.2, self.rising(), 0.05, {"open_market_buys_90d": 0, "open_market_sales_90d": 0}, kh, {"surprise_pct": -1.0, "move_5d": 0.01})
        self.assertEqual((r["known"], r["score"], r["pass_mark"], r["qualifies"]), (5, 4, 4, True))

    def test_a_share_without_its_trend_never_qualifies(self):
        import strategy as S
        px = [200.0 - 0.3 * i for i in range(300)]
        kh = [{"recent_activity": "Add"}, {"recent_activity": "Add"}]
        r = S.score_checks(20.0, 150.0, 0.2, px, -0.9, {"open_market_buys_90d": 1, "buy_value_90d": 10.0}, kh, {"surprise_pct": 1.0, "move_5d": 0.01})
        self.assertFalse(r["qualifies"])


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
