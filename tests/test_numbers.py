# Tests for the engine's key numbers. They run on every change and before every engine run; the engine does not run
# if one fails. Every input here is made up and every expected figure can be checked by hand or against a textbook:
# nothing is read from the network or from the private records.
import datetime
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ops", "engine"))
sys.path.insert(0, os.path.join(HERE, "..", "ops"))
os.environ.setdefault("MC_QUICK", "1")

import numpy as np  # noqa: E402

import actions as A  # noqa: E402
import decide as D  # noqa: E402
import forecast as F  # noqa: E402
import health as H  # noqa: E402
import lab as L  # noqa: E402
import partners as P  # noqa: E402
import plans as PL  # noqa: E402
import keeper as K  # noqa: E402
import answer as ANS  # noqa: E402
import quant as Q  # noqa: E402
import strategy as S  # noqa: E402
import track as T  # noqa: E402

UTC = datetime.timezone.utc


class Fees(unittest.TestCase):
    def test_broker_fee(self):
        # Ben's Revolut plan: about 2 cents a trade, whatever the size (23 Oct 2026)
        self.assertAlmostEqual(D.fee(100.0), 0.02, places=6)
        self.assertAlmostEqual(D.fee(1000.0), 0.02, places=6)
        self.assertEqual(D.fee(0.0), 0.0)

    def test_price_age(self):
        self.assertEqual(D.age_days("2026-10-05", "2026-10-12T08:00:00Z"), 7)
        self.assertTrue(D.stale("2026-10-05", "2026-10-12T08:00:00Z"))
        self.assertFalse(D.stale("2026-10-09", "2026-10-12T08:00:00Z"))      # a weekend is not stale


class Options(unittest.TestCase):
    def test_black_scholes_textbook(self):
        # the standard example: price 100, strike 100, one year, 5% interest, 20% volatility
        self.assertAlmostEqual(Q.bs(100, 100, 1.0, 0.05, 0.20, True), 10.4506, places=3)
        self.assertAlmostEqual(Q.bs(100, 100, 1.0, 0.05, 0.20, False), 5.5735, places=3)

    def test_put_call_parity(self):
        c, p = Q.bs(72, 80, 0.5, 0.04, 0.35, True), Q.bs(72, 80, 0.5, 0.04, 0.35, False)
        self.assertAlmostEqual(c - p, 72 - 80 * math.exp(-0.04 * 0.5), places=8)

    def test_three_methods_agree(self):
        ref = Q.bs(100, 105, 0.75, 0.03, 0.30, True)
        self.assertAlmostEqual(Q.binom(100, 105, 0.75, 0.03, 0.30, True, 200, False), ref, delta=0.05)
        self.assertAlmostEqual(Q.binom(100, 105, 0.75, 0.03, 0.30, True, 200, True), ref, delta=0.05)   # no dividend: early exercise adds nothing
        mc, se = Q.mc_opt(100, 105, 0.75, 0.03, 0.30, True, np.random.default_rng(7))
        self.assertLess(abs(mc - ref), 4 * se + 1e-9)

    def test_american_put_is_worth_at_least_the_european(self):
        self.assertGreaterEqual(Q.binom(100, 110, 1.0, 0.05, 0.25, False, 200, True) + 1e-9, Q.binom(100, 110, 1.0, 0.05, 0.25, False, 200, False))

    def test_implied_volatility_round_trip(self):
        price = Q.bs(100, 95, 0.4, 0.04, 0.27, False)
        self.assertAlmostEqual(Q.implied(price, 100, 95, 0.4, 0.04, False), 0.27, places=4)

    def test_greeks_textbook(self):
        g = Q.greeks(100, 100, 1.0, 0.05, 0.20, True)
        self.assertAlmostEqual(g["delta"], 0.6368, places=3)
        self.assertAlmostEqual(g["vega"], 0.3752, places=3)       # per one point of volatility


class Ranges(unittest.TestCase):
    def setUp(self):
        self.r = np.tile([0.01, -0.01], 1260)                    # ten years of +1% / -1% days

    def test_same_seed_same_figures(self):
        a, va = Q.sim_ranges(self.r, 0.10, np.random.default_rng(Q.SEED))
        b, vb = Q.sim_ranges(self.r, 0.10, np.random.default_rng(Q.SEED))
        self.assertEqual(a, b)
        self.assertAlmostEqual(va, 0.01 * math.sqrt(2520 / 2519.0) * math.sqrt(252), places=4)

    def test_ranges_are_ordered_and_centred(self):
        out, vol = Q.sim_ranges(self.r, 0.10, np.random.default_rng(Q.SEED))
        for kind in ("boot", "bell"):
            y = out[kind]["1y"]
            self.assertLess(y["lo"], y["med"])
            self.assertLess(y["med"], y["hi"])
            self.assertAlmostEqual(y["med"], math.exp(0.10 - vol * vol / 2) - 1, delta=0.03)   # median of a 10%-a-year drift

    def test_first_touch(self):
        paths = np.array([[1.0, 2.0, 3.0], [1.0, 0.5, 3.0], [1.0, 1.0, 1.0]])
        ft = Q.first_touch(paths, 3.0, 0.5)
        self.assertAlmostEqual(ft["target_first"], 1 / 3, places=3)
        self.assertAlmostEqual(ft["stop_first"], 1 / 3, places=3)
        self.assertAlmostEqual(ft["neither"], 1 / 3, places=3)


class BackTestFigures(unittest.TestCase):
    def test_steady_growth(self):
        eq = 1.0004 ** np.arange(1, 505)                         # two years at 0.04% a day
        s = L.stats(eq)
        self.assertAlmostEqual(s["cagr"], 1.0004 ** 252 - 1, places=3)
        self.assertAlmostEqual(s["mdd"], 0.0, places=6)
        self.assertAlmostEqual(s["vol"], 0.0, places=4)

    def test_worst_fall(self):
        s = L.stats(np.array([1.10, 0.99, 1.21]))
        self.assertAlmostEqual(s["total"], 0.21, places=4)
        self.assertAlmostEqual(s["mdd"], 0.99 / 1.10 - 1, places=4)


