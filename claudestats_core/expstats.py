"""Cluster-robust statistics for comparing reply behaviour across experiments.

Sessions are the sampling units (replies within a session are correlated), so
standard errors come from per-session influence values (linearisation), not
from reply counts. This module is stdlib-only and must not import
claudestats_core.experiments (experiments imports this module).
"""
import math

Z95 = 1.959964

_EPS = 1e-12


def _centre_at(centre, s, default: float) -> float:
    """Linearisation point of stratum s: the estimate itself (default), one
    value for every stratum, or a per-stratum {stratum: value} dict."""
    if centre is None:
        return default
    if isinstance(centre, dict):
        return centre[s]
    return centre


def ratio_stat(units: list, weights: dict | None = None,
               centre=None) -> dict:
    """Ratio estimate sum(y)/sum(x) with a cluster-robust standard error.

    units: one dict per session, {stratum: (y, x)}.
    weights: optional {stratum: w} (summing to 1) for direct standardization,
    est = sum_e w_e * Y_e / X_e.
    n_units counts sessions with any x > 0; y and x are the totals over all
    units. se is None below 2 such units; est is None when there is no x (or
    a weighted stratum has none), or when weights are given but none is
    non-zero.
    centre: centre the influence values here instead of at the estimate (or
    at each stratum's own ratio when weighted): a number for every stratum,
    or a {stratum: value} dict. median_stat uses this for Woodruff.
    """
    total_y = sum(xy[0] for u in units for xy in u.values())
    total_x = sum(xy[1] for u in units for xy in u.values())
    c = sum(1 for u in units if any(xy[1] > 0 for xy in u.values()))
    out = {"est": None, "se": None, "n_units": c, "y": total_y,
           "x": total_x}

    if weights is None:
        if total_x <= 0:
            return out
        est = total_y / total_x
        out["est"] = est
        zs = [sum(y - _centre_at(centre, s, est) * x
                  for s, (y, x) in u.items()) / total_x
              for u in units]
    else:
        used = {s: w for s, w in weights.items() if w}
        if not used:
            return out
        sums = {}
        for s in used:
            sy = sum(u[s][0] for u in units if s in u)
            sx = sum(u[s][1] for u in units if s in u)
            if sx <= 0:
                return out
            sums[s] = (sx, sy / sx)
        out["est"] = sum(used[s] * sums[s][1] for s in used)
        zs = []
        for u in units:
            z = 0.0
            for s, w in used.items():
                if s in u:
                    sx, r = sums[s]
                    mid = _centre_at(centre, s, r)
                    z += w * (u[s][0] - mid * u[s][1]) / sx
            zs.append(z)

    if c >= 2:
        out["se"] = math.sqrt(c / (c - 1) * sum(z * z for z in zs))
    return out


def _bin_edges(b: int, steps: int):
    """(lower edge, upper edge, centre) of histogram bin b; bin 0 is value 0."""
    if b < 1:
        return 0.0, 0.0, 0.0
    return 2 ** ((b - 1) / steps), 2 ** (b / steps), 2 ** ((b - 0.5) / steps)


