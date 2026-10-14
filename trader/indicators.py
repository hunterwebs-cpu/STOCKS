import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.Close.shift()
    return pd.concat([df.High - df.Low, (df.High - pc).abs(), (df.Low - pc).abs()], axis=1).max(axis=1)


def linreg_end(s: pd.Series, n: int) -> pd.Series:
    """Value at the last point of a rolling least-squares line (thinkorswim
    Inertia / LazyBear linreg). Implemented as a fixed linear filter."""
    x = np.arange(n, dtype=float)
    xb = x.mean()
    w = 1 / n + (x - xb) * (n - 1 - xb) / ((x - xb) ** 2).sum()
    vals = s.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    if len(vals) >= n:
        out[n - 1:] = np.convolve(vals, w[::-1], mode="valid")
    return pd.Series(out, index=s.index)


def setup_frame(df: pd.DataFrame, ema_lengths=(8, 21, 34, 55, 89), n=20, atr_len=14) -> pd.DataFrame:
    """Columns: bull/bear EMA stack, squeeze on, momentum and its color, ATR."""
    c, h, l = df.Close, df.High, df.Low
    e = [ema(c, k) for k in ema_lengths]
    bull = pd.concat([e[i] > e[i + 1] for i in range(len(e) - 1)], axis=1).all(axis=1)
    bear = pd.concat([e[i] < e[i + 1] for i in range(len(e) - 1)], axis=1).all(axis=1)
    tr = true_range(df)
    sma, sd = c.rolling(n).mean(), c.rolling(n).std(ddof=0)
    sq_on = (2.0 * sd) < (1.5 * tr.rolling(n).mean())
    delta = c - ((h.rolling(n).max() + l.rolling(n).min()) / 2 + sma) / 2
    mom = linreg_end(delta, n)
    rising = mom > mom.shift()
    return pd.DataFrame({
        "bull": bull, "bear": bear, "sq_on": sq_on, "mom": mom,
        "light_blue": (mom > 0) & rising, "red": (mom < 0) & ~rising,
        "atr": tr.rolling(atr_len).mean(),
    }, index=df.index)