class Scorecard(unittest.TestCase):
    def checks(self, **kw):
        px = np.linspace(50.0, 100.0, 300)
        a = dict(mos=0.10, fair=110.0, em=0.20, px=px, spy_mom=0.05,
                 ins={"open_market_buys_90d": 1, "buy_value_90d": 1000.0, "sale_value_90d": 0.0, "open_market_sales_90d": 0},
                 kh=[{"recent_activity": "Add 5%"}, {"recent_activity": "Reduce"}], rv={"surprise_pct": 4.0, "move_5d": 0.02})
        a.update(kw)
        res = S.score_checks(a["mos"], a["fair"], a["em"], a["px"], a["spy_mom"], a["ins"], a["kh"], a["rv"], None, None, a.get("dropped"), a.get("fair_rng"))
        self.last = res
        return dict((c["id"], c["pass"]) for c in res["checks"])

    def test_all_seven_pass(self):
        c = self.checks()
        self.assertEqual(sorted(c), ["drift", "holders", "insiders", "momentum", "quality", "trend", "value"])
        self.assertTrue(all(v is True for v in c.values()), c)

    def test_each_line(self):
        self.assertFalse(self.checks(mos=-0.01)["value"])                     # price above fair value
        self.assertFalse(self.checks(em=0.079)["quality"])                    # margin under 8%
        self.assertTrue(self.checks(em=0.08)["quality"])
        self.assertFalse(self.checks(spy_mom=5.0)["momentum"])                # the fund did better
        self.assertFalse(self.checks(px=np.linspace(100.0, 50.0, 300))["trend"])
        self.assertFalse(self.checks(ins={"open_market_buys_90d": 0, "buy_value_90d": 0, "sale_value_90d": 5.0})["insiders"])
        self.assertFalse(self.checks(kh=[{"recent_activity": "Add"}])["holders"])     # one holder is not enough
        self.assertFalse(self.checks(rv={"surprise_pct": 4.0, "move_5d": -0.01})["drift"])
        self.assertIsNone(self.checks(em=None)["quality"])                    # no data is not a pass


    def test_fair_value_is_a_range(self):
        key = "the operating margin"
        self.assertIsNone(self.checks(fair_rng={"low": 90.0, "high": 120.0, "most_sensitive": key})["value"])   # price 100 is inside: unclear, not a pass
        self.assertEqual(self.last["score"], 6)
        self.assertTrue(self.checks(fair_rng={"low": 105.0, "high": 140.0, "most_sensitive": key})["value"])    # under even the lowest estimate
        self.assertFalse(self.checks(fair_rng={"low": 60.0, "high": 95.0, "most_sensitive": key})["value"])     # above even the highest


class PriceCrossCheck(unittest.TestCase):
    A = [("2026-10-07", 50.0), ("2026-10-08", 51.0), ("2026-10-09", 52.0)]

    def test_agree(self):
        r = D.compare_series(self.A, [("2026-10-08", 51.0), ("2026-10-09", 52.3)], "2026-10-12")
        self.assertIs(r["ok"], True)
        self.assertEqual(r["day"], "2026-10-09")

    def test_disagree(self):
        r = D.compare_series(self.A, [("2026-10-09", 55.0)], "2026-10-12")
        self.assertIs(r["ok"], False)
        self.assertIn("disagree", r["why"])

    def test_series_a_day_behind(self):
        r = D.compare_series(self.A[:2], [("2026-10-08", 51.0), ("2026-10-09", 52.0)], "2026-10-12")
        self.assertIs(r["ok"], False)
        self.assertIn("stops at 2026-10-08", r["why"])

    def test_unfinished_day_is_ignored(self):
        r = D.compare_series(self.A, [("2026-10-09", 52.0), ("2026-10-12", 60.0)], "2026-10-12")
        self.assertIs(r["ok"], True)

    def test_one_source_is_not_a_pass(self):
        self.assertIsNone(D.compare_series(self.A, [], "2026-10-12")["ok"])

    def test_cut_moves_after_the_close(self):
        self.assertEqual(D.price_cut("2026-10-12T15:00:00Z"), "2026-10-12")   # 11:00 in New York: today's bar is unfinished
        self.assertEqual(D.price_cut("2026-10-12T21:40:00Z"), "2026-10-13")   # after the close: today's bar counts


class Health(unittest.TestCase):
    def at(self, s):
        return datetime.datetime.fromisoformat(s).replace(tzinfo=UTC)

    def test_last_due(self):
        times = ("06:40", "13:40", "21:40")
        self.assertEqual(H.last_due(times, 5, self.at("2026-10-12T12:00:00")), self.at("2026-10-12T06:40:00"))
        self.assertEqual(H.last_due(times, 5, self.at("2026-10-12T08:00:00")), self.at("2026-10-09T21:40:00"))   # Monday morning looks back to Friday

    def test_weekday_hours_skip_the_weekend(self):
        self.assertAlmostEqual(H.weekday_hours(self.at("2026-10-09T22:00:00"), self.at("2026-10-12T06:00:00")), 8.0)

    def test_skipped_run_is_late(self):
        job = H.JOBS[0]
        runs = [{"status": "completed", "conclusion": "success", "created_at": "2026-10-12T06:00:00Z"}]      # ran before it was due, then skipped 06:40
        self.assertTrue(H.judge_job(job, runs, self.at("2026-10-12T12:00:00"))["late"])
        runs = [{"status": "completed", "conclusion": "success", "created_at": "2026-10-12T07:55:00Z"}]      # started late, inside the grace period
        self.assertFalse(H.judge_job(job, runs, self.at("2026-10-12T12:00:00"))["late"])

    def test_stale_data_and_one_message(self):
        now = self.at("2026-10-13T12:00:00")
        good = dict((j["id"], [{"status": "completed", "conclusion": "success", "created_at": "2026-10-13T11:30:00Z"}]) for j in H.JOBS)
        dates = dict((d["id"], "2026-10-13T11:00:00Z") for d in H.DATA)
        out, send, over = H.assess(good, dates, {}, None, {}, now)
        self.assertTrue(out["ok"])
        self.assertEqual(send, [])
        dates["quant"] = "2026-10-12T12:00:00Z"                                # engine results a full weekday old
        out, send, over = H.assess(good, dates, {}, None, {}, now)
        self.assertEqual([p["key"] for p in out["problems"]], ["data:quant:stale"])
        self.assertEqual(len(send), 1)
        told = {"alerts": {"data:quant:stale": {"first": "2026-10-13T12:00:00Z", "last_sent": "2026-10-13T12:00:00Z"}}, "problems": out["problems"]}
        out2, send2, over2 = H.assess(good, dates, {}, None, told, self.at("2026-10-13T12:30:00"))
        self.assertEqual(send2, [])                                            # no second message half an hour later
        dates["quant"] = "2026-10-13T12:20:00Z"
        out3, send3, over3 = H.assess(good, dates, {}, None, told, self.at("2026-10-13T12:30:00"))
        self.assertEqual(over3, ["data:quant:stale"])                          # and one message when it clears
        self.assertEqual(send3[0]["title"], "Market Council: back to normal")


