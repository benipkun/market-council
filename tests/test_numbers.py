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

import decide as D  # noqa: E402
import forecast as F  # noqa: E402
import health as H  # noqa: E402
import lab as L  # noqa: E402
import quant as Q  # noqa: E402
import strategy as S  # noqa: E402
import track as T  # noqa: E402

UTC = datetime.timezone.utc


class Fees(unittest.TestCase):
    def test_broker_fee(self):
        # 0.25% of the order, at least 1.12 dollars
        self.assertAlmostEqual(D.fee(100.0), 1.12, places=6)
        self.assertAlmostEqual(D.fee(1000.0), 2.50, places=6)
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
