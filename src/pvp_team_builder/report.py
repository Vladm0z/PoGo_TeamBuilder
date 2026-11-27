"""
Self-contained HTML report (inline CSS only, so it renders anywhere).

    python -m pvp_team_builder teambuild -l great --file mons.txt --html teams.html
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import datetime

from .scoring import Ranking, TeamEvaluator


def _cell_class(rating: float) -> str:
    if rating >= 650:
        return "w2"  # comfortable win
    if rating > 500:
        return "w1"  # win
    if rating > 350:
        return "l1"  # loss
    return "l2"  # bad loss


def _grade_class(grade: str) -> str:
    return {"A": "g-a", "B": "g-b", "C": "g-c", "D": "g-d"}.get(grade, "g-f")


def team_card(rank: int, r: Ranking, meta, evaluator: TeamEvaluator, threat_table: bool = True) -> str:
    lead, switch, closer = r.ordered()
    esc = html.escape
    rows = []
    if threat_table:
        ordered_threats = sorted(evaluator.threats, key=lambda t: r.per_threat[t.species_id]["best"])
        for t in ordered_threats:
            d = r.per_threat[t.species_id]
            cells = "".join(
                f'<td class="{_cell_class(rating)}">{rating:.0f}</td>'
                for rating in (d["ratings"][m.species_id] for m in r.mons)
            )
            badge = "corebreaker" if d["answers"] == 0 else "1 answer" if d["answers"] == 1 else ""
            rows.append(
                f"<tr><th>{esc(t.name)}</th>{cells}"
                f'<td class="ans">{d["answers"]}/3</td><td class="flag">{badge}</td></tr>'
            )
    table = ""
    if rows:
        header = "".join(f"<th>{esc(m.name)}</th>" for m in r.mons)
        table = (
            '<table class="scorecard"><thead><tr><th>meta threat</th>'
            f"{header}<th>answers</th><th></th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    table = table.replace("\n", "\n  ")
    core = ", ".join(f"{esc(n)} ({v:.0f})" for n, v in r.corebreakers[:6]) or "none"
    single = ", ".join(f"{esc(n)} ({v:.0f})" for n, v in r.single_answer[:6]) or "none"
    moves = " &middot; ".join(f"<b>{esc(m.name)}</b> {esc(', '.join(m.move_names()))}" for m in r.mons)

    return f"""
<section class="card">
  <header>
    <div class="rank">#{rank}</div>
    <div class="grade {_grade_class(r.grade)}">{r.grade}</div>
    <div class="stats">
      <div class="score">coverage <b>{r.score:.0f}</b><span>/1000 &middot; PvPoke-style, vs your 6 worst threats</span></div>
      <div class="sub">best-answer avg {r.best_mean:.0f} &middot; scorecard {r.coverage_pct:.0f}% answered
        &middot; {r.corebreaker_pct:.0f}% unanswerable</div>
    </div>
  </header>
  <div class="lineup">
    <div class="slot"><span class="role">lead</span><span class="mon">{esc(lead.name)}</span></div>
    <div class="arrow">&rarr;</div>
    <div class="slot"><span class="role">safe swap</span><span class="mon">{esc(switch.name)}</span></div>
    <div class="arrow">&rarr;</div>
    <div class="slot"><span class="role">closer</span><span class="mon">{esc(closer.name)}</span></div>
  </div>
  <div class="moves">{moves}</div>
  <div class="flags">
    <p><b>corebreakers</b> (nobody wins): {core}</p>
    <p><b>single answer</b>: {single}</p>
  </div>
{table}
  <footer><a href="{meta.team_builder_link(r.mons)}" target="_blank" rel="noopener">open in PvPoke team builder &rarr;</a></footer>