class Forecasts(unittest.TestCase):
    def test_words(self):
        self.assertEqual(F.words(0.62), "about 3 in 5")
        self.assertEqual(F.words(0.50), "about 1 in 2")
        self.assertEqual(F.words(0.67), "about 2 in 3")

    def test_range_covers_every_source(self):
        f = F.combine(0.60, 0.64, 400, 100, 0.62)
        self.assertAlmostEqual(f["p"], 0.62, places=3)
        self.assertFalse(f["disagree"])
        self.assertLessEqual(f["lo"], 0.60)
        self.assertGreaterEqual(f["hi"], 0.64)

    def test_disagreement_widens_the_range(self):
        g = F.combine(0.30, 0.60, 400, 100, None)
        self.assertTrue(g["disagree"])
        self.assertLess(g["lo"], 0.30)
        self.assertGreater(g["hi"], 0.60)

    def test_no_extreme_figure_without_cases(self):
        f = F.combine(0.97, 0.99, 5, 5, None)                 # five cases: the base rate is shown but not counted
        self.assertEqual(f["p"], 0.9)
        self.assertTrue(f["capped"] and f["few"])
        g = F.combine(0.97, 0.95, 500, 120, None)             # with the evidence, an extreme figure may stand
        self.assertAlmostEqual(g["p"], 0.96, places=3)
        self.assertFalse(g["capped"])

    def test_which_level_first(self):
        P = np.array([[1.05, 1.12, 0.80], [0.95, 0.88, 1.20], [1.00, 1.00, 1.00]])
        a, b = F.touch_first(P, 1.10, 0.90)
        self.assertEqual(a.tolist(), [True, False, False])
        self.assertEqual(b.tolist(), [False, True, False])

    def test_log_is_weekly_and_cannot_be_edited_unnoticed(self):
        entries, idx = [], {"2026-10-09": 100, "2026-10-12": 101, "2026-10-19": 106}
        f = {"t": "AAA", "kind": "up", "h": "3m", "d": 63, "due": "2027-01-08", "q": "?", "p": 0.6, "lo": 0.5, "hi": 0.7, "plain": 0.55, "ref": 50.0, "move": 0.08}
        self.assertEqual(F.append_log(entries, [f], "2026-10-09", idx), 1)
        self.assertEqual(F.append_log(entries, [f], "2026-10-12", idx), 0)                  # the same week: nothing new
        self.assertEqual(F.append_log(entries, [dict(f, ref=56.0)], "2026-10-12", idx), 1)  # unless the price moved a lot
        self.assertEqual(F.append_log(entries, [f], "2026-10-19", idx), 1)                  # and again a week later
        self.assertTrue(F.chain_ok(entries))
        entries[0]["p"] = 0.9
        self.assertFalse(F.chain_ok(entries))

    def test_marked_right_or_wrong_by_code(self):
        by = {"AAA": {"t": "AAA", "x": np.array([50.0, 51.0, 44.0, 52.0, 53.0]), "a": 0, "b": 5}}
        ctx = {"idx": {"d0": 0}, "spy": np.array([100.0, 100.0, 100.0, 100.0, 101.0])}
        e = {"made": "d0", "t": "AAA", "d": 4}
        self.assertEqual(F.score_entry(dict(e, kind="up"), by, ctx), 1)
        self.assertEqual(F.score_entry(dict(e, kind="fall10"), by, ctx), 1)
        self.assertEqual(F.score_entry(dict(e, kind="fall25"), by, ctx), 0)
        self.assertEqual(F.score_entry(dict(e, kind="beat"), by, ctx), 1)
        self.assertEqual(F.score_entry(dict(e, kind="stop_first", up=1.05, dn=0.90), by, ctx), 1)
        late = dict(e, d=10)                                                             # its date has not come yet
        self.assertIsNone(F.score_entry(dict(late, kind="up"), by, ctx))
        self.assertEqual(F.score_entry(dict(late, kind="fall10"), by, ctx), 1)           # a fall counts the day it happens
        self.assertIsNone(F.score_entry(dict(late, kind="fall25"), by, ctx))

    def test_score_table(self):
        P, O = [0.7] * 40 + [0.3] * 40, [1] * 28 + [0] * 12 + [1] * 12 + [0] * 28
        s = F.summarise(P, O, [0.5] * 80)
        self.assertAlmostEqual(s["brier"], 0.21, places=4)
        self.assertTrue(s["beats_fifty"])
        row = [b for b in s["bands"] if abs(b["band"] - 0.7) < 1e-9][0]
        self.assertEqual((row["n"], row["happened"]), (40, 0.7))
        self.assertAlmostEqual(s["adjust"]["0.7"], 0.0, places=6)
        self.assertTrue(F.summarise([0.7] * 10, [1] * 10, [0.5] * 10)["verdict"].startswith("Too early"))

    def test_setups_use_only_the_past(self):
        x = np.linspace(50.0, 100.0, 400)
        c = F.cells_for(x)
        self.assertEqual(int(c[100]), -1)                    # not enough history yet that day
        self.assertEqual(int(c[-1]), 6 + 3 + 0)              # above its average, up over three months, calm
        x2 = x.copy()
        x2[-1] = 1.0                                         # change the last day only
        self.assertEqual(F.cells_for(x2)[:-1].tolist(), c[:-1].tolist())


