/**
 * Headless harness around PvPoke's *actual* battle engine.
 *
 * Loads PvPoke's own GameMaster / Pokemon / Battle / DamageCalculator code
 * (fetched from pvpoke.com, unmodified) into a Node vm sandbox with a fake
 * jQuery that serves the local gamemaster file, then rates 1v1 matchups with
 * the exact same simulation the website runs.
 *
 * Protocol: one JSON object on stdin
 *   { "gamemaster": "/abs/path/gamemaster.json", "cp": 1500, "cup": "all",
 *     "shields": 1, "pairs": [["azumarill","skarmory"], ...] }
 * Output: JSON lines, one per pair
 *   { "a": "...", "b": "...", "rating": 612, "winner": "...", ... }
 *
 * Usage from Python: see engine.py
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Engine scripts live in the data cache (downloaded on first run), not in the
// package, so the harness takes their location from the request payload.
let JS_DIR = path.join(__dirname, 'js');
const ENGINE_FILES = [
  'GameMaster.js',
  'Pokemon.js',
  'DamageCalculator.js',
  'ActionLogic.js',
  'TimelineEvent.js',
  'TimelineAction.js',
  'DecisionOption.js',
  'Battle.js',
];


// Minimal jQuery stand-in: enough of $.ajax to feed the local gamemaster.
function makeJQuery(gamemasterPath) {
  function noopObj() {
    const o = function () { return o; };
    o.on = o.off = o.click = o.trigger = o.append = o.prepend = o.insertAfter =
      o.css = o.attr = o.addClass = o.removeClass = o.html = o.text = o.val =
      o.hide = o.show = o.each = o.parent = o.find = o.eq = o.prop = o.fadeIn =
      o.fadeOut = o.animate = o.remove = o.ready = function () { return o; };
    o.length = 0;
    return o;
  }

  function $(arg) {
    return noopObj();
  }
  // Success callbacks are deferred to a macrotask: real $.ajax is async, and
  // GameMaster.js relies on that (it assigns its own methods after the call).
  $.ajax = function (opts) {
    const url = String(opts.url || '');
    let text = '[]';                       // rankings/groups/articles: not needed
    if (url.indexOf('gamemaster') > -1) {
      const file = /min/.test(url) ? gamemasterPath.replace('gamemaster.json', 'gamemaster.min.json') : gamemasterPath;
      text = fs.readFileSync(fs.existsSync(file) ? file : gamemasterPath, 'utf8');
    }
    setTimeout(function () {
      let data;
      try { data = JSON.parse(text); } catch (e) { if (opts.error) opts.error({}, e); return; }
      if (opts.success) opts.success(data);
    }, 0);
  };
  $.getJSON = function (url, cb) { $.ajax({ url: url, success: cb }); };
  $.each = function (arr, fn) { (arr || []).forEach((v, i) => fn(i, v)); };
  $.extend = Object.assign;
  $.isArray = Array.isArray;
  $.trim = (s) => String(s).trim();
  return $;
}

function makeContext(gamemasterPath) {
  const store = {};
  const sandbox = {
    console: { log() {}, error() {}, warn() {} },
    setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Math, Date, Object, Array, String, Number, Boolean, RegExp, Error, parseInt, parseFloat, isNaN,
    $: makeJQuery(gamemasterPath),
    jQuery: undefined,
    host: 'https://pvpoke.com/',
    webRoot: '/',
    siteVersion: '1.40.7.1',
    settings: {
      defaultIVs: 'gamemaster', animateTimeline: 0, matrixDirection: 'row',
      gamemaster: 'gamemaster', pokeboxId: 0, pokeboxLastDateTime: 0, xls: true,
      rankingDetails: 'one-page', hardMovesetLinks: 0, colorblindMode: 0,
      performanceMode: 1, theme: 'default',
    },
    window: {
      localStorage: {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
      },
      location: { href: 'https://pvpoke.com/battle/', search: '', hash: '' },
      addEventListener() {}, removeEventListener() {},
    },
    localStorage: undefined,
    document: { addEventListener() {}, getElementById: () => null, querySelector: () => null,
      querySelectorAll: () => [], createElement: () => ({ style: {}, appendChild() {} }),
      body: { classList: { add() {}, remove() {} } } },
    navigator: { userAgent: 'node' },
    updateFormatSelect: undefined, updateCupSelect: undefined,
    InterfaceMaster: undefined, customRankingInterface: undefined, MultiSelector: undefined,
  };
  sandbox.window.document = sandbox.document;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  for (const f of ENGINE_FILES) {
    const file = path.join(JS_DIR, f);
    if (!fs.existsSync(file)) {
      throw new Error(`missing PvPoke engine script ${file} (delete the engine cache and retry)`);
    }
    const code = fs.readFileSync(file, 'utf8');
    vm.runInContext(code, sandbox, { filename: f });
  }
  return sandbox;
}


// Pair rating (mirrors TeamRanker.js / BattleHistogram conventions)
function ratePair(ctx, battle, a, b, shields) {
  battle.setNewPokemon(a, 0, false);
  battle.setNewPokemon(b, 1, false);
  a.setShields(shields);
  b.setShields(shields);
  battle.simulate();

  // Capture the end state *before* resetting for the next fight.
  const healthRating = a.hp / a.stats.hp;
  const damageRating = (b.stats.hp - b.hp) / b.stats.hp;
  const rating = Math.floor((healthRating + damageRating) * 500);
  const result = {
    rating: rating,
    winner: (a.hp > 0 && b.hp <= 0) ? a.speciesId : ((b.hp > 0 && a.hp <= 0) ? b.speciesId : null),
    hpLeft: Math.round((a.hp / a.stats.hp) * 1000) / 1000,
    energyLeft: Math.round(a.energy),
    shieldsLeft: a.shields,
    foeHpLeft: Math.round((b.hp / b.stats.hp) * 1000) / 1000,
    duration: battle.getDuration ? battle.getDuration() : null,
  };

  a.reset();
  b.reset();
  return result;
}

function main() {
  const chunks = [];
  process.stdin.on('data', (c) => chunks.push(c));
  process.stdin.on('end', () => {
    const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (input.engine) JS_DIR = input.engine;
    const ctx = makeContext(input.gamemaster);
    const gm = ctx.GameMaster.getInstance();

    let waited = 0;
    const run = () => {
      if (!gm.data || !gm.data.pokemon) {
        waited += 5;
        if (waited > 10000) {
          process.stdout.write(JSON.stringify({ error: 'gamemaster failed to load' }) + '\n');
          process.exit(1);
        }
        setTimeout(run, 5);
        return;
      }
      runPairs(input, ctx, gm);
    };
    setTimeout(run, 5);
  });
}

function runPairs(input, ctx, gm) {
    const cp = input.cp || 1500;
    const cup = input.cup || 'all';
    const shields = input.shields === undefined ? 1 : input.shields;
    const mode = input.mode || 'average'; // average = mean of 0-0 and 1-1 shields

    const battle = new ctx.Battle();
    battle.setCP(cp);
    if (gm.getCupById && gm.getCupById(cup)) battle.setCup(cup);
    battle.setLevelCap(50);

    const cache = new Map();
    // PvPoke's published movesets (from the rankings JSON).  Its own
    // selectRecommendedMoveset() picks by usage volume and does NOT match the
    // ranked moveset, so it is always set explicitly when provided.
    const movesets = input.movesets || {};
    function makePokemon(id) {
      const p = new ctx.Pokemon(id, 0, battle);
      p.initialize(cp);
      const ms = movesets[id];
      if (ms && ms.length) {
        p.selectMove('fast', ms[0], 0);
        for (let i = 1; i < ms.length && i <= 2; i++) p.selectMove('charged', ms[i], i - 1);
      } else if (p.selectRecommendedMoveset) {
        p.selectRecommendedMoveset();
      }
      p.reset();
      return p;
    }

    const out = [];
    for (const [idA, idB] of input.pairs) {
      try {
        const a = makePokemon(idA);
        const b = makePokemon(idB);
        let res;
        if (mode === 'average') {
          const r0 = ratePair(ctx, battle, a, b, 0);
          const r1 = ratePair(ctx, battle, a, b, 1);
          res = Object.assign({}, r1, { rating: Math.round((r0.rating + r1.rating) / 2) });
          res.rating0 = r0.rating;
          res.rating1 = r1.rating;
        } else {
          res = ratePair(ctx, battle, a, b, shields);
        }
        out.push(Object.assign({ a: idA, b: idB }, res));
        if (input.debug) {
          out[out.length - 1].debug = {
            aHp: a.hp, aStatsHp: a.stats.hp, aEnergy: a.energy, aFast: a.fastMove && a.fastMove.moveId,
            bHp: b.hp, bFast: b.fastMove && b.fastMove.moveId,
            aCharged: (a.chargedMoves||[]).map(m=>m.moveId), timeline: battle.timeline ? battle.timeline.length : null,
          };
        }
      } catch (e) {
        out.push({ a: idA, b: idB, error: String(e && e.message || e) });
      }
    }
    process.stdout.write(JSON.stringify(out));
}

if (require.main === module) {
  main();
} else {
  module.exports = { makeContext, ratePair };
}