</section>"""


def render(
    meta,
    results: Sequence[Ranking],
    evaluator: TeamEvaluator,
    league: str,
    pool_names: Sequence[str],
    elo: int | None,
    engine_info: str,
    greedy: Ranking | None = None,
) -> str:
    esc = html.escape
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(team_card(i, r, meta, evaluator) for i, r in enumerate(results, 1))
    greedy_card = (
        f"<h2>the post's manual loop, automated (step 1-3)</h2>{team_card(0, greedy, meta, evaluator, threat_table=False)}"
        if greedy
        else ""
    )
    pool = ", ".join(esc(n) for n in pool_names)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(league.title())} League teams &middot; pvp-team-builder</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 28px 20px 60px; background: #0e1116; color: #e6edf3;
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; }}
  h1 {{ margin: 0 0 4px; font-size: 26px; letter-spacing: -.4px; }}
  h2 {{ margin: 34px 0 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 1.2px; color: #8b98a5; }}
  .meta {{ color: #8b98a5; font-size: 13px; margin-bottom: 6px; }}
  .pool {{ color: #6e7b8a; font-size: 12px; margin-bottom: 22px; }}
  .card {{ background: #161b22; border: 1px solid #232b36; border-radius: 14px;
    padding: 16px 18px; margin-bottom: 18px; }}
  .card header {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
  .rank {{ font-size: 13px; color: #6e7b8a; font-variant-numeric: tabular-nums; }}
  .grade {{ width: 42px; height: 42px; border-radius: 11px; display: grid; place-items: center;
    font-weight: 700; font-size: 19px; }}
  .g-a {{ background: #10361f; color: #4ade80; }} .g-b {{ background: #0f2f3a; color: #38bdf8; }}
  .g-c {{ background: #33300f; color: #eab308; }} .g-d {{ background: #3a2a10; color: #fb923c; }}
  .g-f {{ background: #3a1414; color: #f87171; }}
  .stats .score {{ font-size: 15px; }} .stats .score b {{ font-size: 19px; }}
  .stats .score span {{ color: #6e7b8a; font-size: 12px; margin-left: 6px; }}
  .stats .sub {{ color: #8b98a5; font-size: 12.5px; }}
  .lineup {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 16px 0 8px; }}
  .slot {{ background: #1d2530; border: 1px solid #2b3644; border-radius: 10px; padding: 7px 12px; }}
  .slot .role {{ display: block; font-size: 10.5px; text-transform: uppercase; letter-spacing: .9px; color: #7d8b9a; }}
  .slot .mon {{ font-weight: 600; }}
  .arrow {{ color: #44505f; }}
  .moves {{ color: #9aa7b4; font-size: 12.5px; margin-bottom: 10px; }}
  .flags p {{ margin: 3px 0; font-size: 13px; color: #c3ced9; }}
  .flags b {{ color: #e6edf3; }}
  table.scorecard {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 12.5px; }}
  table.scorecard th, table.scorecard td {{ padding: 4px 7px; text-align: center; border-bottom: 1px solid #1f2731; }}
  table.scorecard thead th {{ color: #8b98a5; font-weight: 600; font-size: 11.5px; }}
  table.scorecard tbody th {{ text-align: left; font-weight: 500; color: #c3ced9; }}
  td.w2 {{ background: #123522; color: #6ee7a0; }} td.w1 {{ background: #16281f; color: #9fe6bb; }}
  td.l1 {{ background: #2a2118; color: #e8c290; }} td.l2 {{ background: #331a1a; color: #f0a3a3; }}
  td.ans {{ color: #8b98a5; font-variant-numeric: tabular-nums; }}
  td.flag {{ color: #fb923c; font-size: 11.5px; text-align: left; }}
  .card footer {{ margin-top: 12px; font-size: 12.5px; }}
  a {{ color: #58a6ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
  details summary {{ cursor: pointer; color: #8b98a5; font-size: 13px; margin-top: 10px; }}
</style></head>
<body><div class="wrap">
<h1>{esc(league.title())} League &middot; {esc(meta.cup)} cup (CP {meta.cp})</h1>
<div class="meta">scorecard: top {len(evaluator.threats)} threats
  {"&middot; elo " + str(elo) if elo else ""} &middot; matchups: {esc(engine_info)} &middot; generated {generated}</div>
<div class="pool">box: {pool}</div>
{greedy_card}
<h2>best teams from your box</h2>
{cards}
<script>/* nothing external; keep the file self-contained */</script>
</div></body></html>
"""