class PortfolioFirst(unittest.TestCase):
    def test_spreading_money_shrinks_the_bad_year(self):
        rng = np.random.default_rng(1)
        a, b = rng.normal(0, 0.03, 600), rng.normal(0, 0.03, 600)
        rets, mus = {"A": a, "B": b}, {"A": 0.08, "B": 0.08}
        one, two = D.bad_year({"A": 1.0}, rets, mus), D.bad_year({"A": 0.5, "B": 0.5}, rets, mus)
        self.assertLess(one, two)                                        # one share alone has the worse bad year
        self.assertLess(one, -0.2)
        self.assertEqual(one, D.bad_year({"A": 1.0}, rets, mus))         # the same draws every time
        self.assertIsNone(D.bad_year({"A": 1.0}, {"A": a[:100]}, mus))   # too little history: no figure


class PartnersStatement(unittest.TestCase):
    def test_same_money_in_the_index_fund(self):
        days = [{"date": "2026-09-16", "nav": 1000.0}, {"date": "2026-10-12", "nav": 900.0}]
        spy = [("2026-09-16", 100.0), ("2026-09-28", 110.0), ("2026-10-12", 120.0)]
        a = P.index_alternative(days, [("2026-09-28", -110.0)], spy, 900.0)
        self.assertAlmostEqual(a["result"], 10.0, places=2)             # 900 now, 1,000 at the start, 110 taken out
        self.assertAlmostEqual(a["index_now"], 1077.0, places=2)        # 9.975 units bought, 1 sold at 110, 8.975 left at 120
        self.assertAlmostEqual(a["index_result"], 187.0, places=2)
        self.assertAlmostEqual(a["ahead_of_index"], -177.0, places=2)

    def test_a_withdrawal_is_not_a_loss(self):
        days = [{"date": "d1", "nav": 1000.0}, {"date": "d2", "nav": 890.0}, {"date": "d3", "nav": 801.0}]
        self.assertAlmostEqual(P.drawdown(days, [("d2", -110.0)]), -0.10, places=4)

    def test_only_applied_payments_count(self):
        ledger = {"entries": [{"action": "withdraw", "usd": 95, "status": "applied", "at": "2026-09-28T02:00:37Z"}, {"action": "deposit", "usd": 50, "status": "test", "at": "2026-09-29T00:00:00Z"},
                              {"action": "buy", "usd": 95, "status": "applied", "at": "2026-09-25T12:08:36Z"}]}
        self.assertEqual(P.money_flows(ledger), [("2026-09-28", -95.0)])

    def test_an_undone_payment_is_not_counted(self):
        ledger = {"entries": [{"id": "a", "action": "deposit", "usd": 365.0, "status": "applied", "at": "2026-10-13T09:35:01Z", "undone_by": "u"},
                              {"id": "b", "action": "deposit", "usd": 364.75, "status": "applied", "at": "2026-10-13T22:51:43Z"}]}
        self.assertEqual(P.money_flows(ledger), [("2026-10-13", 364.75)])
        self.assertEqual([(p["id"], p["counted"]) for p in P.payments(ledger)], [("a", False), ("b", True)])

    def test_the_record_at_the_limit(self):
        # $700 of a $1,000 portfolio in one share, limit 30%: $400 moves into the index fund, which rose 10% while the share fell 10%
        days = [{"date": "d1", "nav": 1000.0, "pos": {"AAA": 700.0}}]
        closes = {"SPY": [("d1", 100.0), ("d2", 110.0)], "AAA": [("d1", 50.0), ("d2", 45.0)]}
        r = P.at_cap(days, 0.3, lambda t: closes.get(t, []))
        self.assertAlmostEqual(r["difference"], 400 * 0.2 - 2 * 0.0025 * 400, places=2)