def median_stat(units: list, weights: dict | None = None,
                steps: int = 8) -> dict:
    """Median of log-binned histograms with a Woodruff confidence interval.

    units: one dict per session, {stratum: {bin: count}}. steps must match the
    histogram's bins-per-doubling. The CDF is pooled over all counts, or
    standardized with weights. The CI inverts the CDF at 0.5 -/+ Z95*se,
    where se is the cluster-robust error of F(median bin), so it is never
    narrower than one bin. lo/hi are None when se is None.

    Influence values are centred at 0.5, not at F-hat (which is >= 0.5 and
    can be 1.0 in the top occupied bin, collapsing the CI). Standardized,
    stratum e is centred at F_e(m) - (F(m) - 0.5): the weighted centres sum
    to 0.5 as before, but a stratum whose own F_e(m) is far from 0.5 adds
    no spurious spread (one 0.5 for every stratum inflated the CI).
    """
    n_total = 0
    mass = {}  # bin -> share of the (standardized) distribution
    per_stratum = {}  # stratum -> ({bin: count}, total), weighted only
    if weights is None:
        pooled = {}
        for u in units:
            for hist in u.values():
                for b, n in hist.items():
                    if n > 0:
                        pooled[int(b)] = pooled.get(int(b), 0) + n
        n_total = sum(pooled.values())
        mass = {b: n / n_total for b, n in pooled.items()} if n_total else {}
    else:
        for s, w in weights.items():
            if not w:
                continue
            per = {}
            for u in units:
                for b, n in u.get(s, {}).items():
                    if n > 0:
                        per[int(b)] = per.get(int(b), 0) + n
            n_s = sum(per.values())
            if n_s <= 0:
                return {"est": None, "lo": None, "hi": None, "se": None,
                        "n_units": 0, "n": 0}
            per_stratum[s] = (per, n_s)
            n_total += n_s
            for b, n in per.items():
                mass[b] = mass.get(b, 0.0) + w * n / n_s

    if not mass:
        return {"est": None, "lo": None, "hi": None, "se": None,
                "n_units": 0, "n": 0}

    bins = sorted(mass)
    cdf = []
    run = 0.0
    for b in bins:
        run += mass[b]
        cdf.append(run)

    def bin_at(q):
        for b, f in zip(bins, cdf):
            if f >= q - _EPS:
                return b
        return bins[-1]

    m = bin_at(0.5)
    est = _bin_edges(m, steps)[2]
    centre = 0.5
    if weights is not None:
        f_at = {s: sum(n for b, n in per.items() if b <= m) / n_s
                for s, (per, n_s) in per_stratum.items()}
        shift = sum(weights[s] * f for s, f in f_at.items()) - 0.5
        centre = {s: f - shift for s, f in f_at.items()}

    cluster_units = []
    for u in units:
        cu = {}
        for s, hist in u.items():
            y = x = 0
            for b, n in hist.items():
                if n > 0:
                    x += n
                    if int(b) <= m:
                        y += n
            cu[s] = (y, x)
        cluster_units.append(cu)
    r = ratio_stat(cluster_units, weights, centre=centre)

    out = {"est": est, "lo": None, "hi": None, "se": r["se"],
           "n_units": r["n_units"], "n": n_total}
    if r["se"] is not None:
        half = Z95 * r["se"]
        out["lo"] = _bin_edges(bin_at(0.5 - half), steps)[0]
        out["hi"] = _bin_edges(bin_at(0.5 + half), steps)[1]
    return out


def values_median_stat(values: list) -> dict:
    """Exact median of per-session values with a distribution-free rank CI.

    Rank bounds floor(n/2 - Z95*sqrt(n)/2) .. ceil(n/2 + Z95*sqrt(n)/2),
    1-based and clamped to the sample; lo/hi are None for n < 2.
    """
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    out = {"est": None, "lo": None, "hi": None, "n_units": n, "n": n}
    if n == 0:
        return out
    mid = n // 2
    out["est"] = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
    if n >= 2:
        half = Z95 * math.sqrt(n) / 2
        lo_rank = max(1, math.floor(n / 2 - half))
        hi_rank = min(n, math.ceil(n / 2 + half))
        out["lo"] = vals[lo_rank - 1]
        out["hi"] = vals[hi_rank - 1]
    return out


def _p_value(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def compare(a: dict, b: dict, kind: str) -> dict:
    """Compare an ID side (a) with its baseline (b).

    change = a.est / b.est - 1. kind="ratio" tests a.est - b.est using the
    standard errors; kind="median" works on ln(a/b) with the standard error
    recovered from each side's CI (needs lo > 0). Fields that cannot be
    computed are None.
    """
    out = {"change": None, "lo": None, "hi": None, "p": None}
    ea, eb = a.get("est"), b.get("est")
    if ea is None or not eb:
        return out
    out["change"] = ea / eb - 1

    if kind == "ratio":
        sa, sb = a.get("se"), b.get("se")
        if sa is None or sb is None:
            return out
        denom = math.sqrt(sa * sa + sb * sb)
        if denom > 0:
            out["p"] = _p_value((ea - eb) / denom)
        if ea > 0 and eb > 0:
            half = Z95 * math.sqrt((sa / ea) ** 2 + (sb / eb) ** 2)
            delta = math.log(ea / eb)
            out["lo"] = math.exp(delta - half) - 1
            out["hi"] = math.exp(delta + half) - 1
        return out

    if kind == "median":
        if ea <= 0 or eb <= 0:
            return out
        logs = []
        for side in (a, b):
            lo, hi = side.get("lo"), side.get("hi")
            if lo is None or hi is None or lo <= 0:
                return out
            logs.append((math.log(hi) - math.log(lo)) / (2 * Z95))
        se = math.sqrt(logs[0] ** 2 + logs[1] ** 2)
        delta = math.log(ea / eb)
        if se > 0:
            out["p"] = _p_value(delta / se)
        out["lo"] = math.exp(delta - Z95 * se) - 1
        out["hi"] = math.exp(delta + Z95 * se) - 1
    return out