class TrackRecord(unittest.TestCase):
    def test_every_idea_is_logged_once_at_that_days_close(self):
        cards = [{"id": "I1", "kind": "idea", "ticker": "AAA", "created": "2026-10-09T10:00:00Z", "key": "SCORE:AAA", "greyed": True,
                  "checks": [{"id": "trend", "pass": True}, {"id": "value", "pass": False}]},
                 {"id": "T1", "kind": "test"}, {"id": "I2", "kind": "idea", "ticker": None}]

        def cache(t):
            return [("2026-10-08", 49.0), ("2026-10-09", 50.0), ("2026-10-12", 55.0)]
        entries, added, ok = T.log_cards(cards, cache, "2026-10-12T08:00:00Z", [])
        self.assertEqual((added, ok), (1, True))                               # the greyed idea is logged too; the test card is not an idea
        e = entries[0]
        self.assertEqual((e["day"], e["price"], e["offered"], e["late"], e["source"], e["score"]), ("2026-10-09", 50.0, False, True, "SCORE", 1))
        entries, added, ok = T.log_cards(cards, cache, "2026-10-13T08:00:00Z", entries)
        self.assertEqual(added, 0)                                             # never a second time
        entries[0]["price"] = 40.0                                             # an edit afterwards is detected
        self.assertFalse(T.chain_ok(entries))

    def test_measured_against_the_index_and_the_list_after_fees(self):
        cal = ["d%02d" % k for k in range(30)]

        def share(t, v):
            return {"t": t, "x": np.array(v, dtype=float), "a": 0, "b": 30, "listed": True}
        ctx = {"cal": cal, "idx": dict((d, k) for k, d in enumerate(cal)), "spy": np.array([100 + 0.5 * k for k in range(30)]), "n": 30}
        rows = T.measure([{"id": "I1", "t": "AAA", "day": "d00", "price": 100.0, "offered": True, "checks": {"trend": True}}],
                         [share("AAA", [100.0 + k for k in range(30)]), share("BBB", [100.0] * 30)], ctx)
        m = rows[0]["m"]["1m"]
        self.assertAlmostEqual(m["idea"], 0.21 - 0.005, places=4)              # up 21%, less half a percent of fees
        self.assertAlmostEqual(m["spy"], 0.105 - 0.005, places=4)
        self.assertAlmostEqual(m["list"], (0.205 - 0.005) / 2, places=4)       # the average of the two shares on the list
        self.assertAlmostEqual(m["beat"], 0.5, places=3)
        self.assertNotIn("3m", rows[0]["m"])                                   # that mark has not been reached

    def test_a_dropped_check_stops_counting(self):
        sc = Scorecard()
        c = sc.checks(dropped={"value": {"on": "2027-06-01"}})
        self.assertIsNone(c["value"])
        self.assertEqual((sc.last["of"], sc.last["pass_mark"], sc.last["score"]), (6, 5, 6))
        self.assertTrue(sc.last["qualifies"])

    def test_drop_rule_needs_thirty_ideas_at_both_marks(self):
        def row(v3, v6):
            m = {}
            if v3 is not None:
                m["3m"] = {"idea": v3, "spy": 0.02, "list": 0.03}
            if v6 is not None:
                m["6m"] = {"idea": v6, "spy": 0.04, "list": 0.05}
            return {"checks": {"trend": True}, "m": m}
        few = [row(-0.05, -0.05)] * 29
        self.assertEqual(T.judge_checks(few, {}, "2027-06-01")[2], {})         # 29 losing ideas: not yet
        many = [row(-0.05, -0.05)] * 30
        out, proven, new = T.judge_checks(many, {}, "2027-06-01")
        self.assertEqual(list(new), ["trend"])
        self.assertEqual(out["trend"]["state"], "dropped")
        good = [row(0.10, 0.12)] * 30
        self.assertEqual(T.judge_checks(good, {}, "2027-06-01")[1], ["trend"])  # and proven the other way round


class Actions(unittest.TestCase):
    # a made-up book: a kept holding, a weak holding and one open idea paid for by selling the weak one
    def ctx(self, **kw):
        snap = {"positions": [{"ticker": "KEEP", "qty": 10, "last_price": 70.0, "market_value": 700.0, "cost_basis": 750.0},
                              {"ticker": "OLD", "qty": 10, "last_price": 20.0, "market_value": 200.0, "cost_basis": 120.0}]}
        card = {"kind": "idea", "status": "open", "ticker": "NEW", "id": "I1", "key": "SCORE:NEW", "entry": 100.0, "cost": {"limit": 100.0}, "stop": 92.0, "take_profit": 116.0,
                "profile_size": 150.0, "funding": {"kind": "paired_sale", "sell": "OLD", "why": "OLD passes 0 of 7 checks."},
                "checks": [{"id": "quality", "pass": True}, {"id": "trend", "pass": True}, {"id": "value", "pass": False}]}
        fct = {"NEW": {"h": {"by": {"due": "2026-11-20", "f": {"tp_first": {"p": 0.5, "cases": 900}, "stop_first": {"p": 0.3}}}, "1m": {"f": {"beat": {"p": 0.55}}}}},
               "OLD": {"h": {"1m": {"f": {"beat": {"p": 0.40}}}}}}
        c = {"cards": [card], "fct": fct, "track": {"count": 32, "checks": {"quality": {"state": "unproven"}, "trend": {"state": "proven"}}},
             "hold": A.holding_map(snap), "nav": 1200.0, "cash": 300.0, "limits": {"stock_cap": 0.3, "min_cash": 0.03},
             "keeps": {"KEEP": {"target": 80.0, "by": "2027-10-05", "chance_touch": 0.79}}, "holds": {}, "pf": {}, "fx": 330.0, "stale": [],
             "free_cash": 264.0, "monthly_huf": 120000.0, "monthly_usd": 363.64, "spy": 50.0, "today": datetime.date(2026, 10, 14), "index_mu": 0.0861}
        c.update(kw)
        return c

    def test_swap_with_its_numbers(self):
        acts, _ = A.today(self.ctx())
        a = acts[0]
        self.assertEqual((a["type"], a["sell"]["ticker"], a["buy"]["ticker"]), ("SWAP", "OLD", "NEW"))
        self.assertAlmostEqual(a["sell"]["proceeds"], 198.88, places=2)         # 10 x $20 less the $1.12 minimum fee
        self.assertAlmostEqual(a["sell"]["tax"], 11.83, places=2)               # 15% of the $78.88 gain over the $120 cost
        self.assertEqual(a["buy"]["shares"], 1.0)                               # the idea is capped at $150, so one $100 share
        self.assertAlmostEqual(a["expected_usd"], 3.36, places=2)               # 100 x (0.5 x 16% - 0.3 x 8%) - 2 x $1.12
        self.assertAlmostEqual(a["net_cash"], 97.76, places=2)                  # 198.88 - 100 - 1.12
        self.assertEqual(a["evidence"]["label"], "unproven")                    # one of its two passed checks has no record yet
        self.assertEqual([x["type"] for x in acts[1:]], ["HOLD"])               # the kept holding comes last, as a hold

    def test_a_kept_holding_is_never_offered_for_sale(self):
        a = A.should_sell("keep", self.ctx())[0]
        self.assertEqual((a["type"], a.get("decision")), ("HOLD", True))
        self.assertIn("your decision", a["line"])

    def test_new_money_goes_to_the_idea_then_the_index_fund(self):
        acts = A.plan_amount(100000 / 330.0, self.ctx())                       # $303.03
        self.assertEqual([(x["type"], x.get("ticker")) for x in acts], [("BUY", "NEW"), ("BUY", "SPY"), ("HOLD", None)])
        self.assertEqual(acts[1]["shares"], 4.0)                                # $200.79 after the fee buys four $50 shares

    def test_an_idea_that_makes_money_but_trails_the_index_is_a_labelled_buy(self):
        # a year-long plan: 40% take-profit (+16%) first, 30% stop (-8%) first gives +4.0%, below the index fund's 8.61%
        c = self.ctx()
        c["fct"]["NEW"]["h"]["by"]["due"] = "2027-10-14"
        c["fct"]["NEW"]["h"]["by"]["f"]["tp_first"]["p"] = 0.4
        acts, cands = A.today(c)
        self.assertEqual((acts[0]["type"], acts[0]["ticker"], acts[0]["tier"]), ("BUY", "NEW", 2))   # not a swap: no 1-year forecast shows it clearly better than OLD
        self.assertIn("trails the index fund", acts[0]["flags"])
        self.assertAlmostEqual(acts[0]["expected_usd"], 1.76, places=2)                            # 100 x 4% - 2 x $1.12
        c["fct"]["NEW"]["h"]["by"]["f"]["tp_first"]["p"] = 0.1                                       # 1.6% - 2.4%: loses money
        acts, cands = A.today(c)
        self.assertEqual((acts[0]["type"], acts[0]["ticker"]), ("HOLD", None))

    def year_ctx(self, **kw):
        # NEW trails the index fund (tier 2); in a year the Forecaster's middle outcome is +8% for NEW and -10% for OLD
        c = self.ctx(**kw)
        c["fct"]["NEW"]["h"]["by"]["due"] = "2027-10-14"
        c["fct"]["NEW"]["h"]["by"]["f"]["tp_first"]["p"] = 0.4
        c["fct"]["NEW"].update(price=100.0)
        c["fct"]["NEW"]["h"]["1y"] = {"median": 108.0, "f": {"beat": {"p": 0.52}}}
        c["fct"]["OLD"].update(price=20.0)
        c["fct"]["OLD"]["h"]["1y"] = {"median": 18.0, "f": {"beat": {"p": 0.41}}}
        c["cards"][0]["funding"] = {}
        return c

    def test_sell_this_buy_this_instead_when_clearly_better(self):
        acts, _ = A.today(self.year_ctx())
        a = acts[0]
        self.assertEqual((a["type"], a["sell"]["ticker"], a["buy"]["ticker"], a["tier"]), ("SWAP", "OLD", "NEW", 2))
        self.assertIn("+8.0% for NEW against -10.0% for OLD", a["why_better"])
        self.assertGreaterEqual(a["margin"], A.SWAP_MARGIN)                     # 18 points less the switch costs
        self.assertEqual(A.should_sell("OLD", self.year_ctx())[0]["type"], "SWAP")   # the sell answer agrees with the list

    def test_a_share_you_just_bought_is_not_swapped_away(self):
        acts, _ = A.today(self.year_ctx(recent_buys={"OLD"}))
        self.assertEqual(acts[0]["type"], "BUY")
        self.assertIn("bought it in the last 30 days", A.should_sell("OLD", self.year_ctx(recent_buys={"OLD"}))[0]["line"])

    def test_the_written_answer_and_method(self):
        c = self.ctx()
        out = A.text(A.answer("What should I do with 100000 HUF now?", c))
        self.assertTrue(out.startswith("What to do with $303.03"))
        self.assertTrue(out.endswith(A.FOOT))
        self.assertIn("8.6% now", A.method_text(0.0861))
        self.assertIn("HOLD KEEP", A.text(A.answer("Should I sell KEEP?", c)))

    def test_the_cards_follow_the_action_list(self):
        c = self.ctx()
        v = A.verdicts_from(c)["SCORE:NEW"]
        self.assertEqual((v["buy"], v["type"], v["n"]), (True, "SWAP", 1))
        fresh = dict(c["cards"][0])
        fresh.pop("status")                                                   # the desk judges fresh ideas before they have a status
        self.assertIn("SCORE:NEW", A.verdicts_from(dict(c, cards=A.as_open([fresh]))))
        c["fct"]["NEW"]["h"]["by"]["due"] = "2027-10-14"
        c["fct"]["NEW"]["h"]["by"]["f"]["tp_first"]["p"] = 0.2                                       # +0.8% before fees: the fees take it
        v = A.verdicts_from(c)["SCORE:NEW"]
        self.assertFalse(v["buy"])
        self.assertIn("index fund", v["why"])

    def test_diversification_one_buy_per_sector_and_new_sectors_first(self):
        c = self.ctx(sector={"NEW": "Energy", "TWO": "Energy", "ALT": "Utilities", "KEEP": "Utilities"}, held_sectors=["Utilities"])
        two = dict(c["cards"][0], ticker="TWO", key="SCORE:TWO", id="I2", funding={})
        alt = dict(c["cards"][0], ticker="ALT", key="SCORE:ALT", id="I3", funding={})
        c["cards"] = [alt, c["cards"][0], two]
        c["fct"]["TWO"] = c["fct"]["NEW"]
        c["fct"]["ALT"] = c["fct"]["NEW"]
        c["free_cash"] = 1000.0
        acts, cands = A.today(c)
        bought = [a["ticker"] if a["type"] == "BUY" else a.get("buy", {}).get("ticker") for a in acts if a["type"] in ("BUY", "SWAP")]
        self.assertEqual(bought, ["NEW", "ALT"])                                # Energy is new, so it comes before Utilities; TWO is a second Energy idea
        self.assertIn("for diversification", next(x for x in cands if x["t"] == "TWO")["skip_reason"])
        self.assertIn("adds a new sector (Energy)", acts[0]["line"])

    def test_the_fee_follows_the_desk_setting(self):
        old = (A.FEE_PCT, A.FEE_MIN)
        try:
            A.FEE_PCT, A.FEE_MIN = 0.0, 0.02                                    # Ben's plan: about 2 cents a trade
            self.assertEqual(A.fee(150.0), 0.02)
        finally:
            A.FEE_PCT, A.FEE_MIN = old

    def test_stale_data_holds_every_buy_back(self):


        acts, _ = A.today(self.ctx(stale=["desk"]))
        self.assertEqual((acts[0]["type"], acts[0]["ticker"]), ("HOLD", None))
        self.assertIn("stale", acts[0]["line"])

    def test_questions_are_read_with_their_currency(self):
        c = self.ctx()
        self.assertAlmostEqual(A.parse("What should I do with 100,000 HUF now?", c)[1], 303.03, places=2)
        self.assertAlmostEqual(A.parse("100000 Ft", c)[1], 303.03, places=2)
        self.assertEqual(A.parse("What should I do with $500?", c), ("amount", 500.0))
        self.assertEqual(A.parse("Should I sell uber?", c), ("sell", "UBER"))
        self.assertEqual(A.parse("How much NEW should I buy?", c), ("buy", ("NEW", None, None)))
        self.assertEqual(A.parse("I am going to buy NEW at 152", c), ("buy", ("NEW", None, 152.0)))   # a price, not an amount

    def test_one_idea_at_the_limit_and_above_it(self):
        c = self.ctx()
        a = A.buy_one("NEW", None, c)[0]
        self.assertEqual((a["type"], a["shares"], a["pays_with"]), ("BUY", 1.0, "free cash"))      # $150 allowed, one $100 share
        b = A.buy_one("NEW", 400.0, c)[0]
        self.assertEqual(b["shares"], 4.0)                                                        # the numbers for the amount asked
        self.assertIn("above your limit", b["flags"])


class CardsFollowTrades(unittest.TestCase):
    def test_a_suggestion_you_bought_closes_and_is_not_raised_again(self):
        cards = [{"id": "I1", "key": "SCORE:AAA", "kind": "idea", "ticker": "AAA", "status": "open", "created": "2026-10-21T10:00:00Z", "expires": "2026-11-04"}]
        ledger = {"entries": [{"action": "buy", "ticker": "AAA", "usd": 133.43, "status": "applied", "at": "2026-10-27T03:15:01Z"}]}
        c = D.settle(cards, [], ledger, "2026-10-28T08:00:00Z")
        self.assertEqual(c[0]["status"], "done")
        self.assertIn("you bought AAA on 2026-10-27", c[0]["logged"])
        out = D.merge_cards(c, [{"key": "RULE:dip:AAA", "kind": "idea", "ticker": "AAA", "valid_days": 3}], "2026-10-29T08:00:00Z")
        self.assertEqual([x["status"] for x in out if x.get("ticker") == "AAA"], ["done"])        # no new AAA card


    def test_a_card_raised_after_you_bought_is_withdrawn(self):
        cards = [{"id": "I2", "key": "RULE:dip:BBB", "kind": "idea", "ticker": "BBB", "status": "open", "created": "2026-10-28T10:00:00Z", "expires": "2026-10-31"}]
        ledger = {"entries": [{"action": "buy", "ticker": "BBB", "usd": 198.03, "status": "applied", "at": "2026-10-23T09:00:00Z"}]}
        c = D.settle(cards, [], ledger, "2026-10-28T12:00:00Z")
        self.assertEqual(c[0]["status"], "withdrawn")
        out = D.merge_cards(c, [{"key": "SCORE:BBB", "kind": "idea", "ticker": "BBB", "valid_days": 3}], "2026-10-29T08:00:00Z", bought={"BBB"})
        self.assertFalse([x for x in out if x.get("ticker") == "BBB" and x["status"] == "open"])


    def test_a_new_buy_signal_for_a_share_you_bought_is_raised(self):
        cards = [{"id": "I3", "key": "SCORE:CCC", "kind": "idea", "ticker": "CCC", "status": "done", "created": "2026-10-20T10:00:00Z", "done_at": "2026-10-27T10:00:00Z", "expires": "2026-11-03"}]
        out = D.merge_cards(cards, [{"key": "RULE:dip:CCC", "kind": "idea", "ticker": "CCC", "valid_days": 3, "verdict": {"buy": True, "n": 1}}], "2026-10-29T08:00:00Z", bought={"CCC"})
        self.assertEqual([x["key"] for x in out if x["status"] == "open"], ["RULE:dip:CCC"])


class Answers(unittest.TestCase):
    FACTS = {"books": {"cash": 366.58, "positions": [{"ticker": "UBER", "weight": 0.5466, "price": 67.62}]}, "risk_profile": {"limits": {"stock_cap": 0.3}},
             "portfolio_forecast": {"1y": {"port_loss": 0.487, "port_max": 0.19}}, "question": ""}

    def test_a_direct_answer_with_real_numbers_passes(self):
        a = {"answer": "No, hold UBER.", "why": ["It is 55% of the portfolio against your 30% limit."], "would_change": "A price under the stop.", "evidence": "Model estimate."}
        self.assertEqual(ANS.check(a, self.FACTS), [])

    def test_hedging_banned_phrases_and_invented_numbers_fail(self):
        base = {"why": ["It is 55% of the portfolio."], "would_change": "x", "evidence": "y"}
        self.assertIn("the first sentence does not answer the question", ANS.check(dict(base, answer="It depends on your goals."), self.FACTS))
        self.assertIn("banned phrase: consider", ANS.check(dict(base, answer="No. Consider trimming."), self.FACTS))
        self.assertIn("numbers not in the data: 42", ANS.check(dict(base, answer="About 42%."), self.FACTS))

    def test_the_answer_comes_first(self):
        text = ANS.render({"answer": "No, hold.", "why": ["a", "b"], "would_change": "c", "evidence": "d"})
        self.assertTrue(text.startswith("No, hold."))
        self.assertLess(text.index("Why:"), text.index("What would change it:"))

    def test_code_answers_head_on(self):
        f = dict(self.FACTS, question="What's the chance my portfolio is down this year?")
        self.assertTrue(ANS.code_answer({"actions": []}, f)["answer"].startswith("About 49%"))
        kept = {"actions": [{"type": "HOLD", "ticker": "UBER", "decision": True, "review_by": "2027-10-05", "target": 80.0, "line": "HOLD UBER: your decision."}]}
        self.assertTrue(ANS.code_answer(kept, dict(self.FACTS, question="Should I sell UBER?"))["answer"].startswith("No, hold UBER"))


class Keeper(unittest.TestCase):
    def test_books_follow_the_latest_close_and_cash_is_untouched(self):
        snap = {"cash": 100.0, "positions": [{"ticker": "AAA", "qty": 2, "last_price": 50.0, "market_value": 100.0, "price_as_of": "2026-10-15T20:00:00Z"}]}
        changed = K.remark(snap, {"AAA": ("2026-10-21", 55.0)}, "2026-10-22T08:00:00Z")
        self.assertEqual(changed, ["AAA"])
        self.assertEqual((snap["positions"][0]["market_value"], snap["cash"], snap["nav"]), (110.0, 100.0, 210.0))
        self.assertEqual(K.remark(snap, {"AAA": ("2026-10-20", 60.0)}, "2026-10-22T09:00:00Z"), [])   # an older close never overwrites a newer price

    def test_a_waiting_question_is_answered_end_to_end(self):
        import json as _j
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        old = (K.ROOT, ANS.ROOT, A.ROOT)
        try:
            K.ROOT = ANS.ROOT = A.ROOT = d
            os.makedirs(os.path.join(d, "inbox", "queue"))
            os.makedirs(os.path.join(d, "treasury"))
            with open(os.path.join(d, "inbox", "queue", "20261001T000000Z-ab1.md"), "w") as f:
                f.write("ask: How much cash should I keep?" + chr(10))
            with open(os.path.join(d, "treasury", "snapshot.json"), "w") as f:
                _j.dump({"cash": 100.0, "nav": 1000.0, "positions": []}, f)
            K.asks("2026-10-01T01:00:00Z")
            with open(os.path.join(d, "state", "messages.json")) as f:
                m = _j.load(f)["messages"]
            self.assertEqual([x["from"] for x in m], ["ben", "council"])
            self.assertTrue(m[1]["text"].startswith("Keep at least $30.00 in cash"))
            self.assertFalse(os.path.exists(os.path.join(d, "inbox", "queue", "20261001T000000Z-ab1.md")))
        finally:
            K.ROOT, ANS.ROOT, A.ROOT = old
            shutil.rmtree(d)

    def test_the_command_line_of_a_queue_file(self):
        self.assertEqual(K.command("# note" + chr(10) + chr(10) + "ask: Good or bad?" + chr(10) + "why: x"), "ask: Good or bad?")


class Plans(unittest.TestCase):
    def setUp(self):
        self.vol = PL.daily_vol
        PL.daily_vol = lambda closes, n=20: 0.02                                # 2% normal daily movement

    def tearDown(self):
        PL.daily_vol = self.vol

    def test_the_stop_comes_from_normal_movement_or_a_close_low(self):
        flat = [("d%d" % i, 100.0) for i in range(30)]
        s, why = PL.stop_level(100.0, flat, "short")
        self.assertAlmostEqual(s, round(100 * (1 - 2 * 0.02 * math.sqrt(10)), 2), places=2)   # 87.35
        self.assertIn("normal daily movement", why)
        near = flat[:-3] + [("x", 86.0)] + flat[-2:]                          # a recent low close to that line
        s2, why2 = PL.stop_level(100.0, near, "short")
        self.assertAlmostEqual(s2, 85.14, places=2)                             # 1% under the low
        self.assertIn("lowest close", why2)

    def test_a_holding_plan_and_a_kept_one(self):
        p = {"ticker": "AAA", "qty": 10, "last_price": 50.0, "market_value": 500.0, "cost_basis": 450.0}
        x = PL.holding_plan(p, {}, None, "long", [("d", 50.0)] * 30, {}, 1000.0, None, datetime.date(2026, 10, 15))
        self.assertEqual(x["reward_risk"], 2.0)                                 # take-profit at twice the stop distance
        self.assertTrue(any(r.startswith("Stop-loss:") and "Stop order" in r for r in x["revolut"]))
        self.assertFalse(any(r.startswith("Buy:") for r in x["revolut"]))
        k = PL.holding_plan(p, {"levels": [{"name": "Maximum-loss line (30% below cost)", "price": 31.5}]}, {"target": 80.0, "by": "2027-10-05"}, "long",
                            [("d", 50.0)] * 30, {}, 1000.0, None, datetime.date(2026, 10, 15))
        self.assertEqual((k["stop"], k["take_profit"], k["until"], k["kept"]), (31.5, 80.0, "2027-10-05", True))
        capped = PL.holding_plan(p, {"levels": [{"name": "Maximum-loss line (30% below cost)", "price": 40.0}]}, None, "long", [("d", 50.0)] * 30, {}, 1000.0, None, datetime.date(2026, 10, 15))
        self.assertEqual(capped["stop"], 40.0)                                  # never past the maximum-loss line

    def test_the_trailing_rule(self):
        p = {"id": "H:AAA", "ticker": "AAA", "price": 56.0, "stop": 45.0, "take_profit": 70.0, "average_cost": 50.0, "initial_stop": 45.0,
             "kept": False, "until": None, "label": "long", "shares": 10, "forecast": None}
        ev = PL.watch([p], {}, {}, datetime.date(2026, 10, 15))
        self.assertEqual([e["type"] for e in ev], ["move"])                     # up by its first risk (5): stop to the entry
        self.assertEqual(p["stop_should_be"], 50.0)

    def test_the_stop_back_test_runs_on_prices(self):
        x = np.array([100 * 1.004 ** i * (1 + 0.002 * (-1) ** i) for i in range(700)])
        r = PL.backtest([{"x": x}])["rules"][0]
        self.assertEqual(r["id"], "short")
        self.assertAlmostEqual(r["take_profit_first"] + r["stop_first"] + r["time_limit"], 1.0, places=2)
        self.assertGreater(r["without_plan"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
